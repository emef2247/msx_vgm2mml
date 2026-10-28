"""Loop-first sharing must not spend slots on internal envelope fragments."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'py'))
from mml_sync import _parse
from mml_relative_state import signature
from mml_macro_phrases import prepare,quality
from structured_macros import enhance_macros


class PhraseMacros(unittest.TestCase):
    def test_adjacent_volume_holds_use_a_loop_not_a_macro(self):
        text='1 o4 v15 c64 '+'( & c64 '*7+'r8\n'
        rows=[];result=prepare(text,rows)
        self.assertEqual(signature(text),signature(result))
        self.assertIn('[( & c64]7',result)
        self.assertEqual(rows[0]['repeats'],7)
        self.assertNotRegex(enhance_macros(text),r'^\*\d+\s*=')

    def test_partial_gate_and_control_only_candidates_are_not_phrases(self):
        held=_parse('a+64 ( & a+32 ( & a+16 r8')
        self.assertEqual(quality(held,0,5),0)
        self.assertEqual(quality(_parse('( & e64'),0,3),0)
        self.assertEqual(quality(_parse('> > >'),0,3),0)
        self.assertEqual(quality(_parse('c8'),0,1),0)
        self.assertEqual(quality(held,0,len(held)),1)
        self.assertEqual(quality(_parse('c8 d8'),0,2),2)

    def test_shared_whole_phrase_wins_over_its_internal_holds(self):
        phrase='c64 '+'( & c64 '*7+'r8 d8 e8 r8 '
        text='9 o4 v15 '+phrase+'g8 a8 '+phrase+'f8 g8\n'
        result=enhance_macros(text)
        self.assertEqual(signature(text),signature(result))
        bodies=re.findall(r'^\*\d+\s*=\s*\{([^}]*)\}',result,re.M)
        self.assertTrue(bodies)
        self.assertTrue(any('d8' in body and 'e8' in body for body in bodies))
        self.assertTrue(all(body.strip() not in ('( & c64','> > >') for body in bodies))

    def test_large_repeat_count_is_split_without_losing_iteration_state(self):
        text='9 o4 v15 '+('c64 r64 '*520)+'\n'
        result=prepare(text)
        self.assertEqual(signature(text),signature(result))
        self.assertTrue(all(int(n)<=255 for n in re.findall(r'\](\d+)',result)))

    def test_changing_default_length_is_not_folded_as_literal_loop(self):
        text='9 l8 c l16 c l8 c l16 c\n'
        result=prepare(text)
        self.assertNotIn('[',result)
        self.assertEqual(signature(text),signature(result))

    @unittest.skipUnless(shutil.which('mgsc') and shutil.which('node'),'MGSC/libkss required')
    def test_driver_preserves_tied_hold_loop_volume_sequence(self):
        text='#opll_mode 0\n#alloc { 1=4096 }\n#tempo 75\n1 q8 /1 o4 v15 c64 '+'( & c64 '*7+'r8\n'
        timelines=[]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for index,value in enumerate((text,prepare(text))):
                source=root/f'{index}.mml';source.write_text(value)
                mgs=source.with_suffix('.mgs');vgm=source.with_suffix('.vgm')
                compiled=subprocess.run(['mgsc',str(source),str(mgs)],capture_output=True,timeout=30)
                self.assertEqual(compiled.returncode,0,compiled.stdout)
                rendered=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'2000'],capture_output=True,timeout=45)
                self.assertEqual(rendered.returncode,0,rendered.stderr)
                from vgm_io import read_vgm_bytes
                from vgm_timing import command_times
                raw=read_vgm_bytes(vgm);events=[];state={}
                for event in command_times(raw):
                    if event.command!=0xa0:continue
                    register,value=raw[event.address+1:event.address+3]
                    if state.get(register)==value:continue
                    state[register]=value;events.append((event.vgmticks,register,value))
                timelines.append(events)
        self.assertEqual([r[1:] for r in timelines[0]],[r[1:] for r in timelines[1]])
        self.assertLessEqual(max(abs(a[0]-b[0]) for a,b in zip(*timelines)),4)


if __name__=='__main__':unittest.main()
