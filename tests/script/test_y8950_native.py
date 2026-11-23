"""Y8950 (MSX-AUDIO) native source decoding: codec and musical gates."""
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


def write(register,value):
    return bytes((0x5c,register,value))


class Y8950CodecTests(unittest.TestCase):
    def test_all_registers_round_trip(self):
        device=NativeDevice('y8950:0','y8950',0,3579545)
        for register in range(256):
            for value in (0,1,0x35,0x7f,0x80,0xff):
                raw=bytes((0x5c,register,value));event=CommandTime(0,0x5c,11,0,7)
                control=decode_control(device,event,raw)
                self.assertEqual(encode_control(control,device),raw,(register,value))


class Y8950SourceMusicTests(unittest.TestCase):
    def build(self,raw):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        return build_native_performance(raw,temporary.name,'authored')

    def test_melody_gate_pitch_volume_and_voice(self):
        body=b''.join((
            write(0x20,0x01),write(0x40,0x1d),write(0x60,0xf3),write(0x80,0x23),
            write(0x23,0x02),write(0x43,0x0c),write(0x63,0xf2),write(0x83,0x21),
            write(0xc0,0x0e),write(0xa0,0x44),write(0xb0,0x32),
            b'\x62',write(0xb0,0x12)))
        result=self.build(vgm(body,{0x58:3579545}))
        self.assertEqual(len(result.units),1)
        unit=result.units[0]
        self.assertEqual((unit.section,unit.channel),('fm',0))
        self.assertEqual((unit.start_sample,unit.end_sample),(0,735))
        self.assertEqual(len(unit.pitch_curve),1)
        self.assertAlmostEqual(unit.pitch_curve[0][1],439.99,places=1)
        self.assertEqual(unit.volume_curve,((0,12),))
        voice=dict(next(v for v in result.voices
            if v.voice_id==unit.voice_curve[0][1]).parameters)
        self.assertEqual((voice['feedback'],voice['connection']),(7,0))
        ops=[dict(op) for op in voice['operators']]
        self.assertEqual(ops[0]['total_level'],29)
        self.assertEqual(ops[1]['total_level'],0)
        self.assertEqual((ops[0]['multiple'],ops[1]['multiple']),(1,2))
        self.assertEqual((ops[1]['attack'],ops[1]['sustain_level']),(15,2))

    def test_rhythm_sd_hit_with_register_volume(self):
        body=b''.join((write(0x54,0x10),write(0xbd,0xe0),b'\x62',
            write(0xbd,0xe8),b'\x62',write(0xbd,0xe0)))
        result=self.build(vgm(body,{0x58:3579545}))
        self.assertEqual(len(result.percussion),1)
        hit=result.percussion[0]
        self.assertEqual(hit.instrument_family,'SD')
        self.assertEqual(hit.volume_curve,((735,16),))
        self.assertEqual((hit.start_sample,hit.stop_sample),(735,1470))


if __name__=='__main__':
    unittest.main()
