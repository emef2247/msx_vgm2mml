"""Verify compiled playback, not just accepted MML or simulated token state."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts')]
from mml_sync import annotate_sync_points, definition_allocation
from vgm_reader import parse_vgm
from check_opll_key_edges import extract

TUNE='#psg_tune {3421,3228,3047,2876,2715,2562,2419,2283,2155,2034,1920,1812}'
DEFINITIONS={
    'tune':TUNE,
    'wave':'@s0={'+('00'*32)+'}',
    'envelope':'@e0={0,0,F}',
    'voice':'@16={0,0,15,0,0,15,0,1,0,0,0,0,0,15,0,0,15,0,1,0,0,0,0,0}',
}


class DefinitionAllocationTests(unittest.TestCase):
    def test_empty_track_does_not_reserve_a_definition_buffer(self):
        self.assertEqual(definition_allocation(['#tempo 225']),0)

    def test_nonempty_track_has_an_explicit_end_byte(self):
        self.assertEqual(definition_allocation([TUNE]),26)
        self.assertEqual(definition_allocation([DEFINITIONS['envelope']]),6)
        self.assertEqual(definition_allocation([DEFINITIONS['voice']]),11)
        self.assertEqual(definition_allocation(list(DEFINITIONS.values())),75)


class ActualMgsPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('mgsc') or not shutil.which('node'):
            raise unittest.SkipTest('MGSC and Node are required for real MGS playback')
        check=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),'--check'],capture_output=True)
        if check.returncode:raise unittest.SkipTest('libkss-js is required for actual playback')

    def replay(self,mml,folder):
        source=folder/'probe.mml';source.write_text(mml,encoding='cp932')
        mgs=folder/'probe.mgs';vgm=folder/'probe.vgm'
        compiled=subprocess.run(['mgsc',str(source),str(mgs)],capture_output=True,timeout=30)
        self.assertEqual(compiled.returncode,0,compiled.stdout)
        self.assertTrue(mgs.exists())
        rendered=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'2000'],
                                capture_output=True,timeout=45)
        self.assertEqual(rendered.returncode,0,rendered.stderr)
        paths=parse_vgm(str(vgm),str(folder/'actual'))
        return [e for e in extract(paths[7]) if e['keyon']]

    def test_each_generated_definition_class_and_combination_starts_tracks(self):
        for name,definitions in [*DEFINITIONS.items(),('all','\n'.join(DEFINITIONS.values()))]:
            with self.subTest(kind=name),tempfile.TemporaryDirectory() as tmp:
                mml=annotate_sync_points('#opll_mode 0\n#tempo 225\n'+definitions+'\n9 @0 v15 o5 c4 d4 e4\n')
                edges=self.replay(mml,Path(tmp))
                self.assertEqual(len(edges),3)
                intervals=[b['time']-a['time'] for a,b in zip(edges,edges[1:])]
                self.assertTrue(all(abs(t-60/225)<1/60 for t in intervals),intervals)

    def test_compiler_success_does_not_hide_missing_definition_terminator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            broken='#opll_mode 0\n#tempo 225\n#alloc {0=25,9=15975}\n'+TUNE+'\n9 @0 v15 o5 c4 d4 e4\n'
            self.assertEqual(self.replay(broken,root),[])
            repaired=annotate_sync_points(broken)
            self.assertEqual(len(self.replay(repaired,root)),3)

    def test_default_export_public_opll_has_keyons_and_nonzero_audio(self):
        fixture=ROOT/'tests/fixtures/public/opll/ym2413_retrigger/ym2413_retrigger.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'export'
            converted=subprocess.run(['python3',str(ROOT/'scripts/export_mgs.py'),str(fixture),
                                      '--outdir',str(out)],capture_output=True,timeout=120)
            self.assertEqual(converted.returncode,0,converted.stdout+converted.stderr)
            report=json.loads((out/'_diagnostics/ym2413_retrigger/report.json').read_text())
            self.assertEqual(report['result']['keyon_status'],'compared')
            self.assertEqual(report['result']['missing_keyon'],0)
            self.assertEqual(report['result']['extra_keyon'],0)
            mgs=out/'tracks/ym2413_retrigger.mgs'
            stats=Path(tmp)/'audio.json'
            run=subprocess.run(['node',str(ROOT/'scripts/probe_mgs_audio.mjs'),str(mgs),str(stats),'3000'],
                               capture_output=True,timeout=45)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertGreater(json.loads(stats.read_text())['peak'],0)


if __name__=='__main__':unittest.main()
