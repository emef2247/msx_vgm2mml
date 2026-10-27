"""Source-native score projection: identities, full parts and legal placeholders."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'py'))
from native_music import NativeDevice,NativePerformance,NativeUnit,NativeVoice
from native_blueprint import NativeBlueprintError,render_native_blueprints
from musical_blueprint import write_blueprint,render_blueprints
from mml_sync import analyze_mml


def source(count=1,voices=False):
    devices=(NativeDevice('opm:0','opm',0,4000000),NativeDevice('opm:1','opm',1,4000000))
    units=[];instruments={}
    for i in range(count):
        device=devices[(i//8)%2].device_id if not voices else devices[0].device_id
        channel=i%8 if not voices else 0
        voice=f'{device}:voice:{i}'
        instruments[voice]=NativeVoice(voice,device,'fm',(('algorithm',i%8),))
        start=4410*i if voices else 0
        units.append(NativeUnit(f'u{i}',device,'fm',channel,start,start+4410,
            ((start,440.0),(start+1470,441.0)),((start,15),(start+1470,9),(start+2940,3)),
            ((start,voice),)))
    return NativePerformance(devices,tuple(units),(),tuple(instruments.values()),(),(),
        max(u.end_sample for u in units),'a'*64,'')


def holder(performance,metadata=()):
    return SimpleNamespace(source_performance=performance,metadata=metadata)


class NativeBlueprintTests(unittest.TestCase):
    def test_source_information_is_not_modified_and_volume_pitch_jitter_does_not_split(self):
        performance=source();before=asdict(performance);pages=render_native_blueprints(performance)
        text,report=pages[0];body=report['allocations'][0]['mml']
        self.assertEqual(asdict(performance),before)
        self.assertNotIn('&',body);self.assertNotRegex(body,r'\bv\d+')
        self.assertEqual(re.findall(r'\bv\d+',text),['v15','v15'])  # comment and one track initializer
        self.assertEqual(report['sounding_units'],1)
        self.assertIn('OPM #1 / fm ch 1',text)

    def test_timbres_are_documentary_and_do_not_change_score(self):
        performance=source(count=2,voices=True);text,report=render_native_blueprints(performance)[0]
        self.assertEqual([r['comment_number'] for r in report['voice_mapping']],[1,2])
        code='\n'.join(line.split(';')[0] for line in text.splitlines())
        self.assertEqual(re.findall(r'@\d+',code),['@1'])
        self.assertIn('Timbre 1: source voice',text)
        self.assertIn('Timbre 2: source voice',text)
        self.assertTrue(any(r['emitted_repeats']>=2 for r in report['loops']))

    def test_many_source_parts_split_without_omission(self):
        performance=source(16);pages=render_native_blueprints(performance)
        self.assertEqual(len(pages),2)
        actual=[r['unit_id'] for _,report in pages for r in report['allocations']]
        self.assertEqual(sorted(actual),sorted(u.unit_id for u in performance.units))
        self.assertEqual(len(actual),len(set(actual)))
        self.assertTrue(all(r['omitted_units']==0 for _,r in pages))
        for text,_ in pages:
            tracks,_,_=analyze_mml(text)
            self.assertTrue(all(nodes[0].start==0 for nodes in tracks.values()))

    def test_many_documented_timbres_share_one_structured_score(self):
        performance=source(20,voices=True);pages=render_native_blueprints(performance)
        self.assertEqual(len(pages),1)
        self.assertEqual(sum(r['sounding_units'] for _,r in pages),20)
        self.assertEqual(len(pages[0][1]['voice_mapping']),20)
        text,report=pages[0];tracks,_,_=analyze_mml(text)
        self.assertEqual(tracks['9'][0].start,0)
        self.assertEqual(min(r['step_start'] for r in report['allocations']),0)
        self.assertTrue(any(r['emitted_repeats']==20 for r in report['loops']))
        self.assertEqual(re.findall(r'@\d+','\n'.join(line.split(';')[0] for line in text.splitlines())),['@1'])

    def test_pitch_phrase_repeats_inside_one_held_gate(self):
        performance=source()
        unit=replace(performance.units[0],end_sample=44100,
            pitch_curve=tuple((i*1470,440.0 if i%2==0 else 493.883) for i in range(30)))
        performance=replace(performance,units=(unit,),end_sample=44100)
        text,report=render_native_blueprints(performance)[0]
        self.assertEqual(report['sounding_units'],1)
        self.assertTrue(any(row['emitted_repeats']>2 for row in report['loops']))
        self.assertEqual(report['allocations'][0]['score_atom_end'],30)
        self.assertIn('[',text)

    def test_same_instrument_simultaneous_rhythm_edges_use_separate_pages(self):
        from native_music import NativePercussion
        performance=source()
        device=NativeDevice('opll:0','opll',0,3579545)
        hits=tuple(NativePercussion(f'h{i}',device.device_id,'0','BD',0) for i in range(2))
        performance=replace(performance,devices=(device,),units=(),voices=(),percussion=hits,end_sample=735)
        pages=render_native_blueprints(performance)
        self.assertEqual(len(pages),2)
        self.assertEqual(sum(r['sounding_units'] for _,r in pages),2)

    def test_excessive_voice_changes_inside_held_gate_remain_documentary(self):
        performance=source();unit=replace(performance.units[0],end_sample=44100,
            voice_curve=tuple((i*1470,f'v{i}') for i in range(16)))
        performance=replace(performance,units=(unit,),end_sample=44100)
        before=asdict(performance)
        text,report=render_native_blueprints(performance)[0]
        self.assertEqual(len(report['allocations']),1)
        self.assertEqual(len(report['removed_internal_timbres']),15)
        self.assertNotIn('&',report['allocations'][0]['mml'])
        self.assertEqual(len(report['timing_rounding']),2)
        self.assertIn('internal timbre (removed): source voice v15',text)
        self.assertEqual(asdict(performance),before)

    def test_terminal_rhythm_attack_has_shared_explicit_target_tail(self):
        from native_music import NativePercussion
        performance=source()
        device=NativeDevice('opll:0','opll',0,3579545)
        performance=replace(performance,devices=performance.devices+(device,),
            percussion=(NativePercussion('last',device.device_id,'0','BD',performance.end_sample),))
        before=asdict(performance)
        pages=render_native_blueprints(performance)
        self.assertEqual(len(pages),2)
        for _,report in pages:
            self.assertEqual(report['timing_terminal_tail_steps'],1)
            self.assertEqual(report['terminal_rhythm_attacks'],['last'])
        self.assertIn('b%1',pages[1][0])
        self.assertEqual(asdict(performance),before)

    def test_rhythm_stop_uses_shared_expanded_clock(self):
        from native_music import NativePercussion
        performance=source();base=performance.units[0]
        units=tuple(replace(base,unit_id=f'u{i}',start_sample=i,end_sample=i+1,
                            pitch_curve=((i,440),)) for i in range(3))
        device=NativeDevice('opll:0','opll',0,3579545)
        performance=replace(performance,devices=performance.devices+(device,),units=units,end_sample=4,
            percussion=(NativePercussion('hit',device.device_id,'0','BD',2,3),))
        _,report=render_native_blueprints(performance)[-1]
        row=report['allocations'][0]
        self.assertGreater(row['step_end'],row['step_start'])
        clock={r['sample']:r['step'] for r in report['timing_rounding']}
        self.assertEqual(row['step_end'],clock[3])

    def test_unmapped_native_percussion_is_documented_without_dropping_melody(self):
        from native_music import NativePercussion
        performance=source();device=NativeDevice('opna:0','opna',0,8000000)
        hit=NativePercussion('opna-drum',device.device_id,'5','RIM',0)
        performance=replace(performance,devices=performance.devices+(device,),percussion=(hit,))
        text,report=render_native_blueprints(performance)[0]
        self.assertEqual(report['sounding_units'],1)
        self.assertEqual(report['excluded_percussion'][0]['event_id'],'opna-drum')
        self.assertIn('Unmapped percussion:',text)
        self.assertIn('no_blueprint_rhythm_mapping',text)

    def test_tiny_repeated_overlap_and_mixed_parts_share_legal_clock(self):
        performance=source()
        base=performance.units[0]
        units=(replace(base,unit_id='a',end_sample=1,pitch_curve=((0,440),)),
               replace(base,unit_id='b',start_sample=1,end_sample=2,pitch_curve=((1,440),)),
               replace(base,unit_id='overlap',start_sample=0,end_sample=2,pitch_curve=((0,440),)),
               replace(base,unit_id='mixed',channel=1,start_sample=1,end_sample=3,
                       pitch_curve=((1,440),(2,880))))
        performance=replace(performance,units=units,end_sample=3)
        before=asdict(performance)
        pages=render_native_blueprints(performance)
        rows=[row for _,report in pages for row in report['allocations']]
        self.assertEqual({r['unit_id'] for r in rows},{u.unit_id for u in units})
        clock={r['sample']:r['step'] for r in pages[0][1]['timing_rounding']}
        self.assertEqual(clock,{0:0,1:1,2:2,3:3})
        for row in rows:
            self.assertEqual(row['step_start'],clock[row['sample_start']])
            self.assertGreater(row['step_end'],row['step_start'])
        self.assertNotIn('&',next(r['mml'] for r in rows if r['unit_id']=='b'))
        self.assertEqual(asdict(performance),before)

    def test_close_cross_part_boundaries_do_not_serialize_independent_parts(self):
        performance=source();base=performance.units[0]
        units=tuple(replace(base,unit_id=f'u{i}',channel=i,start_sample=i,end_sample=4410+i,
                            pitch_curve=((i,440),)) for i in range(8))
        _,report=render_native_blueprints(replace(performance,units=units,end_sample=4417))[0]
        self.assertEqual({r['step_start'] for r in report['allocations'] if r['sample_start']}, {1})
        self.assertLessEqual(report['timing_duration_expansion_steps'],1)

    def test_pitch_fold_and_full_voice_parameters_are_explicit(self):
        performance=source();base=performance.units[0]
        unit=replace(base,pitch_curve=((0,0.001),))
        voice=replace(performance.voices[0],parameters=(('algorithm',3),('waveform_hex','00ff'),('operators',((1,2),(3,4)))))
        text,report=render_native_blueprints(replace(performance,units=(unit,),voices=(voice,)))[0]
        self.assertIn('"waveform_hex": "00ff"',text)
        self.assertIn('"operators": [[1, 2], [3, 4]]',text)
        self.assertEqual(report['pitch_placeholders'][0]['reason'],'octave_fold')

    def test_source_instance_and_channel_comments_are_unambiguous(self):
        performance=source();unit=replace(performance.units[0],device_id='opm:1',channel=3)
        performance=replace(performance,units=(unit,))
        text,report=render_native_blueprints(performance)[0]
        self.assertIn('OPM #2 / fm ch 4',text)
        self.assertEqual(report['allocations'][0]['source_instance'],1)
        self.assertEqual(report['allocations'][0]['source_channel'],3)

    def test_pcm_has_no_blueprint_or_wave_asset(self):
        device=NativeDevice('pcm:0','msm6258',0,4000000)
        performance=source();unit=replace(performance.units[0],device_id=device.device_id,section='pcm',role='pcm')
        performance=replace(performance,devices=(device,),units=(unit,),voices=())
        self.assertEqual(render_native_blueprints(performance),[])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);report=write_blueprint(holder(performance),root,'pcm')
            self.assertEqual(report['status'],'not_applicable')
            self.assertFalse(list(root.rglob('*.mml')));self.assertFalse(list(root.rglob('*.wav')))

    def test_pcm_mixed_with_melody_is_excluded_only_from_score(self):
        performance=source();device=NativeDevice('pcm:0','c140',0,8000000)
        unit=replace(performance.units[0],unit_id='pcm',device_id=device.device_id,section='pcm',role='pcm')
        performance=replace(performance,devices=performance.devices+(device,),units=performance.units+(unit,))
        before=asdict(performance);_,report=render_native_blueprints(performance)[0]
        self.assertEqual(report['sounding_units'],1)
        self.assertEqual(report['excluded_units'],[dict(unit_id='pcm',reason='pcm')])
        self.assertEqual(asdict(performance),before)

    def test_percussive_fm_role_does_not_discard_a_source_part(self):
        performance=source();unit=replace(performance.units[0],role='percussion')
        _,report=render_native_blueprints(replace(performance,units=(unit,)))[0]
        self.assertEqual(report['sounding_units'],1)
        self.assertEqual(report['excluded_units'],[])

    def test_split_file_ownership_protects_every_page_and_allows_owned_stale_cleanup(self):
        performance=source(16)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);report=write_blueprint(holder(performance),root,'score')
            self.assertEqual(report['status'],'success');self.assertEqual(len(report['files']),2)
            first,second=map(lambda f:Path(f['path']),report['files'])
            self.assertEqual((first.name,second.name),('score.mml','score.part02.mml'))
            before=first.read_bytes();second.write_text('user edited second page')
            blocked=write_blueprint(holder(performance),root,'score')
            self.assertEqual(blocked['status'],'blocked');self.assertEqual(first.read_bytes(),before)
            self.assertEqual(second.read_text(),'user edited second page')
            second.write_bytes(render_native_blueprints(performance)[1][0].encode())
            simple=replace(performance,units=performance.units[:1])
            report=write_blueprint(holder(simple),root,'score')
            self.assertEqual(report['status'],'success');self.assertEqual(len(report['files']),1)
            self.assertFalse(second.exists())

    def test_huc_projection_alias_changes_only_blueprint_identity(self):
        device=NativeDevice('scc:0','scc',0,1789773)
        performance=source();unit=replace(performance.units[0],device_id=device.device_id,section='wave')
        performance=replace(performance,devices=(device,),units=(unit,),voices=())
        before=asdict(performance)
        metadata=(('source_projection',dict(source='huc6280',allocation=[
            dict(source_channel=4,target_chip='scc',target_channel=0)])),)
        text,report=render_blueprints(holder(performance,metadata))[0]
        self.assertIn('HUC6280 #1 / wave ch 5',text)
        self.assertEqual(report['allocations'][0]['target_chip'],'opll')
        self.assertEqual(asdict(performance),before)

    def test_corrupt_ownership_cannot_delete_an_unrelated_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);foreign=root/'personal.mml';foreign.write_text('my score')
            import hashlib
            (root/'score.blueprint.json').write_text(json.dumps(dict(files=[dict(path=str(foreign),
                sha256=hashlib.sha256(foreign.read_bytes()).hexdigest())])))
            report=write_blueprint(holder(source()),root,'score')
            self.assertEqual(report['status'],'blocked')
            self.assertIn('Invalid blueprint ownership',report['detail'])
            self.assertEqual(foreign.read_text(),'my score')
            self.assertFalse((root/'blueprint/score.mml').exists())

    def test_invalid_ownership_shapes_do_not_escape_failure_isolation(self):
        for value in ([],dict(files=['invalid']),dict(files=[dict(path=7,sha256='bad')])):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);(root/'blueprint').mkdir();target=root/'blueprint/score.mml'
                target.write_text('unowned score');(root/'score.blueprint.json').write_text(json.dumps(value))
                report=write_blueprint(holder(source()),root,'score')
                self.assertEqual(report['status'],'blocked')
                self.assertEqual(target.read_text(),'unowned score')

    @unittest.skipUnless(shutil.which('mgsc'),'MGSC required')
    def test_tiny_mixed_overlap_and_folded_pitch_score_compiles(self):
        performance=source();base=performance.units[0]
        units=tuple(replace(base,unit_id=f'tiny{i}',start_sample=i,end_sample=i+1,
                            pitch_curve=((i,440),)) for i in range(4))
        units+=(replace(base,unit_id='held',end_sample=4,pitch_curve=((0,0.001),(2,880))),
                replace(base,unit_id='other',channel=1,end_sample=4,pitch_curve=((0,660),)))
        performance=replace(performance,units=units,end_sample=4)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);report=write_blueprint(holder(performance),root,'tiny')
            self.assertEqual(report['status'],'success')
            self.assertEqual(report['sounding_units'],6)
            self.assertGreater(report['timing_duration_expansion_steps'],0)
            for row in report['files']:
                mml=Path(row['path'])
                result=subprocess.run(['mgsc',str(mml),str(mml.with_suffix('.mgs'))],capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout)

    @unittest.skipUnless(shutil.which('mgsc'),'MGSC required')
    def test_every_split_page_compiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);report=write_blueprint(holder(source(16)),root,'score')
            self.assertEqual(report['status'],'success')
            for row in report['files']:
                mml=Path(row['path']);result=subprocess.run(['mgsc',str(mml),str(mml.with_suffix('.mgs'))],capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout)


if __name__=='__main__':unittest.main()
