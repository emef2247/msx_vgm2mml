"""sfg01_opl3: OPM melody with OPLL rhythm on the OPL3 rhythm unit."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_music import (NativeDevice, NativePercussion,
                          NativePerformance, NativeUnit, NativeVoice)
from musical_variants import project_variant


def performance():
    device = NativeDevice('opll:0', 'opll', 0, 3579545)
    voice = NativeVoice('v1', 'opll:0', 'fm', (('instrument', 1),))
    unit = NativeUnit('u1', 'opll:0', 'fm', 0, 0, 4410,
                      ((0, 440.0),), ((0, 0),), ((0, 'v1'),))
    bd = NativePercussion('bd', 'opll:0', '0', 'BD', 100, None,
                          ((100, 4),))
    sd = NativePercussion('sd', 'opll:0', '0', 'SD', 200, None,
                          ((200, 6),))
    return NativePerformance((device,), (unit,), (), (voice,), (bd, sd),
                             (), 44100, '', '')


class Sfg01Opl3ProfileTests(unittest.TestCase):
    def test_opl3_rhythm_unit_with_opm_melody(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'sfg01_opl3', force=True)
        self.assertTrue(plan.get('opl3_rhythm_unit'))
        self.assertEqual(prefix, b'')
        # The melody is projected to OPM writes.
        self.assertTrue(any(r['command'][0] == 0x54 for r in rows))
        # No native OPLL writes remain: neither melody nor rhythm.
        self.assertFalse(any(r['command'][0] == 0x51 for r in rows))
        # The OPL3 lane opens with the mode enable and the rhythm
        # template, and the hits land in the rhythm key register.
        self.assertIn(bytes((0x5f, 0x05, 1)),
                      [r['command'] for r in rows])
        keys = [r['command'][2] for r in rows
                if r['command'][:2] == bytes((0x5e, 0xbd))]
        self.assertTrue(any(v & 16 for v in keys))  # BD
        self.assertTrue(any(v & 8 for v in keys))   # SD


if __name__ == '__main__':
    unittest.main()
