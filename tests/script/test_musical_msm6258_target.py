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

    def test_replacement_rate_limit_is_explicit(self):
        p=performance((0,));a=p.pcm_assets[0]
        long=replace(a,asset_id='long',start_sample=200,end_sample=11750,
            samples=tuple(round(10000*math.sin(j*math.tau/64)) for j in range(4096)))
        p=replace(p,pcm_assets=(a,long),end_sample=11750)
        def choose_long(candidates,usage,budget):
            return {0:1,1:1},[1],{'forced_for_test':True}
        with patch('opn2_target_vgm.ADPCM_B_DRAM_BUDGET',2048),patch('pcm_target_budget.fit_bank',side_effect=choose_long):
            _,_,losses,stats=project_pcm(p,'opna',force=True)
        self.assertEqual(losses['msm6258_replacement_rate_clamped_playbacks'],1)
        self.assertGreater(stats['runs'][0]['required_delta_n'],65535)
        self.assertEqual(stats['runs'][0]['delta_n'],65535)
        self.assertGreater(stats['runs'][0]['valid_end_error_samples'],0)

    def test_long_asset_splits_after_padding_within_budget(self):
        p=performance((0,));a=replace(p.pcm_assets[0],end_sample=1000,
            samples=tuple(round(12000*math.sin(j*math.tau/64)) for j in range(355)))
        p=replace(p,pcm_assets=(a,),end_sample=1000)
        with patch('opn2_target_vgm.ADPCM_B_DRAM_BUDGET',64):
            _,_,_,stats=project_pcm(p,'opna',force=True)
        self.assertLessEqual(stats['ram_used_bytes'],64)
        self.assertGreater(stats['playbacks'],1)
        self.assertEqual(stats['runs'][0]['start_sample'],0)
        self.assertEqual(stats['runs'][-1]['end_sample'],1000)
        self.assertTrue(all(r['bytes']%32==0 and r['bytes']<=64 for r in stats['runs']))

    def test_authored_opm_msm_source_publishes_bounded_cartridge_variants(self):
        from test_native_imports import vgm
        from test_native_source_music import opm_setup
        from test_export_mgs_variants import variant_pass,assert_profiles
        commands=opm_setup()+bytes.fromhex('54 08 78 b7 00 01 b7 00 02')
        for value in (0x12,0x34,0x87,0xab)*8:
            commands+=bytes((0xb7,1,value,0x61,8,0))
        commands+=bytes.fromhex('b7 00 01 54 08 00')
        raw=vgm(commands,{0x30:3579545,0x90:11289600},{0x94:4})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'song.vgm';source.write_bytes(raw);out=root/'out'
            rows=variant_pass(source,out,force=True)
            self.assertEqual(rows[0]['status'],'success',rows)
            report=assert_profiles(self,out,('makoto','sfg01_makoto','sfg01_msxaudio','layered'))
            for profile in ('makoto','sfg01_makoto','sfg01_msxaudio','layered'):
                pcm=report['summaries'][profile]['plan']['pcm']
                self.assertEqual(pcm['encoder_path'],'decoded_msm6258_budget_bank')
                self.assertGreater(pcm['playbacks'],0)
                self.assertLessEqual(pcm['ram_used_bytes'],262144)
            import json
            native=json.loads((out/'_diagnostics/song/vgm_variants/native/song.native_music.json').read_text())
            self.assertTrue(native['pcm_assets'])
            self.assertEqual(native['pcm_assets'][0]['start_sample'],0)
            self.assertEqual(native['pcm_assets'][0]['rate_hz'],11025)

    def test_stream_asset_over_budget_uses_chunked_blocks_without_replacement(self):
        d=NativeDevice('msm6258:0','msm6258',0,8000000)
        samples=tuple(((j*2654435761)>>8)%20001-10000 for j in range(600000))
        asset=NativePCM('stream',d.device_id,0,1693440,15625,samples,(0,),
            (('pan',0),('policy_reasons',('irregular_byte_supply',))))
        p=NativePerformance((d,),(),(),(),(),(),1693440,'','',pcm_assets=(asset,))
        rows,prefix,losses,stats=project_pcm(p,'y8950')
        self.assertEqual(stats['delivery'],'chunked_stream');self.assertEqual(stats['blocks'],2)
        self.assertEqual(stats['ram_used_bytes'],262144);self.assertGreater(stats['dram_bytes'],262144)
        self.assertEqual(prefix[2],0x88);self.assertEqual(int.from_bytes(prefix[3:7],'little'),262144+8)
        uploads=[r for r in rows if r['command'][0]==0x67]
        self.assertEqual(len(uploads),1)
        self.assertEqual(int.from_bytes(uploads[0]['command'][3:7],'little'),37856+8)
        self.assertEqual(losses['msm6258_stream_irregular_byte_supply'],1)
        self.assertEqual(losses['msm6258_stream_block_uploads'],1)
        self.assertFalse(losses['msm6258_budget_reused_playbacks'])
        self.assertEqual([r['block'] for r in stats['runs']],[0,0,0,0,1])
        self.assertTrue(all(not r['budget_replaced'] for r in stats['runs']))
        # With a song loop inside the stream, the first chunk at or after the
        # loop point opens a fresh image whose upload row sits at that chunk,
        # inside the looped region.
        p2=NativePerformance((d,),(),(),(),(),(),1693440,'','',
            song_loop_sample=850000,pcm_assets=(asset,))
        rows2,_,_,stats2=project_pcm(p2,'y8950')
        starts=[r['start_sample'] for r in stats2['runs']]
        self.assertIn(850000,starts)
        at=starts.index(850000)
        self.assertGreater(stats2['runs'][at]['block'],stats2['runs'][at-1]['block'])
        self.assertTrue(any(r['command'][0]==0x67 and r['sample']==850000 for r in rows2))

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
