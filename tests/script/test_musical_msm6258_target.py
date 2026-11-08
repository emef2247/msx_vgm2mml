"""Authored MSM PCM capacity, source timing and pan checks."""
from dataclasses import replace
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from native_music import NativeDevice,NativePCM,NativePerformance
from musical_pcm_target import project_pcm
from musical_variants import export_variants,project_variant


def performance(pans=(0,1,2),end=600):
    d=NativeDevice('msm6258:0','msm6258',0,8000000)
    assets=tuple(NativePCM(str(i),d.device_id,200*i,200*i+180,15625,
        tuple(round(12000*math.sin(j*math.tau*(i+1)/64)) for j in range(64)),(i,),
        (('pan',pan),)) for i,pan in enumerate(pans))
    return NativePerformance((d,),(),(),(),(),(),end,'','',pcm_assets=assets)


class MusicalMsm6258TargetTests(unittest.TestCase):
    def test_force_reuses_all_playbacks_and_enforces_aligned_bytes(self):
        p=performance();before=repr(p)
        with patch('opn2_target_vgm.ADPCM_B_DRAM_BUDGET',32):
            with self.assertRaisesRegex(ValueError,'force'):project_pcm(p,'opna')
            rows,prefix,losses,stats=project_pcm(p,'opna',force=True)
        self.assertEqual(repr(p),before)
        self.assertEqual(stats['playbacks'],3);self.assertEqual(stats['ram_used_bytes'],32)
        self.assertEqual(stats['unique_samples'],1)
        self.assertEqual(losses['msm6258_budget_reused_playbacks'],2)
        self.assertEqual(int.from_bytes(prefix[7:11],'little'),32)
        pan=[r['command'][2] for r in rows if r['command'][:2]==bytes((0x57,1))]
        self.assertEqual(pan,[0xc2,0x82,0x42])
        self.assertEqual([r['sample'] for r in rows if r['reason'].endswith('endpoint')],[180,380,580])
        self.assertTrue(all('valid_end_error_samples' in r for r in stats['runs']))

    def test_exact_fit_and_one_aligned_block_over(self):
        p=performance((0,0))
        with patch('opn2_target_vgm.ADPCM_B_DRAM_BUDGET',64):
            _,_,losses,stats=project_pcm(p,'opna')
            self.assertEqual(stats['dram_bytes'],64);self.assertFalse(losses)
        with patch('opn2_target_vgm.ADPCM_B_DRAM_BUDGET',32):
            with self.assertRaisesRegex(ValueError,'DRAM'):project_pcm(p,'opna')

    def test_mute_and_msxaudio_mono_are_explicit(self):
        p=performance((3,1))
        _,prefix,losses,stats=project_pcm(p,'y8950')
        self.assertEqual(stats['playbacks'],1)
        self.assertEqual(losses['msm6258_muted_source_assets_not_encoded'],1)
        self.assertEqual(losses['msm6258_stereo_folded_to_mono'],1)
        self.assertEqual(prefix[2],0x88)
        self.assertLessEqual(stats['ram_used_bytes'],262144)

    def test_loop_split_retains_sample_origin_and_audio_edits(self):
        p=replace(performance((0,)),song_loop_sample=90)
        _,prefix,_,stats=project_pcm(p,'opna')
        self.assertEqual([(r['start_sample'],r['end_sample']) for r in stats['runs']],[(0,90),(90,180)])
        self.assertAlmostEqual(stats['runs'][1]['source_sample_position'],90*15625/44100)
        changed=replace(p,pcm_assets=(replace(p.pcm_assets[0],samples=tuple(-v for v in p.pcm_assets[0].samples)),))
        self.assertNotEqual(prefix,project_pcm(changed,'opna')[1])

    def test_missing_source_decision_is_not_silent_even_without_assets(self):
        from test_musical_fm_target import performance as fm
        p=fm();p=replace(p,devices=p.devices+(NativeDevice('msm','msm6258',0,8000000),),
            decisions=(('msm6258_pcm_unresolved_playback','missing_reset'),))
        with self.assertRaisesRegex(ValueError,'source evidence'):project_variant(p,'makoto')
        _,_,losses,_=project_variant(p,'makoto',force=True)
        self.assertEqual(losses['msm6258_pcm_unavailable_source_assets_omitted'],1)

    def test_pcm_profiles_and_source_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            results=export_variants(performance((0,)),tmp,'authored',force=True)
            for name in ('makoto','sfg01_makoto','sfg01_msxaudio','layered'):
                self.assertEqual(results[name]['status'],'success',results[name])
                self.assertEqual(results[name]['plan']['pcm']['ram_budget_bytes'],262144)
            self.assertEqual(results['sfg01']['status'],'unavailable')
        p=performance((0,));a=replace(p.pcm_assets[0],samples=(1,2))
        with self.assertRaisesRegex(ValueError,'cover'):project_pcm(replace(p,pcm_assets=(a,)),'opna')


if __name__=='__main__':unittest.main()
