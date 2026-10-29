"""Independent pinned HuC6280 core checks using authored register sequences."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from huc6280_reference import Reference, LIBRARY


def upload(channel=0, period=257):
    commands = [(0, channel), (4, 64), (4, 0), (5, 255), (2, period & 255), (3, period >> 8)]
    commands.extend((6, (index * (channel + 3) + 7) & 31) for index in range(32))
    commands.append((4, 159))
    return [('w', reg, value) for reg, value in commands]


def authored_cases():
    yield 'partial_upload_and_masks', [('w', 0, 0), ('w', 4, 64), ('w', 4, 0), ('w', 6, 255), ('w', 6, 17), ('w', 3, 255)]
    yield 'six_independent_wave_counters', [('w', 1, 255)] + sum((upload(ch, 177 + ch * 31) for ch in range(6)), []) + [('a', 511), ('a', 1), ('a', 4097)]
    yield 'frequency_change_and_zero', upload() + [('a', 37), ('w', 2, 91), ('a', 800), ('w', 2, 0), ('w', 3, 0), ('a', 9000)]
    yield 'enable_edges_and_gain_zero', upload() + [('a', 113), ('w', 4, 159), ('a', 2), ('w', 5, 0), ('w', 1, 0), ('a', 700), ('w', 4, 31), ('a', 500), ('w', 4, 159), ('w', 6, 29), ('a', 3)]
    yield 'dda_preserves_wave_then_reset_index', upload() + [('a', 47), ('w', 4, 223), ('w', 6, 31), ('a', 79), ('w', 4, 159), ('w', 6, 9), ('a', 7)]
    yield 'unused_channels_and_lfo_registers', [('w', 0, 6), ('w', 4, 159), ('w', 6, 13), ('w', 2, 57), ('a', 101), ('w', 8, 9), ('w', 9, 128), ('w', 0, 7), ('w', 4, 64), ('w', 6, 15), ('w', 7, 255)]


def make_vgm(commands):
    header = bytearray(256)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x34, 256 - 0x34)
    struct.pack_into('<I', header, 0xa4, 3579545)
    body = bytearray()
    for op in commands:
        if op[0] == 'w':
            body.extend((0xb9, op[1], op[2]))
        else:
            body.extend(b'\x61' + struct.pack('<H', op[1]))
    raw = header + body + b'\x66'
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


@unittest.skipUnless(LIBRARY.is_file(), 'Explicitly setup the optional pinned HuC6280 reference')
class Huc6280ReferenceTests(unittest.TestCase):
    def compare(self, native, reference):
        expected = reference.snapshot()
        for name in ('selected_channel', 'global_balance', 'lfo_frequency', 'lfo_control', 'native_frame'):
            self.assertEqual(getattr(native, name), expected[name], name)
        for channel, (actual, wanted) in enumerate(zip(native.channels, expected['channels'])):
            for name in ('frequency', 'control', 'balance', 'index', 'counter', 'dda', 'noise_control', 'waveform'):
                self.assertEqual(getattr(actual, name), wanted[name], (channel, name))

    def test_authored_runtime_state_against_pinned_core(self):
        from huc6280 import Runtime
        for name, commands in authored_cases():
            with self.subTest(case=name), Reference() as reference:
                native = Runtime(3579545)
                self.compare(native.snapshot(), reference)
                for operation in commands:
                    if operation[0] == 'w':
                        native.write(*operation[1:])
                        reference.write(*operation[1:])
                    else:
                        native.advance(operation[1])
                        reference.advance(operation[1])
                    self.compare(native.snapshot(), reference)

    def test_source_write_scheduler_and_eof_counter_against_core(self):
        from huc6280 import analyze
        commands = [('w', 1, 255)] + upload(2, 311)
        commands += [('a', 13), ('w', 2, 19), ('a', 735), ('w', 5, 113), ('a', 8), ('w', 4, 159), ('a', 321)]
        raw = make_vgm(commands)
        trace = analyze(raw)
        self.assertEqual(trace.clock_hz, 3579545)
        with Reference() as reference:
            for state in trace.states:
                frame = -(-state.write.vgmticks * reference.rate_hz // 44100)
                reference.advance(frame - reference.native_frame)
                reference.write(state.write.register, state.write.value)
                self.compare(state.state, reference)
            frame = -(-trace.source_end_vgmticks * reference.rate_hz // 44100)
            reference.advance(frame - reference.native_frame)
            self.compare(trace.final_state, reference)

    def test_gain_table_and_periodic_audio_profile(self):
        from huc6280 import VOLUME_TABLE, attenuation_levels
        with Reference() as reference:
            self.assertEqual(tuple(VOLUME_TABLE), reference.volume_table())
            self.assertEqual(attenuation_levels(159, 255, 255), (0, 0))
            self.assertEqual(attenuation_levels(128, 255, 255), (31, 31))
            for register, value in [(1, 255), (0, 0), (4, 64), (4, 0), (5, 255), (2, 32), (3, 0)]:
                reference.write(register, value)
            for value in [0] * 16 + [31] * 16:
                reference.write(6, value)
            reference.write(4, 159)
            left, right = reference.render(128)
            level = VOLUME_TABLE[0]
            expected = tuple([-16 * level] * 32 + [15 * level] * 32) * 2
            self.assertEqual(left, expected)
            self.assertEqual(right, expected)
            reference.write(5, 0xf0)
            left, right = reference.render(64)
            self.assertTrue(any(left))
            self.assertEqual(set(right), {0})


if __name__ == '__main__':
    unittest.main()
