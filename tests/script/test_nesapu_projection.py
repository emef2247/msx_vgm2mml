"""NES APU projection to SCC/PSG target VGM; authored fixtures only."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'py'), str(Path(__file__).parent)]
from test_nesapu import make_vgm, pulse_note, wait, write
from nesapu_projection import has_nesapu, project
from vgm_timing import command_times


def commands_by_type(raw):
    result = {}
    for command in command_times(raw):
        result.setdefault(command.command, []).append(command)
    return result


class NesApuProjectionTests(unittest.TestCase):
    def test_pulse_becomes_scc_with_duty_waveform(self):
        projected = project(make_vgm(pulse_note() + wait(44100)))
        by_type = commands_by_type(projected.vgm)
        self.assertIn(0xd2, by_type)
        self.assertEqual(projected.allocation[0], ('scc', 0))
        self.assertEqual(projected.summary['clamped_pitches'], 0)
        controls = [row for row in projected.controls
                    if row['source_channel'] == 0]
        self.assertTrue(controls)
        self.assertAlmostEqual(controls[0]['pitch_error_cents'], 0, delta=6)
        self.assertEqual(controls[0]['waveform'], 'duty2')
        self.assertEqual(len(projected.gates), 1)

    def test_noise_becomes_psg_noise(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1a) + write(14, 0x03) +
                       write(15, 1 << 3) + wait(22050))
        projected = project(raw)
        by_type = commands_by_type(projected.vgm)
        registers = {projected.vgm[c.address + 1] for c in by_type[0xa0]}
        self.assertIn(6, registers)   # AY noise period
        self.assertIn(10, registers)  # AY channel C amplitude
        self.assertEqual(projected.summary['noise_route'], 'psg')

    def test_noise_is_omitted_not_silent_when_ay_is_present(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1f) + write(14, 0x03) +
                       write(15, 1 << 3) + wait(22050))
        raw = bytearray(raw)
        # Insert an AY write ahead of the end command.
        body = bytes((0xa0, 8, 15))
        raw[-1:-1] = body
        import struct
        struct.pack_into('<I', raw, 4, len(raw) - 4)
        projected = project(bytes(raw))
        self.assertEqual(projected.summary['noise_route'], 'omitted_ay_present')
        self.assertEqual(projected.allocation[3], ('omitted', None))

    def test_dpcm_omission_is_recorded(self):
        raw = make_vgm(write(18, 0x10) + write(19, 0x08) + write(16, 0x0f) +
                       write(21, 16) + wait(4410))
        projected = project(raw)
        self.assertEqual(projected.summary['dpcm_events_omitted'], 1)

    def test_has_nesapu(self):
        self.assertTrue(has_nesapu(make_vgm(pulse_note() + wait(735))))
        self.assertFalse(has_nesapu(make_vgm(wait(735))))


if __name__ == '__main__':
    unittest.main()
