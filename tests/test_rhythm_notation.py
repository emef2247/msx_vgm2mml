"""Notation changes preserve onsets, volumes, duration and existing loops."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from rhythm_notation import optimize
from mml_sync import analyze_mml, annotate_sync_points
from test_rhythm_mml import attacks


class RhythmNotation(unittest.TestCase):
    def test_short_step_default_does_not_use_unsupported_divisor(self):
        after = self.check('f vh12 ' + 'h%2 ' * 12 + '\n')
        self.assertNotIn('l96', after)
        self.assertIn('l%2', after)

    def test_rest_before_loop_retains_explicit_length(self):
        after = self.check('f r%18 [vh9 h%18]2 ' + 'h%18 ' * 12 + '\n')
        self.assertIn('r%18', after)
        self.assertNotRegex(after, r'\br\s')

    def check(self, body, raw=False):
        before = '#opll_mode 1\n' + body
        after = '#opll_mode 1\n' + optimize(body, raw)
        self.assertEqual(attacks(before), attacks(after))
        self.assertEqual(analyze_mml(before)[0]['f'][-1].end,
                         analyze_mml(after)[0]['f'][-1].end)
        annotated = annotate_sync_points(after, min_gap=0)
        self.assertEqual(attacks(before), attacks(annotated))
        return after

    def test_redundant_volumes_across_lines(self):
        after = self.check('f vh12 h16 vh12 h16 vh12 h16 vh12 h16\nf vh12 h16 vh12 h16 vh12 h16 vh12 h16\n')
        self.assertEqual(after.count('vh12'), 1)
        self.assertIn('l16', after)
        self.assertEqual(after.count('h:'), 8)

    def test_loop_entry_and_back_edge(self):
        after = self.check('f vs15 s8 [vs15 s8 vs13 s8]4 vs13 s8\n')
        self.assertIn('[vs15', after)  # must reset 13 to 15 on later iterations
        self.assertNotIn(']4 vs13', after)

    def test_loop_with_unchanged_exit_can_drop_entry_setting(self):
        after = self.check('f vh12 h8 [vh12 h8 vh12 h8]3\n')
        self.assertEqual(after.count('vh12'), 1)
        self.assertIn(']3', after)

    def test_nested_loops_and_combined_hits(self):
        self.check('f vb15 vs12 bs8 [vb15 b8 [vs12 s8 vs10 s8]2 vs12 s8]3\n')

    def test_raw_exact_lengths_do_not_round(self):
        after = self.check('f vh12 h%7 h%7 h%8 ' + 'h%7 ' * 8 + 'r%7\n', raw=True)
        self.assertIn('l%7', after)
        self.assertIn('h%8', after)

    def test_no_length_default_when_it_would_be_longer(self):
        after = self.check('f vb15 b8\n')
        self.assertNotIn('l8', after)
        self.assertEqual(optimize(''), '')

    def test_long_loop_wraps_without_expanding_or_retiming(self):
        before = '#opll_mode 1\nf [' + 'vb15 b%7 vs12 s%8 ' * 30 + ']3\n'
        after = annotate_sync_points(before, min_gap=10000)
        self.assertIn(']3', after)
        self.assertEqual(attacks(before), attacks(after))
        self.assertEqual(analyze_mml(before)[0]['f'][-1].end,
                         analyze_mml(after)[0]['f'][-1].end)
        self.assertTrue(all(len(line) <= 122 for line in after.splitlines()
                            if line.startswith('f ')))
