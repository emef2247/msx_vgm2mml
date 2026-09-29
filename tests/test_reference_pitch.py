import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_reference_pitch import reference_notes


class ReferencePitch(unittest.TestCase):
    header = '#psg_tune {3392,3200,3008,2848,2688,2528,2368,2240,2112,2016,1888,1792}\n'

    def test_grouped_tracks_and_signed_detune(self):
        tracks, _ = reference_notes(self.header + '15 o4 c4 \\-1 c4')
        for ch in ('1', '5'):
            self.assertEqual([n['period'] for n in tracks[ch]], [424,425])

    def test_octave_and_loop_state(self):
        tracks, _ = reference_notes(self.header + '5 o3 [c4 >]2')
        self.assertEqual([n['period'] for n in tracks['5']], [848,424])

    def test_noise_and_muted_notes_excluded(self):
        tracks, _ = reference_notes(self.header + '1 v0 c4 v15 /2 d4 /1 e4')
        self.assertEqual([n['note'] for n in tracks['1']], ['e'])

    def test_explicit_infinite_loop_window(self):
        tracks, _ = reference_notes(self.header + '5 o4 [c4 d4]0', 2)
        self.assertEqual([n['period'] for n in tracks['5']], [424,376,424,376])
