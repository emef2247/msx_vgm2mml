"""The bounded reference audit must not silently repair musical loops."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_reference_loop_windows import parse_reference, windows


class ReferenceWindowsTests(unittest.TestCase):
    def test_grouped_unused_track(self):
        tracks, macros, _ = parse_reference('#tempo 120\n9e [\n9 c4\n9 ]0')
        self.assertEqual(set(tracks), {'9'})
        records, state = windows(tracks['9'], macros, infinite_passes=2)
        self.assertEqual(state['step'], 96)

    def test_unclosed_sounded_track_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_reference('#tempo 120\n9 [c4')

    def test_exit_only_shortens_last_iteration(self):
        tracks, macros, _ = parse_reference('#tempo 120\n9 [c4|d4]3')
        records, _ = windows(tracks['9'], macros)
        self.assertEqual([r['step_end']-r['step_start'] for r in records], [96,96,48])

    def test_nested_duration_and_relative_volume(self):
        tracks, macros, _ = parse_reference('#tempo 120\n9 v15 [[c4v-1]2d4]2')
        records, state = windows(tracks['9'], macros)
        self.assertEqual(state['volume'], 11)
        self.assertEqual(state['step'], 288)
        outer = [r for r in records if not r['parent_loop']]
        self.assertEqual(outer[0]['commands'], outer[1]['commands'])


if __name__ == '__main__':
    unittest.main()
