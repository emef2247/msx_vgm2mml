"""Authored decoded PCM evidence, independent of target cartridge encoders."""
import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'py'), str(Path(__file__).parent)]
from native_music import NativePCM, NativeDevice, NativePerformance
from native_source_music import build_native_performance
from test_opn2_native import vgm
from test_nesapu import make_vgm as nes_vgm, write as nes_write, wait
from test_huc6280 import make_vgm as huc_vgm, write as huc_write


def block(kind, payload):
    return bytes((0x67,0x66,kind)) + struct.pack('<I',len(payload)) + payload


class NativePCMTests(unittest.TestCase):
    def build(self, raw, folder):
        source = folder/'source.vgm'
        source.write_bytes(raw)
        performance = build_native_performance(source,folder/'out','source')
        self.assertEqual(source.read_bytes(),raw)
        return performance

    def test_supply_timing_retains_same_value_stream_samples_without_duplicating_values(self):
        raw=vgm(block(0,b'\x80\x80\x80')+bytes.fromhex('52 2b 80 e0 00 00 00 00 82 82 82 52 2b 00'))
        with tempfile.TemporaryDirectory() as tmp:
            p=self.build(raw,Path(tmp));asset=p.pcm_assets[0]
            timeline=dict(asset.parameters)['dac_timeline']
            self.assertEqual([row[0] for row in timeline],[0,2,4])
            self.assertEqual([row[2:] for row in timeline],[(0,1),(1,1),(2,1)])
            self.assertTrue(all(len(row)==4 for row in timeline))
            self.assertEqual(asset.samples,(0,)*6)

    def test_signed16_immutable_and_timeline_validation(self):
        for samples in ([0], (32768,), (-32769,)):
            with self.assertRaises(ValueError):
                NativePCM('a','opn2:0',0,1,44100,samples)
        with self.assertRaises(ValueError):
            NativePCM('a','opn2:0',0,1,float('nan'),(0,))
        asset = NativePCM('a','opn2:0',0,2,44100,(0,1))
        with self.assertRaises(ValueError):
            NativePerformance((NativeDevice('opn2:0','opn2',0,1),),(),(),(),(),(),
                              1,'','',pcm_assets=(asset,))

    def test_direct_dac_gates_holds_and_same_time_order(self):
        raw = vgm(bytes((0x52,0x2a,0, 0x52,0x2b,128)) + wait(2) +
            bytes((0x52,0x2a,255, 0x52,0x2a,128)) + wait(3) +
            bytes((0x52,0x2b,0, 0x52,0x2a,255)) + wait(4))
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            with patch('opn2_target_vgm._encode_adpcm_b',side_effect=AssertionError('target encoding')):
                p=self.build(raw,folder)
            self.assertEqual(len(p.pcm_assets),1)
            asset=p.pcm_assets[0]
            self.assertEqual((asset.start_sample,asset.end_sample),(0,5))
            self.assertEqual(asset.samples,(-32768,-32768,0,0,0))
            self.assertEqual(asset.rate_hz,44100)
            data=json.loads((folder/'out/source.native_music.json').read_text())
            self.assertEqual(data['pcm_assets'][0]['samples'],list(asset.samples))
            with (folder/'out/source.native_music.pcm_assets.csv').open() as stream:
                records=list(csv.DictReader(stream))
            self.assertEqual(json.loads(records[0]['samples']),list(asset.samples))
            self.assertTrue(asset.source_event_ids)

    def test_manual_stream_and_original_packets_retained(self):
        raw=vgm(block(0,b'\x00\xff') + bytes((0x52,0x2b,128,0xe0,0,0,0,0,0x82,0x83)) +
                bytes((0x52,0x2b,0)))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            self.assertEqual(p.pcm_assets[0].samples,(-32768,-32768,32512,32512,32512))
            self.assertTrue(p.pcm_packets)
            self.assertTrue(any(x.kind=='data_block' for x in p.pcm_packets))

    def test_autonomous_stream_is_decoded_without_projection(self):
        setup=bytes((0x90,0,2,0,0x2a,0x91,0,0,1,0,0x92,0))+struct.pack('<I',22050)
        start=bytes((0x93,0))+struct.pack('<I',0)+bytes((1,))+struct.pack('<I',2)
        raw=vgm(block(0,b'\x00\xff')+bytes((0x52,0x2b,128))+setup+start+wait(4)+bytes((0x52,0x2b,0)))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            self.assertEqual(p.pcm_assets[0].samples,(-32768,-32768,32512,32512))

    def test_manual_stream_without_observed_enable_retains_explicit_intent(self):
        raw=vgm(block(0,b'\x00')+bytes((0xe0,0,0,0,0,0x82)))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            self.assertEqual(p.pcm_assets[0].samples,(-32768,-32768))
            self.assertEqual(dict(p.pcm_assets[0].parameters)['enable_basis'],'stream_playback_intent')
            self.assertTrue(any(d[0]=='opn2_pcm_stream_intent_without_observed_enable' for d in p.decisions))

    def test_manual_stream_keeps_second_opn2_device_identity(self):
        setup=bytes((0x90,0,0x82,0,0x2a,0x91,0,0,1,0))
        raw=vgm(block(0,b'\xff')+bytes((0xa2,0x2b,128))+setup+
                bytes((0xe0,0,0,0,0,0x82,0xa2,0x2b,0)))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            self.assertEqual(len(p.pcm_assets),1)
            self.assertEqual(p.pcm_assets[0].device_id,'opn2:1')
            self.assertEqual(p.pcm_assets[0].samples,(32512,32512))

    def test_nes_dpcm_has_bit_samples_and_saturates_without_wrapping(self):
        raw=nes_vgm(block(0xc2,struct.pack('<H',0xc000)+b'\xff')+
            nes_write(16,15)+nes_write(17,125)+nes_write(18,0)+nes_write(19,0)+
            nes_write(21,16)+wait(100))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            asset=p.pcm_assets[0]
            self.assertEqual(asset.device_id,'nesapu:0')
            self.assertEqual(asset.samples,(32256,)*8)
            self.assertAlmostEqual(asset.rate_hz,1789773/54)
            unit=next(u for u in p.units if u.section=='dpcm')
            self.assertEqual(unit.voice_curve[0][0],0)

    def test_nes_missing_sample_data_is_reported(self):
        raw=nes_vgm(nes_write(16,15)+nes_write(19,0)+nes_write(21,16)+wait(100))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            self.assertFalse(p.pcm_assets)
            self.assertTrue(any(d[0]=='nes_pcm_missing_sample_bytes' for d in p.decisions))

    def test_fds_voice_retains_waveform_content(self):
        wave=tuple(range(64))
        commands=nes_write(0x29,128)+b''.join(nes_write(0x40+i,v) for i,v in enumerate(wave))
        commands+=nes_write(0x29,0)+nes_write(0x20,160)+nes_write(0x22,100)+nes_write(0x23,1)+wait(735)
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(nes_vgm(commands),Path(temporary))
            voice=next(v for v in p.voices if v.section=='fds')
            self.assertEqual(dict(voice.parameters)['waveform_u6'],wave)

    def test_huc_noise_retains_native_clock_rate(self):
        raw=huc_vgm(huc_write(1,255)+huc_write(0,4)+huc_write(5,255)+
            huc_write(4,159)+huc_write(7,0x9f)+wait(10))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            voice=next(v for v in p.voices if v.section=='noise')
            self.assertAlmostEqual(dict(voice.parameters)['native_noise_rate_hz'],3579545/64)

    def test_huc_dda_source_levels_and_balance_are_decoded(self):
        raw=huc_vgm(huc_write(1,255)+huc_write(0,0)+huc_write(5,255)+
            huc_write(4,223)+huc_write(6,0)+wait(2)+huc_write(6,31)+wait(3)+huc_write(4,0))
        with tempfile.TemporaryDirectory() as temporary:
            p=self.build(raw,Path(temporary))
            self.assertEqual(len(p.pcm_assets),1)
            asset=p.pcm_assets[0]
            self.assertEqual(asset.samples,(-32768,-32768,30720,30720,30720))
            self.assertEqual(dict(asset.parameters)['channel'],0)


if __name__=='__main__':
    unittest.main()
