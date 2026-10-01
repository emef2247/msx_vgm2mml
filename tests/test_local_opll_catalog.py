"""Optional commercial fixtures: conversion smoke regressions, no bundled data."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LocalOpllCatalog(unittest.TestCase):
    pass


def make_test(relative):
    def test(self):
        source = ROOT / 'tests/fixtures/local_only/opll' / relative
        if not source.exists():
            self.skipTest('Optional local VGM unavailable')
        with tempfile.TemporaryDirectory() as folder:
            run = subprocess.run([sys.executable, str(ROOT/'vgm2mml.py'), str(source),
                                  '--outdir', folder], capture_output=True, timeout=300)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors='replace'))
            self.assertGreater((Path(folder)/(source.stem+'.mml')).stat().st_size, 0)
    return test


for directory, prefix, count in [('www.smspower.org/WBIII','WBIII',14),
                                  ('www.smspower.org/THBSMS','ThBSMS',5),
                                  ('www.smspower.org/YSSMS','YsSMS',20),
                                  ('vgmrips.net/ALESTE2','Alest2',17)]:
    for number in range(1, count+1):
        stem = f'{prefix}{number:02d}'
        setattr(LocalOpllCatalog, 'test_'+stem, make_test(f'{directory}/{stem}.vgm'))

# Quantized same-instrument rhythm collisions, including changed source state.
for relative in (
    'FIREHAWK/FHAWK18', 'FRAY/FRAY03', 'FRAY/FRAY04', 'FRAY/FRAY09',
    'FRAY/FRAY14', 'FRAY/FRAY23', 'ILCITY/ILCITY06',
    'TOGZL/TOGZL23', 'TOGZL/TOGZL25', 'TOGZL/TOGZL27',
    'XAK_I/XAK_I_02', 'XAK_I/XAK_I_26', 'XAK_I/XAK_I_35', 'XAK_I/XAK_I_41',
    'XAK_II/XAK_II12', 'XAK_II/XAK_II30',
):
    setattr(LocalOpllCatalog, 'test_'+Path(relative).name,
            make_test('vgmrips.net/'+relative+'.vgm'))
