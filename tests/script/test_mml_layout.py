from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'py'))
from mml_layout import format_mml_loops
from mml_sync import analyze_mml


class MmlLayoutTests(unittest.TestCase):
    def test_loop_starts_break_and_closures_continue(self):
        before='1 o4 c4 [ d4 [ e4 ]3 f4 ]4 g4 [ a4 ]2 b4\n'
        actual=format_mml_loops(before)
        self.assertIn('1 [ d4\n1   [ e4 ]3 f4 ]4 g4\n1 [ a4 ]2 b4',actual)
        self.assertEqual(re.sub(r'\s','',before.replace('1 ','')),
                         re.sub(r'\s','',actual.replace('1 ','')))
        self.assertEqual(format_mml_loops(actual),actual)

    def test_timing_macros_and_comments_are_unchanged(self):
        before='*0 = { o4 c4 d4 }\n#alloc {\n1 = 1000\n}\n1 [ *0\n; sync boundary\n1 [ e8 f8 ]2 ]3 g4\n'
        actual=format_mml_loops(before)
        self.assertTrue(actual.startswith('*0 = { o4 c4 d4 }\n#alloc {\n1 = 1000\n}'))
        self.assertIn('; sync boundary\n1   [ e8 f8 ]2 ]3 g4',actual)
        a,ab,_=analyze_mml(before);b,bb,_=analyze_mml(actual)
        self.assertEqual(ab,bb)
        self.assertEqual({k:v[-1].end for k,v in a.items()},{k:v[-1].end for k,v in b.items()})

    def test_long_lines_wrap_without_changing_tokens(self):
        before='1 [ '+' '.join(['c8']*90)+' ]2 d4\n'
        actual=format_mml_loops(before,width=70)
        self.assertTrue(all(len(line)<=70 for line in actual.splitlines()))
        score=lambda s:re.sub(r'\s+','', ''.join(re.sub(r'^[1-9a-h]\s+','',line) for line in s.splitlines()))
        self.assertEqual(score(before),score(actual))


if __name__=='__main__':unittest.main()
