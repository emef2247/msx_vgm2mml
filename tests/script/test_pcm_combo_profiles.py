"""PCM-complement profiles: misato_msxaudio, opl3_makoto, opl3_msxaudio.

Misato and the OPL3 composition have no PCM unit of their own, so
these pairings give PCM content a destination on a second
cartridge.  There is deliberately no misato_makoto: Misato and
Makoto are both OPNA cartridges and their I/O ports collide.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_music import (NativeDevice, NativePCM, NativePerformance,
                          NativeUnit, NativeVoice)
from musical_variants import PROFILES, project_variant


def performance():
    device = NativeDevice('opll:0', 'opll', 0, 3579545)
    voice = NativeVoice('v1', 'opll:0', 'fm', (('instrument', 1),))
    unit = NativeUnit('u1', 'opll:0', 'fm', 0, 0, 4410,
                      ((0, 440.0),), ((0, 0),), ((0, 'v1'),))
    asset = NativePCM('pcm', 'opll:0', 0, 80, 44100, (0,) * 80)
    return NativePerformance((device,), (unit,), (), (voice,), (), (),
                             44100, '', '', pcm_assets=(asset,))


class PcmComboProfileTests(unittest.TestCase):
    def test_misato_msxaudio_gives_pcm_a_delta_t_destination(self):
        p = performance()
        _, _, losses, _ = project_variant(p, 'misato', force=True)
        self.assertIn('pcm_content_omitted_no_misato_destination', losses)
        rows, prefix, losses, plan = project_variant(
            p, 'misato_msxaudio', force=True)
        self.assertNotIn('pcm_content_omitted_no_misato_destination',
                         losses)
        self.assertIn(b'\x67\x66\x88', prefix)  # Y8950 Delta-T block
        self.assertTrue(any(r['command'][0] == 0x5c for r in rows))
        self.assertIn('pcm', plan)

    def test_opl3_combos_give_pcm_a_destination(self):
        p = performance()
        _, _, losses, _ = project_variant(p, 'opl3', force=True)
        self.assertIn('pcm_content_omitted_no_opl3_destination', losses)
        rows, prefix, losses, plan = project_variant(
            p, 'opl3_makoto', force=True)
        self.assertNotIn('pcm_content_omitted_no_opl3_destination',
                         losses)
        self.assertIn(b'\x67\x66\x81', prefix)  # OPNA ADPCM-B block
        self.assertTrue(any(r['command'][0] in (0x56, 0x57)
                            for r in rows))
        self.assertIn('pcm', plan)
        rows, prefix, losses, plan = project_variant(
            p, 'opl3_msxaudio', force=True)
        self.assertNotIn('pcm_content_omitted_no_opl3_destination',
                         losses)
        self.assertIn(b'\x67\x66\x88', prefix)  # Y8950 Delta-T block
        self.assertTrue(any(r['command'][0] == 0x5c for r in rows))
        self.assertIn('pcm', plan)

    def test_no_misato_makoto_pairing(self):
        self.assertNotIn('misato_makoto', PROFILES)
        with self.assertRaisesRegex(ValueError,
                                    'Unknown cartridge profile'):
            project_variant(performance(), 'misato_makoto', force=True)


if __name__ == '__main__':
    unittest.main()
