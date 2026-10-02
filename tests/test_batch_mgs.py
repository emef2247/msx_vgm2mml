import csv
import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from batch_vgm_to_mgs import run_batch, check_keyons


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
                rows = run_batch(source,out,keyon=False,normalize_lengths=True)
            self.assertEqual(len(calls),2)
            self.assertEqual(calls[1][0],'/usr/local/bin/mgsc')
            self.assertIn('--normalize-lengths', calls[0])
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
                rows = run_batch(source,out,keyon=False)
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
                    run_batch(source,out,keyon=False)
                self.assertEqual(run.call_count,1)
            self.assertFalse(out.exists())

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_keyon_counts_reuse_compiled_mgs_and_keep_failures_separate(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir()
            for name in ('a', 'b'):
                (source/(name+'.vgm')).write_bytes(b'fixture')
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                if command[0] == '/usr/local/bin/mgsc':
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            counts = dict(reference_keyon=8, actual_keyon=7, missing_keyon=2, extra_keyon=1)
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('batch_vgm_to_mgs.check_keyons', side_effect=[counts, ValueError('export failed')]) as compare:
                rows = run_batch(source, out)
            self.assertEqual([r['status'] for r in rows], ['success', 'success'])
            self.assertEqual([r['keyon_status'] for r in rows], ['compared', 'error'])
            self.assertEqual(rows[0]['missing_keyon'], 2)
            self.assertEqual(rows[1]['actual_keyon'], '')
            self.assertIn('export failed', rows[1]['keyon_error'])
            self.assertEqual(sum(c[0] == sys.executable for c in calls), 2)
            self.assertEqual(compare.call_args_list[0].args[1], out/'a.vgm/a.mgs')
            with (out/'results.csv').open() as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(saved[0]['extra_keyon'], '1')
            self.assertEqual(saved[1]['reference_keyon'], '')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_missing_libkss_does_not_change_compile_status(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgz').write_bytes(b'fixture')
            def run(command, **kwargs):
                if '--check' in command:
                    return subprocess.CompletedProcess(command, 1, b'', b'libkss missing')
                if command[0] == '/usr/local/bin/mgsc':
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('batch_vgm_to_mgs.check_keyons') as compare:
                row = run_batch(source, out)[0]
            self.assertEqual(row['status'], 'success')
            self.assertEqual(row['keyon_status'], 'unavailable')
            self.assertEqual(row['actual_keyon'], '')
            compare.assert_not_called()

    def test_export_uses_existing_binary_and_rejects_duration_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, mgs = root/'source.vgm', root/'source.mgs'
            header = bytearray(0x40); header[:4] = b'Vgm '
            struct.pack_into('<I', header, 0x18, 44100)
            source.write_bytes(header); mgs.write_bytes(b'original binary')
            def run(command, **kwargs):
                self.assertEqual(command[2], str(mgs))
                exported = bytearray(header)
                struct.pack_into('<I', exported, 0x18, 44100)
                Path(command[3]).write_bytes(exported)
                return subprocess.CompletedProcess(command, 0, b'exported', b'')
            totals = dict(reference_keyon=9, actual_keyon=8, missing_keyon=1, extra_keyon=0)
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('batch_vgm_to_mgs.compare_files', return_value=totals) as compare:
                self.assertEqual(check_keyons(source, mgs, root, 'node', None, 10), totals)
                compare.assert_called_once_with(source, root/'source.roundtrip.vgm', root/'keyon', segment_dumps=False)
            self.assertEqual(mgs.read_bytes(), b'original binary')
            def truncated(command, **kwargs):
                exported = bytearray(header)
                struct.pack_into('<I', exported, 0x18, int(command[4])*44100//1000)
                Path(command[3]).write_bytes(exported)
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=truncated), \
                 patch('batch_vgm_to_mgs.compare_files') as compare:
                with self.assertRaisesRegex(ValueError, 'duration limit'):
                    check_keyons(source, mgs, root, 'node', None, 10)
                compare.assert_not_called()
