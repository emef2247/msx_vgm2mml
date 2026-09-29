"""Public and optional local fixtures: source rhythm groups survive loops, notation and macros."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_rhythm_mml import attacks
from mml_sync import analyze_mml

ROOT = Path(__file__).resolve().parents[1]


class RhythmPipeline(unittest.TestCase):
    def test_public_rhythm_fixtures(self):
        fixtures = [(f'rhythm_only_test{i:02d}', ROOT / 'tests/fixtures/public/opll' /
                     f'rhythm_only_test{i:02d}') for i in range(1, 4)]
        fixtures.append(('sample', ROOT / 'tests/fixtures/public/psg_opll/msxplay.com/sample'))
        for stem, folder in fixtures:
            with self.subTest(stem=stem):
                self.check_fixture(stem, folder)

    def test_local_grider(self):
        folder = ROOT / 'tests/fixtures/local_only/opll/msxplay.com/grider'
        if not (folder / 'grider.vgm').exists():
            self.skipTest('Optional local fixture unavailable: grider')
        self.check_fixture('grider', folder)

    def check_fixture(self, stem, folder):
        with tempfile.TemporaryDirectory() as out:
            vgm = folder / f'{stem}.vgm'
            self.assertTrue(vgm.exists(), vgm)
            run = subprocess.run([sys.executable, str(ROOT/'vgm2mml.py'), str(vgm),
                                  '--outdir', out, '--dump-passes'], capture_output=True, timeout=180)
            self.assertEqual(run.returncode, 0, run.stderr)
            dest = Path(out)
            expected = []
            letters = dict(BD='b', SD='s', HH='h', TOM='m', CYM='c')
            with (dest/f'{stem}.opll.rhythm.groups.csv').open() as stream:
                for row in csv.DictReader(stream):
                    for hit in json.loads(row['hits']):
                        expected.append((int(row['tick'])*3, letters[hit['instrument']], 15-hit['vol']))
            text = (dest/f'{stem}.mml').read_text()
            self.assertEqual(attacks(text), sorted(expected))
            with (dest/f'{stem}_trace.opll.csv').open() as stream:
                end = max(int(row['ticks']) for row in csv.DictReader(stream))
            # A terminal attack requires at least one source tick of length.
            self.assertEqual(analyze_mml(text)[0]['f'][-1].end,
                             max(end*3, max(t for t, _, _ in expected)+3))
