"""Authored MSM4 source reconstruction; no private fixture material."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import struct
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'py'))
from native_imports import msm6258
from native_imports.vgm_timing import command_times
from native_msm6258_pcm import add_msm6258_pcm, decode_msm4


def authored_msm6258(pan=0, options=4, count=32):
    commands = bytearray((0xb7,0,1,0xb7,2,pan,0xb7,0,2))
    for i in range(count): commands.extend((0xb7,1,(i*37)&255,0x77))
    commands.extend((0xb7,0,1,0x66))
    raw=bytearray(256);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
    struct.pack_into('<I',raw,0x90,11289600);raw[0x94]=options
    raw.extend(commands);struct.pack_into('<I',raw,4,len(raw)-4)
    return bytes(raw)


class Builder:
    def __init__(self,raw,analysis=None):
        self.bundle={'analyses':{'msm6258':analysis or msm6258.analyze(raw)},'events':tuple(command_times(raw))}
        self.pcm_assets=[];self.decisions=[]
    def device(self,chip,instance=0):
        return SimpleNamespace(device_id=f'{chip}:{instance}',chip=chip)


class NativeMsm6258PcmTests(unittest.TestCase):
    def test_known_decoder_reset_and_nibble_order(self):
        self.assertEqual(decode_msm4(b'\x81'),(256,128))
        self.assertEqual(decode_msm4(b'\x00'),(0,128))
        self.assertTrue(all(-32768<=x<=32767 for x in decode_msm4(bytes(range(256)))))

    def test_exact_cadence_preserves_source_rate_pan_and_provenance(self):
        for pan in range(4):
            b=Builder(authored_msm6258(pan));add_msm6258_pcm(b)
            self.assertEqual(b.decisions,[]);self.assertEqual(len(b.pcm_assets),1)
            a=b.pcm_assets[0];analysis=b.bundle['analyses']['msm6258'];params=dict(a.parameters)
            self.assertEqual((a.start_sample,a.end_sample),(0,256))
            self.assertEqual(a.rate_hz,11025);self.assertEqual(len(a.samples),64)
            self.assertEqual(a.samples,decode_msm4(analysis.samples[0].encoded_bytes))
            self.assertEqual(params['pan'],pan);self.assertTrue(params['decoder_reset_known'])
            self.assertEqual(params['source_playback_id'],0);self.assertEqual(params['clipped_samples'],0)
            self.assertTrue(a.source_event_ids);self.assertIsNone(params['consumed_nibbles'])

    def test_adpcm3_and_12bit_are_explicitly_unresolved(self):
        for options in (0,12):
            b=Builder(authored_msm6258(options=options));add_msm6258_pcm(b)
            self.assertEqual(b.pcm_assets,[])
            self.assertTrue(any(r[0]=='msm6258_pcm_unresolved_playback' for r in b.decisions))

    def test_unknown_reset_does_not_produce_asset(self):
        raw=authored_msm6258();a=msm6258.analyze(raw)
        b=Builder(raw,replace(a,playbacks=(replace(a.playbacks[0],decoder_reset_known=False),)))
        add_msm6258_pcm(b);self.assertEqual(b.pcm_assets,[])
        self.assertIn('decoder_reset_unknown',b.decisions[-1][-1])

    def test_finite_exhaustion_does_not_invent_held_tail(self):
        raw=authored_msm6258();a=msm6258.analyze(raw)
        b=Builder(raw,replace(a,playbacks=(replace(a.playbacks[0],end_vgmticks=264),)))
        add_msm6258_pcm(b);self.assertEqual(b.pcm_assets,[])
        self.assertIn('source_gate_exceeds_finite_decoded_samples',b.decisions[-1][-1])

    def test_fractional_exhaustion_clips_at_most_one_vgm_tick(self):
        raw=authored_msm6258();a=msm6258.analyze(raw)
        p=replace(a.playbacks[0],rate_num=15625,rate_den=1,end_vgmticks=181)
        b=Builder(raw,replace(a,playbacks=(p,)));add_msm6258_pcm(b)
        self.assertEqual(len(b.pcm_assets),1)
        self.assertEqual(b.pcm_assets[0].end_sample,180)
        self.assertEqual(len(b.pcm_assets[0].samples),64)
        self.assertEqual(dict(b.pcm_assets[0].parameters)['source_gate_end_vgmticks'],181)
        self.assertIn('finite_exhaustion_endpoint_rounding',b.decisions[-1])
        b=Builder(raw,replace(a,playbacks=(replace(p,end_vgmticks=182),)))
        add_msm6258_pcm(b);self.assertFalse(b.pcm_assets)
        self.assertIn('source_gate_exceeds_finite_decoded_samples',b.decisions[-1][-1])

    def test_short_gate_clips_without_changing_native_sample(self):
        raw=authored_msm6258();a=msm6258.analyze(raw);original=a.samples[0].encoded_bytes
        b=Builder(raw,replace(a,playbacks=(replace(a.playbacks[0],end_vgmticks=248),)))
        add_msm6258_pcm(b);self.assertEqual(len(b.pcm_assets[0].samples),62)
        self.assertEqual(dict(b.pcm_assets[0].parameters)['clipped_samples'],2)
        self.assertEqual(a.samples[0].encoded_bytes,original)

if __name__=='__main__':unittest.main()
