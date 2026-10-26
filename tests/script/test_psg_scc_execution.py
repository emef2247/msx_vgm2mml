"""Accepted score execution, including shared source controls and wave RAM."""
from dataclasses import replace
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))
from psg_scc_performance import analyze
from psg_scc_execution import build_psg_scc, accepted_note_decision
from test_psg_scc_performance import psg, scc


def vgm(commands):
    data = bytearray(256)
    data[:4] = b'Vgm '
    struct.pack_into('<I', data, 8, 0x171)
    struct.pack_into('<I', data, 0x34, 256-0x34)
    data.extend(commands + b'\x66')
    struct.pack_into('<I', data, 4, len(data)-4)
    return bytes(data)


class ExecutionTests(unittest.TestCase):
    def test_score_partitions_and_runs_not_native_segment_gates(self):
        perf = analyze({0: [psg(0, 2, tone_period=427),
                            psg(2, 3, tone_period=427, volume=8),
                            psg(5, 1, tone_period=427, volume=0, scale='r')]}, 'psg')
        plan = build_psg_scc(perf)
        self.assertEqual(len(plan.units), 2)
        self.assertEqual([(c.sample,c.value) for c in plan.controls if c.kind=='volume'],
                         [(0,(12,)),(1470,(8,))])
        self.assertEqual([(c.sample,c.value) for c in plan.controls if c.kind=='gate'],
                         [(0,(1,)),(3675,(0,)),(3675,(0,))])
        self.assertEqual(plan.units[0].source_indices, (0,1))
        parameters=dict(plan.units[0].parameters)
        self.assertEqual(parameters['native_period'],427)
        self.assertEqual(parameters['accepted_period'],427)
        self.assertEqual(parameters['volume_runs'],((12,2),(8,3)))
        self.assertEqual(parameters['mode'],1)
        self.assertEqual(plan.end_sample,4410)

    def test_pitch_policy_is_same_pure_renderer_decision(self):
        perf = analyze({0:[psg(tone_period=1)]},'psg')
        note=perf.channels[0][1][0]
        decision=accepted_note_decision(note,'psg')
        plan=build_psg_scc(perf)
        self.assertEqual(next(c.value[0] for c in plan.controls if c.kind=='pitch'),decision.period)
        self.assertFalse(decision.period_exact)
        self.assertEqual(plan.decisions[0][1],'period_approximated')

    def test_shared_raw_noise_period_and_repeated_shape_order(self):
        raw=vgm(bytes([0xa0,11,0x34,0xa0,12,0x12,0xa0,6,7,
                       0xa0,13,9,0xa0,13,9,0x61,0xdf,2]))
        perf=analyze({0:[psg(envelope_enabled=1,envelope_period=2)]},'psg')
        plan=build_psg_scc(perf,source_raw=raw)
        shared=[c for c in plan.ordered_controls() if c.origin=='ordered_source_shared_control']
        self.assertEqual([c.kind for c in shared],['psg_envelope_period','psg_envelope_period',
                                                 'psg_noise','psg_envelope_shape','psg_envelope_shape'])
        self.assertEqual([c.value for c in shared],[(0x34,),(0x1234,),(7,),(9,),(9,)])
        self.assertEqual([c.source_event_id for c in shared],list(range(5)))
        self.assertTrue(all(c.channel is None for c in shared))
        self.assertEqual(sum(c.kind=='psg_envelope_shape' for c in plan.controls),2)

    def test_repeated_shared_hw_reset_during_held_units_has_no_gate_effect(self):
        from musical_vgm import scheduled_writes
        raw=vgm(bytes([0xa0,13,9,0x61,0xbe,5,0xa0,13,9,0xa0,13,9,0x61,0xbe,5]))
        perf=analyze({0:[psg(0,4,envelope_enabled=1)],
                      1:[psg(0,4,ch=1,envelope_enabled=1)]},'psg')
        plan=build_psg_scc(perf,source_raw=raw)
        reset=[r for r in scheduled_writes(plan) if r['register']==13 and r['sample']==1470]
        self.assertEqual([r['data'] for r in reset],[9,9])
        self.assertEqual([r['source_event_id'] for r in reset],[2,3])
        self.assertFalse(any(c.sample==1470 and c.kind=='gate' for c in plan.controls))
        self.assertEqual(len(plan.units),2)

    def test_no_synthetic_hw_reset_at_each_pitch_partition(self):
        perf=analyze({0:[psg(envelope_enabled=1,envelope_period=0x1234),
                        psg(2,envelope_enabled=1,envelope_period=0x1234,ev_type='fCA')]},'psg')
        plan=build_psg_scc(perf)
        self.assertEqual(sum(c.kind=='psg_envelope_shape' for c in plan.controls),1)
        self.assertEqual(next(c.value for c in plan.controls if c.kind=='psg_envelope_period'),(0x1234,))

    def test_scc_shared_slot_and_live_wave_writes_remain_ordered(self):
        raw=vgm(bytes([0xd2,0,96,128,0x61,0xdf,2,0xd2,0,96,127]))
        perf=analyze({3:[scc(ch=3)],4:[scc(ch=4)]},'scc')
        plan=build_psg_scc(perf,source_raw=raw)
        waves=[c for c in plan.controls if c.kind=='wave_write']
        self.assertEqual([(c.sample,c.value) for c in waves],[(0,(3,0,128)),(0,(3,0,127))])
        self.assertTrue(all(c.channel is None for c in waves))
        self.assertFalse(any(c.kind=='waveform' for c in plan.controls))
        self.assertEqual({u.channel for u in plan.units},{3,4})

    def test_coincident_note_end_precedes_next_note_start(self):
        perf=analyze({0:[psg(),psg(2,ev_type='fCA')]},'psg')
        controls=build_psg_scc(perf).ordered_controls()
        boundary=[c.value[0] for c in controls if c.sample==1470 and c.kind=='gate']
        self.assertEqual(boundary,[0,1])

    def test_default_raw_timing_matches_existing_tcl_tick_rounding(self):
        raw=vgm(bytes([0x61,0xe8,3,0xa0,13,9]))
        perf=analyze({0:[psg()]},'psg')
        shape=next(c for c in build_psg_scc(perf,source_raw=raw).controls
                   if c.kind=='psg_envelope_shape')
        self.assertEqual((shape.sample,shape.source_sample),(1470,1000))

    def test_scc_observed_zero_gate_edges_restore_next_wait_state(self):
        from musical_vgm import scheduled_writes
        raw=vgm(bytes([0xd2,3,0,1,0x61,0xbe,5,
                       0xd2,3,0,0,0xd2,3,0,1,0x61,0xbe,5]))
        perf=analyze({0:[scc(0,4)]},'scc')
        plan=build_psg_scc(perf,source_raw=raw)
        edges=[c for c in plan.controls if c.origin=='observed_zero_transition']
        self.assertEqual([(c.sample,c.value,c.source_event_id) for c in edges],
                         [(1470,(0,),2),(1470,(1,),3)])
        written=[r for r in scheduled_writes(plan) if r['origin']=='observed_zero_transition']
        self.assertEqual([r['data'] for r in written],[0,1])
        self.assertEqual(written[-1]['data'],1)

    def test_psg_zero_mixer_edge_does_not_toggle_unrelated_channels(self):
        raw=vgm(bytes([0xa0,7,62,0x61,0xbe,5,0xa0,7,63,0xa0,7,62,0x61,0xbe,5]))
        perf=analyze({0:[psg(0,4)]},'psg')
        controls=build_psg_scc(perf,source_raw=raw).controls
        edges=[c for c in controls if c.origin=='observed_zero_transition']
        self.assertEqual([(c.channel,c.kind,c.value) for c in edges],
                         [(0,'psg_mode',(0,)),(0,'psg_mode',(1,))])
        self.assertFalse(any(c.channel in (1,2) for c in edges))

    def test_terminal_explicit_off_follows_accepted_controls(self):
        raw=vgm(bytes([0xd2,3,0,1,0x61,0xbe,5,0xd2,3,0,0]))
        perf=analyze({0:[scc(0,2)]},'scc')
        controls=build_psg_scc(perf,source_raw=raw).ordered_controls()
        self.assertEqual(controls[-1].origin,'observed_terminal_off')
        self.assertEqual(controls[-1].value,(0,))

    def test_scc_fallback_waveform_is_complete_target_bytes(self):
        perf=analyze({0:[scc(waveform_hex='8078'*16)]},'scc')
        plan=build_psg_scc(perf)
        wave=next(c for c in plan.controls if c.kind=='waveform')
        self.assertEqual(wave.value,(128,120)*16)
        parameters=dict(plan.units[0].parameters)
        self.assertEqual(parameters['waveform_id'],0)
        self.assertEqual(parameters['waveform_hex'],'8078'*16)
        with tempfile.TemporaryDirectory() as d:
            plan.dump(d,'authored')
            self.assertTrue((Path(d)/'authored.musical_plan.controls.csv').exists())

    def test_accepted_ends_retime_but_envelope_holds_stay_frame_based(self):
        class Timing:
            def sample(self,tick): return tick*1000
            def boundaries(self,ticks,source_samples): return tuple(t*1000 for t in ticks)
        perf=analyze({0:[psg(0,2),psg(2,2,volume=8),psg(4,2,ev_type='fCA')]},'psg')
        plan=build_psg_scc(perf,timing=Timing())
        self.assertEqual([(u.start_sample,u.end_sample) for u in plan.units],[(0,4000),(4000,6000)])
        self.assertEqual([c.sample for c in plan.controls if c.kind=='volume'],[0,1470,4000])

    def test_retiming_and_raw_provenance_use_distinct_mapping(self):
        class Timing:
            def sample(self,tick): return tick*1000
            def source_sample(self,source): return round(source/735)*1000
        perf=analyze({0:[psg()]},'psg')
        raw=vgm(bytes([0x61,0xdf,2,0xa0,13,9]))
        plan=build_psg_scc(perf,source_raw=raw,timing=Timing())
        shape=next(c for c in plan.controls if c.kind=='psg_envelope_shape')
        self.assertEqual((shape.sample,shape.source_sample),(1000,735))
        self.assertEqual(plan.units[0].end_sample,2000)
        self.assertEqual(plan.patterns,())


if __name__=='__main__':unittest.main()
