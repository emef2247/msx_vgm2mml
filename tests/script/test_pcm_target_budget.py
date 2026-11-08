"""Pure target byte capacity policy with no source or playback mutation."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'py'))
from pcm_target_budget import fit_bank


def sample(sid, *, cost=32, wave=(1000,-1000)*64,rate=16000):
    return dict(sample_id=sid,encoded=bytes([sid%256])*cost,amplitudes=wave,rate_hz=rate)


class PcmTargetBudgetTests(unittest.TestCase):
    def test_exact_budget_preserves_identity_and_inputs(self):
        samples=[sample(2),sample(1)]
        before=deepcopy(samples)
        mapping,selected,report=fit_bank(samples,{1:3,2:4},64)
        self.assertEqual(mapping,{1:1,2:2})
        self.assertEqual(selected,[1,2])
        self.assertEqual(report['output_bytes'],64)
        self.assertEqual(report['forced_playback_count'],0)
        self.assertEqual(samples,before)

    def test_overflow_maps_every_playback_within_byte_budget(self):
        samples=[sample(i,wave=tuple([1000]*i+[-1000]*(64-i))) for i in range(1,10)]
        usage={i:i*2 for i in range(1,10)}
        mapping,selected,report=fit_bank(samples,usage,96)
        self.assertEqual(set(mapping),set(usage))
        self.assertTrue(set(mapping.values())<=set(selected))
        self.assertLessEqual(report['output_bytes'],96)
        self.assertEqual(report['playback_count'],sum(usage.values()))
        self.assertEqual(report['omitted_playback_count'],0)
        self.assertTrue(report['forced_sample_count'])
        self.assertEqual(report['forced_playback_count'],sum(usage[i] for i in usage if mapping[i]!=i))

    def test_silence_and_delayed_onsets_cannot_replace_active_onset(self):
        samples=[sample(0,wave=(0,)*128),sample(1),sample(2,wave=(0,)*64+(1000,-1000)*32)]
        mapping,selected,report=fit_bank(samples,{0:1000,1:1,2:1000},32)
        self.assertEqual(selected,[1])
        self.assertEqual(mapping[1],1)
        self.assertEqual(mapping[2],1)

    def test_deterministic_across_caller_order(self):
        samples=[sample(i,wave=(1000,)*i+(-1000,)*(65-i)) for i in range(1,7)]
        a=fit_bank(samples,{1:3,5:8},64)
        b=fit_bank(list(reversed(samples)),{5:8,1:3},64)
        self.assertEqual(a,b)

    def test_usage_priority_selects_frequent_timbre(self):
        samples=[sample(1,wave=(1000,-1000)*64),sample(2,wave=((1000,)*32+(-1000,)*32)*2)]
        self.assertEqual(fit_bank(samples,{1:100,2:1},32)[1],[1])
        self.assertEqual(fit_bank(samples,{1:1,2:100},32)[1],[2])

    def test_no_candidate_fits_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError,'no existing'):
            fit_bank([sample(1,cost=64)],{1:1},32)
        with self.assertRaisesRegex(ValueError,'active sample onset'):
            fit_bank([sample(0,wave=(0,)*128),sample(1,cost=64)],{0:1,1:1},32)

    def test_no_inherited_96_slot_limit(self):
        samples=[sample(i,cost=32) for i in range(120)]
        mapping,selected,report=fit_bank(samples,{},3840)
        self.assertEqual(len(selected),120)
        self.assertIsNone(report['slot_limit'])

    def test_nonzero_dc_cannot_replace_an_audible_waveform(self):
        mapping,selected,_=fit_bank([sample(0,wave=(10000,)*128),sample(1)],{0:1000,1:1},32)
        self.assertEqual(selected,[1])
        self.assertEqual(mapping[1],1)

    def test_empty_bank_is_valid(self):
        self.assertEqual(fit_bank([],{},0)[:2],({},[]))


if __name__=='__main__':
    unittest.main()
