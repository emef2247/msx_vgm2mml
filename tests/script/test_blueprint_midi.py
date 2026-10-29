"""Independent byte-level SMF checks and paired blueprint publication."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts'),str(Path(__file__).parent)]
from blueprint_midi import render, _vlq
from musical_blueprint import render_blueprints, write_blueprint
from test_native_blueprint import source, holder
from test_musical_blueprint import plan, note
import batch_vgm_to_mgs as batch


def parse(raw):
    """Small test decoder; does not reuse writer serialization helpers."""
    assert raw[:4]==b'MThd'
    size,format_,count,ppqn=struct.unpack_from('>IHHH',raw,4)
    assert size==6 and format_==1 and ppqn==480
    at=14;tracks=[]
    def vlq():
        nonlocal at
        value=0
        for _ in range(4):
            byte=raw[at];at+=1;value=value*128+(byte&127)
            if byte<128:return value
        raise AssertionError('Oversized VLQ')
    for _ in range(count):
        assert raw[at:at+4]==b'MTrk'
        length=int.from_bytes(raw[at+4:at+8],'big');at+=8;end=at+length
        tick=0;events=[]
        while at<end:
            tick+=vlq();status=raw[at];at+=1
            if status==255:
                kind=raw[at];at+=1;n=vlq();data=raw[at:at+n];at+=n
                events.append((tick,status,kind,data))
            else:
                n=1 if status>>4 in (12,13) else 2
                data=raw[at:at+n];at+=n
                assert status>=128 and all(value<128 for value in data)
                events.append((tick,status,None,data))
        assert at==end and events[-1][1:]==(255,47,b'')
        tracks.append(events)
    assert at==len(raw)
    return tracks


def score_note(index=0, start=0, stop=48, pitch=60, percussion=False):
    return dict(unit_id=f'u{index}',source_device='psg:0',source_section='tone',
        source_channel=index,track=str(index),step_start=start,step_end=stop,
        midi_note=pitch,attack=True,percussion=percussion)


class MidiBytesTests(unittest.TestCase):
    def test_same_pitch_continuation_has_one_midi_attack(self):
        first=score_note(start=0,stop=3)
        second=dict(first,step_start=3,step_end=6,attack=False)
        raw,_=render(dict(tempo=225,end_step=9,score_notes=[first,second]))
        events=[(tick,status>>4) for tick,status,_,_ in parse(raw)[1] if status>>4 in (8,9)]
        self.assertEqual(events,[(0,9),(60,8)])

    def test_vlq_boundaries_and_invalid_values(self):
        for value,expected in ((0,'00'),(127,'7f'),(128,'8100'),(16383,'ff7f'),
                               (16384,'818000'),(0xfffffff,'ffffff7f')):
            self.assertEqual(_vlq(value).hex(),expected)
        for value in (-1,0x10000000,1.0):
            with self.assertRaises(ValueError):_vlq(value)

    def test_tempo_retriggers_and_trailing_rest(self):
        notes=[score_note(start=0,stop=48),score_note(start=48,stop=96)]
        raw,report=render(dict(tempo=225,end_step=144,score_notes=notes))
        tracks=parse(raw)
        self.assertEqual(len(tracks),2)
        self.assertIn((0,255,81,(266667).to_bytes(3,'big')),tracks[0])
        at_boundary=[status>>4 for tick,status,_,_ in tracks[1] if tick==480 and status!=255]
        self.assertEqual(at_boundary,[8,9])
        self.assertTrue(all(track[-1][0]==1440 for track in tracks))
        self.assertEqual(report['note_count'],2)
        self.assertEqual([data[1] for _,status,_,data in tracks[1] if status>>4==9],[96,96])

    def test_more_than_fifteen_melodic_parts_use_explicit_ports(self):
        raw,report=render(dict(tempo=225,end_step=48,score_notes=[score_note(i) for i in range(17)]))
        mappings=report['tracks']
        self.assertEqual(len({(r['midi_port'],r['midi_channel']) for r in mappings}),17)
        self.assertTrue(all(r['midi_channel']!=10 for r in mappings))
        tracks=parse(raw)
        for track,mapping in zip(tracks[1:],mappings):
            self.assertIn((0,255,33,bytes((mapping['midi_port'],))),track)
            self.assertEqual(sum(status>>4==9 for _,status,_,_ in track),1)

    def test_slow_tempo_scaling_keeps_elapsed_time(self):
        raw,report=render(dict(tempo=1,end_step=192,score_notes=[score_note(stop=192)]))
        self.assertEqual(report['metric_scale'],4)
        self.assertEqual(report['end_tick']*report['microseconds_per_quarter']//480,240000000)
        self.assertEqual(parse(raw)[-1][-1][0],7680)

    def test_rhythm_uses_channel_ten_and_valid_fixed_velocity(self):
        raw,report=render(dict(tempo=225,end_step=48,score_notes=[score_note(pitch=35,percussion=True)]))
        self.assertEqual(report['tracks'][0]['midi_channel'],10)
        self.assertIn((0,0x99,None,bytes((35,96))),parse(raw)[1])

    def test_invalid_note_cannot_silently_wrap_pitch_or_time(self):
        for fields in (dict(midi_note=128),dict(step_start=-1),dict(step_end=0),dict(step_end=49)):
            bad=dict(score_note(),**fields)
            with self.assertRaises(ValueError):render(dict(tempo=225,end_step=48,score_notes=[bad]))

    def test_note_events_match_rendered_blueprint_spans_and_repeat_counts(self):
        p=plan(*(note(start=i*4410,uid=f'n{i}') for i in range(4)))
        _,page=render_blueprints(p)[0]
        raw,report=render(page)
        self.assertTrue(page['loops'])
        on=[(tick,data[0]) for track in parse(raw) for tick,status,_,data in track if status>>4==9]
        expected=[(row['step_start']*10,row['midi_note']) for row in page['score_notes']]
        self.assertEqual(on,expected)
        self.assertEqual(report['note_count'],4)

    def test_pitch_changing_continuation_is_retained_as_score_spans(self):
        from musical_plan import MusicalControl
        unit,controls=note('opll')
        controls.append(MusicalControl(1470,'opll',0,'pitch',(194,3,0),unit_id=unit.unit_id))
        _,page=render_blueprints(plan((unit,controls)))[0]
        raw,report=render(page)
        self.assertEqual([row['attack'] for row in page['score_notes']],[True,False])
        self.assertEqual(report['note_count'],2)
        self.assertEqual(len({data[0] for track in parse(raw) for _,status,_,data in track if status>>4==9}),2)


class MidiPublicationTests(unittest.TestCase):
    def test_failed_publication_retains_previous_hashes_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            old=write_blueprint(plan(note()),root,'score')
            changed=plan(note(length=8820))
            real_replace=Path.replace;calls=0
            def fail_once(path,target):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('injected second replacement failure')
                return real_replace(path,target)
            with patch.object(Path,'replace',fail_once):
                failed=write_blueprint(changed,root,'score')
            self.assertEqual(failed['status'],'blocked')
            self.assertEqual(failed['files'],json.loads(json.dumps(old['files'])))
            self.assertEqual(failed['midi_files'],old['midi_files'])
            self.assertEqual(write_blueprint(changed,root,'score')['status'],'success')

    def test_pages_are_paired_owned_and_shrink_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);performance=source(16)
            report=write_blueprint(holder(performance),root,'score')
            self.assertEqual(report['status'],'success')
            self.assertEqual(len(report['files']),len(report['midi_files']))
            self.assertEqual(len(report['midi_files']),2)
            for text,midi in zip(report['files'],report['midi_files']):
                self.assertEqual(Path(text['path']).with_suffix('.midi'),Path(midi['path']))
                parse(Path(midi['path']).read_bytes())
            late=Path(report['midi_files'][1]['path'])
            report=write_blueprint(holder(replace(performance,units=performance.units[:1])),root,'score')
            self.assertEqual(report['status'],'success');self.assertFalse(late.exists())
            self.assertTrue((root/'score.blueprint.notes.csv').is_file())

    def test_edited_midi_or_unowned_sibling_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            result=write_blueprint(holder(source()),root,'score')
            score=Path(result['path']);before=score.read_bytes()
            midi=Path(result['midi_files'][0]['path']);midi.write_bytes(b'my edited MIDI')
            blocked=write_blueprint(holder(source()),root,'score')
            self.assertEqual(blocked['status'],'blocked')
            self.assertEqual(score.read_bytes(),before);self.assertEqual(midi.read_bytes(),b'my edited MIDI')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);midi=root/'blueprint/score.midi';midi.parent.mkdir();midi.write_bytes(b'unowned')
            self.assertEqual(write_blueprint(holder(source()),root,'score')['status'],'blocked')
            self.assertFalse((root/'blueprint/score.mml').exists())
            self.assertEqual(midi.read_bytes(),b'unowned')

    def test_batch_publishes_both_and_blocks_an_edited_optional_midi(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);diag=root/'diag';package=root/'package';package.mkdir()
            report=dict(blueprint=write_blueprint(holder(source()),diag,'score'))
            pubs,deletes,products,status,_,targets=batch.prepare_blueprints(report,diag,'score',package,{})
            self.assertEqual(status,'success');self.assertEqual(len(targets),2)
            manifest=package/'listening_manifest.json'
            state=dict(schema_version=1,entries={'score.vgm':dict(published=products)})
            batch.publish_bundle(pubs,manifest,state,diag,deletions=deletes)
            (package/'blueprint/score.midi').write_bytes(b'edited')
            pubs,deletes,_,status,_,_=batch.prepare_blueprints(report,diag,'score',package,products)
            self.assertEqual(status,'blocked');self.assertEqual((pubs,deletes),([],[]))

    def test_failed_rollback_preserves_disk_recovery_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);old=write_blueprint(holder(source()),root,'score')
            target=Path(old['path']);before=target.read_bytes()
            real_replace=Path.replace;real_write=Path.write_bytes
            def replace_once(path,dest):
                if Path(dest).suffix=='.midi':raise OSError('authored publication failure')
                return real_replace(path,dest)
            def fail_restore(path,data):
                if path==target:raise OSError('authored rollback failure')
                return real_write(path,data)
            with patch.object(Path,'replace',replace_once),patch.object(Path,'write_bytes',fail_restore):
                report=write_blueprint(holder(source()),root,'score')
            self.assertEqual(report['status'],'blocked')
            recovery=report['publication_recovery']
            backup=next(r for r in recovery['backups'] if r['path']==str(target))
            self.assertEqual(Path(backup['backup']).read_bytes(),before)
            self.assertTrue(Path(recovery['directory']).is_dir())


if __name__=='__main__':unittest.main()
