"""Channel identity and target scheduling must survive track separation."""
import csv
from dataclasses import replace
from pathlib import Path
import re,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts')]
from opm_to_mdx_mml import convert
from opm_mdx import project_segments,scheduled_projection,render
from test_opm_reader import vgm

def rows(path):
    with path.open(encoding='utf-8') as stream:
        return list(csv.DictReader(stream))

def write(reg,data):return bytes((0x54,reg,data))
def wait(n):return b'\x61'+n.to_bytes(2,'little')

class MdxChannelTrackTests(unittest.TestCase):
    def convert(self,root,commands):
        source=root/'source.vgm';source.write_bytes(vgm(commands))
        return convert(source,root/'out',dump_passes=True,notation='registers')

    def test_eight_channels_key_masks_pitch_and_operator_banks_are_owned_by_each_track(self):
        commands=b''.join(write(0x28+ch,0x4e)+write(0x60+ch,ch)+write(8,0x78+ch) for ch in range(8))
        commands+=wait(101)+b''.join(write(8,ch) for ch in range(8))+wait(101)
        with tempfile.TemporaryDirectory() as tmp:
            path,analysis,plan=self.convert(Path(tmp),commands)
            text=path.read_text()
            owned={chr(65+ch):[] for ch in range(8)}
            for track,reg,data in re.findall(r'^([A-H]) y(\d+),(\d+)',text,re.M):owned[track].append((int(reg),int(data)))
            for ch in range(8):
                track=chr(65+ch)
                self.assertEqual(owned[track],[(0x28+ch,0x4e),(0x60+ch,ch),(8,0x78+ch),(8,ch)])
                advances=[int(n) for n in re.findall(r'^'+track+r' r%(\d+)$',text,re.M)]
                self.assertEqual(sum(advances),plan.end_mdx_tick)
                held=next(s for s in analysis.segments if s.ch==ch and s.rising_mask)
                self.assertEqual(held.state.operators[0].tl,ch)
            trace_rows=rows(path.parent/'source_trace.opm_regs.csv')
            self.assertEqual([int(r['ch']) for r in trace_rows],[ch for ch in range(8) for _ in range(3)]+list(range(8)))

    def test_shared_controls_are_once_on_A_noise_is_on_H_and_sources_stay_ordered(self):
        commands=write(0x19,12)+write(0x19,0x93)+write(0x2f,0x4e)+write(8,0x7f)+wait(101)+write(15,0x94)+wait(101)
        with tempfile.TemporaryDirectory() as tmp:
            path,analysis,plan=self.convert(Path(tmp),commands)
            text=path.read_text()
            self.assertIn('A y25,12',text);self.assertIn('A y25,147',text)
            self.assertIn('H y47,78',text);self.assertIn('H y8,127',text);self.assertIn('H y15,148',text)
            trace_rows=rows(path.parent/'source_trace.opm_regs.csv')
            self.assertEqual([r['ch'] for r in trace_rows],['','','7','7','7'])
            self.assertEqual([r['register_scope'] for r in trace_rows],['shared','shared','channel','key','noise'])
            projected=rows(path.parent/'source.mdx.controls.csv')
            self.assertEqual([r['mdx_track'] for r in projected],['A','A','H','H','H'])
            self.assertEqual(len(projected),5)
            self.assertTrue(all(e.ch==7 for e in analysis.events if e.register==15))
            self.assertTrue(all(s.state.noise_raw is None for s in analysis.segments if s.ch!=7))
            self.assertEqual([w.source_event_id for w in plan.writes],sorted(w.source_event_id for w in plan.writes))

    def test_same_time_operator_key_pulses_preserve_their_order_and_channel(self):
        commands=write(8,0x7b)+write(8,3)+write(8,0x0b)+write(8,0x1b)+wait(101)
        with tempfile.TemporaryDirectory() as tmp:
            path,analysis,plan=self.convert(Path(tmp),commands)
            self.assertEqual(re.findall(r'^D y8,(\d+)',path.read_text(),re.M),['123','3','11','27'])
            self.assertNotIn('A y8',path.read_text())
            self.assertEqual([w.mdx_tick for w in plan.writes],[0]*4)
            self.assertEqual(sum(s.rising_mask.bit_count() for s in analysis.segments),6)

    def test_scheduled_projection_keeps_source_ids_and_lane_order_and_legacy_replay_exists(self):
        commands=write(8,0x7f)+write(8,0x78)+write(8,7)+write(8,0)+wait(101)
        with tempfile.TemporaryDirectory() as tmp:
            path,_,plan=self.convert(Path(tmp),commands)
            scheduled=scheduled_projection(plan)
            self.assertEqual([w.data for w in scheduled.writes],[0x78,0,0x7f,7])
            self.assertEqual({w.source_event_id for w in plan.writes},{w.source_event_id for w in scheduled.writes})
            self.assertEqual([w.data for w in plan.writes],[0x7f,0x78,7,0])
            legacy=render(plan,track_layout='conductor')
            self.assertEqual(re.findall(r'^A y8,(\d+)',legacy,re.M),['127','120','7','0'])
            self.assertNotRegex(legacy,r'^H y')

    def test_shared_controls_keep_original_source_identity_in_separate_tracks(self):
        commands=write(0x19,0)+write(0x29,0x4e)+write(8,0x79)+write(0x19,12)+wait(101)
        with tempfile.TemporaryDirectory() as tmp:
            path,analysis,plan=self.convert(Path(tmp),commands)
            self.assertEqual([w.data for w in plan.writes],[0,0x4e,0x79,12])
            self.assertIn('B y8,121',path.read_text())
            self.assertIn('A y25,12',path.read_text())
            # Target scheduling is explicit; independent roundtrip state
            # validation must still reject any known-state discrepancy.
            self.assertNotEqual([w.source_event_id for w in plan.writes],
                                [w.source_event_id for w in scheduled_projection(plan).writes])

    def test_wrong_raw_csv_channel_annotation_is_not_ignored(self):
        from opm import build_segments
        with tempfile.TemporaryDirectory() as tmp:
            path,analysis,_=self.convert(Path(tmp),write(0x29,0x4e)+wait(101))
            trace=path.parent/'source_trace.opm_regs.csv'
            data=rows(trace);data[0]['ch']='0'
            with trace.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
            with self.assertRaisesRegex(ValueError,'trace channel'):
                build_segments(trace,end_vgmticks=analysis.source_end_vgmticks)

    def test_corrupt_segment_channel_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,analysis,plan=self.convert(Path(tmp),write(0x2b,0x4e)+write(8,0x7b)+write(15,148)+wait(101))
            for register in (0x2b,8,15):
                bad=[replace(s,ch=0) if s.source_event_id is not None and s.register==register else s for s in analysis.segments]
                with self.subTest(register=register), self.assertRaisesRegex(ValueError,'Segment channel'):
                    project_segments(bad,end_vgmticks=analysis.source_end_vgmticks)

if __name__=='__main__':unittest.main()
