"""Authored NES APU native-state evidence; no game-derived fixtures."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from nesapu import Runtime, analyze


def write(register, value):
    return bytes((0xb4, register, value))


def wait(samples):
    return b'\x61' + struct.pack('<H', samples)


def make_vgm(commands, *, clock=1789773, version=0x171):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, version)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    struct.pack_into('<I', raw, 0x84, clock)
    raw.extend(commands + b'\x66')
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


def pulse_note(*, control=0xbf, period=253, length_index=1):
    # status: pulse1 enable; control: duty 2, constant volume 15 by default
    return (write(21, 1) + write(0, control) + write(2, period & 255) +
            write(3, ((period >> 8) & 7) | (length_index << 3)))


class NesApuSourceTests(unittest.TestCase):
    def test_constant_volume_pulse_is_audible_with_source_values(self):
        trace = analyze(make_vgm(pulse_note() + wait(44100)))
        audible = [s for s in trace.segments if s.channel == 0 and s.active]
        self.assertEqual(len(audible), 1)
        self.assertEqual(audible[0].state.period, 253)
        self.assertEqual(audible[0].state.duty, 2)
        self.assertEqual(audible[0].state.volume, 15)
        self.assertEqual(audible[0].start_vgmticks, 0)
        self.assertEqual(audible[0].end_vgmticks, 44100)

    def test_envelope_decay_reaches_silence(self):
        # duty 2, hardware envelope, divider period 1: decay 15 -> 0
        trace = analyze(make_vgm(pulse_note(control=0x81) + wait(44100)))
        volumes = [s.state.volume for s in trace.segments
                   if s.channel == 0 and s.active]
        self.assertEqual(volumes[0], 15)
        self.assertEqual(volumes, sorted(volumes, reverse=True))
        self.assertEqual(volumes[-1], 1)
        self.assertFalse(any(s.channel == 0 and s.active
                             and s.end_vgmticks == 44100 for s in trace.segments))

    def test_period_below_eight_is_sweep_muted(self):
        trace = analyze(make_vgm(pulse_note(period=4) + wait(4410)))
        self.assertFalse(any(s.channel == 0 and s.active for s in trace.segments))

    def test_disabled_channel_loads_no_length(self):
        raw = make_vgm(write(0, 0xbf) + write(2, 253) + write(3, 1 << 3) +
                       wait(4410))
        trace = analyze(raw)
        self.assertFalse(any(s.channel == 0 and s.active for s in trace.segments))

    def test_triangle_uses_linear_counter_gate(self):
        raw = make_vgm(write(21, 4) + write(8, 0xff) + write(10, 253) +
                       write(11, 1 << 3) + wait(22050))
        trace = analyze(raw)
        audible = [s for s in trace.segments if s.channel == 2 and s.active]
        self.assertEqual(len(audible), 1)
        self.assertEqual(audible[0].state.volume, 15)

    def test_noise_segment_keeps_mode_and_period_index(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1a) + write(14, 0x83) +
                       write(15, 1 << 3) + wait(22050))
        trace = analyze(raw)
        audible = [s for s in trace.segments if s.channel == 3 and s.active]
        self.assertEqual(len(audible), 1)
        self.assertEqual(audible[0].state.volume, 10)
        self.assertEqual(audible[0].state.lfsr_mode, 1)
        self.assertEqual(audible[0].state.noise_period_index, 3)

    def test_dpcm_trigger_is_recorded_not_sounded(self):
        raw = make_vgm(write(18, 0x10) + write(19, 0x08) + write(16, 0x0f) +
                       write(21, 16) + wait(4410))
        trace = analyze(raw)
        self.assertEqual(len(trace.dpcm_events), 1)
        event = trace.dpcm_events[0]
        self.assertEqual(event.address, 0xc000 + 0x10 * 64)
        self.assertEqual(event.length_bytes, 0x08 * 16 + 1)
        self.assertIn('dpcm_sample_playback_observed', trace.issues)
        self.assertFalse(any(s.active for s in trace.segments))

    def test_runtime_sweep_moves_period(self):
        runtime = Runtime(1789773)
        runtime.write(21, 1, 0)
        runtime.write(0, 0xbf, 0)
        runtime.write(1, 0xf1, 0)  # enabled, divider 7, shift 1, add
        runtime.write(2, 200, 0)
        runtime.write(3, 1 << 3, 0)
        before = runtime.views()[0].period
        for _ in range(40):
            runtime.advance_to(runtime._next_step_cycle())
        self.assertGreater(runtime.views()[0].period, before)


if __name__ == '__main__':
    unittest.main()
