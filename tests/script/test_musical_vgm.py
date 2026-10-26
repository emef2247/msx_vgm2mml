"""Independent command/time/state checks for the direct musical VGM backend."""
import csv
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from musical_plan import MusicalControl as C, MusicalPlan, MusicalUnit
from musical_vgm import write_vgm
from vgm_timing import command_times


def control(sample,chip,channel,kind,value,order=0):
    return C(sample,chip,channel,kind,tuple(value),order,
             source_sample=sample,source_event_id=order,source_indices=(order,))


def serialize(plan,**kwargs):
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'authored.vgm'
        mapping=Path(folder)/'mapping.csv'
        writes=write_vgm(plan,path,mapping_path=mapping,**kwargs)
        with mapping.open(newline='') as stream:
            rows=list(csv.DictReader(stream))
        return path.read_bytes(),writes,rows


def intervals(raw):
    """Snapshot effective native registers at each positive source wait."""
    ay=[0]*16;opll=[0]*64;scc={};result=[]
    for event in command_times(raw):
        at=event.address
        if event.command==0xa0:ay[raw[at+1]]=raw[at+2]
        elif event.command==0x51:opll[raw[at+1]]=raw[at+2]
        elif event.command==0xd2:scc[(raw[at+1],raw[at+2])]=raw[at+3]
        if event.wait_samples:
            result.append((event.vgmticks,event.vgmticks+event.wait_samples,tuple(ay),tuple(opll),dict(scc)))
    return result


