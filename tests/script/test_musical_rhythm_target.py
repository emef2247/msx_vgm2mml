"""Percussion score edits are authoritative over original rhythm key evidence."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py')]
from native_music import NativeDevice,NativeControl,NativePercussion,NativePerformance
from musical_rhythm_target import project_rhythm


def score(chip='opll'):
    device=NativeDevice(chip+':0',chip,0,3579545)
    event=NativePercussion('drum',device.device_id,'0','BD',100,400,((100,4),(200,8)))
    control=NativeControl('old',device.device_id,'rhythm',None,0,1,'opll_rhythm',
        (('register',14),('port',0),('mode',1),('instrument_mask',16),('reserved',0)))
    return NativePerformance((device,),(),(control,) if chip=='opll' else (),(),(event,),(),1000,'','')


class MusicalRhythmTargetTests(unittest.TestCase):
    def test_moved_opll_attack_stop_and_volume_replace_original_key_evidence(self):
        p=score();event=replace(p.percussion[0],start_sample=150,stop_sample=500,volume_curve=((150,6),(200,9)))
        rows,_=project_rhythm(replace(p,percussion=(event,)))
        keys=[(r['sample'],r['command'][2]) for r in rows if r['command'][1]==14]
        self.assertEqual(keys,[(0,32),(150,48),(500,32)])
        levels=[(r['sample'],r['command'][2]&15) for r in rows if r['command'][1]==0x36]
        self.assertIn((150,6),levels);self.assertIn((200,9),levels)

    def test_opna_natural_decay_never_gets_invented_dump(self):
        p=score('opna');p=replace(p,percussion=(replace(p.percussion[0],stop_sample=None),))
        rows,_=project_rhythm(p,makoto=True)
        triggers=[r['command'][2] for r in rows if r['command'][1]==0x10]
        self.assertEqual(triggers,[1])
        self.assertFalse(any(v&128 for v in triggers))
        _,losses=project_rhythm(p,makoto=False)
        self.assertEqual(losses['opna_rhythm_requires_makoto'],1)

    def test_opll_shared_volume_nibbles_do_not_destroy_other_drum(self):
        p=score();sd=replace(p.percussion[0],event_id='sd',instrument_family='SD',volume_curve=((100,5),))
        hh=replace(sd,event_id='hh',instrument_family='HH',volume_curve=((100,9),))
        rows,_=project_rhythm(replace(p,percussion=(sd,hh)))
        level=[r['command'][2] for r in rows if r['command'][1]==0x37 and r['sample']==100]
        self.assertEqual(level[-1],0x95)


if __name__=='__main__':unittest.main()
