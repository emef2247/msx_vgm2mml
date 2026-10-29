"""State-aware sharing without changing note/timing or loop exit state."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'py'))
from mml_relative_state import normalize, compact_callers, relative_body, signature
from mml_macros import compress_macros
from structured_macros import enhance_macros


class RelativeMacros(unittest.TestCase):
    def test_shifted_octave_and_volume_share_one_relative_definition(self):
        phrases=[]
        for channel,octave,volume in (('9',3,8),('a',5,10)):
            phrase=f'o{octave} v{volume} c8 o{octave} d8 v{volume+1} e8 o{octave+1} f8 v{volume+2} g8 o{octave} a8 b8'
            phrases.append(channel+' '+phrase)
        original='#opll_mode 0\n'+'\n'.join(phrases)+'\n'
        result=compress_macros(original)
        bodies=re.findall(r'^\*\d+\s*=\s*\{([^}]*)\}',result,re.M)
        self.assertEqual(len(bodies),1)
        self.assertTrue(relative_body(bodies))
        self.assertIn('>',bodies[0]);self.assertIn(')',bodies[0])
        self.assertEqual(signature(original),signature(result))

    def test_repeated_reset_and_relative_accumulation_keep_nested_loop_exits(self):
        original='9 o3 v5 [o4 v8 c8 > d8 [< e8 > f8]3]4 < g4 v3 a4\n'
        result=normalize(original)
        self.assertEqual(signature(original),signature(result))
        self.assertEqual(signature(original),signature(compact_callers(result)))
        self.assertIn('[o4 v8',result)

    def test_long_relative_changes_only_use_absolute_spelling_outside_macros(self):
        original='*0 = { > > > c8 < < < d8 ) ) ) e8 ( ( ( f8 }\n9 o3 v5 *0 > > > g8\n'
        result=compact_callers(original)
        self.assertIn('*0 = { > > > c8',result)
        self.assertIn('*0 o6 g8',result)
        self.assertEqual(signature(original),signature(result))

    def test_unknown_entry_and_range_boundaries_are_conservative(self):
        for original in ('9 > c8 o4 d8\n','9 v15 ) c8 v15 d8\n','9 o8 > c8 o8 d8\n'):
            self.assertEqual(signature(original),signature(normalize(original)))

    def test_physical_line_wrap_does_not_break_a_nested_loop(self):
        original='9 o3 v5 [c8 > d8\n9 [e8 f8]3 < g8]4 > > > a8\n'
        self.assertEqual(signature(original),signature(compact_callers(original)))

    def test_enhanced_macro_audit_keeps_entry_and_relative_intermediates(self):
        original='9 o4 v8 c8 d8 e8 f8 g8 a8\na o6 v10 c8 d8 e8 f8 g8 a8\n'
        with tempfile.TemporaryDirectory() as temporary:
            prefix=Path(temporary)/'probe'
            result=enhance_macros(original,dump_prefix=prefix)
            self.assertEqual(signature(original),signature(result))
            self.assertTrue(prefix.with_suffix('.macro_state.relative.mml').is_file())
            self.assertTrue(prefix.with_suffix('.macro_state.json').is_file())

    @unittest.skipUnless(shutil.which('mgsc'),'native MGSC required')
    def test_compiled_music_matches_for_shifted_shared_gestures(self):
        body='o4 v10 c8 o4 d8 v11 e8 o5 f8 v12 g8 o4 a8 b8 '
        original='#opll_mode 0\n#alloc { 9=4096 }\n#tempo 75\n9 @1 '+body*4+'\n'
        result=enhance_macros(original)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);timelines=[]
            for number,text in enumerate((original,result)):
                source=folder/f'{number}.mml';output=source.with_suffix('.mgs')
                source.write_text(text)
                compiled=subprocess.run(['mgsc',str(source),str(output)],capture_output=True,timeout=30)
                self.assertEqual(compiled.returncode,0,compiled.stdout)
                if not shutil.which('node'):
                    continue
                root=Path(__file__).resolve().parents[2]
                vgm=output.with_suffix('.vgm')
                rendered=subprocess.run(['node',str(root/'scripts/mgs_to_vgm.mjs'),str(output),str(vgm),'12000'],capture_output=True,timeout=45)
                self.assertEqual(rendered.returncode,0,rendered.stderr)
                from vgm_io import read_vgm_bytes
                from vgm_timing import command_times
                raw=read_vgm_bytes(vgm);state={};events=[]
                for event in command_times(raw):
                    if event.command!=0x51:continue
                    register,value=raw[event.address+1:event.address+3]
                    if state.get(register)==value:continue
                    state[register]=value;events.append((event.vgmticks,register,value))
                timelines.append(events)
            if timelines:
                self.assertEqual([r[1:] for r in timelines[0]],[r[1:] for r in timelines[1]])
                # Absolute/relative bytecodes have different Z80 dispatch costs.
                self.assertLessEqual(max(abs(a[0]-b[0]) for a,b in zip(*timelines)),4)


if __name__=='__main__':unittest.main()
