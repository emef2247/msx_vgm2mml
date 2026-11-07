"""PCM target content edits and inherited OPN2 inventory parity."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from native_music import NativeDevice,NativePCM,NativePerformance
from native_source_music import build_native_performance
from musical_pcm_target import project_pcm
from musical_variants import export_variants
from native_imports.source import analyze_source
from opn2_target_vgm import project_dac
from test_native_pcm import block
from test_opn2_native import vgm
from test_nesapu_dpcm import make_vgm as nes_vgm,fds_note,wait


class MusicalPCMTargetTests(unittest.TestCase):
    def test_opn2_inventory_and_rate_match_inherited_decoded_timeline(self):
        raw=vgm(block(0,bytes(range(64)))+bytes.fromhex('52 2b 80 e0 00 00 00 00')+b'\x82'*64+bytes.fromhex('52 2b 00'))
        with tempfile.TemporaryDirectory() as tmp:
            p=build_native_performance(raw,tmp,'pcm')
            bundle=analyze_source(raw,Path(tmp)/'legacy','pcm')
            for target in ('opna','y8950'):
                rows,prefix,_,stats=project_pcm(p,target)
                old,oldprefix,_,oldstats,_=project_dac(bundle['analyses']['opn2'],source_end=p.end_sample,raw=raw,events=bundle['events'],dac_target=target)
                self.assertEqual(prefix,oldprefix)
                actual=[(r['sample'],r['command']) for r in rows]
                expected=[(r['source_vgmticks'],bytes((r['target_command'],r['target_register'],r['target_data']))) for r in old]
                self.assertEqual(actual,expected)
                self.assertEqual(stats['dram_bytes'],oldstats['dram_bytes'])
            edited=replace(p,pcm_assets=(replace(p.pcm_assets[0],samples=(0,)*len(p.pcm_assets[0].samples)),))
            self.assertNotEqual(project_pcm(p,'opna')[1],project_pcm(edited,'opna')[1])

    def test_impossible_dram_budget_fails_without_silently_dropping_playback(self):
        from test_musical_fm_target import performance
        from musical_variants import project_variant
        from unittest.mock import patch
        p=performance()
        a=NativePCM('pcm','source',10,90,44100,(0,)*80,
            parameters=(('dac_timeline',tuple((at,i,None,None) for i,at in enumerate(range(10,90,2)))),))
        p=replace(p,pcm_assets=(a,))
        with patch('opn2_target_vgm.ADPCM_B_DRAM_BUDGET',1):
            with self.assertRaisesRegex(ValueError,'DRAM'):
                project_variant(p,'makoto')
            with self.assertRaisesRegex(ValueError,'DRAM'):
                project_variant(p,'makoto',force=True)

    def test_both_cartridges_use_independent_256_kib_budgets(self):
        d=NativeDevice('pcm','nesapu',0,1789773)
        a=NativePCM('a','pcm',0,64,44100,(0,)*64)
        p=NativePerformance((d,),(),(),(),(),(),64,'','',pcm_assets=(a,))
        for target in ('opna','y8950'):
            _,_,_,stats=project_pcm(p,target)
            self.assertEqual(stats['ram_budget_bytes'],262144)
            self.assertLessEqual(stats['ram_used_bytes'],262144)

    def test_native_opna_packet_cannot_exceed_cartridge_budget(self):
        from native_music import NativePacket
        from test_musical_fm_target import performance
        from musical_variants import project_variant
        import struct
        p=performance()
        data=block(0x81,struct.pack('<II',262144,262140)+b'12345678')
        packet=NativePacket('bank',0,0,data.hex(),'opna','data_block')
        p=replace(p,pcm_packets=(packet,))
        with self.assertRaisesRegex(ValueError,'256 KiB'):
            project_variant(p,'makoto')
        _,prefix,losses,_=project_variant(p,'makoto',force=True)
        self.assertFalse(prefix)
        self.assertEqual(losses['native_opna_adpcm_capacity_lane_omitted'],1)

    def test_pcm_crossing_song_loop_restarts_inside_loop_in_both_renderers(self):
        raw=vgm(block(0,bytes(range(64)))+bytes.fromhex('52 2b 80 e0 00 00 00 00')+b'\x82'*64+bytes.fromhex('52 2b 00'))
        with tempfile.TemporaryDirectory() as tmp:
            p=replace(build_native_performance(raw,tmp,'loop'),song_loop_sample=64)
            rows,_,_,stats=project_pcm(p,'opna')
            triggers=[row['sample'] for row in rows if row['command']==bytes((0x57,0,0xa0))]
            self.assertEqual(triggers,[0,64])
            self.assertEqual(stats['loop_run_splits'],1)
        d=NativeDevice('nes','nesapu',0,1789773)
        a=NativePCM('a','nes',0,128,44100,(1000,)*128)
        p=NativePerformance((d,),(),(),(),(),(),128,'','',song_loop_sample=64,pcm_assets=(a,))
        rows,_,_,_=project_pcm(p,'y8950')
        triggers=[row['sample'] for row in rows if row['command']==bytes((0x5c,7,0x80))]
        self.assertEqual(triggers,[0,64])

    def test_opn2_overflow_reuses_bank_without_losing_playback_times(self):
        from unittest.mock import patch
        import struct
        payload=bytes(range(64))+bytes(255-value for value in range(64))
        raw=vgm(block(0,payload)+bytes.fromhex('52 2b 80 e0 00 00 00 00')+b'\x82'*64+
            bytes.fromhex('61 58 02 e0 40 00 00 00')+b'\x82'*64+bytes.fromhex('52 2b 00'))
        with tempfile.TemporaryDirectory() as tmp:
            p=build_native_performance(raw,tmp,'bank')
            for target,constant,opcode,startreg,startvalue in (('opna','ADPCM_B_DRAM_BUDGET',0x57,0,0xa0),('y8950','Y8950_RAM_BUDGET',0x5c,7,0x80)):
                with patch('opn2_target_vgm.'+constant,32):
                    rows,_,losses,stats=project_pcm(p,target)
                starts=[row['sample'] for row in rows if row['command']==bytes((opcode,startreg,startvalue))]
                self.assertEqual(starts,[0,728])
                self.assertLessEqual(stats['dram_bytes'],32)
                self.assertEqual(stats['playbacks'],2)
                self.assertEqual(stats['bank_budget']['omitted_playback_count'],0)
                self.assertEqual(stats['bank_budget']['forced_playback_count'],1)
                self.assertEqual(losses['dac_budget_reused_playbacks'],1)

    def test_authored_pcm_needs_no_original_transport_packets(self):
        d=NativeDevice('nes','nesapu',0,1789773)
        a=NativePCM('a','nes',0,128,22050,tuple(1000 if i%2 else -1000 for i in range(64)))
        p=NativePerformance((d,),(),(),(),(),(),128,'','',pcm_assets=(a,))
        for target,blocktype,opcode in (('opna',0x81,0x57),('y8950',0x88,0x5c)):
            rows,prefix,_,stats=project_pcm(p,target)
            self.assertEqual(prefix[:3],bytes((0x67,0x66,blocktype)))
            self.assertTrue(all(row['command'][0]==opcode for row in rows))
            self.assertEqual(stats['playbacks'],1)
            self.assertTrue(any(row['sample']==128 and row['order']==-1 for row in rows))

    def test_fds_wave_content_reaches_both_fm_cartridge_profiles(self):
        raw=nes_vgm(fds_note()+wait(1470))
        with tempfile.TemporaryDirectory() as tmp:
            p=build_native_performance(raw,Path(tmp)/'native','fds')
            self.assertTrue(any('waveform_u6' in dict(v.parameters) for v in p.voices))
            results=export_variants(p,Path(tmp)/'target','fds',force=True)
            for profile in ('sfg01','makoto'):
                self.assertEqual(results[profile]['status'],'success',results[profile])
                self.assertTrue(results[profile]['losses']['fds_64_to_32_wave_cells'])


if __name__=='__main__':unittest.main()
