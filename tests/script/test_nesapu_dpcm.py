"""NES APU DPCM slicing and SCC complement lanes; authored fixtures only."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'py'), str(Path(__file__).parent)]
from test_nesapu import make_vgm, wait, write
from nesapu import analyze, lfsr_tick_cells
from nesapu_projection import project
from vgm_timing import command_times


def block(data, start=0xc000):
    return (b'\x67\x66\xc2' + struct.pack('<I', 2 + len(data))
            + struct.pack('<H', start) + data)


def dpcm_setup(sample, rate=15, loop=False):
    length_reg = (len(sample) - 1) // 16
    return (block(sample) + write(16, rate | (0x40 if loop else 0))
            + write(18, 0) + write(19, length_reg) + write(21, 0x1f))


def scc_writes(raw, port=None, register_range=None):
    found = []
    for command in command_times(raw):
        if command.command != 0xd2:
            continue
        p, register = raw[command.address + 1], raw[command.address + 2]
        if port is not None and p != port:
            continue
        if register_range and register not in register_range:
            continue
        found.append((p, register, raw[command.address + 3]))
    return found


class DpcmSliceTests(unittest.TestCase):
    def test_long_sample_slices_with_ramp_and_saturation(self):
        # 497 playable bytes of 0xff at rate 15 -> 5290 samples -> 8 slices
        trace = analyze(make_vgm(dpcm_setup(bytes([0xff]) * 512)
                                 + wait(44100)))
        self.assertEqual(len(trace.dpcm_events), 1)
        self.assertEqual(len(trace.dpcm_slices), 8)
        first, last = trace.dpcm_slices[0], trace.dpcm_slices[-1]
        self.assertLess(first.cells[0], first.cells[-1])  # rising ramp
        self.assertEqual(last.volume, 15)
        self.assertTrue(all(c == 121 for c in last.cells))  # saturated

    def test_retrigger_restarts_the_sample(self):
        raw = make_vgm(dpcm_setup(bytes([0xff]) * 512) + wait(2000)
                       + write(21, 0x0f) + write(21, 0x1f) + wait(3000))
        trace = analyze(raw)
        starts = [s.start_vgmticks for s in trace.dpcm_slices]
        self.assertIn(2000, starts)
        restarted = next(s for s in trace.dpcm_slices
                         if s.start_vgmticks == 2000)
        self.assertLess(restarted.cells[0], restarted.cells[-1])

    def test_looped_sample_runs_until_disabled(self):
        raw = make_vgm(dpcm_setup(bytes([0xff]) * 64, loop=True)
                       + wait(4410) + write(21, 0x0f) + wait(1000))
        trace = analyze(raw)
        self.assertEqual(len(trace.dpcm_slices), 6)

    def test_trigger_without_sample_data_records_issue(self):
        raw = make_vgm(write(16, 15) + write(18, 0) + write(19, 3)
                       + write(21, 0x1f) + wait(4410))
        trace = analyze(raw)
        self.assertEqual(trace.dpcm_slices, ())
        self.assertIn('dpcm_trigger_without_sample_data', trace.issues)


def fds_note(freq=1000, gain=32):
    stream = write(0x29, 0x80)
    for i in range(64):
        stream += write(0x40 + i, 63 if i < 32 else 0)
    return (stream + write(0x29, 0) + write(0x22, freq & 255)
            + write(0x23, (freq >> 8) & 15) + write(0x20, 0x80 | gain))


class FdsTests(unittest.TestCase):
    def test_fixed_gain_note_is_audible_with_wave(self):
        trace = analyze(make_vgm(fds_note() + wait(44100)))
        audible = [s for s in trace.segments
                   if s.channel == 4 and s.state.audible]
        self.assertEqual(len(audible), 1)
        self.assertEqual(audible[0].state.period, 1000)
        self.assertEqual(audible[0].state.volume, 15)
        self.assertEqual(len(trace.fds_waves), 1)

    def test_envelope_ramps_gain(self):
        stream = write(0x2a, 255) + write(0x29, 0x80)
        for i in range(64):
            stream += write(0x40 + i, 32)
        stream += (write(0x29, 0) + write(0x22, 232) + write(0x23, 3)
                   + write(0x20, 0x40 | 63))
        trace = analyze(make_vgm(stream + wait(44100)))
        volumes = [s.state.volume for s in trace.segments
                   if s.channel == 4]
        self.assertEqual(volumes, sorted(volumes))
        self.assertGreater(volumes[-1], volumes[0])

    def test_fds_renders_on_scc_lane_when_free(self):
        projected = project(make_vgm(fds_note() + wait(44100)))
        self.assertEqual(projected.summary['fds_route'], 'scc')
        controls = [c for c in projected.controls
                    if c['source_channel'] == 4]
        self.assertEqual(controls[0]['target_chip'], 'scc')

    def test_fds_outranks_slow_noise_for_the_lane(self):
        raw = make_vgm(fds_note() + write(21, 8) + write(12, 0x1f)
                       + write(14, 15) + write(15, 1 << 3) + wait(22050))
        projected = project(raw)
        self.assertEqual(projected.summary['fds_route'], 'scc')
        self.assertEqual(projected.summary['noise_scc_segments'], 0)
        self.assertEqual(projected.summary['noise_lane_deferred'], 1)

    def test_fds_falls_back_to_layered_opll_when_lane_busy(self):
        raw = make_vgm(dpcm_setup(bytes([0xff]) * 512) + fds_note()
                       + wait(44100))
        projected = project(raw)
        self.assertEqual(projected.summary['fds_route'], 'opll')
        self.assertTrue(projected.summary['fds_presets'])
        opll = [c for c in command_times(projected.vgm)
                if c.command == 0x51]
        self.assertTrue(opll)
        import struct as st
        clock = st.unpack_from('<I', projected.vgm, 0x10)[0] & 0x3fffffff
        self.assertEqual(clock, 3579545)


class LfsrSliceTests(unittest.TestCase):
    def test_cells_are_32_bipolar_and_mode_dependent(self):
        slow = list(lfsr_tick_cells(1789773, 12, 0, 10))
        self.assertTrue(all(len(cells) == 32 for cells in slow))
        self.assertTrue(all(-110 <= c <= 110 for cells in slow
                            for c in cells))
        short = list(lfsr_tick_cells(1789773, 12, 1, 10))
        self.assertNotEqual(slow, short)


class ComplementLaneProjectionTests(unittest.TestCase):
    def test_dpcm_renders_on_scc_channel_3(self):
        raw = make_vgm(dpcm_setup(bytes([0xff]) * 512) + wait(44100))
        projected = project(raw)
        waves = scc_writes(projected.vgm, port=0, register_range=range(96, 128))
        self.assertTrue(waves)
        self.assertEqual(projected.summary['dpcm_events_rendered'], 1)
        self.assertEqual(projected.summary['dpcm_events_omitted'], 0)
        self.assertGreaterEqual(projected.summary['dpcm_slices'], 8)

    def test_slow_noise_renders_on_scc_waveform_lane(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1f) + write(14, 15)
                       + write(15, 1 << 3) + wait(22050))
        projected = project(raw)
        controls = [c for c in projected.controls
                    if c['source_channel'] == 3]
        self.assertEqual(controls[0]['target_chip'], 'scc')
        self.assertEqual(controls[0]['target_channel'], 3)
        waves = scc_writes(projected.vgm, port=0,
                           register_range=range(96, 128))
        self.assertTrue(waves)
        self.assertEqual(projected.summary['noise_scc_segments'], 1)

    def test_slow_noise_defers_when_dpcm_claims_the_lane(self):
        raw = make_vgm(dpcm_setup(bytes([0xff]) * 512)
                       + write(21, 8) + write(12, 0x1f) + write(14, 15)
                       + write(15, 1 << 3) + wait(22050))
        projected = project(raw)
        self.assertEqual(projected.summary['dpcm_events_rendered'], 1)
        self.assertEqual(projected.summary['noise_scc_segments'], 0)
        self.assertEqual(projected.summary['noise_lane_deferred'], 1)
        controls = [c for c in projected.controls
                    if c['source_channel'] == 3]
        self.assertEqual(controls[0]['target_chip'], 'psg')
        self.assertGreater(abs(controls[0]['pitch_error_cents']), 50)

    def test_fast_noise_stays_on_psg(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1f) + write(14, 5)
                       + write(15, 1 << 3) + wait(22050))
        projected = project(raw)
        controls = [c for c in projected.controls
                    if c['source_channel'] == 3]
        self.assertEqual(controls[0]['target_chip'], 'psg')
        self.assertEqual(projected.summary['noise_scc_segments'], 0)


if __name__ == '__main__':
    unittest.main()
