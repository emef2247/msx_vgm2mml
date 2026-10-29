"""Per-device timing projection with exact source evidence and executable views."""
from dataclasses import asdict,replace
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts')]
from native_music import NativeDevice,NativeControl,NativeUnit,NativePerformance,NativePercussion,NativePacket
from score_normalization import normalize,score_tempo


def unit(device,channel,start,stop,index=0):
    return NativeUnit(f'{device}:{channel}:{index}',device,'tone',channel,start,stop,
        ((start,440.0),),((start,15),))


def performance(units,controls=(),percussion=(),packets=(),end=10000):
    identities=sorted({u.device_id for u in units}|{c.device_id for c in controls}|{e.device_id for e in percussion})
    devices=tuple(NativeDevice(identity,identity.split(':')[0],int(identity.split(':')[1]),1789773) for identity in identities)
    return NativePerformance(devices,tuple(units),tuple(controls),(),tuple(percussion),tuple(packets),end,'source-hash','')


def make_psg():
    write=lambda r,v:bytes((0xa0,r,v))
    wait=lambda n:b'\x61'+struct.pack('<H',n)
    body=write(7,63)+write(0,170)+write(1,1)+write(8,15)+wait(1000)
    body+=write(7,62)+wait(2000)+write(7,63)+wait(2000)+write(7,62)+wait(1000)+write(7,63)+wait(1000)+b'\x66'
    raw=bytearray(256);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
    struct.pack_into('<I',raw,0x74,1789773)
    raw.extend(body);struct.pack_into('<I',raw,4,len(raw)-4)
    return bytes(raw)


