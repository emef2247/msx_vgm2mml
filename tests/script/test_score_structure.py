"""A source score is a guide, never a replacement for curves or note edges."""
from dataclasses import asdict,replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io
import struct

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(Path(__file__).parent)]
from score_structure import build,map_partitions,partition_key,guided_partition_keys
from native_blueprint import render_native_blueprints
from native_music import NativeDevice,NativePerformance,NativeUnit
from pre_envelope_loops import prepare,LoopFirstEnvelopeBank,ScoreGuidedEnvelopeBank
from curve_projection_validation import repartition
from test_native_blueprint import source
from test_psg_scc_curve_approx import fixture,apply
from test_mml_envelopes import sounding_timeline
import vgm2mml


class ScoreStructureTests(unittest.TestCase):
    def test_source_samples_and_curves_unchanged_and_blueprint_reuses_points(self):
        performance=source();before=asdict(performance)
        guide=build(performance,repeats=True)
        self.assertEqual(asdict(performance),before)
        self.assertEqual(guide.events[0].start_sample,0)
        self.assertEqual(guide.events[0].end_sample,4410)
        self.assertEqual(guide.events[0].articulation,'attack')
        self.assertEqual(render_native_blueprints(performance),
                         render_native_blueprints(performance,score_guide=guide))
        with tempfile.TemporaryDirectory() as temporary:
            guide.dump(temporary,'score')
            data=json.loads((Path(temporary)/'score.score_guide.json').read_text())
            self.assertEqual(data['time_domain'],'original_source_samples')
            self.assertFalse(data['executable'])
            self.assertTrue((Path(temporary)/'score.score_guide.events.csv').exists())

    def test_internal_pitch_phrase_has_hold_events_without_volume_timbre_keys(self):
        performance=source();unit=replace(performance.units[0],end_sample=29400,
            pitch_curve=tuple((i*1470,440 if i%2==0 else 493.883) for i in range(20)))
        performance=replace(performance,units=(unit,),end_sample=29400)
        guide=build(performance,repeats=True)
        self.assertEqual(len(guide.events),20)
        self.assertTrue(all(e.articulation=='hold' for e in guide.events[1:]))
        self.assertTrue(any(p['emitted_repeats']>2 for p in guide.patterns))
        changed=replace(unit,volume_curve=((0,1),),voice_curve=((0,'other'),))
        self.assertEqual([e.key for e in guide.events],
            [e.key for e in build(replace(performance,units=(changed,))).events])

    def test_many_to_many_mapping_does_not_cut_an_accepted_note(self):
        performance=fixture('psg');note=dict(performance.channels)[0][0]
        unit=NativeUnit('u','psg:0','tone',0,0,2940,((0,440),(1470,880)),(),())
        native=NativePerformance((NativeDevice('psg:0','psg',0,1789773),),(unit,),(),(),(),(),2940,'a'*64,'')
        rows=map_partitions(build(native),performance)
        row=next(r for r in rows if r['channel']==0)
        self.assertEqual(row['status'],'many_to_many')
        self.assertEqual(row['internal_guide_cuts'],[1470])
        self.assertFalse(row['executable_cuts_applied'])
        self.assertEqual(dict(performance.channels)[0][0],note)

    def test_source_guide_keys_abstain_on_gaps_overlaps_and_multiple_units(self):
        performance=fixture('psg');device=NativeDevice('psg:0','psg',0,1789773)
        full=NativeUnit('u',device.device_id,'tone',0,0,2940,((0,440),),(),())
        def keys(units):
            native=NativePerformance((device,),tuple(units),(),(),(),(),2940,'a'*64,'')
            return guided_partition_keys(build(native),performance)
        self.assertEqual(keys((full,))[0,0][0],'source_score_candidate')
        for units in ((replace(full,end_sample=735),),
                      (full,replace(full,unit_id='overlap',start_sample=735)),
                      (replace(full,end_sample=1470),replace(full,unit_id='second',start_sample=1470))):
            with self.subTest(units=units):
                self.assertEqual(keys(units)[0,0][0],'exact_unmapped_partition')

    def test_curve_variants_survive_a_shared_score_slot(self):
        performance=fixture();notes=[dict(performance.channels)[i][0] for i in range(2)]
        rows=[replace(notes[i%2],start=i*4,gate_ids=(f'g{i}',)) for i in range(8)]
        plans,reps=prepare({0:rows},'scc',score_guided=True)
        self.assertEqual(len(set(plans[0].guide.keys)),1)
        self.assertEqual({n.runs for n in reps[0]},{n.runs for n in notes})
        self.assertEqual(len(reps[0]),2)
        commands=[f'v{15-i%2} c4' for i in range(8)]
        text,_=plans[0].render(commands)
        self.assertTrue(plans[0].comparison)
        from source_loop_plan import expanded_tokens
        self.assertEqual(expanded_tokens(text),expanded_tokens(' '.join(commands)))

    def test_same_curve_at_different_score_positions_is_counted_separately(self):
        performance=fixture();note=dict(performance.channels)[0][0]
        rows=[replace(note,start=i*4,gate_ids=(str(i),),segment=replace(note.segment,
                     scale='c' if i%2==0 else 'd')) for i in range(8)]
        _,reps=prepare({0:rows},'scc',score_guided=True)
        self.assertEqual(len(reps[0]),2)

    def test_guided_bank_preserves_every_curve_and_incoming_state(self):
        performance=fixture();notes=[dict(performance.channels)[i][0] for i in range(2)]
        rows=tuple(replace(notes[i%2],start=i*4,gate_ids=(str(i),)) for i in range(8))
        performance=replace(performance,channels=((0,rows),))
        with tempfile.TemporaryDirectory() as temporary:
            texts=[]
            for factory in (LoopFirstEnvelopeBank,ScoreGuidedEnvelopeBank):
                path=Path(temporary)/(factory.__name__+'.mml');bank=factory(deferred=True)
                bank.submit(dict(performance.source_segments),'scc',path,raw_ticks=True,performance=performance)
                bank.flush();texts.append(path.read_text())
            self.assertEqual(sounding_timeline(texts[0]),sounding_timeline(texts[1]))

    def test_hardware_envelope_is_not_a_repeat_barrier_or_extra_reset(self):
        from test_psg_scc_performance import psg
        from psg_scc_performance import analyze
        from source_loop_plan import expanded_tokens
        segments={0:[psg(i*4,4,ev_type='evS',volume=0,envelope_enabled=1,
                         amplitude_register=16,envelope_period=100,envelope_shape=10)
                     for i in range(8)]}
        performance=analyze(segments,'psg')
        with tempfile.TemporaryDirectory() as temporary:
            texts=[]
            for factory in (LoopFirstEnvelopeBank,ScoreGuidedEnvelopeBank):
                path=Path(temporary)/(factory.__name__+'.mml');bank=factory(deferred=True)
                bank.submit(segments,'psg',path,raw_ticks=True,performance=performance)
                bank.flush();texts.append(path.read_text())
            bodies=[' '.join(l.split(' ',1)[1] for l in text.splitlines() if l.startswith('1 ')) for text in texts]
            self.assertEqual(expanded_tokens(bodies[0]),expanded_tokens(bodies[1]))
            self.assertEqual(expanded_tokens(bodies[1]).count('s10'),8)
            self.assertIn('[',bodies[1])

    def test_autonomous_hardware_source_keeps_one_shape_write_in_reference(self):
        from vgm_io import read_vgm_bytes
        from vgm_timing import command_times
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);raw=bytearray(256);raw[:4]=b'Vgm '
            for offset,value in ((8,0x171),(0x34,256-0x34),(0x74,1789773)):
                struct.pack_into('<I',raw,offset,value)
            raw.extend(bytes.fromhex('a0 07 3e a0 08 10 a0 0b 64 a0 0c 00 a0 0d 0a'))
            for period in (400,336)*4:
                raw.extend(bytes((0xa0,0,period&255,0xa0,1,period>>8,0x62)))
            raw.extend(bytes.fromhex('a0 08 00 62 66'))
            struct.pack_into('<I',raw,4,len(raw)-4);struct.pack_into('<I',raw,0x18,9*735)
            path=root/'hardware.vgm';path.write_bytes(raw)
            argv=['vgm2mml.py',str(path),'--outdir',str(root/'out'),
                  '--output-format','vgm','--score-guided-loops','--dump-passes']
            with patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                vgm2mml.main()
            output=read_vgm_bytes(root/'out/tracks/hardware.vgm')
            shapes=[output[e.address+2] for e in command_times(output)
                    if e.command==0xa0 and output[e.address+1]==13]
            self.assertEqual(shapes.count(10),1)

    def test_opll_score_guidance_preserves_patch_volume_and_pitch_controls(self):
        from test_opll_inner_loops import OpllInnerLoops
        from opll_target import render
        from structured_macros import expanded
        rows=OpllInnerLoops().rows()
        rows[8].vol=5;rows[9].inst=2;rows[10].fnum+=1
        before=repr(rows)
        old=render({0:rows},raw_ticks=True,source_loops=True,source_strategy='structural')
        new=render({0:rows},raw_ticks=True,source_loops=True,source_strategy='structural',score_guided=True)
        self.assertEqual(expanded(old),expanded(new))
        self.assertEqual(repr(rows),before)

    def test_normalized_opll_score_candidates_keep_every_command(self):
        from test_musical_timing import segment
        from note_normalization import TimingPlan,render_melody
        from source_loop_plan import expanded_tokens
        rows=[]
        for i in range(12):
            rows.extend((segment(i*5512,i*5512+4000,inst=1+i%2,volume=2+i%3),
                         segment(i*5512+4000,(i+1)*5512,key=0,edge=0)))
        plan=TimingPlan(120,12,5512.5,0,1,735)
        old,_,_,_=render_melody({0:rows},None,plan,source_loops=True)
        new,_,_,_=render_melody({0:rows},None,plan,source_loops=True,score_guided=True)
        def body(text):return ' '.join(line.split(' ',1)[1] for line in text.splitlines() if line.startswith('9 '))
        self.assertEqual(expanded_tokens(body(old)),expanded_tokens(body(new)))

    def test_repartition_keeps_approximated_values_at_backend_cuts(self):
        base=fixture();projection=apply(base)
        note=dict(base.channels)[0][0]
        split=(replace(note,length=2,runs=((15,1),(11,1)),segment_indices=(0,1)),
               replace(note,start=2,length=2,runs=((10,1),(6,1)),segment_indices=(2,3)))
        original=replace(base,channels=((0,split),base.channels[1]))
        result=repartition(original,projection.performance)
        self.assertEqual(dict(result.channels)[0][0].runs,((15,1),(10,1)))
        self.assertEqual(dict(result.channels)[0][1].runs,((10,1),(6,1)))
        self.assertIs(result.source_segments,base.source_segments)
        self.assertEqual([n.start for n in dict(result.channels)[0]],[0,2])

    def test_canonical_approximation_and_guide_are_inspectable_before_rendering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);raw=bytearray(256);raw[:4]=b'Vgm '
            struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
            struct.pack_into('<I',raw,0x74,1789773)
            raw.extend(bytes.fromhex('a0 07 3c a0 00 90 a0 01 01 a0 02 90 a0 03 01'))
            for left,right in zip((15,15,11,10,6),(15,15,10,10,6)):
                raw.extend(bytes((0xa0,8,left,0xa0,9,right,0x62)))
            raw.extend(bytes.fromhex('a0 08 00 a0 09 00 62 66'))
            struct.pack_into('<I',raw,4,len(raw)-4);struct.pack_into('<I',raw,0x18,4410)
            path=root/'curves.vgm';path.write_bytes(raw)
            argv=['vgm2mml.py',str(path),'--outdir',str(root/'out'),'--dump-passes',
                  '--software-volume-curves','--score-guided-loops','--psg-state-ms','24',
                  '--curve-volume-error','1','--curve-mean-error','0.25']
            with patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                vgm2mml.main()
            out=root/'out'
            summary=json.loads((out/'curves.psg.curve_approx.json').read_text())
            self.assertEqual(summary['replaced_notes'],1)
            self.assertTrue((out/'curves.score_guide.events.csv').is_file())
            self.assertTrue((out/'curves.psg.score_guide.mapping.json').is_file())
            self.assertTrue((out/'curves.psg.score_guide.loops.json').is_file())
            report=json.loads((out/'curves.conversion.json').read_text())
            self.assertEqual(report['direct_vgm']['status'],'success')
            self.assertEqual(report['blueprint']['status'],'success')
            self.assertEqual(path.read_bytes(),bytes(raw))
            from musical_timing import AcceptedTimingMapper
            from note_normalization import TimingPlan
            normalized=AcceptedTimingMapper(plan=TimingPlan(225,3,735,0,1,352),report=dict(applied=True))
            argv[argv.index(str(out))]=str(root/'normalized')
            argv+=['--normalization-ms','8']
            with patch.object(sys,'argv',argv),patch('musical_timing.choose_timing',return_value=normalized),contextlib.redirect_stdout(io.StringIO()):
                vgm2mml.main()
            summary=json.loads((root/'normalized/curves.psg.curve_approx.json').read_text())
            self.assertEqual(summary['status'],'abstained')
            self.assertEqual(summary['replaced_notes'],0)
            self.assertFalse(summary['lossy'])


if __name__=='__main__':unittest.main()
