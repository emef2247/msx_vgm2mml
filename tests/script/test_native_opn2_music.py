"""OPN2 source-native units, typed controls and exact reference timing."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from native_music import NativeDevice
from native_registers import decode_control,encode_control
from native_imports.vgm_timing import CommandTime,command_times
from native_source_music import build_native_performance
from native_vgm import write_native_vgm
from test_native_imports import vgm,block


def setup():
    return bytes.fromhex('52 b0 07 52 b4 c0 52 a4 22 52 a0 69')+b''.join(
        bytes((0x52,base+4*i,value)) for i in range(4)
        for base,value in ((0x30,1),(0x40,20),(0x50,31),(0x60,0),(0x70,0),(0x80,15),(0x90,0)))


class NativeOpn2MusicTests(unittest.TestCase):
    def build(self,body):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        raw=vgm(body,{0x2c:7670454})
        return build_native_performance(raw,tmp.name,'authored'),Path(tmp.name),raw

    def test_native_codec_preserves_both_instances_ports_and_packed_bytes(self):
        for cmd in (0x52,0x53,0xa2,0xa3):
            d=NativeDevice('opn2:'+str(int(cmd>=0xa2)),'opn2',int(cmd>=0xa2),7670454)
            for register in range(256):
                for value in (0,0x35,0xff):
                    raw=bytes((cmd,register,value))
                    c=decode_control(d,CommandTime(0,cmd,0,0),raw)
                    self.assertEqual(encode_control(c,d),raw)

    def test_pitch_volume_midnote_voice_and_partial_keys_stay_one_unit(self):
        p,_,_=self.build(setup()+bytes.fromhex('52 28 f0 62 52 40 30 52 28 70 62 52 b0 06 62 52 28 00'))
        self.assertEqual(len(p.units),1)
        u=p.units[0]
        self.assertGreater(len(u.voice_curve),1)
        self.assertAlmostEqual(u.pitch_curve[0][1],250.71,delta=.1)
        self.assertTrue(any(dict(c.parameters).get('key_mask')==7 for c in p.controls))
        self.assertNotIn('opn2_projection_not_implemented',[d[0] for d in p.decisions])
        self.assertEqual(u.end_sample,2205)

    def test_reference_vgm_preserves_inline_dac_wait_and_bytes(self):
        body=block(0,bytes((128,200,100)))+bytes.fromhex('52 2b 80 e0 00 00 00 00 83 84 85 52 2b 00 62')
        p,root,source=self.build(body)
        target=root/'reference.vgm';write_native_vgm(p,target)
        raw=target.read_bytes()
        def data(data):
            return [(e.vgmticks,data[e.address:e.address+(1 if 0x80<=e.command<=0x8f else 3)])
                for e in command_times(data) if e.command in (0x52,0x80,0x83,0x84,0x85)]
        self.assertEqual(data(raw),data(source))
        self.assertEqual(tuple(command_times(raw))[-1].vgmticks,p.end_sample)
        self.assertEqual(int.from_bytes(raw[0x2c:0x30],'little'),7670454)

    def test_same_sample_zero_gate_does_not_cancel_following_positive_gate(self):
        from musical_fm_target import project_fm
        p,_,_=self.build(setup()+bytes.fromhex('52 28 f0 52 28 00 52 28 f0 62 52 28 00'))
        self.assertEqual([(u.start_sample,u.end_sample) for u in p.units],[(0,0),(0,735)])
        rows,_,_=project_fm(p,'opm',3579545,force=True)
        keys=[(r['sample'],r['command'][2]) for r in rows if r['command'][1]==8]
        self.assertEqual(keys,[(0,0x78),(0,0),(0,0x78),(735,0)])

    def test_same_sample_voice_after_key_is_retained_and_projection_loss_is_explicit(self):
        from musical_fm_target import project_fm
        before,_,_=self.build(setup()+bytes.fromhex('52 50 01 52 28 f0 62 52 28 00'))
        after,_,_=self.build(setup()+bytes.fromhex('52 28 f0 52 50 01 62 52 28 00'))
        self.assertFalse(dict(before.units[0].parameters)['onset_controls_after_key'])
        self.assertTrue(dict(after.units[0].parameters)['onset_controls_after_key'])
        self.assertTrue(any(c.kind=='fm_operator_attack' for c in after.controls))
        self.assertGreater(project_fm(after,'opm',3579545)[1]['fm_same_sample_onset_control_order_collapsed'],0)

    def test_dac_ownership_does_not_create_an_audible_fm_unit_on_channel_six(self):
        p,_,_=self.build(bytes.fromhex('53 b2 07 53 a6 22 53 a2 69 52 2b 80 52 28 f6 62 52 2b 00 62 52 28 06'))
        self.assertEqual([(u.start_sample,u.end_sample) for u in p.units],[(735,1470)])


if __name__=='__main__':unittest.main()