class MusicalVgmTests(unittest.TestCase):
    def test_loop_reentry_rejects_missing_restore_without_overwriting_output(self):
        controls = (control(0,'scc',0,'waveform',tuple(range(32))),
            control(0,'scc',0,'pitch',(427,)), control(0,'scc',0,'volume',(15,)),
            control(0,'scc',0,'gate',(1,)), control(1470,'scc',0,'pitch',(499,)))
        plan = MusicalPlan((),controls,2205,2205,song_loop_sample=735)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'target.vgm';path.write_bytes(b'previous')
            with self.assertRaisesRegex(ValueError,'re-entry'):
                write_vgm(plan,path)
            self.assertEqual(path.read_bytes(),b'previous')
        fixed = MusicalPlan((),controls+(control(735,'scc',0,'pitch',(427,)),),2205,2205,
                            song_loop_sample=735)
        self.assertTrue(serialize(fixed)[0].startswith(b'Vgm '))

    def test_mixed_native_states_at_positive_waits_and_provenance(self):
        controls=[control(0,'psg',0,'pitch',(427,),1),control(0,'psg',0,'volume',(10,),2),
            control(0,'psg',0,'psg_mode',(1,),3),control(0,'psg',0,'gate',(1,),4),
            control(0,'scc',4,'waveform',tuple(range(32)),5),control(0,'scc',4,'pitch',(213,),6),
            control(0,'scc',4,'volume',(12,),7),control(0,'scc',4,'gate',(1,),8),
            control(0,'opll',8,'pitch',(290,3,1),9),control(0,'opll',8,'instrument',(4,),10),
            control(0,'opll',8,'volume',(15,),11),control(0,'opll',8,'gate',(1,),12),
            control(735,'opll',8,'volume',(0,),13)]
        units=(MusicalUnit('authored','opll',8,0,1470,False),)
        plan=MusicalPlan(units,tuple(controls),1470,1470,
            (('psg',1789773),('scc',1789773),('opll',3579545)))
        with patch.object(subprocess,'run',side_effect=AssertionError('No external tool')) as run, \
             patch('mml_sync.analyze_mml', side_effect=AssertionError('No MML parsing')), \
             patch('opll_target.render', side_effect=AssertionError('No MML rendering')):
            raw,writes,mapping=serialize(plan)
        run.assert_not_called()
        self.assertEqual([struct.unpack_from('<I',raw,offset)[0] for offset in (0x74,0x9c,0x10)],
                         [1789773,1789773,3579545])
        periods=intervals(raw)
        self.assertEqual([(p[0],p[1]) for p in periods],[(0,735),(735,1470)])
        for _,_,ay,opll,scc in periods:
            self.assertEqual(ay[0]|ay[1]<<8,427)
            self.assertEqual(ay[7]&1,0)
            self.assertEqual(ay[8],10)
            self.assertEqual(opll[0x18]|(opll[0x28]&1)<<8,290)
            self.assertEqual(opll[0x28]&0x3e,0x36)
            self.assertEqual(scc[(1,8)]|scc[(1,9)]<<8,213)
            self.assertEqual(scc[(3,0)],16)
        self.assertEqual(periods[0][3][0x38],0x40)
        self.assertEqual(periods[1][3][0x38],0x4f)
        self.assertEqual(len(mapping),len(writes))
        self.assertTrue(any(row['unit_id'] is None and row['reason']=='initial_state' for row in writes))
        for row in writes:
            address=row['target_command_address']
            self.assertEqual(raw[address:address+len(bytes.fromhex(row['command_hex']))],bytes.fromhex(row['command_hex']))

    def test_same_sample_retrigger_and_shared_scc_slot_are_not_deduplicated(self):
        controls=(control(0,'psg',None,'psg_envelope_shape',(9,),1),
            control(0,'psg',None,'psg_envelope_shape',(9,),2),
            control(0,'opll',0,'gate',(1,),3),control(735,'opll',0,'gate',(0,),1),
            control(735,'opll',0,'gate',(1,),2),
            control(735,'scc',3,'waveform',(1,)*32,3),control(735,'scc',4,'waveform',(2,)*32,4))
        raw,writes,_=serialize(MusicalPlan((),controls,1470,1470))
        shapes=[r['data'] for r in writes if r['chip']=='psg' and r['register']==13]
        self.assertEqual(shapes,[9,9])
        gates=[r['data']&16 for r in writes if r['sample']==735 and r['chip']=='opll' and r['register']==32]
        self.assertEqual(gates,[0,16])
        scc=intervals(raw)[-1][4]
        self.assertTrue(all(scc[(0,96+i)]==2 for i in range(32)))
        self.assertFalse(any(port==0 and address>=128 for port,address in scc))

    def test_global_patch_and_rhythm_preserve_actual_bits(self):
        controls=(control(0,'opll',None,'patch_write',(0,0x71),1),
            control(0,'opll',None,'patch_write',(3,0x17),2),
            control(0,'opll',None,'rhythm_register',(14,0x20),3),
            control(735,'opll',None,'rhythm_register',(14,0x30),1),
            control(735,'opll',None,'rhythm_register',(0x36,0xab),2),
            control(1470,'opll',None,'rhythm_register',(14,0x20),1))
        raw,_,_=serialize(MusicalPlan((),controls,2205,2205))
        states=intervals(raw)
        self.assertEqual([s[3][14] for s in states],[0x20,0x30,0x20])
        self.assertEqual(states[1][3][0x36],0xab)
        self.assertTrue(all(s[3][0]==0x71 and s[3][3]==0x17 for s in states))

    def test_long_wait_gd3_eof_and_loop_offset_on_boundary(self):
        gd3=b'Gd3 '+struct.pack('<II',0x100,4)+b'A\x00\x00\x00'
        plan=MusicalPlan((),(control(0,'psg',0,'pitch',(100,),0),),150000,150000,
                         song_loop_sample=70000)
        raw,_,_=serialize(plan,gd3=gd3)
        events=list(command_times(raw))
        self.assertEqual(events[-1].command,0x66)
        self.assertEqual(events[-1].vgmticks,150000)
        self.assertEqual(struct.unpack_from('<I',raw,4)[0]+4,len(raw))
        self.assertEqual(struct.unpack_from('<I',raw,0x18)[0],150000)
        address=struct.unpack_from('<I',raw,0x1c)[0]+0x1c
        self.assertEqual(next(e.vgmticks for e in events if e.address==address),70000)
        self.assertEqual(struct.unpack_from('<I',raw,0x20)[0],80000)
        gd3_address=struct.unpack_from('<I',raw,0x14)[0]+0x14
        self.assertEqual(raw[gd3_address:],gd3)
        self.assertFalse(any(e.command==0xa0 and raw[e.address+1]==7 and e.vgmticks==150000 for e in events))

    def test_typed_parameter_and_duration_guards(self):
        bad=[('opll',0,'pitch',(512,3,0)),('opll',0,'volume',(16,)),
             ('psg',0,'pitch',(-1,)),('scc',4,'waveform',(256,)*32),
             ('scc',0,'wave_write',(4,0,0)),('opll',None,'patch_write',(8,0)),
             ('opll',None,'rhythm_register',(0x0f,0)),('psg',0,'gate',(2,))]
        bad += [('psg', 0, 'psg_envelope_shape', (9,)),
                ('scc', 0, 'wave_write', (3, 0, 12)),
                ('opll', 0, 'patch_write', (0, 1)),
                ('opll', None, 'pitch', (172, 3, 0)),
                ('psg', None, 'gate', (1,)),
                ('scc', None, 'volume', (15,))]
        for chip,ch,kind,value in bad:
            with self.subTest(kind=kind,value=value),self.assertRaises(ValueError):
                control(0,chip,ch,kind,value)
        with self.assertRaises(ValueError):MusicalPlan((),(control(2,'psg',0,'gate',(1,)),),1,1)
        for loop in (-1,100):
            with self.assertRaises(ValueError):MusicalPlan((),(),100,100,song_loop_sample=loop)

    def test_event_count_is_independent_of_mgs_channel_allocation(self):
        controls=tuple(control(i,'psg',0,'volume',(i%16,),i) for i in range(20000))
        raw,writes,_=serialize(MusicalPlan((),controls,20000,20000))
        self.assertGreater(len(writes),16384)
        self.assertEqual(list(command_times(raw))[-1].vgmticks,20000)
        self.assertEqual(len([r for r in writes if r['reason']=='volume']),20000)

    def test_reconstructed_opll_gate_survives_zero_volume_interval(self):
        from opll_execution import build_opll
        def row(start,end,**updates):
            fields=dict(tick_start=start,tick_end=end,time=start/60,keyon=1,key_on_edge=0,
                fnum=173,block=3,inst=1,vol=0,sus=0,vgmticks=start*735,vgmticks_end=end*735)
            fields.update(updates)
            return SimpleNamespace(**fields)
        plan=build_opll({0:[row(0,2,key_on_edge=1),row(2,4,vol=15),row(4,6,keyon=0)]})
        raw,_,_=serialize(plan)
        states=intervals(raw)
        for start,end,_,opll,_ in states:
            if start<2940:
                self.assertTrue(opll[32]&16)
                self.assertEqual(opll[16]|((opll[32]&1)<<8),172)
            else:self.assertFalse(opll[32]&16)
        self.assertTrue(any(start==1470 and opll[48]&15==15 for start,_,_,opll,_ in states))


