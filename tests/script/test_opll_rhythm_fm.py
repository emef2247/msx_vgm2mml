"""OPLL percussion projected to fitted OPM FM one-shot voices."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_music import (NativeControl, NativeDevice, NativePercussion,
                          NativePerformance)
from opll_rhythm_fm import project_opll_rhythm_fm


def performance(events, controls=()):
    device = NativeDevice('opll:0', 'opll', 0, 3579545)
    return NativePerformance((device,), (), controls, (), events, (),
                             100000, '', '')


def hit(event_id, family, start, vol, stop=None):
    return NativePercussion(event_id, 'opll:0', '0', family, start, stop,
                            ((start, vol),))


def key_ons(rows):
    return [r for r in rows if r['command'][1] == 8
            and r['command'][2] & 0x78]


class OpllRhythmFmTests(unittest.TestCase):
    def test_bd_hit_uses_a_free_channel_with_key_off(self):
        rows, losses, info = project_opll_rhythm_fm(
            performance((hit('bd', 'BD', 100, 4),)), 'opll',
            reserved={0, 1, 2, 3, 4, 5})
        ons = key_ons(rows)
        self.assertEqual(len(ons), 1)
        ch = ons[0]['command'][2] & 7
        self.assertIn(ch, (6, 7))
        offs = [r for r in rows if r['command'][1] == 8
                and r['command'][2] == ch]
        self.assertEqual(len(offs), 1)
        self.assertGreater(offs[0]['sample'], 100)
        self.assertTrue(all(r['command'][0] == 0x54 for r in rows))

    def test_simultaneous_hits_keep_the_two_loudest(self):
        events = (hit('bd', 'BD', 100, 0), hit('sd', 'SD', 100, 6),
                  hit('hh', 'HH', 100, 12))
        rows, losses, info = project_opll_rhythm_fm(
            performance(events), 'opll', reserved={0, 1, 2, 3, 4, 5})
        self.assertEqual({r['unit_id'] for r in key_ons(rows)},
                         {'bd', 'sd'})
        self.assertEqual(losses['opll_rhythm_fm_simultaneous_omitted'], 1)

    def test_noise_voice_takes_channel_8_and_enables_noise(self):
        rows, losses, info = project_opll_rhythm_fm(
            performance((hit('sd', 'SD', 100, 0),)), 'opll', reserved=set())
        ons = key_ons(rows)
        self.assertEqual(ons[0]['command'][2] & 7, 7)
        noise = [r for r in rows if r['command'][1] == 0x0F]
        self.assertEqual(noise[0]['command'][2], 0x80 | 31)

    def test_tom_pitch_follows_the_rhythm_oscillator(self):
        def control(cid, kind, sample, params):
            return NativeControl(cid, 'opll:0', 'pitch', 8, sample, 0,
                                 kind, params)
        controls = (
            control('pl0', 'opll_pitch_low', 0,
                    (('register', 0x18), ('fnum_low', 192))),
            control('ph0', 'opll_pitch_high', 0,
                    (('register', 0x28), ('fnum_high', 1), ('block', 0),
                     ('key_on', 0), ('sustain', 0))),
            control('pl1', 'opll_pitch_low', 5000,
                    (('register', 0x18), ('fnum_low', 192))),
            control('ph1', 'opll_pitch_high', 5000,
                    (('register', 0x28), ('fnum_high', 1), ('block', 1),
                     ('key_on', 0), ('sustain', 0))))
        events = (hit('t1', 'TOM', 100, 0), hit('t2', 'TOM', 6000, 0))
        rows, losses, info = project_opll_rhythm_fm(
            performance(events, controls), 'opll', reserved=set())
        kcs = [r['command'][2] for r in rows
               if 0x28 <= r['command'][1] <= 0x2F
               and r['reason'] == 'OPLL rhythm FM pitch']
        self.assertEqual(len(kcs), 2)
        self.assertNotEqual(kcs[0], kcs[1])


if __name__ == '__main__':
    unittest.main()
