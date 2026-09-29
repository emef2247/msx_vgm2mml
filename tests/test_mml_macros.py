import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from mml_macros import compress_macros
from mml_sync import analyze_mml, _leaves


def expanded(text):
    tracks, _, _ = analyze_mml(text)
    return {ch: [(n.text, n.start, n.end) for n in _leaves(nodes)] for ch, nodes in tracks.items()}


class Macros(unittest.TestCase):
    def test_all_melodic_chips_and_comments(self):
        phrase = 'o4 v12 c8 d8 e8 f8 g8 a8 b8 > c8 < '
        text = '#opll_mode 1\n#alloc { 1=5000, 5=5000, 9=5000 }\n'
        for ch in ('1', '5', '9'):
            for i in range(5):
                text += f'; ch{ch} --- step {i*216} ---\n{ch} {phrase}\n'
        result = compress_macros(text)
        self.assertLess(len(result), len(text))
        self.assertIn('*0 =', result)
        self.assertEqual(expanded(text), expanded(result))
        self.assertEqual([l for l in text.splitlines() if l.startswith(';')],
                         [l for l in result.splitlines() if l.startswith(';')])
        self.assertIn('#alloc { 1=5000, 5=5000, 9=5000 }', result)

    def test_loops_and_ties(self):
        text = '#opll_mode 1\n9 ' + ('o4 v12 [c8 & c8 d8 e8]2 r8 ' * 12) + '\n'
        result = compress_macros(text)
        self.assertEqual(expanded(text), expanded(result))
        self.assertTrue(all(len(l) < 200 for l in result.splitlines()))

    def test_existing_macros_and_small_input_unchanged(self):
        for text in ('9 c4\n', '*0 = { c4 }\n9 *0\n'):
            self.assertEqual(compress_macros(text), text)

    def test_rhythm_macros_preserve_combined_hits_and_levels(self):
        from test_rhythm_mml import attacks
        text = '#opll_mode 1\n'
        for i in range(8):
            text += f'; sync {i}\nf vb15 vs12 vh10 l16 bs: h: s8 h: [b: h:]2 r8\n'
        result = compress_macros(text)
        self.assertIn('*0 =', result)
        self.assertEqual(expanded(text), expanded(result))
        self.assertEqual(attacks(text), attacks(result))
        self.assertEqual(expanded(result), expanded(__import__('mml_sync').annotate_sync_points(result)))
