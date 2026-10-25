"""Authored real-driver probe for unchanged-period release continuation."""
import csv
from pathlib import Path
import re
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


def release_motifs():
    rows = []; noise = 3; envelope_period = 10
    main = ((14,1),(13,3),(12,2),(11,2),(10,2),(9,2),(8,4))
    tail = ((7,2),(6,1),(5,1))
    for repeat in range(8):
        tick = repeat*20
        if repeat:
            rows.append(psg(tick,0,tone_period=400,volume=5,amplitude_register=5,ev_type='fCB',
                            noise_period=noise,envelope_period=envelope_period))
        for index,(volume,duration) in enumerate(main):
            rows.append(psg(tick,duration,tone_period=400,volume=volume,
                            amplitude_register=volume,ev_type='fCA' if not repeat and not index else 'aVC',
                            noise_period=noise,envelope_period=envelope_period))
            tick += duration
        # Both bytes are redundantly rewritten; no ordered period excursion.
        for event in ('fCA','fCB'):
            rows.append(psg(tick,0,tone_period=400,volume=8,amplitude_register=8,ev_type=event,
                            noise_period=noise,envelope_period=envelope_period))
        if repeat % 2:
            # Complete snapshots carry changed but inactive hardware latches.
            noise = 7 if noise == 3 else 3
            rows.append(psg(tick,0,tone_period=400,volume=8,amplitude_register=8,
                            ev_type='wNC',noise_period=noise,envelope_period=envelope_period))
            envelope_period += 1
            rows.append(psg(tick,0,tone_period=400,volume=8,amplitude_register=8,
                            ev_type='ePL',noise_period=noise,envelope_period=envelope_period))
            envelope_period += 256
            rows.append(psg(tick,0,tone_period=400,volume=8,amplitude_register=8,
                            ev_type='evM',noise_period=noise,envelope_period=envelope_period))
        for volume,duration in tail:
            rows.append(psg(tick,duration,tone_period=400,volume=volume,
                            amplitude_register=volume,ev_type='aVC',
                            noise_period=noise,envelope_period=envelope_period))
            tick += duration
    rows += [psg(160,6,tone_period=400,volume=0,amplitude_register=0,scale='r'),
             psg(166,10,tone_period=400,volume=10,amplitude_register=10,ev_type='fCA'),
             psg(176,24,tone_period=400,volume=0,amplitude_register=0,scale='r')]
    return rows


class UnchangedPsgPeriodPlaybackTests(unittest.TestCase):
    used_bytes = {}

    @classmethod
    def setUpClass(cls):
        if not shutil.which('mgsc') or not shutil.which('node'):
            raise unittest.SkipTest('MGSC and Node are required')
        result = subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),'--check'],
                                capture_output=True,timeout=30)
        if result.returncode:
            raise unittest.SkipTest('libkss-js is required')

    def test_release_tail_joins_keep_all_frames_and_next_attack(self):
        for tempo in (75,225):
            with self.subTest(tempo=tempo),tempfile.TemporaryDirectory() as tmp:
                rows=release_motifs();original=analyze({0:rows},'psg');result=project(original)
                self.assertEqual(result.summary()['unchanged_period_joins'],8)
                self.assertIs(result.performance.controls,original.controls)
                self.assertIs(result.performance.boundaries,original.boundaries)
                self.assertEqual(result.performance.reconstruct_segments(),{0:rows})
                self.assertTrue(any(decision['reason']=='unchanged_period_write_release_continuation'
                                    for decision in result.decisions))
                notes=dict(result.performance.channels)[0]
                self.assertEqual([(note.start,note.length) for note in notes if not note.rest],
                                 [(tick,20) for tick in range(0,160,20)]+[(166,10)])
                replays=[];usage=[];onsets=[]
                for index,performance in enumerate((original,result.performance)):
                    folder=Path(tmp)/str(index);folder.mkdir();target=folder/'score.mml'
                    bank=LoopFirstEnvelopeBank(deferred=True)
                    bank.submit({0:rows},'psg',target,raw_ticks=tempo==75,performance=performance)
                    bank.flush()
                    texts,_=compensate({'psg':target.read_text()},tempo=tempo)
                    target.write_text(annotate_sync_points('#opll_mode 0\n'+texts['psg']),encoding='cp932')
                    mgs=folder/'score.mgs';vgm=folder/'score.vgm'
                    run=subprocess.run(['mgsc',str(target),str(mgs),'-T'],capture_output=True,timeout=30)
                    log=(run.stdout+run.stderr).decode('cp932',errors='replace')
                    self.assertEqual(run.returncode,0,log)
                    match=re.search(r'track\s*:\s*1\s*\(\s*\d+\)\s*\(\s*(\d+)\)',log)
                    self.assertIsNotNone(match);usage.append(int(match[1]))
                    run=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'4000'],
                                       capture_output=True,timeout=45)
                    self.assertEqual(run.returncode,0,run.stderr)
                    path=Path(parse_vgm(str(vgm),str(folder/'trace'),include_vgmticks=True)[2])
                    values={}
                    with path.open() as stream:
                        for row in csv.DictReader(stream):
                            if row['ch']!='0':continue
                            enabled=int(row['en']);amplitude=int(row['aVCtrl'])
                            period=int(row['fCtrlA'])+256*int(row['fCtrlB'])
                            mixer=int(row['vVCtrl'])&9
                            values[round(int(row['vgmticks'])/735)]=(enabled,period if enabled else 0,
                                amplitude if enabled else 0,mixer if enabled else 0)
                    first=min(frame for frame,state in values.items() if state[0] and state[2])
                    replay=[];state=(0,0,0,0)
                    for frame in range(first,first+200):
                        state=values.get(frame,state);replay.append(state)
                    replays.append(replay)
                    onsets.append([i for i,state in enumerate(replay)
                                   if state[0] and state[2] and (i==0 or not replay[i-1][2])])
                self.assertEqual(replays[0],replays[1])
                self.assertEqual(onsets[0],onsets[1])
                self.assertEqual(replays[1][166][2],10)
                # Used-byte evidence is compiler-specific; exact savings are not
                # part of this semantics test and are not asserted.
                self.assertTrue(all(value>0 for value in usage))
                self.used_bytes[tempo] = dict(ordinary=usage[0], projected=usage[1])


if __name__ == '__main__':
    unittest.main()
