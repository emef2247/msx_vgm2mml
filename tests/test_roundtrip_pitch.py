import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from roundtrip_pitch import compare


class PitchComparison(unittest.TestCase):
    def test_equal_pitch_different_rows(self):
        self.assertEqual(compare({0: {0: (427, 2), 1: (427, 2)}},
                                 {0: {0: (427, 3), 1: (427, 4)}}, 'psg'), [])

    def test_wrong_pitch_not_hidden(self):
        diff = compare({0: {t: (427, 2) for t in range(4)}},
                       {0: {t: (428, 3) for t in range(4)}}, 'scc')
        self.assertEqual(diff[0]['kind'], 'pitch')
        self.assertEqual(diff[0]['tick_end'], 4)

    def test_boundary_is_reported(self):
        diff = compare({0: {0: (400, 2), 1: (420, 3), 2: (420, 3)}},
                       {0: {0: (400, 2), 1: (400, 2), 2: (420, 3)}}, 'scc')
        self.assertEqual(diff[0]['kind'], 'boundary')

    def test_missing_end_is_failure(self):
        diff = compare({0: {0: (427, 2), 1: (427, 2)}}, {0: {0: (427, 2)}}, 'psg')
        self.assertEqual(diff[0]['kind'], 'coverage')

    def test_explicit_offset(self):
        self.assertEqual(compare({0: {0: (427, 2)}}, {0: {2: (427, 2)}}, 'psg', offset=2), [])

    def test_omitted_silence(self):
        self.assertEqual(compare({0: {0: (None, 2)}}, {}, 'psg'), [])
