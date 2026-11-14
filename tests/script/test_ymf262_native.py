"""YMF262 (OPL3) native source decoding: codec and musical gates."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from native_music import NativeDevice
from native_imports.vgm_timing import CommandTime
from native_registers import decode_control,encode_control
from native_source_music import build_native_performance
from test_native_imports import vgm


def write(register,value,bank=0):
    return bytes((0x5f if bank else 0x5e,register,value))


class Ymf262CodecTests(unittest.TestCase):
    def test_all_registers_round_trip(self):
        device=NativeDevice('ymf262:0','ymf262',0,14318180)
        for command in (0x5e,0x5f):
            for register in range(256):
                for value in (0,1,0x35,0x7f,0x80,0xff):
                    raw=bytes((command,register,value));event=CommandTime(0,command,11,0,7)
                    control=decode_control(device,event,raw)
                    self.assertEqual(encode_control(control,device),raw,(command,register,value))


class Ymf262SourceMusicTests(unittest.TestCase):
    def build(self,raw):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        return build_native_performance(raw,temporary.name,'authored')

    def test_two_op_gate_pitch_volume_and_voice(self):
        body=b''.join((
            write(0x20,0x01),write(0x40,0x1d),write(0x60,0xf3),write(0x80,0x23),
            write(0x23,0x02),write(0x43,0x0c),write(0x63,0xf2),write(0x83,0x21),
            write(0xc0,0x3e),write(0xa0,0x44),write(0xb0,0x32),
            b'\x62',write(0xb0,0x12)))
        result=self.build(vgm(body,{0x64:14318180}))
        self.assertEqual(len(result.units),1)
        unit=result.units[0]
        self.assertEqual((unit.section,unit.channel),('fm',0))
        self.assertEqual((unit.start_sample,unit.end_sample),(0,735))
        self.assertAlmostEqual(unit.pitch_curve[0][1],440.0,delta=2.0)
        self.assertEqual(unit.volume_curve,((0,12),))
        voice=dict(next(v for v in result.voices
            if v.voice_id==unit.voice_curve[0][1]).parameters)
        self.assertEqual(voice['feedback'],7)
        self.assertEqual(voice['connection'],0)
        self.assertEqual((voice['left'],voice['right']),(1,1))
        ops=[dict(o) for o in voice['operators']]
        self.assertEqual([o['multiple'] for o in ops],[1,2])
        self.assertEqual(ops[1]['total_level'],0)  # carrier attenuation removed

    def test_four_op_pair_interleaves_operators(self):
        body=b''.join((
            write(0x05,0x01,1),write(0x04,0x01,1),     # OPL3 mode, pair ch0+ch1
            write(0x20,0x01),write(0x40,10),write(0x60,0xf0),write(0x80,0x00),
            write(0x21,0x02),write(0x41,20),write(0x61,0xf0),write(0x81,0x00),
            write(0x23,0x03),write(0x43,30),write(0x63,0xf0),write(0x83,0x00),
            write(0x24,0x04),write(0x44,5),write(0x64,0xf0),write(0x84,0x00),
            write(0xc0,0x30),write(0xc1,0x30),
            write(0xa0,0x44),write(0xb0,0x32),
            b'\x62',write(0xb0,0x12)))
        result=self.build(vgm(body,{0x64:14318180}))
        self.assertEqual(len(result.units),1)
        unit=result.units[0]
        self.assertEqual(unit.channel,0)
        self.assertEqual(unit.volume_curve,((0,5),))  # sole carrier is chain op 4
        voice=dict(next(v for v in result.voices
            if v.voice_id==unit.voice_curve[0][1]).parameters)
        self.assertEqual(voice['connection'],0)
        ops=[dict(o) for o in voice['operators']]
        self.assertEqual([o['multiple'] for o in ops],[1,2,3,4])

    def test_rhythm_hit(self):
        body=b''.join((
            write(0x54,0x0c),
            write(0xbd,0x20),write(0xbd,0x28),   # rhythm mode, SD on
            b'\x62',write(0xbd,0x20)))
        result=self.build(vgm(body,{0x64:14318180}))
        self.assertEqual(len(result.percussion),1)
        hit=result.percussion[0]
        self.assertEqual(hit.instrument_family,'SD')
        self.assertEqual(hit.volume_curve,((0,12),))


if __name__=='__main__':
    unittest.main()
