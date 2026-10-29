"""MGSC-safe notation shortening, including real compiler/driver comparisons."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts')]
from mml_notation import compact
from mml_note_values import _meaning
from mml_sync import analyze_mml,_leaves


def meaning(text):
    rows=_meaning(text)
    return {ch:[r for r in values if not (r[0]=='control' and r[1].lower().startswith('l'))]
            for ch,values in rows.items()}


class Notation(unittest.TestCase):
    def test_compaction_preserves_nested_loop_indentation(self):
        from mml_layout import format_mml_loops
        before=format_mml_loops('1 [ [ [ c8 d8 e8 ]2 f8 g8 a8 ]3 b8 c8 ]2 d8 e8 f8\n')
        result=compact(before)
        self.assertLess(len(result),len(before))
        depths=lambda text:[len(line)-len(line.lstrip()) for line in
            (line[2:] for line in text.splitlines() if line.startswith('1 '))]
        self.assertEqual(depths(result),depths(before))
        self.assertIn('1     [',result)
        self.assertIn('1   ]3',result)
        self.assertEqual(meaning(before),meaning(result))

    def test_same_pitch_uses_additive_length_but_retriggers_remain(self):
        text='#tempo 225\n9 o5 c8 & c8 c8 & d8 e8 f8 g8\n'
        result=compact(text)
        self.assertIn('l8 ',result)
        self.assertIn('c^',result)
        self.assertIn('& d',result)
        self.assertEqual(meaning(text),meaning(result))

    def test_default_length_and_nested_macro_scope_remain_independent(self):
        for text in ('9 l32 d1 d d\n',
                     '*0 = { c8 d16 e8 }\n9 c8 d8 e8 [f8 *0]3 g8 a8 b8\n',
                     '9 q6 c8 & c8 c8 c8 c8\n',
                     '9 c d8 e8 f8 g8 a8 b8\n',
                     '*0 = { c d e }\n9 c8 d8 e8 f8 *0 g8 a8 b8\n'):
            with self.subTest(text=text):
                self.assertEqual(meaning(text),meaning(compact(text)))
        self.assertNotIn('^',compact('9 q6 c8 & c8\n'))

    def test_relative_octave_changes_do_not_turn_slurs_into_length_addition(self):
        text='9 o4 c8 & > c8 & < c8\n'
        self.assertNotIn('^',compact(text))
        self.assertEqual(meaning(text),meaning(compact(text)))

    def test_dotted_defaults_and_compiler_length_limit(self):
        text='9 o4 c16. d16. e16. f16. g16. a16. c1 & c1 & c4 & c8\n'
        self.assertEqual(meaning(text),meaning(compact(text)))
        self.assertIn('l16.',compact(text))
        self.assertIn('& c1',compact(text))

    def test_length_addition_never_starts_a_physical_score_line(self):
        text='9 c8 &\n9 c8 d8 e8 f8 g8 a8\n'
        self.assertFalse(any(line.startswith('9 ^') for line in compact(text).splitlines()))

    @unittest.skipUnless(shutil.which('mgsc') and shutil.which('node'),'MGSC and Node required')
    def test_actual_compiler_replay_keeps_key_edges_and_dispatch_times(self):
        from vgm_reader import parse_vgm
        from check_opll_key_edges import extract
        if subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),'--check'],capture_output=True).returncode:
            self.skipTest('libkss-js required')
        text='#opll_mode 0\n#tempo 225\n#alloc {9=4000}\n9 @0 v15 o5 c8 & c8 c8 d8 e8 [f8 g8]3 a4\n'
        results=[]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for number,value in enumerate((text,compact(text))):
                folder=root/str(number);folder.mkdir()
                path=folder/'p.mml';path.write_text(value)
                run=subprocess.run(['mgsc',str(path),str(path.with_suffix('.mgs'))],capture_output=True)
                self.assertEqual(run.returncode,0,run.stdout)
                run=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(path.with_suffix('.mgs')),
                                    str(path.with_suffix('.vgm')),'3000'],capture_output=True)
                self.assertEqual(run.returncode,0,run.stderr)
                paths=parse_vgm(str(path.with_suffix('.vgm')),str(folder/'actual'))
                results.append([(e['keyon'],e['time']) for e in extract(paths[7])])
        self.assertEqual([r[0] for r in results[0]],[r[0] for r in results[1]])
        # Different compiler bytecode changes dispatch cost by two samples.
        self.assertLessEqual(max(abs(a[1]-b[1]) for a,b in zip(*results)),4/44100)


if __name__=='__main__':unittest.main()
