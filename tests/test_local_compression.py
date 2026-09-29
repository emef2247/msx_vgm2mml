"""Optional private fixtures: lossless compression checks, no bundled game data."""
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_melody_loops import expand
from test_mml_envelopes import sounding_timeline, segment_timeline

ROOT = Path(__file__).resolve().parents[1]


class LocalCompression(unittest.TestCase):
    def check_fixture(self, stem):
        source = ROOT / f'tests/fixtures/local_only/psg_scc/msxplay.com/gra2_msx/{stem}/{stem}.vgm'
        if not source.exists():
            source = ROOT / f'tests/fixtures/local_only/gra2_msx/{stem}/{stem}.vgm'
        if not source.exists():
            self.skipTest(f'Optional local fixture unavailable: {stem}')
        with tempfile.TemporaryDirectory() as directory:
            run = subprocess.run([sys.executable, str(ROOT/'vgm2mml.py'), str(source),
                                  '--outdir', directory, '--dump-passes'],
                                 capture_output=True, timeout=240)
            self.assertEqual(run.returncode, 0, run.stderr)
            folder = Path(directory)
            final = (folder/f'{stem}.mml').read_text()
            self.assertEqual(sounding_timeline(final, False), segment_timeline(folder, stem))
            for chip in ('psg', 'scc'):
                def tracks(label):
                    result = {}
                    for line in (folder/f'{stem}.{chip}.melody.{label}.target.mml').read_text().splitlines():
                        if len(line)>1 and line[0] in '12345678' and line[1]==' ':
                            result.setdefault(line[0], []).append(line[2:])
                    return {ch:expand(' '.join(lines)) for ch,lines in result.items()}
                self.assertEqual(tracks('before'), tracks('after'))
                with (folder/f'{stem}.{chip}.performed.units.csv').open(newline='') as stream:
                    self.assertTrue(list(csv.DictReader(stream)))

    def test_gra2_003(self):
        self.check_fixture('gra2_003')

    def test_gra2_005(self):
        self.check_fixture('gra2_005')
