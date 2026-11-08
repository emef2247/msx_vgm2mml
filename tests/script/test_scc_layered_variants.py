"""Authored real-SCC and FM companion projections, no private source data."""
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest

from test_musical_variants import performance
from musical_variants import export_variants, project_variant
from musical_scc_target import project_scc
from native_imports.vgm_timing import command_times


class SccLayeredTests(unittest.TestCase):
    def test_three_companions_headers_timing_and_single_psg(self):
        p=replace(performance(),song_loop_sample=1000)
        ay=performance('psg',voice={'mode':1,'hardware_envelope':False})
        p=replace(p,devices=p.devices+ay.devices,voices=p.voices+tuple(
            replace(v,voice_id='ayvoice') for v in ay.voices),units=p.units+tuple(
            replace(u,unit_id='ayunit',voice_curve=((0,'ayvoice'),)) for u in ay.units))
        with tempfile.TemporaryDirectory() as tmp:
            result=export_variants(p,tmp,'song',force=True)
            for name,opm,opna in (('scc_sfg01',True,False),('scc_makoto',False,True),('scc_layered',True,True)):
                self.assertEqual(result[name]['status'],'success',result[name])
                raw=Path(result[name]['path']).read_bytes()
                self.assertEqual(struct.unpack_from('<I',raw,0x9c)[0],1789773)
                self.assertEqual(bool(struct.unpack_from('<I',raw,0x30)[0]),opm)
                self.assertEqual(bool(struct.unpack_from('<I',raw,0x48)[0]),opna)
                self.assertEqual(struct.unpack_from('<I',raw,0x20)[0],3410)
                events=tuple(command_times(raw));self.assertEqual(events[-1].vgmticks,4410)
                self.assertTrue(any(e.command==0xd2 and e.vgmticks==1000 and raw[e.address+1:e.address+4]==bytes((3,0,0)) for e in events))
                self.assertEqual(sum(e.command==0xa0 and raw[e.address+1]==8 and raw[e.address+2]==15 for e in events),1)
            self.assertEqual(p.units[0].volume_curve,((0,15),))
            self.assertEqual(result['scc_layered']['plan']['real_scc']['fm_companion_gain'],.5)

    def test_scc_curves_and_voice_are_authoritative(self):
        p=performance();wave='00'*16+'ff'*16
        v=replace(p.voices[0],voice_id='edited',parameters=(('waveform_hex',wave),))
        u=replace(p.units[0],pitch_curve=((0,880.),),volume_curve=((0,7),),voice_curve=((0,'edited'),))
        changed=replace(p,voices=(v,),units=(u,))
        rows,_,_=project_scc(changed)
        values=lambda port,reg:[r['command'][3] for r in rows if r['command'][1:3]==bytes((port,reg))]
        self.assertEqual(values(2,0)[0],7)
        self.assertEqual(values(1,0)[0],round(1789773/(16*880)-1)&255)
        self.assertEqual(values(0,0)[0],0)
        self.assertEqual(values(0,16)[0],255)
        plain,_,_,_=project_variant(p,'sfg01',force=True)
        layered,_,_,_=project_variant(p,'scc_sfg01',force=True)
        tl=lambda rr:next(r['command'][2] for r in rr if r['command'][:2]==bytes((0x54,0x60)))
        self.assertGreater(tl(layered),tl(plain))

    def test_shared_wave_changes_at_same_sample_and_conflicts(self):
        p=performance();v=replace(p.voices[0],voice_id='new',parameters=(('waveform_hex','01'*32),))
        a=replace(p.units[0],channel=3,voice_curve=((0,'voice'),(500,'new')))
        b=replace(a,channel=4,unit_id='second')
        p=replace(p,voices=p.voices+(v,),units=(a,b))
        project_scc(p)
        with self.assertRaisesRegex(ValueError,'shared'):
            project_scc(replace(p,units=(a,replace(b,voice_curve=((0,'voice'),)))))
        plus=replace(p.devices[0],clock_raw=0x80000000|1789773)
        rows,_,_=project_scc(replace(p,devices=(plus,)))
        self.assertTrue(any(r['command'][1:3]==bytes((4,128)) for r in rows))

    def test_non_scc_input_has_explicit_unavailable_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=export_variants(performance('psg',voice={'mode':1}),tmp,'song',force=True)
            for name in ('scc_sfg01','scc_makoto','scc_layered'):
                self.assertEqual(result[name]['status'],'unavailable')
                self.assertIn('No sounding SCC',result[name]['reason'])

    def test_source_ingestion_preserves_real_scc_period(self):
        from native_source_music import build_native_performance
        raw=bytearray(256);raw[:4]=b'Vgm '
        for offset,value in ((8,0x171),(0x34,256-0x34),(0x9c,1789773)):
            struct.pack_into('<I',raw,offset,value)
        for i in range(32):raw.extend((0xd2,0,i,127 if i<16 else 128))
        for port,reg,value in ((1,0,123),(1,1,1),(2,0,12),(3,0,1)):
            raw.extend((0xd2,port,reg,value))
        raw.extend(bytes.fromhex('61 00 10 d2 02 00 00 66'))
        struct.pack_into('<I',raw,4,len(raw)-4)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.vgm';path.write_bytes(raw)
            p=build_native_performance(path,Path(tmp)/'native','source')
            rows,_,_=project_scc(p)
            period=[r['command'][3] for r in rows if r['command'][1:3]==bytes((1,0))]
            self.assertEqual(period[0],123)
            result=export_variants(p,Path(tmp)/'targets','source',force=True)
            self.assertEqual(result['scc_layered']['status'],'success',result['scc_layered'])
            from test_export_mgs_variants import variant_pass, assert_profiles
            out=Path(tmp)/'published';variant_pass(path,out,force=True)
            assert_profiles(self,out,('sfg01','makoto','layered','scc_sfg01','scc_makoto','scc_layered'),'source')


if __name__=='__main__':unittest.main()
