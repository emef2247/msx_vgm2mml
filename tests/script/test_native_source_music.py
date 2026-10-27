"""Native codecs and musical gates are source-derived and renderer independent."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from native_music import NativeDevice
from native_imports.vgm_timing import CommandTime
from native_registers import decode_control,encode_control
from native_source_music import build_native_performance
from test_native_imports import vgm,block


def opm_setup(attenuation=20):
    return bytes.fromhex('54 20 c7 54 28 4a 54 30 00')+b''.join(
        bytes((0x54,0x60+8*i,attenuation)) for i in range(4))


class NativeCodecTests(unittest.TestCase):
    def test_all_packed_fm_bytes_preserve_fields_reserved_bits_and_ports(self):
        for chip,commands in (('opm',(0x54,0xa4)),('opna',(0x56,0x57,0xa6,0xa7)),('opll',(0x51,0xa1))):
            for command in commands:
                instance=int(command in (0xa4,0xa6,0xa7,0xa1))
                device=NativeDevice(f'{chip}:{instance}',chip,instance,4000000)
                for register in range(256):
                    for value in (0,1,0x35,0x7f,0x80,0xff):
                        raw=bytes((command,register,value));event=CommandTime(0,command,11,0,7)
                        control=decode_control(device,event,raw)
                        self.assertEqual(encode_control(control,device),raw,(chip,command,register,value))

    def test_opm_pan_names_differ_from_opna_and_match_native_state(self):
        for chip,raw in (('opm',bytes.fromhex('54 20 40')),('opna',bytes.fromhex('56 b4 80'))):
            device=NativeDevice(chip+':0',chip,0,4000000)
            control=decode_control(device,CommandTime(0,raw[0],0,0),raw)
            fields=dict(control.parameters)
            self.assertEqual((fields['left'],fields['right']),(1,0))

    def test_editing_native_pitch_fields_changes_serialization_without_source_bytes(self):
        device=NativeDevice('opm:0','opm',0,3579545)
        control=decode_control(device,CommandTime(0,0x54,0,0),bytes.fromhex('54 28 4a'))
        fields=dict(control.parameters);fields['octave']=5
        edited=replace(control,parameters=tuple(fields.items()))
        self.assertEqual(encode_control(edited,device),bytes.fromhex('54 28 5a'))
        self.assertNotIn('command_hex',fields)

    def test_ay_scc_and_dcsg_reconstruct_all_original_wire_values(self):
        for instance in (0,1):
            ay=NativeDevice(f'psg:{instance}','psg',instance,1789773)
            for register in range(16):
                for value in (0,0x5a,0xff):
                    raw=bytes((0xa0,register|instance<<7,value))
                    c=decode_control(ay,CommandTime(0,0xa0,0,0),raw)
                    self.assertEqual(encode_control(c,ay),raw)
            scc=NativeDevice(f'scc:{instance}','scc',instance,1789773)
            for port,register in ((0,117),(1,3),(2,4),(3,0),(4,150),(5,1)):
                raw=bytes((0xd2,port|instance<<7,register,0xab))
                c=decode_control(scc,CommandTime(0,0xd2,0,0),raw)
                self.assertEqual(encode_control(c,scc),raw)
            sn=NativeDevice(f'dcsg:{instance}','dcsg',instance,3579545);latches={}
            for value in (0x34,0x85,0x67,0x9e,0x32,0xe5,0x05):
                cmd=0x30 if instance else 0x50;raw=bytes((cmd,value))
                c=decode_control(sn,CommandTime(0,cmd,0,0),raw,latches=latches)
                self.assertEqual(encode_control(c,sn),raw)


class NativeSourceMusicTests(unittest.TestCase):
    def build(self,raw):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        return build_native_performance(raw,temporary.name,'authored'),Path(temporary.name)

    def test_fm_gate_keeps_volume_and_pitch_changes_without_artificial_attacks(self):
        raw=vgm(opm_setup()+bytes.fromhex('54 08 78 62 54 60 28 54 28 4b 62 54 08 00'),{0x30:3579545})
        result,folder=self.build(raw)
        self.assertEqual(len(result.units),1)
        unit=result.units[0]
        self.assertEqual((unit.start_sample,unit.end_sample),(0,1470))
        self.assertEqual(unit.pitch_curve[0],(0,440.0))
        self.assertGreater(len(unit.pitch_curve),1)
        self.assertEqual(len(unit.voice_curve),1)
        self.assertEqual(unit.parameters[2][0],'volume_domain')
        self.assertTrue((folder/'authored.native_music.json').is_file())
        self.assertTrue(unit.control_ids)

    def test_partial_operator_edges_remain_inside_gate_but_full_retrigger_splits(self):
        raw=vgm(opm_setup()+bytes.fromhex('54 08 78 62 54 08 38 62 54 08 00 54 08 78 62 54 08 00'),{0x30:3579545})
        result,_=self.build(raw)
        self.assertEqual([(u.start_sample,u.end_sample) for u in result.units],[(0,1470),(1470,2205)])
        keys=[dict(c.parameters)['key_mask'] for c in result.controls if c.kind=='opm_key']
        self.assertEqual(keys,[15,7,0,15,0])

    def test_uniform_carrier_attenuation_does_not_create_new_instrument_ids(self):
        setup=opm_setup();keys=bytes.fromhex('54 08 78 62 54 08 00')
        changes=b''.join(bytes((0x54,0x60+8*i,40)) for i in range(4))
        result,_=self.build(vgm(setup+keys+changes+keys,{0x30:3579545}))
        self.assertEqual(len(result.units),2)
        self.assertEqual(result.units[0].voice_curve[0][1],result.units[1].voice_curve[0][1])
        self.assertNotEqual(result.units[0].volume_curve,result.units[1].volume_curve)

    def test_zero_width_gate_is_retained_and_never_becomes_a_held_note(self):
        result,_=self.build(vgm(opm_setup()+bytes.fromhex('54 08 78 54 08 00 62'),{0x30:3579545}))
        self.assertEqual(len(result.units),1)
        self.assertEqual((result.units[0].start_sample,result.units[0].end_sample),(0,0))
        self.assertEqual(sum(c.kind=='opm_key' for c in result.controls),2)

    def test_empty_legacy_performances_do_not_activate_unused_devices(self):
        result,_=self.build(vgm(opm_setup()+bytes.fromhex('54 08 78 62'),{0x30:3579545,0x74:1789773,0x9c:1789773}))
        self.assertEqual([d.chip for d in result.devices],['opm'])

    def test_legacy_psg_scc_opll_mix_uses_original_samples(self):
        wave=b''.join(bytes((0xd2,0,i,i*7&255)) for i in range(32))
        commands=wave+bytes.fromhex('a0 00 ac a0 01 01 a0 07 3e a0 08 0c '
            'd2 01 00 ac d2 01 01 01 d2 02 00 0f d2 03 00 01 '
            '51 10 ac 51 30 10 51 20 16 61 be 05 a0 08 00 d2 03 00 00 51 20 06')
        result,_=self.build(vgm(commands,{0x74:1789773,0x9c:1789773,0x10:3579545}))
        self.assertEqual({d.chip for d in result.devices},{'psg','scc','opll'})
        self.assertEqual({u.device_id for u in result.units},{'psg:0','scc:0','opll:0'})
        self.assertTrue(all(u.end_sample==1470 for u in result.units))

    def test_pcm_data_stream_and_registers_are_packets_not_blueprint_notes(self):
        pcm=block(4,b'\x11\x22')+bytes.fromhex('90 00 17 00 01 91 00 04 01 00 '
            '92 00 40 1f 00 00 93 00 00 00 00 00 01 02 00 00 00 b7 00 01 62 94 00')
        result,_=self.build(vgm(opm_setup()+bytes.fromhex('54 08 78')+pcm,{0x30:3579545,0x90:4000000}))
        self.assertTrue(result.pcm_packets)
        self.assertEqual({u.device_id for u in result.units},{'opm:0'})
        self.assertTrue(any(p.dependencies for p in result.pcm_packets if p.kind=='stream_control'))
        self.assertTrue(any(p.command_hex.startswith('b700') for p in result.pcm_packets))

    def test_native_opll_and_opna_percussion_keep_curves_and_explicit_stops(self):
        commands=bytes.fromhex('51 36 05 51 0e 30 56 18 c5 56 10 01 62 '
            '51 36 0a 56 18 c9 62 51 0e 20 56 10 81')
        result,_=self.build(vgm(commands,{0x10:3579545,0x48:8000000}))
        self.assertEqual(len(result.percussion),2)
        for event in result.percussion:
            self.assertEqual(event.instrument_family,'BD')
            self.assertEqual((event.start_sample,event.stop_sample),(0,1470))
            self.assertEqual(len(event.volume_curve),2)
            self.assertTrue(event.control_ids)

    def test_native_opna_natural_decay_has_no_invented_stop(self):
        result,_=self.build(vgm(bytes.fromhex('56 18 c5 56 10 01 62'),{0x48:8000000}))
        self.assertIsNone(result.percussion[0].stop_sample)

    def test_native_opna_ssg_and_special_fm_controls_survive(self):
        commands=bytes.fromhex('56 00 ac 56 01 01 56 07 3e 56 08 0c '
            '56 27 40 56 ac 2a 56 a8 34 62 56 08 00')
        result,_=self.build(vgm(commands,{0x48:8000000}))
        self.assertTrue(any(u.section=='ssg' for u in result.units))
        self.assertTrue(any(c.kind=='opna_mode' for c in result.controls))
        self.assertTrue(any(dict(c.parameters).get('register')==0xac for c in result.controls))

    def test_unknown_active_source_is_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsupported active native source'):
            self.build(vgm(bytes.fromhex('55 20 00 62')))

    def test_complete_unit_patterns_do_not_expand_controls_or_drop_retriggers(self):
        repeat=bytes.fromhex('54 08 78 62 54 08 00')
        result,folder=self.build(vgm(opm_setup()+repeat*4,{0x30:3579545}))
        self.assertEqual(len(result.units),4)
        self.assertEqual(sum(c.kind=='opm_key' for c in result.controls),8)
        self.assertTrue(any(p['repeats']>=2 for p in result.patterns))
        self.assertTrue(all(not p['executable'] for p in result.patterns))
        self.assertTrue(list(folder.glob('*.repeat_candidates.csv')))

    def test_loop_order_and_gd3_are_retained_without_source_file_dependency(self):
        raw=bytearray(vgm(opm_setup()+bytes.fromhex('54 08 78 62 54 08 00'),{0x30:3579545}))
        loop_address=256+len(opm_setup())
        struct.pack_into('<I',raw,0x1c,loop_address-0x1c);struct.pack_into('<I',raw,0x20,735)
        gd3=b'Gd3 '+struct.pack('<II',0x100,4)+b'a\x00\x00\x00'
        struct.pack_into('<I',raw,0x14,len(raw)-0x14);raw.extend(gd3);struct.pack_into('<I',raw,4,len(raw)-4)
        result,_=self.build(bytes(raw))
        self.assertEqual(result.song_loop_sample,0)
        self.assertIsNotNone(result.song_loop_order)
        self.assertEqual(bytes.fromhex(dict(result.metadata)['gd3_hex']),gd3)

    def test_stateful_wait_override_is_flagged_for_source_loop_projection(self):
        setup=opm_setup()
        raw=bytearray(vgm(setup+bytes.fromhex('64 62 07 00 54 08 78 62 54 08 00'),{0x30:3579545}))
        loop_address=256+len(setup)
        struct.pack_into('<I',raw,0x1c,loop_address-0x1c);struct.pack_into('<I',raw,0x20,7)
        result,_=self.build(bytes(raw))
        self.assertTrue(dict(result.metadata)['wait_override_in_loop'])
        self.assertEqual(result.end_sample,7)


if __name__=='__main__':unittest.main()
