"""The opl3 profile: YMF262 as the primary cartridge target."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from musical_variants import export_variants
from native_source_music import build_native_performance
from test_native_imports import vgm


def opll(register,value):
    return bytes((0x51,register,value))


def ymf262(register,value,bank=0):
    return bytes((0x5f if bank else 0x5e,register,value))


def opm(register,value):
    return bytes((0x54,register,value))


class Opl3ProfileTests(unittest.TestCase):
    def build(self,raw):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        return build_native_performance(raw,temporary.name,'song'),temporary.name

    def export(self,performance,folder):
        return export_variants(performance,folder,'song')

    def test_table_carries_realchip_ws(self):
        from musical_opl3_target import _table
        _doc, table = _table()
        by_name = {v['name']: v for v in table.values()}
        self.assertEqual([op['ws'] for op in by_name['AcoustBass']['ops']],
                         [6, 2])
        self.assertEqual([op['ws'] for op in by_name['Clarinet']['ops']],
                         [7, 3])
        self.assertEqual([op['ws'] for op in by_name['Violin']['ops']],
                         [0, 0])

    def test_opll_melody_and_rhythm_project_to_opl3(self):
        body=b''.join((
            opll(0x30,0x73),                 # instrument 7, volume 3
            opll(0x37,0x01),                 # SD attenuation 1 (low nibble)
            opll(0x10,0x22),opll(0x20,0x19), # 440 Hz gate on (fnum 290, block 4)
            opll(0x0e,0x20),opll(0x0e,0x28), # rhythm mode, SD hit
            b'\x62',
            opll(0x0e,0x20),opll(0x20,0x09)))# SD off, gate end
        performance,folder=self.build(vgm(body,{0x10:3579545,0x5c:14318180}))
        results=self.export(performance,folder+'/out')
        result=results['opl3']
        self.assertEqual(result['status'],'success',result.get('reason'))
        import struct
        written=open(result['path'],'rb').read()
        # The YMF262 clock belongs at header offset 0x5c per the VGM
        # specification; 0x64 is the YMF271 field. A player that finds
        # no clock at 0x5c treats the file as having no OPL3 chip.
        self.assertEqual(struct.unpack_from('<I',written,0x5c)[0],14318180)
        self.assertEqual(struct.unpack_from('<I',written,0x64)[0],0)
        self.assertEqual(results['scc_opl3']['status'],'unavailable')
        back,_=self.build(open(result['path'],'rb').read())
        self.assertEqual(len(back.units),1)
        unit=back.units[0]
        self.assertEqual((unit.section,unit.channel),('fm',0))
        self.assertAlmostEqual(unit.pitch_curve[0][1],440.0,delta=2.0)
        # carrier TL = VOL << 2 plus the voice's level trim
        # (the fitted Trumpet trim is 0; see OPL3_FIT)
        self.assertEqual(unit.volume_curve[0][1],12)
        voice=dict(next(v for v in back.voices
            if v.voice_id==unit.voice_curve[0][1]).parameters)
        self.assertEqual(voice['feedback'],7)         # established Trumpet
        self.assertEqual(len(back.percussion),1)
        self.assertEqual(back.percussion[0].instrument_family,'SD')
        # att << 2 plus the OPL3 rhythm re-anchor shift for SD (+2 TL;
        # see _RHYTHM_TL_SHIFT in musical_opl3_target.py)
        self.assertEqual(back.percussion[0].volume_curve[0][1],6)

    def test_opll_shared_control_does_not_leak_into_opl3(self):
        # A source write to OPLL register 0x0F (a shared, non-musical
        # control) belongs to the native lane; when the OPLL device is
        # consumed by the OPL3 projection it must not appear in the
        # output as a YM2413 (0x51) write.
        body=b''.join((
            opll(0x0f,0x00),
            opll(0x30,0x73),opll(0x10,0x22),opll(0x20,0x19),
            b'\x62',opll(0x20,0x09)))
        performance,folder=self.build(vgm(body,{0x10:3579545,0x5c:14318180}))
        result=self.export(performance,folder+'/out')['opl3']
        self.assertEqual(result['status'],'success',result.get('reason'))
        import csv, struct
        written=open(result['path'],'rb').read()
        self.assertEqual(struct.unpack_from('<I',written,0x10)[0],0)
        writes_path=Path(result['path']).with_suffix('.writes.csv')
        commands=[row['command_hex'] for row in
                  csv.DictReader(writes_path.open())]
        self.assertFalse(any(c.startswith('51') for c in commands),
                         commands)

    def test_ymf262_four_op_source_reemits(self):
        body=b''.join((
            ymf262(0x05,0x01,1),ymf262(0x04,0x01,1),
            ymf262(0x20,0x01),ymf262(0x40,10),ymf262(0x60,0xf0),ymf262(0x80,0x00),
            ymf262(0x21,0x02),ymf262(0x41,20),ymf262(0x61,0xf0),ymf262(0x81,0x00),
            ymf262(0x23,0x03),ymf262(0x43,30),ymf262(0x63,0xf0),ymf262(0x83,0x00),
            ymf262(0x24,0x04),ymf262(0x44,5),ymf262(0x64,0xf0),ymf262(0x84,0x00),
            ymf262(0xc0,0x30),ymf262(0xc1,0x30),
            ymf262(0xa0,0x44),ymf262(0xb0,0x32),
            b'\x62',ymf262(0xb0,0x12)))
        performance,folder=self.build(vgm(body,{0x5c:14318180}))
        result=self.export(performance,folder+'/out')['opl3']
        self.assertEqual(result['status'],'success',result.get('reason'))
        back,_=self.build(open(result['path'],'rb').read())
        self.assertEqual(len(back.units),1)
        unit=back.units[0]
        voice=dict(next(v for v in back.voices
            if v.voice_id==unit.voice_curve[0][1]).parameters)
        ops=[dict(o) for o in voice['operators']]
        self.assertEqual([o['multiple'] for o in ops],[1,2,3,4])
        self.assertEqual(unit.volume_curve,((0,5),))

    def test_opm_source_is_unavailable(self):
        body=b''.join((
            opm(0x20,0xc7),opm(0x38,0x00),opm(0x40,0x00),opm(0x60,0x00),
            opm(0x28,0x4a),opm(0x08,0x78),b'\x62',opm(0x08,0x00)))
        performance,folder=self.build(vgm(body,{0x30:3579545,0x5c:14318180}))
        result=self.export(performance,folder+'/out')['opl3']
        self.assertEqual(result['status'],'unavailable')
        self.assertIn('opm',result['reason'])

    def test_psg_opl3_waits_for_the_waveform_projection(self):
        body=b''.join((
            opll(0x30,0x73),opll(0x10,0x22),opll(0x20,0x19),
            b'\x62',opll(0x20,0x09)))
        performance,folder=self.build(vgm(body,{0x10:3579545,0x5c:14318180}))
        result=self.export(performance,folder+'/out')['psg_opl3']
        self.assertEqual(result['status'],'unavailable')
        self.assertIn('waveform',result['reason'])


if __name__=='__main__':
    unittest.main()