class ScoreTiming(unittest.TestCase):
    def test_score_durations_floor_original_samples_without_frame_or_epsilon_rounding(self):
        from score_normalization import ScoreTiming as Clock
        self.assertEqual(Clock().span(0,734),(0,0))
        self.assertEqual(Clock().span(700,800),(0,0))
        self.assertEqual(Clock().span(1000,3000),(3,9))
        self.assertEqual(Clock(127).span(0,1302),(0,0))
        self.assertEqual(Clock(127).span(0,1303),(0,3))

    def test_abstained_device_only_receives_final_mml_step_projection(self):
        from score_normalization import timing_for_chip
        report=normalize(performance([unit('psg:0',0,0,900),unit('opm:0',0,0,900)]),source_loop=True).report
        self.assertFalse(timing_for_chip(report,'psg').quantize)
        self.assertEqual(timing_for_chip(report,'psg').span(0,900),(0,4))
    def test_same_device_channels_share_quiet_end_anchor(self):
        source=performance([unit('psg:0',0,1000,3000),unit('psg:0',1,1500,2800),
                            unit('psg:0',0,5000,6000,1),unit('psg:0',1,5000,6200,1)])
        before=asdict(source);result=normalize(source)
        row=next(a for a in result.anchors if a['source_end']==5000)
        self.assertTrue(row['applied']);self.assertEqual(row['evidence'],'score_gate_quiet')
        self.assertEqual(row['projected_anchor'],5145)
        self.assertGreater(row['compensation_samples'],0)
        starts=[u.start_sample for u in result.performance.units if u.unit_id.endswith(':1')]
        self.assertEqual(starts,[5145,5145]);self.assertEqual(asdict(source),before)

    def test_different_devices_and_identical_chip_instances_are_independent(self):
        original=performance([unit('opm:0',0,1000,3000),unit('opm:0',0,5000,6000,1)])
        added=replace(original,devices=original.devices+(NativeDevice('opm:1','opm',1,3579545),),
                      units=original.units+tuple(unit('opm:1',i%8,101*i,101*i+89,i) for i in range(30)))
        a,b=normalize(original),normalize(added)
        self.assertEqual([a.clocks['opm:0'].position(t) for t in range(10000)],
                         [b.clocks['opm:0'].position(t) for t in range(10000)])
        self.assertEqual(b.report['devices'][1]['status'],'applied')

    def test_collapsed_instantaneous_groups_keep_all_controls_and_order(self):
        controls=tuple(NativeControl(str(i),'psg:0','shared',None,t,i,kind,())
                       for i,(t,kind) in enumerate(((900,'mixer'),(901,'envelope'),(902,'wave'),(902,'off'),(902,'on'))))
        result=normalize(performance([unit('psg:0',0,0,4000)],controls))
        self.assertEqual([c.kind for c in result.performance.controls],[c.kind for c in controls])
        self.assertEqual([c.sample for c in result.performance.controls],[735]*5)
        self.assertEqual(result.report['collapsed_control_groups'],1)

    def test_unknown_rhythm_and_pcm_do_not_supply_false_quiet_windows(self):
        rhythm=NativePercussion('beat','opll:0','BD','BD',1000)
        pcm=NativePacket('pcm',2000,0,'','opna','adpcm_b_register')
        source=performance([unit('opll:0',0,0,100),unit('opna:0',0,0,100)],
                           percussion=(rhythm,),packets=(pcm,))
        result=normalize(source)
        self.assertEqual({d['reason'] for d in result.report['devices']},
                         {'unknown_percussion_stop','opaque_pcm_or_stream_dependencies'})
        self.assertFalse(result.anchors)

    def test_csm_after_an_ordinary_gate_prevents_false_quiet_anchors(self):
        for chip,kind,parameters in (('opm','opm_timer_control',(('timer_flags',128),)),
                                     ('opna','opna_mode',(('csm',1),))):
            with self.subTest(chip=chip):
                device=chip+':0'
                csm=NativeControl('csm',device,'shared',None,5000,0,kind,parameters)
                source=performance([unit(device,0,1000,2000)],(csm,))
                result=normalize(source)
                self.assertEqual(result.report['devices'][0]['reason'],'unmodeled_csm_timer_generated_gates')
                self.assertEqual(result.performance.controls,source.controls)
                self.assertFalse(result.anchors)

    def test_no_silence_does_not_require_an_anchor_or_accumulate_error(self):
        result=normalize(performance([unit('scc:0',0,0,10000)]))
        clock=result.clocks['scc:0']
        self.assertFalse(result.anchors)
        self.assertLess(max(t-clock.position(t) for t in range(10000)),735)
        self.assertEqual(clock.position(10000),10000)

    def test_short_gate_is_reported_as_collapsed_not_redefined_as_a_control(self):
        result=normalize(performance([unit('opm:0',0,0,100)]))
        self.assertTrue(result.intervals[0]['collapsed'])
        self.assertEqual(result.intervals[0]['source_end'],100)

    def test_grid_straddling_short_gate_is_explicitly_retained_under_sync_priority(self):
        result=normalize(performance([unit('opm:0',0,0,4000),unit('opm:0',1,700,800)]))
        short=result.intervals[1]
        self.assertEqual((short['projected_start'],short['projected_end']),(0,735))
        self.assertEqual(result.report['devices'][0]['sub_quantum_units_retained'],1)
        self.assertIn('lengthening',result.report['quantization_priority'])

    def test_fractional_grid_is_monotone_and_bounded_between_many_epochs(self):
        units=[unit('opm:0',0,1000+i*5000,3000+i*5000,i) for i in range(100)]
        result=normalize(performance(units,end=501000),tempo=127)
        clock=result.clocks['opm:0'];points=[clock.position(t) for t in range(0,501001,73)]
        self.assertEqual(points,sorted(points))
        self.assertLessEqual(max(abs(clock.position(t)-t) for t in range(0,501001,73)),math.ceil(Fraction(3,2)*clock.quantum)+1)
        self.assertEqual(clock.position(501000),501000)

    def test_source_loop_explicitly_abstains_and_secondary_psg_coverage_is_protected(self):
        source=performance([unit('psg:1',0,1000,3000)])
        self.assertEqual(normalize(source).report['devices'][0]['reason'],'dual_instance_gate_coverage_not_proven')
        self.assertEqual(normalize(source,source_loop=True).report['devices'][0]['reason'],
                         'source_song_loop_requires_shared_boundary_validation')

    def test_all_analyzed_gate_families_use_the_same_generic_rule(self):
        for chip in ('psg','scc','opll','opm','opna','dcsg','huc6280'):
            with self.subTest(chip=chip):
                result=normalize(performance([unit(chip+':0',0,1000,3000)]))
                self.assertEqual(result.report['devices'][0]['status'],'applied')

    def test_configuration_validation_and_frontend_forwarding(self):
        from mgs_conversion_config import MgsOptions
        options=MgsOptions(score_normalize=True,score_tempo=127,normalization_ms=8,fm_state_ms=24)
        self.assertFalse(options.enabled)
        self.assertIn('--score-normalize',options.cli_args())
        with self.assertRaises(ValueError):MgsOptions(normalize_lengths=True,score_normalize=True)
        for value in (0,256,'nan',150.5):
            with self.assertRaises(ValueError):score_tempo(value)


