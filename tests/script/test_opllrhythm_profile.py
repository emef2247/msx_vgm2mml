"""sfg01_opllrhythm: OPM melody with the OPLL rhythm left native."""
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


class OpllRhythmProfileTests(unittest.TestCase):
    def test_opllrhythm_keeps_rhythm_native_and_melody_on_opm(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'sfg01_opllrhythm', force=True)
        self.assertTrue(plan.get('native_opll_rhythm'))
        self.assertNotIn('opll_rhythm_fm', plan)
        self.assertEqual(prefix, b'')
        # Native rhythm: BD and SD key bits in the rhythm register.
        self.assertTrue(any(r['command'] == bytes((0x51, 0x0E, 0x20 | 16))
                            for r in rows))
        self.assertTrue(any(r['command'][0] == 0x51
                            and r['command'][1] == 0x0E
                            and r['command'][2] & 0x20
                            and r['command'][2] & 8 for r in rows))
        # The melody is consumed by the FM projection, not re-emitted
        # natively: no OPLL instrument/volume write for channel 0.
        self.assertFalse(any(r['command'][0] == 0x51
                             and r['command'][1] == 0x30 for r in rows))
        # FM melody sounds, and no FM rhythm: the YM2151 noise
        # register is never written.
        self.assertTrue(any(r['command'][0] == 0x54 for r in rows))
        self.assertFalse(any(r['command'][0] == 0x54
                             and r['command'][1] == 0x0F for r in rows))

    def test_sfg01_still_projects_rhythm_to_fm(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'sfg01', force=True)
        self.assertIn('opll_rhythm_fm', plan)
        # Both hits sound as FM key-ons (the opll table is all-FM
        # since the 2026-11-21 refit; no noise-register ride).
        ons = {r['unit_id'] for r in rows
               if r['command'][0] == 0x54 and r['command'][1] == 0x08
               and r['command'][2] & 0x78}
        self.assertTrue({'bd', 'sd'} <= ons)
        # No native rhythm key rows.
        self.assertFalse(any(r['command'][0] == 0x51
                             and r['command'][1] == 0x0E for r in rows))


if __name__ == '__main__':
    unittest.main()
