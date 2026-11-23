"""Authored YM2203 (OPN) source check: a synthetic VGM with one
FM gate and one SSG gate must decode into native units at the
OPN-family pitches, and project onto OPNA and OPM targets."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_source_music import build_native_performance
from musical_variants import project_variant

CLOCK = 4000000


def synthetic_vgm():
    header = bytearray(256)
    header[0:4] = b'Vgm '
    struct.pack_into('<I', header, 0x08, 0x171)       # version 1.71
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)  # data offset
    struct.pack_into('<I', header, 0x44, CLOCK)       # YM2203 clock

    def w(register, value):
        return bytes((0x55, register, value))

    stream = bytearray()
    # FM channel 0 voice: algorithm 0, op4 carrier TL 16.
    stream += w(0x30, 0x01)   # op1 dt/mul
    stream += w(0x4c, 0x10)   # op4 total level
    stream += w(0x50, 0x1f)   # op1 ks/ar
    stream += w(0xb0, 0x00)   # algorithm/feedback
    stream += w(0xa4, 0x2c)   # block 5, fnum high (fnum 1038)
    stream += w(0xa0, 0x0e)   # fnum low
    stream += w(0x28, 0xf0)   # key on, channel 0
    stream += b'\x61\x44\xac'  # wait 44100
    stream += w(0x28, 0x00)   # key off
    # SSG channel 0: period 142 (440 Hz at the 1 MHz prescale-6
    # SSG clock), tone on, amplitude 12.
    stream += w(0x00, 142)
    stream += w(0x01, 0)
    stream += w(0x07, 0x3e)
    stream += w(0x08, 12)
    stream += b'\x61\x44\xac'
    stream += w(0x08, 0)
    stream += b'\x66'
    struct.pack_into('<I', header, 0x04, 256 + len(stream) - 4)
    return bytes(header) + bytes(stream)


class OpnSourceTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.perf = build_native_performance(
            synthetic_vgm(), self._td.name, 'opn')

    def tearDown(self):
        self._td.cleanup()

    def test_device_and_units(self):
        devices = {d.device_id: d for d in self.perf.devices}
        self.assertIn('opn:0', devices)
        self.assertEqual(devices['opn:0'].clock_hz, CLOCK)
        fm = [u for u in self.perf.units if u.section == 'fm']
        self.assertEqual(len(fm), 1)
        self.assertEqual(fm[0].channel, 0)
        hz = fm[0].pitch_curve[0][1]
        self.assertAlmostEqual(hz, 1038 * CLOCK / (144 * 2 ** 16), places=1)
        ssg = [u for u in self.perf.units if u.section == 'ssg']
        self.assertEqual(len(ssg), 1)
        self.assertEqual(ssg[0].channel, 0)
        self.assertAlmostEqual(ssg[0].pitch_curve[0][1],
                               (CLOCK / 4) / (16 * 142), places=1)

    def test_projects_to_opna_and_opm(self):
        for profile, opcode in (('makoto', 0x56), ('sfg01', 0x54)):
            rows, prefix, losses, plan = project_variant(
                self.perf, profile, force=True)
            opcodes = {row['command'][0] for row in rows}
            self.assertIn(opcode, opcodes)
            self.assertIn(0xa0, opcodes)  # SSG lands on the AY lane


if __name__ == '__main__':
    unittest.main()
