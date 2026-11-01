"""NES APU source evidence in the native performance layer."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'py'), str(Path(__file__).parent)]
from test_nesapu import make_vgm, pulse_note, wait, write
from native_source_music import build_native_performance
from native_registers import encode_control
from vgm_timing import command_times


class NativeNesApuTests(unittest.TestCase):
    def build(self, raw, folder):
        source = folder / 'source.vgm'
        source.write_bytes(raw)
        return build_native_performance(source, folder / 'out', 'source')

    def test_every_native_command_is_retained_once(self):
        raw = make_vgm(pulse_note() + wait(735) + write(0, 0x30) + wait(735))
        with tempfile.TemporaryDirectory() as temporary:
            performance = self.build(raw, Path(temporary))
            expected = [raw[e.address:e.address + 3]
                        for e in command_times(raw) if e.command == 0xb4]
            self.assertEqual(
                [encode_control(c, performance.devices[0])
                 for c in performance.controls], expected)

    def test_pulse_gate_becomes_a_melody_unit_at_source_pitch(self):
        raw = make_vgm(pulse_note() + wait(44100))
        with tempfile.TemporaryDirectory() as temporary:
            performance = self.build(raw, Path(temporary))
            units = [u for u in performance.units if u.device_id == 'nesapu:0']
            self.assertEqual(len(units), 1)
            unit = units[0]
            self.assertEqual(unit.role, 'melody')
            self.assertEqual(unit.section, 'pulse')
            self.assertEqual((unit.start_sample, unit.end_sample), (0, 44100))
            self.assertAlmostEqual(unit.pitch_curve[0][1], 440.4, delta=1.0)
            self.assertEqual(unit.volume_curve, ((0, 15),))
            self.assertTrue(unit.control_ids)

    def test_retrigger_splits_units(self):
        raw = make_vgm(pulse_note() + wait(22050) +
                       write(3, 1 << 3) + wait(22050))
        with tempfile.TemporaryDirectory() as temporary:
            performance = self.build(raw, Path(temporary))
            units = [u for u in performance.units if u.device_id == 'nesapu:0']
            self.assertEqual([(u.start_sample, u.end_sample) for u in units],
                             [(0, 22050), (22050, 44100)])


if __name__ == '__main__':
    unittest.main()
