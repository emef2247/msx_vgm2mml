"""Authored HuC6280 native-state evidence; no game-derived fixtures."""
from pathlib import Path
import csv
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from huc6280 import analyze, Runtime, attenuation_levels, VOLUME_TABLE


def write(register, value):
    return bytes((0xb9, register, value))


def wait(samples):
    return b'\x61' + struct.pack('<H', samples)


def make_vgm(commands, *, clock=3579545, version=0x171):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, version)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    struct.pack_into('<I', raw, 0xa4, clock)
    raw.extend(commands + b'\x66')
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


def wave(channel=0, values=tuple(range(32)), *, period=255, level=31, balance=255):
    return (write(0, channel) + write(4, 64) + write(4, 0) +
            b''.join(write(6, value) for value in values) + write(2, period & 255) +
            write(3, period >> 8) + write(5, balance) + write(4, 128 | level))


class Huc6280SourceTests(unittest.TestCase):
    def test_wave_pointer_and_dda_reset_keep_unknown_bytes_distinct(self):
        runtime = Runtime(3579545)
        runtime.write(6, 9)
        state = runtime.snapshot().channels[0]
        self.assertEqual(state.index, 1)
        self.assertEqual(state.waveform[0], 9)
        self.assertTrue(state.waveform_known[0])
        self.assertFalse(state.waveform_known[1])
        runtime.write(4, 64)
        runtime.write(6, 31)
        self.assertEqual(runtime.snapshot().channels[0].dda, 31)
        self.assertEqual(runtime.snapshot().channels[0].waveform[1], 0)
        runtime.write(4, 0)
        self.assertEqual(runtime.snapshot().channels[0].index, 0)
        runtime.write(6, 7)
        self.assertEqual(runtime.snapshot().channels[0].waveform[0], 7)
        self.assertFalse(runtime.snapshot().channels[0].waveform_complete)

    def test_control_volume_and_frequency_writes_do_not_retrigger(self):
        runtime = Runtime(3579545)
        runtime.write(2, 25)
        runtime.write(4, 159)
        runtime.advance(10)
        before = runtime.snapshot().channels[0]
        self.assertNotEqual(before.counter, 0)
        runtime.write(4, 144)
        runtime.write(2, 40)
        self.assertEqual(runtime.snapshot().channels[0].counter, before.counter)
        runtime.write(4, 0)
        runtime.write(4, 159)
        self.assertEqual(runtime.snapshot().channels[0].counter, 0)

    def test_ordered_states_and_native_global_balance_intervals(self):
        commands = write(1, 255) + wave() + wait(44) + write(1, 136) + wait(44)
        trace = analyze(make_vgm(commands))
        self.assertEqual(trace.source_end_vgmticks, 88)
        self.assertEqual(trace.clock_hz, 3579545)
        self.assertEqual(trace.rate_hz, 3579545 // 16)
        self.assertEqual(trace.writes[0].source_event_id, 0)
        self.assertEqual(trace.writes[-1].source_event_id, len(trace.writes))
        self.assertEqual(len(trace.states), len(trace.writes))
        self.assertEqual(sum(s.key_on_edge for s in trace.states), 1)
        for ch in range(6):
            intervals = [s for s in trace.segments if s.channel == ch]
            self.assertEqual([(s.start_vgmticks, s.end_vgmticks) for s in intervals], [(0, 44), (44, 88)])
            self.assertEqual([s.global_balance for s in intervals], [255, 136])
        self.assertTrue(next(s for s in trace.segments if s.channel == 0).active)
        self.assertTrue(all(s.end_vgmticks > s.start_vgmticks for s in trace.segments))
        self.assertEqual([w.vgmticks for w in trace.writes[:-1]], [0] * (len(trace.writes) - 1))

    def test_wave_versions_are_immutable_and_source_values_not_target_bytes(self):
        trace = analyze(make_vgm(wave() + wait(10) + write(4, 0) + wave(values=(31,) * 32) + wait(10)))
        first = next(s.channels[0] for s in trace.states if s.channels[0].waveform_complete)
        self.assertEqual(first.waveform, tuple(range(32)))
        self.assertEqual(trace.waveforms[first.waveform_id], tuple(range(32)))
        final = trace.final_state.channels[0]
        self.assertEqual(final.waveform, (31,) * 32)
        self.assertNotEqual(first.waveform_id, final.waveform_id)
        self.assertEqual(trace.waveforms[final.waveform_id], (31,) * 32)

    def test_dda_upload_setup_and_enabled_dda_remain_different(self):
        commands = (write(1, 255) + write(5, 255) + write(4, 64) +
                    write(6, 17) + wait(10) + write(4, 223) + write(6, 16) + wait(10))
        trace = analyze(make_vgm(commands))
        ch0 = [s for s in trace.segments if s.channel == 0]
        self.assertFalse(ch0[0].active)
        self.assertTrue(ch0[-1].active)
        self.assertEqual(ch0[-1].state.mode, 'dda')
        self.assertEqual(ch0[-1].state.dda, 16)
        self.assertFalse(ch0[-1].state.waveform_complete)

    def test_noise_and_lfo_evidence_is_not_a_target_waveform(self):
        runtime = Runtime(3579545)
        runtime.write(0, 4)
        runtime.write(7, 129)
        runtime.write(4, 159)
        self.assertEqual(runtime.snapshot().channels[4].mode, 'noise')
        runtime.write(0, 0)
        runtime.write(4, 159)
        runtime.write(9, 1)
        runtime.advance(10)
        self.assertIsNone(runtime.snapshot().channels[0].counter)
        self.assertEqual(runtime.snapshot().channels[0].index_origin, 'unmodeled_lfo_phase')
        self.assertEqual(runtime.snapshot().channels[4].noise_control, 129)

    def test_clock_bounds_and_second_instance_are_inspectable(self):
        trace = analyze(make_vgm(write(0x80, 1) + wait(10), clock=0x40000000 | 3579545))
        self.assertEqual(trace.writes[0].chip_instance, 1)
        self.assertIn('dual_huc6280_header_unsupported', trace.issues)
        self.assertIn('second_huc6280_write_unsupported', trace.issues)
        old = analyze(make_vgm(write(0, 0), version=0x150))
        self.assertEqual(old.clock_hz, 0)
        self.assertIn('missing_huc6280_clock', old.issues)
        unused = analyze(make_vgm(wait(10), clock=0))
        self.assertEqual(unused.writes, ())
        self.assertEqual(unused.issues, ())

    def test_native_gain_law_and_assumption_dumps(self):
        self.assertEqual(attenuation_levels(159, 255, 255), (0, 0))
        self.assertEqual(attenuation_levels(128, 255, 255), (31, 31))
        self.assertEqual(attenuation_levels(159, 240, 255), (0, 31))
        self.assertGreater(VOLUME_TABLE[0], VOLUME_TABLE[1])
        self.assertEqual(VOLUME_TABLE[-1], 0)
        trace = analyze(make_vgm(write(0, 0) + write(6, 12) + wait(5)))
        with tempfile.TemporaryDirectory() as temp:
            trace.dump(temp, 'AUTH')
            root = Path(temp)
            report = json.loads((root / 'AUTH.huc6280.source.json').read_text())
            self.assertFalse(report['initialization']['observed'])
            self.assertEqual(report['reference_native_rate_hz'], 3579545 // 16)
            with (root / 'AUTH.huc6280.states.csv').open() as stream:
                states = list(csv.DictReader(stream))
            self.assertEqual(len(states), len(trace.states) * 8)
            self.assertEqual(states[-8]['waveform_known'], '1' + '0' * 31)
            self.assertEqual(states[-8]['waveform_id'], '')
            self.assertTrue((root / 'AUTH.huc6280.segments.csv').is_file())


if __name__ == '__main__':
    unittest.main()
