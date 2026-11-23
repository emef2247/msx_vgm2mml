"""misato / sfg01_misato: the Makoto composition without an ADPCM
unit; OPLL percussion plays on the native YM2608 rhythm unit."""
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


class MisatoProfileTests(unittest.TestCase):
    def test_misato_rhythm_uses_the_opna_rhythm_unit(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'misato', force=True)
        self.assertTrue(plan.get('misato_no_adpcm'))
        # No ADPCM anywhere: no data-block prefix, no block rows.
        self.assertEqual(prefix, b'')
        self.assertFalse(any(r['command'][0] == 0x67 for r in rows))
        # Rhythm total level is set once, unattenuated.
        self.assertTrue(any(r['command'] == bytes((0x56, 0x11, 0x3F))
                            for r in rows))
        # BD and SD key bits on the rhythm key register.
        self.assertTrue(any(r['command'] == bytes((0x56, 0x10, 0x01))
                            for r in rows))
        self.assertTrue(any(r['command'] == bytes((0x56, 0x10, 0x02))
                            for r in rows))
        # Levels follow IL = 31 - 4 * att (OPLL att 4 -> 15, 6 -> 7),
        # with both pan bits on.
        self.assertTrue(any(r['command'] == bytes((0x56, 0x18, 0xC0 | 15))
                            for r in rows))
        self.assertTrue(any(r['command'] == bytes((0x56, 0x19, 0xC0 | 7))
                            for r in rows))
        # The melody is on OPNA FM (key-ons present), as in makoto.
        self.assertTrue(any(r['command'][0] == 0x56
                            and r['command'][1] == 0x28 for r in rows))

    def test_makoto_still_uses_adpcm_for_the_same_rhythm(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'makoto', force=True)
        self.assertFalse(any(r['command'][0] == 0x56
                             and r['command'][1] == 0x10 for r in rows))
        self.assertTrue(prefix.startswith(b'\x67\x66\x81')
                        or any(r['command'][0] == 0x57 for r in rows))

    def test_sfg01_misato_pairs_opm_with_the_rhythm_unit(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'sfg01_misato', force=True)
        self.assertTrue(plan.get('misato_no_adpcm'))
        self.assertEqual(prefix, b'')
        self.assertTrue(any(r['command'][0] == 0x54 for r in rows))
        self.assertTrue(any(r['command'] == bytes((0x56, 0x10, 0x01))
                            for r in rows))


if __name__ == '__main__':
    unittest.main()
