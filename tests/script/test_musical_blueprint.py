"""Blueprint is a simple score projection; native dynamics remain untouched."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'py'), str(ROOT/'scripts')]
from musical_plan import MusicalPlan, MusicalUnit, MusicalControl
from musical_blueprint import BlueprintError, render_blueprint, render_blueprints, write_blueprint, _length
from mml_sync import analyze_mml
from vgm_io import read_vgm_bytes
from vgm_timing import command_times


def note(chip='psg', channel=0, start=0, length=4410, uid='unit', volumes=((0,15),(1470,9),(2940,3))):
    unit=MusicalUnit(uid,chip,channel,start,start+length,False)
    controls=[MusicalControl(start,chip,channel,'pitch',(172,3,0) if chip=='opll' else (426,),unit_id=uid)]
    controls += [MusicalControl(start+t,chip,channel,'volume',(v,),unit_id=uid) for t,v in volumes if t<length]
    return unit,controls


def plan(*notes,metadata=()):
    units,controls=zip(*notes);end=max(u.end_sample for u in units)
    return MusicalPlan(tuple(units),tuple(c for rows in controls for c in rows),end,end,
        (('psg',1789773),('scc',1789773),('opll',3579545)),metadata=metadata)


def music(text):
    return '\n'.join(re.sub(r';.*','',line) for line in text.splitlines())


class BlueprintTests(unittest.TestCase):
    def test_blueprint_only_score_view_leaves_production_and_guide_untouched(self):
        from musical_blueprint import score_timing_view, _legacy_performance
        from score_structure import build
        p = plan(*(note(start=i*4410, length=4000, uid=f'n{i}') for i in range(4)))
        source = _legacy_performance(p)
        p = replace(p, source_performance=source, score_guide=build(source, repeats=True))
        before = asdict(p)
        view = score_timing_view(p, tempo=225)
        self.assertEqual(asdict(p), before)
        self.assertIs(view.score_guide, p.score_guide)
        self.assertIs(view.source_performance, p.source_performance)
        self.assertIs(view.score_performance, p.source_performance)
        self.assertIn('#tempo 225', render_blueprint(view)[0])
        self.assertNotIn('score_normalization', dict(p.metadata))

    def test_subframe_duration_spelling_and_long_final_piece(self):
        self.assertEqual(_length('c',1),'c%1');self.assertEqual(_length('c',2),'c%2')
        self.assertEqual(_length('c',3),'c64');self.assertEqual(_length('c',48),'c4')
        self.assertEqual(_length('c',256,minimum=3),'c%253 &c64')

    def test_native_lanes_remove_volume_and_volume_only_ties(self):
        for chip,track in (('psg','1'),('scc','4'),('opll','9')):
            with self.subTest(chip=chip):
                p=plan(note(chip));before=asdict(p);text,report=render_blueprint(p)
                self.assertEqual(re.findall(r'\bv(?:[bsmch])?[-+]?\d+',music(text)),['v15'])
                self.assertNotIn('&',music(text))
                self.assertEqual(bool(re.search(r'(?m)^@s0=',text)),chip=='scc')
                self.assertNotIn('@e',text)
                tracks,_,_=analyze_mml(text)
                self.assertEqual(set(tracks),{track});self.assertEqual(tracks[track][-1].end,6)
                self.assertIn(f'Source: {chip.upper()} #1',text)
                self.assertEqual(report['omitted_units'],0)
                self.assertEqual(asdict(p),before)

    def test_complete_units_form_finite_repeats(self):
        p=plan(*(note(start=i*4410,uid=f'n{i}') for i in range(4)))
        text,report=render_blueprint(p)
        self.assertRegex(text,r'\]\s*4');self.assertTrue(report['loops'])
        tracks,_,_=analyze_mml(text);self.assertEqual(tracks['1'][-1].end,24)

    def test_pitch_change_ties_but_explicit_retrigger_does_not(self):
        unit,controls=note('opll')
        controls += [MusicalControl(1470,'opll',0,'pitch',(194,3,0),unit_id=unit.unit_id)]
        _,report=render_blueprint(plan((unit,controls)))
        text=report['allocations'][0]['mml'];self.assertIn('&d',text)
        controls += [MusicalControl(2940,'opll',0,'gate',(0,),order=1,unit_id=unit.unit_id),
                     MusicalControl(2940,'opll',0,'gate',(1,),order=2,unit_id=unit.unit_id)]
        _,report=render_blueprint(plan((unit,controls)))
        self.assertEqual(len(report['allocations']),2)
        self.assertNotIn('&',report['allocations'][1]['mml'])

    def test_source_gate_volume_only_partitions_rejoin(self):
        a,ac=note(start=0,length=1470,uid='a',volumes=((0,15),))
        b,bc=note(start=1470,length=1470,uid='b',volumes=((0,9),))
        a=replace(a,gate_ids=('gate0',));b=replace(b,gate_ids=('gate0',))
        p=plan((a,ac),(b,bc));before=asdict(p)
        text,report=render_blueprint(p)
        self.assertEqual(report['sounding_units'],1);self.assertNotIn('&',music(text))
        self.assertEqual(asdict(p),before)

    def test_observed_edge_prevents_partition_merge(self):
        a,ac=note(start=0,length=1470,uid='a',volumes=((0,15),))
        b,bc=note(start=1470,length=1470,uid='b',volumes=((0,9),))
        a=replace(a,gate_ids=('gate0',));b=replace(b,gate_ids=('gate0',))
        bc += [MusicalControl(1470,'psg',0,'gate',(0,),order=1,unit_id='b',origin='observed_zero_transition'),
               MusicalControl(1470,'psg',0,'gate',(1,),order=2,unit_id='b',origin='observed_zero_transition')]
        _,report=render_blueprint(plan((a,ac),(b,bc)));self.assertEqual(report['sounding_units'],2)

    def test_huc_source_comment_and_free_opll_then_psg(self):
        metadata=(('source_projection',dict(source='huc6280',allocation=[
            dict(source_channel=2,target_chip='scc',target_channel=0)])),)
        others=[note('opll',channel=i,uid=f'o{i}') for i in range(9)]
        text,report=render_blueprint(plan(note('scc'),*others,metadata=metadata))
        row=next(r for r in report['allocations'] if r['unit_id']=='unit')
        self.assertEqual((row['source_chip'],row['source_channel']),('huc6280',2))
        self.assertEqual((row['target_chip'],row['track']),('psg','1'))
        self.assertIn('HUC6280 #1 / wave ch 3',text)

    def test_capacity_splits_without_dropping_parts(self):
        metadata=(('source_projection',dict(source='huc6280',allocation=[
            dict(source_channel=0,target_chip='scc',target_channel=0)])),)
        p=plan(note('scc'),*(note('opll',channel=i,uid=f'o{i}') for i in range(9)),
            *(note('psg',channel=i,uid=f'p{i}') for i in range(3)),metadata=metadata)
        pages=render_blueprints(p);self.assertEqual(len(pages),2)
        self.assertEqual(sum(r['sounding_units'] for _,r in pages),13)

    def test_hardware_and_software_envelopes_are_removed_only_in_template(self):
        unit,controls=note();unit=replace(unit,parameters=(('mode',1),('hardware_envelope',True)))
        controls += [MusicalControl(0,'psg',0,'psg_envelope_enable',(1,),unit_id=unit.unit_id),
                     MusicalControl(0,'psg',None,'psg_envelope_period',(900,)),
                     MusicalControl(0,'psg',None,'psg_envelope_shape',(10,))]
        p=plan((unit,controls));before=asdict(p);text,_=render_blueprint(p)
        self.assertNotRegex(music(text),r'\b[ms]\d+')
        self.assertEqual(re.findall(r'\bv\d+',music(text)),['v15'])
        self.assertEqual(asdict(p),before)

    def test_zero_time_positive_gate_is_not_silently_discarded(self):
        _,report=render_blueprint(plan(note(length=1)))
        self.assertEqual(report['allocations'][0]['step_end'],1)
        self.assertGreater(report['timing_duration_expansion_steps'],0)

    def test_edited_output_and_failed_attempt_preserve_owned_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);good=write_blueprint(plan(note()),root,'song');target=Path(good['path'])
            before=target.read_bytes();failed=write_blueprint(plan(note(length=1)),root,'song')
            self.assertEqual(failed['status'],'success')
            self.assertNotEqual(target.read_bytes(),before)
            self.assertEqual(write_blueprint(plan(note()),root,'song')['status'],'success')
            target.write_text('my score');failed=write_blueprint(plan(note()),root,'song')
            self.assertEqual(failed['status'],'blocked');self.assertIn('edited blueprint',failed['detail'])
            self.assertEqual(target.read_text(),'my score')

    def test_legacy_rhythm_is_a_separate_volume_free_score(self):
        p=plan(note('opll'));p=replace(p,controls=p.controls+tuple(MusicalControl(t,'opll',None,'rhythm_register',v)
            for t,v in ((0,(0x36,5)),(0,(14,48)),(735,(0x36,10)),(1470,(14,32)))))
        before=asdict(p);pages=render_blueprints(p);self.assertEqual(len(pages),2)
        text,report=pages[1]
        self.assertIn('#opll_mode 1',text);self.assertIn('rhythm track f',text)
        self.assertEqual(re.findall(r'\bv(?:[bsmch])?\d+',music(text)),[])
        self.assertEqual(report['sounding_units'],1);self.assertEqual(asdict(p),before)


@unittest.skipUnless(shutil.which('mgsc'),'MGSC required')
class BlueprintPlaybackTests(unittest.TestCase):
    def test_subframe_retriggers_compile_with_explicit_approximation(self):
        p=plan(*(note(start=245*i,length=245,uid=f'n{i}',volumes=((0,10),)) for i in range(3)))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);r=write_blueprint(p,root,'short')
            self.assertEqual(r['status'],'success')
            self.assertEqual(len(r['allocations']),3)
            self.assertEqual([a['step_end']-a['step_start'] for a in r['allocations']],[1,1,1])
            compiled=subprocess.run(['mgsc',r['path'],str(root/'short.mgs')],capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout)

    def test_long_split_compiles_and_score_keeps_full_gate_without_volume_curve(self):
        p=plan(note(length=44100,volumes=((0,15),(14700,9),(29400,3))))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);r=write_blueprint(p,root,'probe')
            compiled=subprocess.run(['mgsc',r['path'],str(root/'probe.mgs')],capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout)
            audition=root/'audition.mml'
            audition.write_text(Path(r['path']).read_text())
            compiled=subprocess.run(['mgsc',str(audition),str(root/'probe.mgs')],capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout)
            if not shutil.which('node'):return
            check=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),'--check'],capture_output=True)
            if check.returncode:return
            rendered=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(root/'probe.mgs'),str(root/'probe.vgm'),'2000'],capture_output=True,timeout=45)
            self.assertEqual(rendered.returncode,0,rendered.stderr)
            raw=read_vgm_bytes(root/'probe.vgm')
            actual=[(e.vgmticks,raw[e.address+2]) for e in command_times(raw) if e.command==0xa0 and raw[e.address+1]==8]
            levels=[(t,v) for t,v in actual if v]
            self.assertTrue(levels)
            self.assertEqual(len(set(v for _,v in levels)),1)
            self.assertLess(abs(actual[-1][0]-levels[0][0]-44100),735)

    def test_unedited_blueprints_play_at_a_fixed_level_on_all_three_chips(self):
        if not shutil.which('node'):self.skipTest('Node required')
        for chip in ('psg','scc','opll'):
            with self.subTest(chip=chip), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);result=write_blueprint(plan(note(chip,length=44100)),root,'audition')
                compiled=subprocess.run(['mgsc',result['path'],str(root/'audition.mgs')],capture_output=True,timeout=30)
                self.assertEqual(compiled.returncode,0,compiled.stdout)
                played=subprocess.run(['node',str(ROOT/'scripts/probe_mgs_audio.mjs'),str(root/'audition.mgs'),
                    str(root/'audio.json'),'2000'],capture_output=True,timeout=45)
                self.assertEqual(played.returncode,0,played.stderr)
                self.assertGreater(json.loads((root/'audio.json').read_text())['peak'],100)

    def test_tiny_opll_retriggers_survive_compilation_and_driver_playback(self):
        if not shutil.which('node'):
            self.skipTest('Node required for libkss')
        check=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),'--check'],capture_output=True)
        if check.returncode:
            self.skipTest('libkss unavailable')
        p=plan(*(note('opll',start=i,length=1,uid=f'n{i}',volumes=()) for i in range(4)))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);r=write_blueprint(p,root,'tiny')
            self.assertEqual(r['status'],'success')
            audition=root/'audition.mml'
            audition.write_text(Path(r['path']).read_text().replace('9 q8 ', '9 q8 v12 ').replace('@0','@1'))
            compiled=subprocess.run(['mgsc',str(audition),str(root/'tiny.mgs')],capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout)
            rendered=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(root/'tiny.mgs'),str(root/'tiny.vgm'),'1000'],capture_output=True,timeout=45)
            self.assertEqual(rendered.returncode,0,rendered.stderr)
            raw=read_vgm_bytes(root/'tiny.vgm')
            keyon=False;attacks=[]
            for event in command_times(raw):
                if event.command==0x51 and raw[event.address+1]==0x20:
                    enabled=bool(raw[event.address+2]&16)
                    if enabled and not keyon:
                        attacks.append(event.vgmticks)
                    keyon=enabled
            self.assertEqual(len(attacks),4)
            self.assertEqual(len(set(attacks)),4)


if __name__=='__main__':unittest.main()
