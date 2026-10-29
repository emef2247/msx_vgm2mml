"""Accepted OPLL plans preserve musical decisions and native/global provenance."""
from pathlib import Path
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from opll_execution import build_opll
from opll_target import segment_decisions, note_pitch, MGSDRV_FNUM


def segment(start, end, **values):
    fields = dict(tick_start=start, tick_end=end, time=start/60, keyon=1,
        key_on_edge=0, fnum=172, block=3, inst=1, vol=0, sus=0,
        vgmticks=start*735, vgmticks_end=end*735)
    fields.update(values)
    return SimpleNamespace(**fields)


def raw_vgm(commands):
    raw = bytearray(64)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x150)
    raw.extend(commands + b'\x66')
    struct.pack_into('<I', raw, 4, len(raw)-4)
    return bytes(raw)


class OpllExecutionTests(unittest.TestCase):
    def test_continuous_units_accept_semitone_and_retain_native_values(self):
        rows = [segment(0, 2, key_on_edge=1, fnum=173), segment(2, 4, vol=15, sus=1),
                segment(4, 6, keyon=0)]
        with patch('opll_target.render', side_effect=AssertionError('No text rendering')):
            plan = build_opll({0: rows})
        self.assertEqual([u.source_indices for u in plan.units], [(0,1), (2,)])
        self.assertEqual(plan.units[0].parameters[0][1:3], (173,3))
        self.assertEqual([c.value for c in plan.controls if c.kind=='pitch'][:2], [(172,3,0),(172,3,1)])
        self.assertIn((0,), [c.value for c in plan.controls if c.kind=='volume'])
        self.assertFalse(any(c.kind=='gate' and c.value==(0,) and c.sample==1470 for c in plan.controls))

    def test_zero_duration_release_and_reattack_remain_ordered(self):
        rows = [segment(0,2,key_on_edge=1),segment(2,2,keyon=0),
                segment(2,2,key_on_edge=1),segment(2,4)]
        plan = build_opll({0: rows})
        gates = [c.value[0] for c in plan.ordered_controls() if c.kind=='gate' and c.sample==1470]
        self.assertIn(0,gates)
        self.assertIn(1,gates)
        self.assertLess(gates.index(0),gates.index(1))
        self.assertTrue(any(u.start_sample==u.end_sample for u in plan.units))

    def test_partial_live_patch_is_global_and_source_ordered(self):
        raw = raw_vgm(b'\x51\x00\x71\x51\x03\x17\x61\xdf\x02\x51\x00\x61')
        rows = [segment(0,2,inst=0,key_on_edge=1)]
        plan = build_opll({0:rows,1:rows}, source_raw=raw)
        controls = [c for c in plan.controls if c.kind=='patch_write']
        self.assertEqual([c.value for c in controls],[(0,0x71),(3,0x17),(0,0x61)])
        self.assertEqual([c.source_event_id for c in controls],[0,1,3])
        self.assertTrue(all(c.channel is None for c in controls))
        self.assertEqual([c.source_sample for c in controls],[0,0,735])

    def test_nine_melodic_channels_and_rhythm_shared_state(self):
        raw=raw_vgm(b'\x51\x0e\x20\x51\x36\x45\x51\x0e\x30\x51\x0e\x20\x51\x0e\x00')
        plan=build_opll({8:[segment(0,2,key_on_edge=1)]},source_raw=raw)
        self.assertEqual(plan.units[0].channel,8)
        shared=[c.value for c in plan.controls if c.kind=='rhythm_register' and c.origin=='observed_global_register']
        self.assertEqual(shared,[(14,32),(54,69),(14,48),(14,32),(14,0)])
        restored = [c for c in plan.controls if c.kind=='instrument' and c.origin=='accepted_melody_at_rhythm_exit']
        self.assertEqual([(c.channel,c.value) for c in restored],[(6,(4,)),(7,(0,)),(8,(0,))])

    def test_rhythm_bank_is_not_overwritten_by_melodic_quantization(self):
        from vgm_reader import parse_vgm
        from opll import _build_segments
        from musical_vgm import write_vgm
        from vgm_timing import command_times
        raw = raw_vgm(bytes.fromhex('51 16 99 51 26 16 51 36 19 61 be 05 '
            '51 0e 20 51 36 ab 51 16 44 51 26 05 51 0e 30 61 be 05 '
            '51 0e 00 61 be 05'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'rhythm.vgm'
            source.write_bytes(raw)
            paths = parse_vgm(str(source), str(root), include_vgmticks=True)
            segments, _ = _build_segments(paths[5])
            plan = build_opll(segments, paths[6], source_raw=raw)
            target = root / 'target.vgm'
            write_vgm(plan, target)
            output = target.read_bytes()
        registers, states = [0] * 64, []
        for event in command_times(output):
            if event.command == 0x51:
                registers[output[event.address + 1]] = output[event.address + 2]
            if event.wait_samples:
                states.append((event.vgmticks, tuple(registers)))
        active_rhythm = [state for _, state in states if state[14] & 32]
        self.assertTrue(active_rhythm)
        for state in active_rhythm:
            self.assertEqual((state[0x16], state[0x26], state[0x36]), (0x44, 0x05, 0xab))
        self.assertTrue(any(u.articulation == 'rhythm_resource' for u in plan.units))
        observed = {c.unit_id for c in plan.controls if c.unit_id}
        self.assertTrue(observed <= {u.unit_id for u in plan.units})

    def test_shared_decision_and_measured_chromatic_table(self):
        rows=[segment(0,2,key_on_edge=1),segment(2,4,inst=4)]
        decisions=segment_decisions(rows)
        self.assertTrue(decisions[0].continuation)
        self.assertFalse(decisions[1].continuation)
        self.assertEqual(MGSDRV_FNUM,(172,182,194,205,217,230,244,258,273,290,307,325))
        self.assertEqual(note_pitch(4,'g'),(258,3))
        self.assertEqual(decisions[1].instrument,4)

    def test_normalized_path_consumes_accepted_states(self):
        from musical_timing import NormalizedState, NormalizedNote, NormalizedTrack, NormalizedMelody
        state=NormalizedState(0,1470,0,12,9,6,(4,'g',3,10,1,''),(0,))
        note=NormalizedNote(0,0,1470,0,12,9,(state,),(0,))
        track=NormalizedTrack(0,6,10,True,True,3,(note,))
        melody=NormalizedMelody((track,),(),(),())
        class Timing:
            plan=object()
            def __init__(self):self.melody=melody
            def step_sample(self,step):return round(step*100)
            def source_sample(self,sample):return sample
        plan=build_opll({0:[segment(0,2,key_on_edge=1)]},timing=Timing())
        self.assertEqual((plan.units[0].start_sample,plan.units[0].end_sample),(0,1200))
        self.assertIn((258,3,1),[c.value for c in plan.controls if c.kind=='pitch'])
        self.assertIn((4,),[c.value for c in plan.controls if c.kind=='instrument'])
        self.assertIn(900,[c.sample for c in plan.controls if c.kind=='gate' and c.value==(0,)])

    def test_normalized_zero_pulse_settles_to_following_rest(self):
        from musical_timing import NormalizedState, NormalizedNote, NormalizedTrack, NormalizedMelody
        from musical_vgm import write_vgm
        from vgm_timing import command_times
        state=NormalizedState(0,735,0,1,1,8,(4,'c',0,15,0,''),(0,))
        note=NormalizedNote(0,0,735,0,1,1,(state,),(0,))
        track=NormalizedTrack(0,8,15,True,True,0,(note,))
        melody=NormalizedMelody((track,),(),(),())
        class Timing:
            plan=object()
            def __init__(self):self.melody=melody
            def step_sample(self,step):return round(step*735)
            def source_sample(self,sample):return sample
        rows=[segment(0,1,key_on_edge=1),segment(1,2,keyon=0),
              segment(2,2,key_on_edge=1),segment(2,4,keyon=0)]
        plan=build_opll({0:rows},timing=Timing())
        gates=[c.value[0] for c in plan.ordered_controls() if c.kind=='gate' and c.sample==1470]
        self.assertEqual(gates[-2:],[1,0])
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'pulse.vgm';write_vgm(plan,target);raw=target.read_bytes()
        high=0
        for event in command_times(raw):
            if event.command==0x51 and raw[event.address+1]==0x20:
                high=raw[event.address+2]
            if event.wait_samples and event.vgmticks>=1470:
                self.assertFalse(high&16,'Instantaneous source pulse must not become a held note')


if __name__=='__main__':unittest.main()
