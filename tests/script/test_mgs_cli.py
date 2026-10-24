"""Exercise real frontend settings, source evidence and scoped force failures."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


def vgm(extra=b''):
    raw=bytearray(0x80);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x161)
    struct.pack_into('<I',raw,0x34,0x80-0x34)
    struct.pack_into('<I',raw,0x74,3579545)
    raw+=b'\xa0\x00\x64\xa0\x01\x00\xa0\x07\x3e\xa0\x08\x0f'
    raw+=extra+b'\x62\xa0\x08\x00\x62\x66'
    struct.pack_into('<I',raw,4,len(raw)-4)
    return bytes(raw)


class MgsCliTests(unittest.TestCase):
    def run_cli(self,source,out,*flags):
        return subprocess.run([sys.executable,str(ROOT/'vgm2mml.py'),str(source),
                               '--outdir',str(out),*flags],capture_output=True,timeout=60)

    def test_explicit_state_threshold_activates_and_explains_no_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'test.vgm';source.write_bytes(vgm())
            for name,flags in [('default',[]),('requested',['--fm-state-ms','24'])]:
                result=self.run_cli(source,base/name,'--vgmticks','--dump-passes',*flags)
                self.assertEqual(result.returncode,0,result.stderr.decode())
            original=base/'default';target=base/'requested'
            self.assertEqual((original/'test.psg.segments.csv').read_bytes(),
                             (target/'test.psg.segments.csv').read_bytes())
            self.assertEqual((original/'test.mml').read_bytes(),(target/'test.mml').read_bytes())
            disabled=json.loads((original/'test.normalization.json').read_text())
            report=json.loads((target/'test.normalization.json').read_text())
            self.assertEqual(disabled['status'],'disabled')
            self.assertEqual(report['status'],'unchanged')
            self.assertEqual(report['fm_state_samples'],1058)
            self.assertEqual(report['configured_threshold_samples'],352)
            self.assertIn('no confident shared clock',report['reason'])
            self.assertFalse(report['whole_gate_omission'])
            self.assertFalse(report['psg_scc_curves_filtered'])
            self.assertFalse((target/'test.fm.short_states.csv').exists())

    def test_forced_write_omission_and_failed_rerun_do_not_leave_stale_mml(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'mixed.vgm';source.write_bytes(vgm(b'\x54\x20\xc7'))
            out=base/'out';forced=self.run_cli(source,out,'--force','--dump-passes')
            self.assertEqual(forced.returncode,0,forced.stderr.decode())
            report=json.loads((out/'mixed.mgs.force.json').read_text())
            self.assertEqual(report['omission_count'],1)
            self.assertEqual(report['omissions'][0]['chip'],'OPM')
            self.assertTrue((out/'mixed.mml').is_file())
            performance_files=[out/f'mixed.{chip}.performance.{suffix}'
                               for chip in ('psg','scc')
                               for suffix in ('json','notes.csv','gates.csv','controls.csv',
                                              'boundaries.csv','segments.csv')]
            self.assertTrue(all(path.is_file() for path in performance_files))
            strict=self.run_cli(source,out)
            self.assertNotEqual(strict.returncode,0)
            self.assertFalse((out/'mixed.mml').exists())
            self.assertTrue(all(not path.exists() for path in performance_files))
            conversion=json.loads((out/'mixed.conversion.json').read_text())
            self.assertEqual(conversion['status'],'conversion_failed')
            self.assertTrue((out/'mixed.mgs.source.json').is_file())

    def test_invalid_threshold_and_raw_tick_conflicts_precede_output_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'source.vgm';source.write_bytes(vgm())
            for flags in [('--fm-state-ms','nan'),('--normalization-ms','0'),
                          ('--raw-ticks','--fm-state-ms','24'),
                          ('--raw-ticks','--normalization-ms','8')]:
                with self.subTest(flags=flags):
                    result=self.run_cli(source,base/'out',*flags)
                    self.assertEqual(result.returncode,2)
                    self.assertFalse((base/'out').exists())


if __name__=='__main__':
    unittest.main()
