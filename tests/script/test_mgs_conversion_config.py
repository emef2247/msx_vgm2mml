"""Shared frontend options and target-only OPLL threshold decisions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))
from mgs_conversion_config import MgsOptions, sample_threshold
from note_normalization import TimingPlan, render_melody, infer_timing, retime_rhythm


def segment(a, b, *, edge=0, key=1, inst=1, sus=0, vol=2, fnum=217):
    return SimpleNamespace(vgmticks=a, vgmticks_end=b, keyon=key, key_on_edge=edge,
                           fnum=fnum, block=3, inst=inst, vol=vol, sus=sus)


class MgsOptionsTests(unittest.TestCase):
    def test_default_and_explicit_activation(self):
        base = MgsOptions()
        self.assertFalse(base.enabled)
        self.assertEqual(base.cli_args(), [])
        self.assertEqual(base.as_dict()['fm_state_samples'], 44)
        self.assertEqual(base.as_dict()['normalization_samples'], 352)
        for opts in [MgsOptions(normalize_lengths=True), MgsOptions(fm_state_ms=24),
                     MgsOptions(normalization_ms=16)]:
            self.assertTrue(opts.enabled)
        self.assertEqual(MgsOptions(fm_state_ms=24,force=True).cli_args(),
                         ['--fm-state-ms', '24', '--force'])

    def test_rhythm_name_and_psg_part_options(self):
        for part in ('all', 'melody', 'rhythm'):
            options = MgsOptions(enhance_drums=True, psg_part=part)
            self.assertEqual(options.cli_args(), ['--enhance-rhythm'] +
                             ([] if part == 'all' else ['--psg-'+part+'-only']))
            self.assertEqual(options.as_dict()['psg_part'], part)
            self.assertTrue(options.as_dict()['enhance_drums'])
            self.assertTrue(options.as_dict()['enhance_rhythm'])
        with self.assertRaisesRegex(ValueError, 'psg_part'):
            MgsOptions(psg_part='other')

    def test_finite_positive_validation_and_floor(self):
        self.assertEqual(sample_threshold(24,'test'),1058)
        for value in [0,-1,float('nan'),float('inf'),.001]:
            for name in ['fm_state_ms','normalization_ms']:
                with self.subTest(value=value,name=name), self.assertRaises(ValueError):
                    MgsOptions(**{name:value})

    def test_filter_preserves_terminal_timbre_sustain_and_native_rows(self):
        # One long sounding unit. Only its brief pitch/volume state is eligible.
        rows = [segment(0,2000,edge=1),segment(2000,2100,fnum=194),
                segment(2100,4000),segment(4000,4600,inst=2),
                segment(4600,6500),segment(6500,7100,sus=1),
                segment(7100,9000),segment(9000,9600,vol=8),
                segment(9600,10000,key=0)]
        before=[vars(s).copy() for s in rows]
        plan=TimingPlan(120,12,5512.5,0,1,352)
        with tempfile.TemporaryDirectory() as folder:
            voice=Path(folder)/'voice.csv';voice.write_text('#type,vgmticks,patch_hex\n')
            decisions=[]
            render_melody({0:rows},voice,plan,fm_state_ms=24,state_evidence=decisions)
        omitted=[r for r in decisions if r['action']=='omit_internal_state']
        self.assertEqual([r['run_index'] for r in omitted],[1])
        self.assertTrue(decisions[-1]['protected'])
        self.assertEqual([vars(s) for s in rows],before)

    def test_custom_patch_transition_is_not_a_short_level_state(self):
        rows=[segment(0,2000,edge=1,inst=0),segment(2000,2600,inst=0),
              segment(2600,4000,inst=0),segment(4000,4500,key=0,inst=0)]
        plan=TimingPlan(120,12,5512.5,0,1,352)
        with tempfile.TemporaryDirectory() as folder:
            voice=Path(folder)/'voice.csv'
            voice.write_text('#type,vgmticks,patch_hex\npatch,0,0000000000000000\n'
                             'patch,2000,0100000000000000\npatch,2600,0000000000000000\n')
            decisions=[]
            render_melody({0:rows},voice,plan,fm_state_ms=24,state_evidence=decisions)
        self.assertEqual(len(decisions),3)
        self.assertTrue(all(row['protected'] for row in decisions))
        self.assertTrue(all(row['action']=='retain' for row in decisions))

    def test_correction_budget_does_not_change_anchor_interval_eligibility(self):
        # Tight and loose budgets fit the same regular source clock but expose
        # different permissible target shifts; source attacks are not removed.
        rows=[segment(round(1000+i*5518.15),round(1000+i*5518.15)+3000,edge=1)
              for i in range(48)]
        tight=infer_timing({0:rows},normalization_ms=8)
        loose=infer_timing({0:rows},normalization_ms=24)
        self.assertIsNotNone(tight);self.assertIsNotNone(loose)
        self.assertEqual(tight.tempo,loose.tempo)
        self.assertEqual(tight.tolerance_samples,352)
        self.assertEqual(loose.tolerance_samples,1058)


    def test_rhythm_bound_and_new_attack_collision_reject_projection(self):
        from dataclasses import dataclass
        @dataclass(slots=True)
        class Rhythm:
            vgmticks: int
            vgmticks_end: int
            time: float
            ev_type: str = 'rhythm_expand'
            is_ryt: int = 1
            keyon: int = 1
            tick_start: int = 0
            tick_end: int = 0
        plan=TimingPlan(120,12,5512.5,0,1,44)
        with self.assertRaisesRegex(ValueError,'rhythm boundary'):
            retime_rhythm({9:[Rhythm(200,450,200/44100)]},plan)
        loose=TimingPlan(120,12,5512.5,0,1,352)
        rows=[Rhythm(10,200,10/44100),Rhythm(20,220,20/44100)]
        with self.assertRaisesRegex(ValueError,'merge distinct rhythm attacks'):
            retime_rhythm({9:rows},loose)
        same=Rhythm(0,459,0)
        proxies,shift=retime_rhythm({9:[same]},loose)
        self.assertNotEqual(id(proxies[9][0]),id(same))
        self.assertEqual(same.tick_end,0)
        self.assertLessEqual(shift,352)


if __name__=='__main__':
    unittest.main()
