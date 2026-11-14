"""Layered stacks every FM source, including the native OPLL."""
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
    hit = NativePercussion('bd', 'opll:0', '0', 'BD', 100, None,
                           ((100, 0),))
    return NativePerformance((device,), (unit,), (), (voice,), (hit,),
                             (), 44100, '', '')


class LayeredNativeOpllTests(unittest.TestCase):
    def test_layered_keeps_native_opll_melody_and_rhythm(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'layered', force=True)
        self.assertTrue(plan.get('native_opll_layer'))
        self.assertNotIn('opll_rhythm_pcm', plan)
        self.assertEqual(prefix, b'')
        # Native melody lane: instrument/volume write on channel 0.
        self.assertTrue(any(r['command'][0] == 0x51
                            and r['command'][1] == 0x30 for r in rows))
        # Native rhythm: BD key bit set in the rhythm register.
        self.assertTrue(any(r['command'] == bytes((0x51, 0x0E, 0x20 | 16))
                            for r in rows))
        # Both FM projections still sound.
        self.assertTrue(any(r['command'][0] == 0x54 for r in rows))
        self.assertTrue(any(r['command'][0] == 0x56 for r in rows))

    def test_makoto_still_substitutes_pcm_rhythm(self):
        rows, prefix, losses, plan = project_variant(
            performance(), 'makoto', force=True)
        self.assertEqual(plan.get('opll_rhythm_pcm'), 'ika')
        self.assertTrue(prefix)
        self.assertFalse(any(r['command'][0] == 0x51
                             and r['command'][1] == 0x0E for r in rows))


if __name__ == '__main__':
    unittest.main()
