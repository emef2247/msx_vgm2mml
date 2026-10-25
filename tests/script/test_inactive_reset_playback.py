"""Authored real-driver verification of inactive PSG hardware-reset joins."""
import csv
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'py'), str(Path(__file__).resolve().parent)]
from test_psg_scc_performance import psg
from psg_scc_performance import analyze
from psg_scc_volume_curves import project
from pre_envelope_loops import LoopFirstEnvelopeBank
from mgs_envelope_ties import compensate
from mml_sync import annotate_sync_points
from vgm_reader import parse_vgm


class InactiveResetPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('mgsc') or not shutil.which('node'):
            raise unittest.SkipTest('MGSC and Node are required')
        check = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'), '--check'],
                               capture_output=True, timeout=30)
        if check.returncode:
            raise unittest.SkipTest('libkss-js is required')

    def test_inactive_joins_keep_replay_and_later_active_hardware_resets(self):
        for tempo in (75, 225):
            for levels in ((12,12,12), (12,9,6)):
                with self.subTest(tempo=tempo, levels=levels), tempfile.TemporaryDirectory() as tmp:
                    rows = [psg(i*40,40,volume=volume,tone_period=400,
                                ev_type='fCA' if i==0 else 'evS') for i,volume in enumerate(levels)]
                    rows += [psg(120,6,volume=0,scale='r',tone_period=400),
                             psg(126,12,volume=10,tone_period=400,ev_type='fCA'),
                             psg(138,6,volume=0,scale='r',tone_period=400),
                             psg(144,12,volume=15,tone_period=400,ev_type='aVC',
                                 envelope_enabled=1,amplitude_register=16,envelope_period=1000,envelope_shape=10),
                             psg(156,12,volume=15,tone_period=400,ev_type='evS',
                                 envelope_enabled=1,amplitude_register=16,envelope_period=1000,envelope_shape=10),
                             psg(168,6,volume=0,scale='r',tone_period=400),
                             psg(174,10,volume=8,tone_period=400,ev_type='fCA'),
                             psg(184,10,volume=0,scale='r',tone_period=400)]
                    original = analyze({0: rows}, 'psg'); result = project(original)
                    self.assertEqual(result.summary()['inactive_reset_joins'], 2)
                    self.assertIs(result.performance.controls, original.controls)
                    self.assertIs(result.performance.boundaries, original.boundaries)
                    self.assertEqual(result.performance.reconstruct_segments(), {0: rows})
                    self.assertEqual(sum(control.source_event=='evS' for control in result.performance.controls),
                                     sum(control.source_event=='evS' for control in original.controls))
                    replays = []; active_resets = []
                    for index,performance in enumerate((original,result.performance)):
                        folder=Path(tmp)/str(index);folder.mkdir();target=folder/'score.mml'
                        bank=LoopFirstEnvelopeBank(deferred=True)
                        bank.submit({0:rows},'psg',target,raw_ticks=tempo==75,performance=performance)
                        bank.flush()
                        text,evidence=compensate({'psg':target.read_text()},tempo=tempo)
                        target.write_text(annotate_sync_points('#opll_mode 0\n'+text['psg']),encoding='cp932')
                        mgs=folder/'score.mgs';vgm=folder/'score.vgm'
                        run=subprocess.run(['mgsc',str(target),str(mgs)],capture_output=True,timeout=30)
                        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                        run=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'4000'],
                                           capture_output=True,timeout=45)
                        self.assertEqual(run.returncode,0,run.stderr)
                        path=Path(parse_vgm(str(vgm),str(folder/'trace'),include_vgmticks=True)[2])
                        values={};resets=[]
                        with path.open() as stream:
                            for row in csv.DictReader(stream):
                                if int(row['ch']) != 0:continue
                                frame=round(int(row['vgmticks'])/735)
                                enabled=int(row['en']);amplitude=int(row['aVCtrl'])
                                hardware=bool(enabled and amplitude&16)
                                period=int(row['envPCtrlL'])+256*int(row['envPCtrlM'])
                                shape=int(row['envShape'])
                                mixer=int(row['vVCtrl'])&9
                                tone=int(row['fCtrlA'])+256*int(row['fCtrlB'])
                                values[frame]=(enabled,tone if enabled else 0,
                                               amplitude if enabled else 0,mixer if enabled else 0,
                                               period if hardware else 0,shape if hardware else 0)
                                if row['#type']=='evS' and hardware:resets.append(frame)
                        first=min(frame for frame,state in values.items() if state[0] and state[2])
                        replay=[];state=(0,0,0,0,0,0)
                        for frame in range(first,first+200):
                            state=values.get(frame,state);replay.append(state)
                        replays.append(replay);active_resets.append([frame-first for frame in resets])
                    self.assertEqual(replays[0],replays[1])
                    self.assertEqual(active_resets[0],active_resets[1])
                    # The first HW setup writes shape before setting amplitude
                    # bit 4. The later reset occurs while HW mode is active.
                    self.assertEqual(active_resets[1],[156])
                    self.assertTrue(any(state[2]&16 for state in replays[1][144:169]))


if __name__ == '__main__':
    unittest.main()
