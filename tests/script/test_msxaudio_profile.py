"""The msxaudio profile: Y8950 FM as the primary cartridge target."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from musical_variants import export_variants, project_variant
from native_source_music import build_native_performance
from test_native_imports import vgm


def opll(register,value):
    return bytes((0x51,register,value))


def y8950(register,value):
    return bytes((0x5c,register,value))


class MsxaudioProfileTests(unittest.TestCase):
    def build(self,raw):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        return build_native_performance(raw,temporary.name,'song'),temporary.name

    def export(self,performance,folder):
        return export_variants(performance,folder,'song')

    def test_opll_melody_and_rhythm_project_to_y8950(self):
        body=b''.join((
            opll(0x30,0x73),                 # instrument 7, volume 3
            opll(0x37,0x01),                 # SD attenuation 1 (low nibble)
            opll(0x10,0x22),opll(0x20,0x19), # 440 Hz gate on (fnum 290, block 4)
            opll(0x0e,0x20),opll(0x0e,0x28), # rhythm mode, SD hit
            b'\x62',
            opll(0x0e,0x20),opll(0x20,0x09)))# SD off, gate end
        performance,folder=self.build(vgm(body,{0x10:3579545}))
        result=self.export(performance,folder+'/out')['msxaudio']
        self.assertEqual(result['status'],'success',result.get('reason'))
        back,_=self.build(open(result['path'],'rb').read())
        self.assertEqual(len(back.units),1)
        unit=back.units[0]
        self.assertEqual((unit.section,unit.channel),('fm',0))
        self.assertAlmostEqual(unit.pitch_curve[0][1],440.0,delta=2.0)
        self.assertEqual(unit.volume_curve[0][1],12)  # carrier TL = VOL << 2
        voice=dict(next(v for v in back.voices
            if v.voice_id==unit.voice_curve[0][1]).parameters)
        self.assertEqual(voice['feedback'],7)         # established Trumpet
        self.assertEqual(len(back.percussion),1)
        self.assertEqual(back.percussion[0].instrument_family,'SD')
        self.assertEqual(back.percussion[0].volume_curve[0][1],4)  # att << 2

    def test_y8950_native_source_reemits(self):
        body=b''.join((
            y8950(0x20,0x01),y8950(0x40,0x1d),y8950(0x60,0xf3),y8950(0x80,0x23),
            y8950(0x23,0x02),y8950(0x43,0x0c),y8950(0x63,0xf2),y8950(0x83,0x21),
            y8950(0xc0,0x0e),y8950(0xa0,0x44),y8950(0xb0,0x32),
            b'\x62',y8950(0xb0,0x12)))
        performance,folder=self.build(vgm(body,{0x58:3579545}))
        result=self.export(performance,folder+'/out')['msxaudio']
        self.assertEqual(result['status'],'success',result.get('reason'))
        back,_=self.build(open(result['path'],'rb').read())
        self.assertEqual(len(back.units),1)
        unit=back.units[0]
        self.assertAlmostEqual(unit.pitch_curve[0][1],439.99,places=1)
        self.assertEqual(unit.volume_curve[0][1],12)

    def test_four_op_source_is_unavailable(self):
        body=bytes.fromhex('54 20 c7 54 28 4a 54 08 78 62 54 08 00')
        performance,folder=self.build(vgm(body,{0x30:3579545}))
        with self.assertRaises(ValueError):
            project_variant(performance,'msxaudio')


if __name__=='__main__':
    unittest.main()
