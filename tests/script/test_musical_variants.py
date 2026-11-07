"""Cartridge projections consume musical evidence without consulting VGM files."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py')]
from native_music import NativeDevice,NativeVoice,NativeUnit,NativePerformance
from musical_wave_target import project_waves,project_psg_opll
from musical_variants import _write,export_variants
from native_imports.vgm_timing import command_times


def performance(chip='scc',section='tone',voice=None,units=None,end=4410):
    d=NativeDevice(chip+':0',chip,0,1789773)
    v=NativeVoice('voice',d.device_id,section,tuple((voice or {'waveform_hex':'7f'*16+'80'*16}).items()))
    u=NativeUnit('unit',d.device_id,section,0,0,end,((0,440.),),((0,15),),((0,v.voice_id),))
    return NativePerformance((d,),tuple(units or (u,)),(),(v,),(),(),end,'','')


class MusicalVariantTests(unittest.TestCase):
    def test_wave_projection_uses_edited_curves_and_both_target_clocks(self):
        p=performance()
        original,_,_=project_waves(p,'opm',3579545,force=True)
        unit=replace(p.units[0],pitch_curve=((0,880.),),volume_curve=((0,7),),end_sample=2205)
        altered,_,_=project_waves(replace(p,units=(unit,)),'opm',3579545,force=True)
        value=lambda rows,reg:next(r['command'][2] for r in rows if r['command'][1]==reg)
        self.assertNotEqual(value(original,0x28),value(altered,0x28))
        self.assertGreater(value(altered,0x60),value(original,0x60))
        self.assertEqual(altered[-1]['sample'],2205)
        opna,_,_=project_waves(p,'opna',8000000,force=True)
        high=value(opna,0xa4);low=value(opna,0xa0)
        hz=((high&7)*256+low)*8000000/(144*2**(21-((high>>3)&7)))
        self.assertAlmostEqual(hz,440,delta=.5)

    def test_no_source_file_needed_all_profiles_have_explicit_capability_results(self):
        p=performance()
        with tempfile.TemporaryDirectory() as tmp:
            result=export_variants(p,tmp,'authored',force=True)
            self.assertEqual(result['sfg01']['status'],'success')
            self.assertEqual(result['makoto']['status'],'success')
            self.assertEqual(result['sfg01_msxaudio']['status'],'unavailable')
            for name in ('sfg01','makoto'):
                raw=Path(result[name]['path']).read_bytes()
                self.assertEqual(tuple(command_times(raw))[-1].vgmticks,4410)
                self.assertEqual(struct.unpack_from('<I',raw,0x9c)[0],0)
                self.assertFalse(result[name]['source_file_consulted'])
                self.assertTrue((Path(tmp)/name/'authored.writes.csv').is_file())

    def test_voice_curve_updates_spectrum_inside_one_gate(self):
        p=performance();v=replace(p.voices[0],voice_id='sine',parameters=(('waveform_hex',bytes(round(127*__import__('math').sin(i*__import__('math').tau/32))&255 for i in range(32)).hex()),))
        u=replace(p.units[0],voice_curve=((0,'voice'),(735,'sine')))
        rows,losses,_=project_waves(replace(p,units=(u,),voices=(*p.voices,v)),'opm',3579545,force=True)
        self.assertTrue(any(r['sample']==735 and 0x40<=r['command'][1]<0x80 for r in rows))
        self.assertEqual(sum(r['command']==bytes((0x54,8,0x78)) for r in rows),1)

    def test_psg_musical_curves_override_observed_level_evidence(self):
        p=performance('psg',voice={'mode':1,'hardware_envelope':False})
        rows,_=project_psg_opll(p,force=True)
        self.assertTrue(any(r['command']==bytes((0xa0,8,15)) for r in rows))
        p=replace(p,units=(replace(p.units[0],volume_curve=((0,5),)),))
        rows,_=project_psg_opll(p,force=True)
        self.assertTrue(any(r['command']==bytes((0xa0,8,5)) for r in rows))

    def test_zero_duration_wave_and_psg_end_after_same_sample_onset(self):
        for chip in ('scc','psg'):
            p=performance(chip,voice={'waveform_hex':'7f'*16+'80'*16} if chip=='scc' else {'mode':1})
            p=replace(p,units=(replace(p.units[0],end_sample=0),))
            rows,_,_=project_waves(p,'opm',3579545,force=True) if chip=='scc' else (*project_psg_opll(p,force=True),{})
            ordered=sorted(rows,key=lambda r:(r['sample'],r['order']))
            if chip=='scc':
                keys=[r['command'][2] for r in ordered if r['command'][1]==8]
                self.assertEqual(keys, [0x78,0])
            else:
                levels=[r['command'][2] for r in ordered if r['command'][1]==8]
                self.assertEqual(levels,[15,0])

    def test_writer_keeps_first_loop_register_assignment_even_if_intro_matches(self):
        p=replace(performance(),song_loop_sample=1000)
        rows=[dict(sample=0,order=0,command=bytes.fromhex('54 20 c7')),
              dict(sample=1000,order=0,command=bytes.fromhex('54 20 c7')),
              dict(sample=2000,order=0,command=bytes.fromhex('54 20 c0'))]
        with tempfile.TemporaryDirectory() as tmp:
            result=_write(p,rows,b'',Path(tmp)/'loop.vgm')
            self.assertTrue(all(r['emitted'] for r in result))

    def test_serialized_native_records_can_render_without_source_ingestion(self):
        from native_music import NativeDevice,NativeVoice,NativeUnit,NativePerformance
        def freeze(value):
            if isinstance(value,list):return tuple(freeze(v) for v in value)
            if isinstance(value,dict):return {k:freeze(v) for k,v in value.items()}
            return value
        p=performance()
        with tempfile.TemporaryDirectory() as tmp:
            p.dump(tmp,'native')
            data=json.loads((Path(tmp)/'native.native_music.json').read_text())
            for key in ('sample_rate','time_domain','projection_applied','patterns_are_descriptive'):data.pop(key)
            constructors={'devices':NativeDevice,'voices':NativeVoice,'units':NativeUnit}
            for key,cls in constructors.items():data[key]=tuple(cls(**freeze(item)) for item in data[key])
            restored=NativePerformance(**freeze(data))
            from unittest.mock import patch
            with patch('native_imports.analyze_source',side_effect=AssertionError('source ingestion')):
                result=export_variants(restored,Path(tmp)/'targets','restored',force=True)
            self.assertEqual(result['sfg01']['status'],'success')

    def test_unknown_devices_are_not_silently_dropped(self):
        from musical_variants import project_variant
        with self.assertRaisesRegex(ValueError,'unsupported_source_device'):
            project_variant(performance('c140'), 'makoto',force=True)

    def test_writer_exact_sample_timing_loop_and_same_sample_order(self):
        p=replace(performance(),song_loop_sample=1000)
        rows=[dict(sample=1000,order=0,command=bytes.fromhex('54 28 4a')),
              dict(sample=1000,order=1,command=bytes.fromhex('54 08 78'))]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'one.vgm';_write(p,rows,b'',path)
            raw=path.read_bytes();events=tuple(command_times(raw))
            actual=[(e.vgmticks,raw[e.address:e.address+3]) for e in events if e.command==0x54]
            self.assertEqual(actual,[(1000,r['command']) for r in rows])
            self.assertEqual(int.from_bytes(raw[0x20:0x24],'little'),3410)


if __name__=='__main__':unittest.main()
