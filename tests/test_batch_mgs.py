import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from batch_vgm_to_mgs import run_batch


class BatchMgs(unittest.TestCase):
    def test_native_preferred_and_empty_output_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgm').write_bytes(b'fixture')
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command,0,b'Bad MML',b'diagnostic')
            with patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc'), \
                 patch('batch_vgm_to_mgs.subprocess.run', side_effect=run):
                rows = run_batch(source,out)
            self.assertEqual(len(calls),2)
            self.assertEqual(calls[1][0],'/usr/local/bin/mgsc')
            self.assertEqual(calls[1][1:], [str(out/'a.vgm/a.mml'),str(out/'a.vgm/a.mgs')])
            self.assertEqual(rows[0]['status'],'compile_failed')
            self.assertIn('diagnostic',(out/'a.vgm/compile.log').read_text())

    @patch('batch_vgm_to_mgs.shutil.which', return_value=None)
    def test_failure_continues_and_removes_stale_binary(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir()
            for name in ('a','b'):
                (source/(name+'.vgm')).write_bytes(b'fixture')
            stale = out/'a.vgm'/'a.mgs'
            stale.parent.mkdir(parents=True); stale.write_bytes(b'stale')
            def run(command, **kwargs):
                if command[0] == 'node':
                    if command[2] == '--check':
                        return subprocess.CompletedProcess(command,0,b'',b'')
                    if 'a.mml' in command[2]:
                        return subprocess.CompletedProcess(command,1,b'Track buffer full',b'')
                    Path(command[3]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run):
                rows = run_batch(source,out)
            self.assertEqual([r['status'] for r in rows], ['buffer_error','success'])
            self.assertFalse(stale.exists())
            with (out/'results.csv').open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))),2)

    @patch('batch_vgm_to_mgs.shutil.which', return_value=None)
    def test_setup_failure_stops_before_conversion(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgm').write_bytes(b'fixture')
            with patch('batch_vgm_to_mgs.subprocess.run', return_value=
                       subprocess.CompletedProcess([],2,b'',b'MGSC setup error')) as run:
                with self.assertRaisesRegex(RuntimeError, 'before conversion'):
                    run_batch(source,out)
                self.assertEqual(run.call_count,1)
            self.assertFalse(out.exists())