class ScoreIntegration(unittest.TestCase):
    def test_rest_crossing_an_anchor_ends_at_the_next_synchronized_onset(self):
        from score_normalization import timing_for_chip
        from test_psg_scc_performance import scc
        from psg_scc_performance import analyze
        from mml_envelopes import render,EnvelopeBank
        from mml_sync import analyze_mml,_leaves
        native=performance([unit('scc:0',0,1845,2940),unit('scc:0',1,4035,6000),
                            unit('scc:0',0,4557,6500,1)],end=7000)
        clock=timing_for_chip(normalize(native).report,'scc')
        self.assertEqual(clock.position(4557),15)
        self.assertEqual(clock.span(2940,4557,rest=True),(12,15))
        rows=[scc(1845,1095,vgmticks=1845,vgmticks_end=2940),
              scc(2940,1617,volume=0,enabled=0,vgmticks=2940,vgmticks_end=4557),
              scc(4557,1943,vgmticks=4557,vgmticks_end=6500)]
        text=render({0:rows},'scc',EnvelopeBank(),performance=analyze({0:rows},'scc',tick_clock_hz=44100),score_timing=clock)
        timed=[n for n in _leaves(analyze_mml(text)[0]['4']) if n.end>n.start and not n.text.startswith('r')]
        self.assertEqual([n.start for n in timed],[9,15])

    def test_collapsed_psg_scc_partitions_do_not_duplicate_a_leading_rest(self):
        from test_psg_scc_performance import scc
        from psg_scc_performance import analyze
        from mml_envelopes import render,EnvelopeBank
        from score_normalization import ScoreTiming as Clock
        from mml_sync import analyze_mml,_leaves
        rows=[scc(1470,30,vgmticks=1470,vgmticks_end=1500),
              scc(1500,705,volume=0,enabled=0,vgmticks=1500,vgmticks_end=2205),
              scc(2205,1470,vgmticks=2205,vgmticks_end=3675)]
        text=render({0:rows},'scc',EnvelopeBank(),performance=analyze({0:rows},'scc',tick_clock_hz=44100),score_timing=Clock())
        timed=[n for n in _leaves(analyze_mml(text)[0]['4']) if n.end>n.start]
        self.assertEqual([(n.start,n.end) for n in timed if not n.text.startswith('r')],[(9,15)])
        self.assertEqual(sum(n.end-n.start for n in timed if n.text.startswith('r')),9)

    def test_blueprint_internal_pitch_never_exceeds_the_truncated_gate(self):
        from native_blueprint import render_native_blueprints
        u=replace(unit('scc:0',0,700,1500),pitch_curve=((700,440.0),(1475,493.883)))
        source=performance([u],end=2205)
        report=normalize(source).report
        rendered=render_native_blueprints(source,tempo=225,note_values=True,sync_report=report)[0]
        self.assertEqual(rendered[1]['allocations'][0]['step_end'],3)
        from mml_sync import analyze_mml,_leaves
        notes=[n for n in _leaves(analyze_mml(rendered[0])[0]['4']) if n.end>n.start and not n.text.startswith('r')]
        self.assertTrue(notes)
        self.assertEqual(max(n.end for n in notes),3)

    def test_psg_selection_preserves_sample_clock_and_driver_envelope_units(self):
        from musical_conversion import build_plan
        from mml_envelopes import frame_curve
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'psg.vgm';source.write_bytes(make_psg())
            sink={}
            build_plan(source,root/'out',score_normalize=True,psg_part='melody',decision_sink=sink)
            psg=next(p for p in sink['performances'] if p.chip=='psg')
            self.assertEqual(psg.tick_clock_hz,44100)
            self.assertEqual(frame_curve(((15,735),(12,1470)),psg.tick_clock_hz),((15,1),(12,2)))

    def test_internal_opll_updates_do_not_delete_a_complete_sounding_unit(self):
        from types import SimpleNamespace
        from opll_target import render
        from score_normalization import ScoreTiming as Clock
        from test_opll_target import segment
        rows=[segment(0,tick_end=700,keyon=1,fnum=290,vol=0),
              segment(700,tick_end=1400,keyon=1,fnum=290,vol=1),
              segment(1400,tick_end=2100,keyon=1,fnum=290,vol=2)]
        for row in rows:
            row.inst=1;row.block=3;row.sus=0;row.is_ryt=0
        result=render({0:rows},num_channels=1,score_timing=Clock())
        from mml_sync import analyze_mml
        timed=analyze_mml(result)[0]['9']
        self.assertEqual(max(token.end for token in timed),6)

    def test_opll_first_frame_gate_and_patch_lookup_share_the_target_clock(self):
        import csv
        from musical_conversion import build_plan
        write=lambda r,v:bytes((0x51,r,v))
        wait=lambda n:b'\x61'+struct.pack('<H',n)
        raw=bytearray(256);raw[:4]=b'Vgm '
        struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
        struct.pack_into('<I',raw,0x10,3579545)
        patch=(0x21,0x21,0x18,0x06,0xf0,0xf0,0x0f,0x0f)
        raw.extend(write(0x30,0x10)+write(0x10,170)+write(0x20,0x18)+wait(735)+
                   write(0x20,0x08)+wait(735)+
                   b''.join(write(r,v) for r,v in enumerate(patch))+write(0x30,0)+
                   write(0x20,0x18)+wait(1470)+write(0x20,0x08)+wait(735)+b'\x66')
        struct.pack_into('<I',raw,4,len(raw)-4)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'opll.vgm';source.write_bytes(raw)
            sink={}
            plan,report=build_plan(source,root/'out',score_normalize=True,decision_sink=sink)
            self.assertNotIn('mgs_projection_error',report)
            rows=sink['opll_source_segments'][0]
            self.assertTrue(any(s.keyon and s.tick_start==0 and s.tick_end==735 for s in rows))
            self.assertTrue(any(s.keyon and s.inst==0 and s.tick_start==1470 and s.tick_end==2940 for s in rows))
            voice_path=next((root/'out/_score_normalized').glob('*voice*.csv'))
            with voice_path.open(newline='') as stream:
                voices=list(csv.DictReader(stream))
            self.assertTrue(any(int(r['ticks'])==1470 and int(r['vgmticks'])==1470 for r in voices))
            # The accepted lowerer, not only the native reference view, retained the gate.
            accepted=sink['legacy_execution_plan']
            self.assertTrue(any(u.start_sample==0 and u.end_sample==735 for u in accepted.units if u.chip=='opll'))

    def test_normalized_native_fm_instances_keep_ordered_register_evidence(self):
        from musical_conversion import build_plan
        from native_registers import encode_control
        write=lambda cmd,r,v:bytes((cmd,r,v))
        wait=lambda n:b'\x61'+struct.pack('<H',n)
        raw=bytearray(256);raw[:4]=b'Vgm '
        struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
        struct.pack_into('<I',raw,0x30,4000000|0x40000000)
        raw.extend(write(0x54,0x28,0x4c)+write(0xa4,0x28,0x5c)+wait(1000)+
            write(0x54,8,0x78)+wait(900)+write(0xa4,8,0x78)+wait(800)+
            write(0x54,8,0)+wait(300)+write(0xa4,8,0)+wait(1000)+b'\x66')
        struct.pack_into('<I',raw,4,len(raw)-4)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'fm.vgm';source.write_bytes(raw)
            plan,report=build_plan(source,root/'out',score_normalize=True)
            self.assertEqual(len(report['score_normalization']['devices']),2)
            self.assertTrue(all(d['status']=='applied' for d in report['score_normalization']['devices']))
            original=json.loads((root/'out/fm.native_music.json').read_text())
            for device in plan.source_performance.devices:
                expected=[c['parameters'] for c in original['controls'] if c['device_id']==device.device_id]
                actual=[json.loads(json.dumps(c.parameters)) for c in plan.source_performance.controls if c.device_id==device.device_id]
                self.assertEqual(actual,expected)

    def test_blueprint_clock_does_not_couple_independent_devices(self):
        from native_blueprint import render_native_blueprints
        source=performance([unit('psg:0',0,1000,2000)],end=4000)
        base=render_native_blueprints(source)[0][1]['allocations'][0]
        mixed=replace(source,devices=source.devices+(NativeDevice('scc:0','scc',0,1789773),),
            units=source.units+tuple(unit('scc:0',0,i,i+1,i) for i in range(10)))
        rows=render_native_blueprints(mixed)[0][1]['allocations']
        actual=next(row for row in rows if row['unit_id']==base['unit_id'])
        self.assertEqual((actual['step_start'],actual['step_end']),(base['step_start'],base['step_end']))

    def test_cli_keeps_native_source_and_reimports_projected_state_for_all_outputs(self):
        from vgm_io import read_vgm_bytes
        from vgm_timing import command_times
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'song.vgm';raw=make_psg();source.write_bytes(raw)
            out=root/'out'
            command=[sys.executable,str(ROOT/'vgm2mml.py'),str(source),'--outdir',str(out),
                     '--score-normalize','--software-volume-curves','--dump-passes']
            result=subprocess.run(command,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode(errors='replace')[-2500:])
            original=json.loads((out/'song.native_music.json').read_text())
            projected=json.loads((out/'_score_normalized/reference/song.native_music.json').read_text())
            score_source=json.loads((out/'_score_normalized/song.native_music.json').read_text())
            self.assertEqual(original['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertNotEqual(original['source_sha256'],projected['source_sha256'])
            self.assertEqual(original['source_sha256'],score_source['source_sha256'])
            self.assertEqual(source.read_bytes(),raw)
            report=json.loads((out/'song.score_normalization.json').read_text())
            self.assertEqual(report['reference_tempo'],225)
            self.assertTrue((out/'native_legacy/song.psg.segments.csv').is_file())
            self.assertTrue((out/'song.mml').is_file())
            self.assertIn('#tempo 225',(out/'blueprint/song.mml').read_text())
            self.assertIn('; score-sync psg:0',(out/'blueprint/song.mml').read_text())
            self.assertIn('; score-sync psg:0',(out/'song.mml').read_text())
            self.assertTrue((out/'_score_normalized/song.note_values.json').is_file())
            def events(path):
                data=read_vgm_bytes(path)
                return [(e.vgmticks,data[e.address:e.address+3]) for e in command_times(data) if e.command==0xa0]
            self.assertEqual(events(out/'tracks/song.vgm'),events(out/'_score_normalized/song.vgm'))
            if shutil.which('mgsc'):
                for path in (out/'song.mml',out/'blueprint/song.mml'):
                    compiled=subprocess.run(['mgsc',str(path),str(path.with_suffix('.mgs'))],capture_output=True,timeout=30)
                    self.assertEqual(compiled.returncode,0,compiled.stdout)


class NoteValues(unittest.TestCase):
    def test_decomposition_and_long_tied_repeat_keep_original_musical_time(self):
        from mml_note_values import decompose,_meaning
        text='#tempo 75\n9 q8 o4 c%147 d%49 r%147 e%1200\n'
        result=decompose(text)
        self.assertIn('c2. & c64',result)
        self.assertIn('d4 & d%1',result)
        self.assertIn(']',result)
        self.assertEqual(_meaning(text),_meaning(result))

    def test_partial_gate_and_percussion_are_not_split_into_new_attacks(self):
        from mml_note_values import decompose
        self.assertIn('c%147',decompose('9 q6 c%147\n'))
        self.assertIn('b%147',decompose('#opll_mode 1\nf b%147 r%147\n'))


if __name__=='__main__':unittest.main()