@unittest.skipUnless((ROOT / '.tools/musical-vgm-reference/metadata.json').exists(),
                     'Optional local pinned audio cores require explicit setup')
class MusicalVgmAudioReferenceTests(unittest.TestCase):
    def test_authored_mixed_vgm_plays_and_chip_frequencies_match(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        from musical_vgm_reference import render_vgm
        controls=[control(0,'psg',0,'pitch',(427,),1),control(0,'psg',0,'volume',(15,),2),
                  control(0,'psg',0,'psg_mode',(1,),3),control(0,'psg',0,'gate',(1,),4),
                  control(0,'scc',0,'waveform',(128,)*16+(127,)*16,5),
                  control(0,'scc',0,'pitch',(213,),6),control(0,'scc',0,'volume',(15,),7),
                  control(0,'scc',0,'gate',(1,),8)]
        # Quiet modulator plus a sustained sine carrier: independent pitch probe.
        patch_bytes=(0x21,0x21,0x3f,0,0xf0,0xf0,0,0)
        controls.extend(control(0,'opll',None,'patch_write',(reg,value),10+reg)
                        for reg,value in enumerate(patch_bytes))
        controls.extend((control(0,'opll',0,'instrument',(0,),20),
                         control(0,'opll',0,'volume',(15,),21),
                         control(0,'opll',0,'pitch',(172,3,0),22),
                         control(0,'opll',0,'gate',(1,),23)))
        raw,_,_=serialize(MusicalPlan((),tuple(controls),88200,88200,
            (('psg',1789773),('scc',1789773),('opll',3579545))))
        rendered=render_vgm(raw)
        self.assertEqual(len(rendered['mixed']),88200)
        self.assertTrue(any(rendered['mixed']))
        for chip,expected in (('psg',1789773/(16*427)),('scc',1789773/(16*214)),
                              ('opll',3579545/72*172*8/524288)):
            with self.subTest(chip=chip):
                entry=rendered['chips'][chip]
                self.assertTrue(any(entry['left']))
                # Ignore startup envelopes, measure repeated native cycles.
                signal=entry['left'][entry['rate_hz']//2:entry['rate_hz']*3//2]
                midpoint=(max(signal)+min(signal))/2
                edges=sum(a<=midpoint<b for a,b in zip(signal,signal[1:]))
                measured=edges*entry['rate_hz']/len(signal)
                self.assertAlmostEqual(measured,expected,delta=2)


if __name__=='__main__':unittest.main()
