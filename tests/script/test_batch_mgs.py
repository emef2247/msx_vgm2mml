import csv
import json
import io
import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from batch_vgm_to_mgs import run_batch, check_keyons


class BatchMgs(unittest.TestCase):
    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_timeouts_are_separate_and_preserve_partial_diagnostics(self, _which):
        for stage in ('convert', 'compile'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                source, out = Path(tmp)/'input', Path(tmp)/'out'
                source.mkdir()
                for name in ('a','b'):
                    (source/(name+'.vgm')).write_bytes(b'fixture')
                def run(command, **kwargs):
                    if '--outdir' in command:
                        folder = Path(command[command.index('--outdir') + 1])
                        (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
                    is_compile = command[0] == '/usr/local/bin/mgsc'
                    if any(name in ' '.join(command) for name in ('a.vgm', 'a.mml')) and is_compile == (stage == 'compile'):
                        if is_compile:
                            Path(command[2]).write_bytes(b'incomplete')
                        raise subprocess.TimeoutExpired(command,17,output=b'partial stdout',stderr=b'partial stderr')
                    if is_compile:
                        Path(command[2]).write_bytes(b'MGS')
                    return subprocess.CompletedProcess(command,0,b'',b'')
                with patch('batch_vgm_to_mgs.subprocess.run',side_effect=run):
                    rows = run_batch(source,out,keyon=False,timeout=17)
                self.assertEqual([r['status'] for r in rows],['conversion_failed' if stage == 'convert' else 'compilation_failed','success'])
                log = (out/'_diagnostics/a'/f'{stage}.log').read_text()
                self.assertIn('partial stdout',log)
                self.assertIn('partial stderr',log)
                self.assertIn('timed out after 17 seconds',log)
                self.assertFalse((out/'_diagnostics/a/a.mgs').exists())
                with (out/'_diagnostics/results.csv').open() as stream:
                    self.assertEqual(next(csv.DictReader(stream))['error_code'],'timeout')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_keyon_timeout_does_not_change_successful_compile(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgm').write_bytes(b'fixture')
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
                if command[0] == '/usr/local/bin/mgsc':
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('batch_vgm_to_mgs.subprocess.run',side_effect=run), \
                 patch('batch_vgm_to_mgs.check_keyons',side_effect=
                       subprocess.TimeoutExpired(['export'],17,output=b'playback progress')):
                row = run_batch(source,out)[0]
            self.assertEqual((row['status'],row['keyon_status']),('success','timeout'))
            self.assertEqual(row['actual_keyon'],'')
            self.assertIn('playback progress',(out/'_diagnostics/a/keyon.log').read_text())
            self.assertTrue((out/'tracks/a.mgs').exists())

    def test_native_preferred_and_empty_output_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgm').write_bytes(b'fixture')
            calls = []
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
                calls.append(command)
                return subprocess.CompletedProcess(command,0,b'Bad MML',b'diagnostic')
            with patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc'), \
                 patch('batch_vgm_to_mgs.subprocess.run', side_effect=run):
                rows = run_batch(source,out,keyon=False,normalize_lengths=True,enhance_macros=False,legacy_loops=True)
            self.assertEqual(len(calls),2)
            self.assertEqual(calls[1][0],'/usr/local/bin/mgsc')
            self.assertIn('--normalize-lengths', calls[0])
            self.assertIn('--legacy-macros', calls[0])
            self.assertIn('--legacy-loops', calls[0])
            self.assertIn('--no-software-volume-curves', calls[0])
            self.assertNotIn('--software-volume-curves', calls[0])
            self.assertEqual(calls[1][1:], [str(out/'_diagnostics/a/a.mml'),str(out/'_diagnostics/a/a.mgs')])
            self.assertEqual(rows[0]['status'],'compilation_failed')
            self.assertIn('diagnostic',(out/'_diagnostics/a/compile.log').read_text())

    @patch('batch_vgm_to_mgs.shutil.which', return_value=None)
    def test_failure_continues_and_preserves_owned_publication(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir()
            for name in ('a','b'):
                (source/(name+'.vgm')).write_bytes(b'fixture')
            stale = out/'tracks/a.mgs'
            stale.parent.mkdir(parents=True); stale.write_bytes(b'stale')
            manifest = out/'listening_manifest.json'
            manifest.parent.mkdir(parents=True, exist_ok=True)
            import hashlib
            manifest.write_text(json.dumps(dict(schema_version=1, entries={'a.vgm': dict(published={'tracks/a.mgs': hashlib.sha256(b'stale').hexdigest()})})))
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
                if command[0] == 'node':
                    if command[2] == '--check':
                        return subprocess.CompletedProcess(command,0,b'',b'')
                    if 'a.mml' in command[2]:
                        return subprocess.CompletedProcess(command,1,b'Track buffer full',b'')
                    Path(command[3]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run):
                rows = run_batch(source,out,keyon=False)
            self.assertEqual([r['status'] for r in rows], ['compilation_failed','success'])
            self.assertEqual(stale.read_bytes(), b'stale')
            with (out/'_diagnostics/results.csv').open() as stream:
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
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
                calls.append(command)
                if command[0] == '/usr/local/bin/mgsc':
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            counts = dict(reference_keyon=8, actual_keyon=7, missing_keyon=2, extra_keyon=1)
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('batch_vgm_to_mgs.check_keyons', side_effect=[counts, ValueError('export failed')]) as compare:
                rows = run_batch(source, out)
            self.assertEqual([r['status'] for r in rows], ['success', 'success'])
            self.assertEqual([r['keyon_status'] for r in rows], ['mismatch', 'error'])
            self.assertEqual(rows[0]['missing_keyon'], 2)
            self.assertEqual(rows[1]['actual_keyon'], '')
            self.assertIn('export failed', rows[1]['keyon_error'])
            self.assertEqual(sum(c[0] == sys.executable for c in calls), 2)
            self.assertEqual(compare.call_args_list[0].args[1], out/'_diagnostics/a/a.mgs')
            with (out/'_diagnostics/results.csv').open() as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(saved[0]['extra_keyon'], '1')
            self.assertEqual(saved[1]['reference_keyon'], '')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_missing_libkss_does_not_change_compile_status(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgz').write_bytes(b'fixture')
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
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
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
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


    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_options_reports_and_nested_identical_names(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            for sub in ('one', 'two'):
                folder = source/sub
                folder.mkdir(parents=True)
                (folder/'same.vgm').write_bytes(b'fixture')
            calls = []
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder / (Path(command[2]).stem + '.mml')).write_text('1 c4')
                calls.append(command)
                self.assertEqual(kwargs['timeout'], 1200)
                if command[0] == '/usr/local/bin/mgsc':
                    Path(command[2]).write_bytes(b'MGS')
                else:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder/'same.normalization.json').write_text(json.dumps(dict(
                        status='unchanged', reason='no confident shared clock')))
                    (folder/'same.fm.short_states.json').write_text(json.dumps(dict(applied=False)))
                    for chip in ('psg', 'scc'):
                        (folder/('same.' + chip + '.volume_curves.json')).write_text(json.dumps(dict(enabled=True)))
                    (folder/'same.mgs.force.json').write_text(json.dumps(dict(
                        enabled=True, omission_count=2, omissions=[], csv_path='same.mgs.force.csv')))
                    if 'two' in str(folder):
                        self.assertEqual(len(json.loads((out/'_diagnostics/results.json').read_text())), 1)
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('sys.stdout', new_callable=io.StringIO) as console:
                rows = run_batch(source, out, keyon=False, force=True, fm_state_ms=4,
                                 normalization_ms=16, dump_passes=True, software_volume_curves=True)
            self.assertEqual([r['status'] for r in rows], ['success', 'success'])
            self.assertIn('2/2 exported', console.getvalue())
            self.assertIn('2 omitted target operations', console.getvalue())
            for command in calls[::2]:
                self.assertIn('--force', command)
                self.assertIn('--dump-passes', command)
                self.assertIn('--software-volume-curves', command)
                self.assertEqual(float(command[command.index('--fm-state-ms')+1]), 4)
                self.assertEqual(float(command[command.index('--normalization-ms')+1]), 16)
            for row in rows:
                report = json.loads((out/row['diagnostics']).read_text())
                self.assertTrue(report['options']['force'])
                self.assertTrue(report['options']['software_volume_curves'])
                self.assertEqual(row['normalization_status'], 'unchanged')
                self.assertEqual(row['normalization_reason'], 'no confident shared clock')
                self.assertFalse(report['summaries']['fm_states']['applied'])
                self.assertTrue(report['summaries']['psg_volume_curves']['enabled'])
                self.assertTrue(report['summaries']['scc_volume_curves']['enabled'])
                self.assertEqual(report['result']['status'], 'success')
                self.assertEqual(len(report['commands']), 2)
                self.assertTrue((out/row['report']).is_file())
            self.assertNotEqual(rows[0]['mgs'], rows[1]['mgs'])

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_rerun_cleans_only_owned_artifacts_before_conversion(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'a.vgm', Path(tmp)/'out'
            source.write_bytes(b'fixture')
            folder = out/'_diagnostics/a'; folder.mkdir(parents=True)
            names = ['a.mml', 'a.mgs', 'a.roundtrip.vgm', 'report.json', 'report.txt',
                     'a.normalization.json', 'a.mgs.force.json', 'a.mgs.force.csv', 'compile.log',
                     'a.psg.selection.json', 'a.psg.selection.candidates.csv', 'a.psg.selection.mask.csv']
            names += ['a.' + chip + '.volume_curves.' + suffix
                      for chip in ('psg', 'scc')
                      for suffix in ('json', 'candidates.csv', 'notes.csv', 'decisions.csv')]
            for name in names:
                (folder/name).write_text('stale')
            (folder/'personal.txt').write_text('keep')
            (folder/'a.psg.selection.segments.csv').write_text('retained pass')
            def run(command, **kwargs):
                self.assertTrue(all(not (folder/name).exists() for name in names))
                return subprocess.CompletedProcess(command, 1, b'ValueError: damaged input', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run):
                row = run_batch(source, out, keyon=False, force=True)[0]
            self.assertEqual(row['error_code'], 'conversion_error')
            self.assertEqual(row['detail'], 'ValueError: damaged input')
            self.assertFalse((folder/'a.mgs').exists())
            self.assertEqual((folder/'personal.txt').read_text(), 'keep')
            self.assertEqual(row['force_summary'], '')
            report = json.loads((out/row['diagnostics']).read_text())
            self.assertNotIn('psg_selection', report['summaries'])
            self.assertEqual((folder/'a.psg.selection.segments.csv').read_text(), 'retained pass')

    def test_invalid_options_fail_before_setup_or_output_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir(); (source/'a.vgm').write_bytes(b'fixture')
            for options in ({'fm_state_ms': -1}, {'normalization_ms': float('nan')}, {'timeout': 0}):
                with self.subTest(options=options), patch('batch_vgm_to_mgs.subprocess.run') as run:
                    with self.assertRaises(ValueError):
                        run_batch(source, out, keyon=False, **options)
                    run.assert_not_called()
                    self.assertFalse(out.exists())


    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_missing_conversion_output_does_not_compile_or_link_nonexistent_mml(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'a.vgm', Path(tmp)/'out'
            source.write_bytes(b'fixture')
            with patch('batch_vgm_to_mgs.subprocess.run', return_value=
                       subprocess.CompletedProcess([], 0, b'conversion ended', b'')) as run:
                row = run_batch(source, out, keyon=False)[0]
            self.assertEqual(run.call_count, 1)
            self.assertEqual(row['status'], 'conversion_failed')
            self.assertEqual(row['error_code'], 'missing_output')
            self.assertEqual(row['mml'], '')
            self.assertIn('MML output', row['detail'])


    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_strict_zero_omission_report_does_not_print_force_label(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'a.vgm', Path(tmp)/'out'
            source.write_bytes(b'fixture')
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir') + 1])
                    (folder/'a.mml').write_text('1 c4')
                    (folder/'a.mgs.force.json').write_text(json.dumps(dict(
                        enabled=False, omission_count=0, omissions=[])))
                else:
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('sys.stdout', new_callable=io.StringIO) as console:
                row = run_batch(source, out, keyon=False)[0]
            self.assertEqual(row['force_summary'], '')
            self.assertNotIn('Forced MGS projection', console.getvalue())


class CleanOutputTests(unittest.TestCase):
    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_solo_publication_keeps_names_and_diagnostics_separate(self, _which):
        for part in ('all', 'melody', 'rhythm'):
            with self.subTest(part=part), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, out = root/'input', root/'out'
                (source/'nested').mkdir(parents=True)
                basename = 'A long.song name'
                (source/'nested'/(basename+'.vgz')).write_bytes(b'fixture')
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    if '--outdir' in command:
                        folder = Path(command[command.index('--outdir')+1])
                        (folder/(basename+'.mml')).write_text('1 c4')
                        (folder/'arbitrary.pass.csv').write_text('evidence')
                        (folder/(basename+'.drums.json')).write_text(json.dumps(dict(enabled=True, added_hits=2, reason='inferred')))
                        if part != 'all':
                            (folder/(basename+'.psg.selection.json')).write_text(json.dumps(dict(
                                enabled=True, part=part, eligible_rhythm_candidates=3,
                                selected_audible_intervals=7, hardware_phase_abstentions=1)))
                    else:
                        Path(command[2]).write_bytes(b'MGS')
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                     patch('sys.stdout', new_callable=io.StringIO) as console:
                    row = run_batch(source, out, keyon=False, psg_part=part, enhance_drums=True)[0]
                mode = Path() if part == 'all' else Path('psg_'+part)
                expected = mode/'nested'/'tracks'/(basename+'.mml')
                self.assertEqual(Path(row['mml']), expected)
                self.assertEqual(Path(row['mgs']), expected.with_suffix('.mgs'))
                diagnostic = mode/'nested'/'_diagnostics'/basename
                self.assertEqual(Path(row['diagnostics']), diagnostic/'report.json')
                self.assertTrue((out/'_diagnostics'/mode/'results.json').is_file())
                self.assertEqual(sorted(p.suffix for p in (out/mode/'nested'/'tracks').iterdir()), ['.mgs', '.mml'])
                self.assertIn('--enhance-rhythm', calls[0])
                if part != 'all':
                    self.assertIn('--psg-'+part+'-only', calls[0])
                self.assertTrue((out/diagnostic/'arbitrary.pass.csv').is_file())
                report = json.loads((out/row['diagnostics']).read_text())
                self.assertIn('Rhythm enhancement: 2 added hits; inferred', console.getvalue())
                self.assertNotIn('Drum enhancement:', console.getvalue())
                if part == 'all':
                    self.assertNotIn('psg_selection', report['summaries'])
                    self.assertNotIn('PSG selection:', console.getvalue())
                else:
                    self.assertEqual(report['summaries']['psg_selection']['part'], part)
                    self.assertEqual(report['summaries']['psg_selection']['selected_audible_intervals'], 7)
                    self.assertIn(f'PSG selection: {part}; 3 rhythm candidates; 7 audible intervals; '
                                  '1 hardware-envelope abstentions', console.getvalue())

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_owned_publications_preserved_on_failure_with_latest_status(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'a.vgm', root/'out'
            source.write_bytes(b'fixture')
            old = out/'a.vgm/a.mgs'; old.parent.mkdir(parents=True); old.write_bytes(b'old layout')
            def success(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir')+1]); (folder/'a.mml').write_text('1 c4')
                else:
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=success):
                run_batch(source, out, keyon=False)
            self.assertTrue((out/'tracks/a.mgs').is_file())
            with patch('batch_vgm_to_mgs.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'failed', b'')):
                row = run_batch(source, out, keyon=False)[0]
            self.assertEqual(row['mml'], '')
            self.assertEqual((out/'tracks/a.mml').read_text(), '1 c4'); self.assertEqual((out/'tracks/a.mgs').read_bytes(), b'MGS')
            entry = json.loads((out/'listening_manifest.json').read_text())['entries']['a.vgm']
            self.assertEqual(entry['status'], 'success')
            self.assertEqual(entry['latest_attempt_status'], 'conversion_failed')
            self.assertEqual(old.read_bytes(), b'old layout')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_compile_failure_publishes_valid_mml_only(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'fixture')
            def run(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir')+1]); (folder/'a.mml').write_text('1 c4')
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                Path(command[2]).write_bytes(b'invalid partial')
                return subprocess.CompletedProcess(command, 1, b'compiler failed', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run):
                row = run_batch(source, out, keyon=False)[0]
            self.assertEqual(row['mml'], 'tracks/a.mml'); self.assertEqual(row['mgs'], '')
            self.assertEqual((out/'tracks/a.mml').read_text(), '1 c4'); self.assertFalse((out/'tracks/a.mgs').exists())

    def test_collisions_fail_before_any_mutation_or_setup(self):
        cases = [('foo.vgm', 'foo.vgz'), ('Foo.vgm', 'foo.vgm'),
                 ('_diagnostics/a.vgm',), ('psg_melody/a.vgm',),
                 ('tracks/a.vgm',)]
        for names in cases:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, out = root/'input', root/'out'
                for name in names:
                    path = source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
                out.mkdir(); sentinel = out/'keep.txt'; sentinel.write_text('keep')
                with patch('batch_vgm_to_mgs.subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError, 'Colliding|Reserved'):
                        run_batch(source, out, keyon=False)
                    run.assert_not_called()
                self.assertEqual(list(out.iterdir()), [sentinel])

    def test_foreign_or_modified_final_product_is_preserved(self):
        import hashlib
        for recorded in (None, hashlib.sha256(b'previous').hexdigest()):
            with self.subTest(recorded=recorded), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'fixture'); out.mkdir()
                final = out/'tracks/a.mgs'; final.parent.mkdir(); final.write_bytes(b'personal')
                if recorded:
                    manifest = out/'listening_manifest.json'
                    manifest.write_text(json.dumps(dict(schema_version=1, entries={'a.vgm': dict(published={'tracks/a.mgs': recorded})})))
                with patch('batch_vgm_to_mgs.subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError, 'unowned or modified'):
                        run_batch(source, out, keyon=False)
                    run.assert_not_called()
                self.assertEqual(final.read_bytes(), b'personal')

    def test_batch_parser_aliases_and_mutual_exclusion(self):
        from batch_vgm_to_mgs import build_parser
        parser = build_parser()
        self.assertFalse(parser.parse_args(['input']).software_volume_curves)
        self.assertTrue(parser.parse_args(['input', '--software-volume-curves']).software_volume_curves)
        self.assertFalse(parser.parse_args(['input', '--no-software-volume-curves']).software_volume_curves)
        with self.assertRaises(SystemExit):
            parser.parse_args(['input', '--software-volume-curves', '--no-software-volume-curves'])
        for alias in ('--enhance-rhythm', '--enhance-drums'):
            self.assertTrue(parser.parse_args(['input', '--outdir', 'out', alias]).enhance_drums)
        for alias in ('--psg-melody-only', '--psg-melody_only'):
            self.assertEqual(parser.parse_args(['input', '--outdir', 'out', alias]).psg_part, 'melody')
        self.assertEqual(parser.parse_args(['input', '--outdir', 'out', '--psg-rhythm-only']).psg_part, 'rhythm')
        with self.assertRaises(SystemExit):
            parser.parse_args(['input', '--outdir', 'out', '--psg-rhythm-only', '--psg-melody-only'])


class SoloVerificationTests(unittest.TestCase):
    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_solo_exports_and_retains_counts_without_comparing_excluded_opll(self, _which):
        for part in ('melody', 'rhythm'):
            with self.subTest(part=part), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, out = root/'a.vgm', root/'out'
                source.write_bytes(b'fixture')
                def run(command, **kwargs):
                    if '--outdir' in command:
                        folder = Path(command[command.index('--outdir')+1]); (folder/'a.mml').write_text('1 c4')
                    elif command[0] == '/usr/local/bin/mgsc':
                        Path(command[2]).write_bytes(b'MGS')
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                counts = dict(reference_keyon=8, actual_keyon=0, missing_keyon=8, extra_keyon=0)
                with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                     patch('batch_vgm_to_mgs.check_keyons', return_value=counts) as compare:
                    row = run_batch(source, out, psg_part=part)[0]
                compare.assert_called_once()
                self.assertEqual(row['keyon_status'], 'selection_only')
                self.assertEqual({field: row[field] for field in counts}, counts)
                self.assertIn('native OPLL intentionally excluded', row['keyon_error'])
                self.assertIn('not applicable', row['keyon_error'])
                report = json.loads((out/row['diagnostics']).read_text())
                self.assertEqual(report['result']['missing_keyon'], 8)
                self.assertEqual(report['result']['keyon_status'], 'selection_only')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_solo_playback_export_failures_keep_verification_failure(self, _which):
        for error, status in ((ValueError('export duration limit'), 'error'),
                              (subprocess.TimeoutExpired(['export'], 17), 'timeout')):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'fixture')
                def run(command, **kwargs):
                    if '--outdir' in command:
                        folder = Path(command[command.index('--outdir')+1]); (folder/'a.mml').write_text('1 c4')
                    elif command[0] == '/usr/local/bin/mgsc':
                        Path(command[2]).write_bytes(b'MGS')
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                     patch('batch_vgm_to_mgs.check_keyons', side_effect=error):
                    row = run_batch(source, out, psg_part='melody')[0]
                self.assertEqual(row['status'], 'success')
                self.assertEqual(row['keyon_status'], status)


class AdjacentOutputTests(unittest.TestCase):
    @staticmethod
    def converted(command, **kwargs):
        if '--outdir' in command:
            folder = Path(command[command.index('--outdir')+1])
            stem = Path(command[2]).stem
            (folder/(stem+'.mml')).write_text('1 c4')
        else:
            Path(command[2]).write_bytes(b'MGS')
        return subprocess.CompletedProcess(command, 0, b'', b'')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_explicit_output_keeps_game_subdirectories_and_original_sources(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'psg_scc', Path(tmp)/'out'
            for game in ('NEMESIS2', 'SALAMD'):
                path = source/'vgmrips.net'/game/'SONG01.vgm'
                path.parent.mkdir(parents=True); path.write_bytes(game.encode())
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                rows = run_batch(source, output, keyon=False)
            self.assertEqual({r['mgs'] for r in rows},
                {'vgmrips.net/NEMESIS2/tracks/SONG01.mgs', 'vgmrips.net/SALAMD/tracks/SONG01.mgs'})
            for game in ('NEMESIS2', 'SALAMD'):
                self.assertTrue((output/'vgmrips.net'/game/'tracks/SONG01.mml').is_file())
                self.assertTrue((output/'vgmrips.net'/game/'tracks/SONG01.mgs').is_file())
                self.assertEqual((source/'vgmrips.net'/game/'SONG01.vgm').read_bytes(),game.encode())

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_adjacent_directory_rerun_ignores_generated_vgm_and_mode_trees(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'psg_scc'
            for game in ('NEMESIS2', 'SALAMD'):
                path=source/'vgmrips.net'/game/'SONG01.vgm'
                path.parent.mkdir(parents=True); path.write_bytes(game.encode())
            for branch in ('_diagnostics/old', 'psg_melody', 'psg_rhythm'):
                p=source/branch/'ignored.vgm';p.parent.mkdir(parents=True);p.write_bytes(b'generated')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted) as run:
                for _ in range(2):
                    rows=run_batch(source,keyon=False)
                    self.assertEqual(len(rows),2)
                    self.assertEqual({r['input'] for r in rows},
                        {'vgmrips.net/NEMESIS2/SONG01.vgm','vgmrips.net/SALAMD/SONG01.vgm'})
            self.assertEqual(run.call_count,8)
            for game in ('NEMESIS2','SALAMD'):
                parent=source/'vgmrips.net'/game
                self.assertTrue((parent/'tracks/SONG01.mgs').is_file())
                self.assertEqual((parent/'SONG01.vgm').read_bytes(),game.encode())
                report=json.loads((source/'vgmrips.net'/game/'_diagnostics/SONG01/report.json').read_text())
                self.assertTrue(report['adjacent_output'])
                self.assertEqual(report['output_root'],str(source))
            self.assertTrue((source/'_diagnostics/results.csv').is_file())
            self.assertEqual((source/'_diagnostics/old/ignored.vgm').read_bytes(),b'generated')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_single_source_default_and_solo_outputs_are_beside_source(self, _which):
        from batch_vgm_to_mgs import build_parser
        self.assertIsNone(build_parser().parse_args(['input.vgm']).outdir)
        for part in ('all','melody','rhythm'):
            with self.subTest(part=part),tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'SONG01.vgz';source.write_bytes(b'original')
                with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                    row=run_batch(source,keyon=False,psg_part=part)[0]
                mode=Path() if part=='all' else Path('psg_'+part)
                self.assertEqual(Path(row['mgs']),mode/'tracks/SONG01.mgs')
                self.assertTrue((source.parent/mode/'tracks/SONG01.mgs').is_file())
                self.assertEqual(source.read_bytes(),b'original')

    def test_adjacent_output_keeps_ownership_protection_and_explicit_overlap_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'a.vgm';source.write_bytes(b'original')
            mml=source.parent/'tracks/a.mml';mml.parent.mkdir();mml.write_bytes(b'authored')
            with patch('batch_vgm_to_mgs.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,'unowned or modified'):
                    run_batch(source,keyon=False)
                with self.assertRaisesRegex(ValueError,'separate'):
                    run_batch(source,source.parent,keyon=False)
                run.assert_not_called()
            self.assertEqual(source.read_bytes(),b'original')
            self.assertEqual(mml.read_bytes(),b'authored')


class PackagePublicationTests(unittest.TestCase):
    converted = staticmethod(AdjacentOutputTests.converted)
    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_package_manifest_staging_and_partial_rerun(self, _which):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'input', root/'out'
            game = source/'publisher/GAME'; game.mkdir(parents=True)
            for name in ('a', 'b'):
                (game/(name+'.vgm')).write_bytes(name.encode())
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                rows = run_batch(source, out, keyon=False)
                package = out/'publisher/GAME'
                run_batch(game/'a.vgm', package, keyon=False)
            self.assertEqual({p.name for p in (package/'tracks').iterdir()}, {'a.mml','a.mgs','b.mml','b.mgs'})
            self.assertFalse((package/'tracks/a').exists())
            state = json.loads((package/'listening_manifest.json').read_text())
            self.assertEqual(state['schema_version'], 1)
            self.assertEqual(set(state['entries']), {'a.vgm','b.vgm'})
            for name in ('a','b'):
                entry = state['entries'][name+'.vgm']
                self.assertEqual((package/entry['staged_input']).read_bytes(), name.encode())
                self.assertEqual(entry['source_sha256'], hashlib.sha256(name.encode()).hexdigest())
                self.assertEqual(entry['staged_sha256'], entry['source_sha256'])
                self.assertEqual(entry['diagnostics'], '_diagnostics/'+name)
                self.assertEqual(set(entry['published']), {'tracks/'+name+'.mml','tracks/'+name+'.mgs'})
            saved = json.loads((package/'results.json').read_text())
            self.assertEqual({r['input'] for r in saved}, {'a.vgm','b.vgm'})
            self.assertTrue(all(r['mgs'].startswith('tracks/') for r in saved))
            self.assertTrue(all(r['mgs'].startswith('publisher/GAME/tracks/') for r in rows))

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_modified_staged_source_aborts_without_overwriting_publication(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'original')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                run_batch(source, out, keyon=False)
            staged = out/'_source_inputs/a.vgm'; staged.write_bytes(b'edited')
            with patch('batch_vgm_to_mgs.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'Staged source is unowned or modified'):
                    run_batch(source, out, keyon=False)
                run.assert_not_called()
            self.assertEqual(staged.read_bytes(), b'edited')
            self.assertEqual((out/'tracks/a.mgs').read_bytes(), b'MGS')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_compile_failure_preserves_prior_listening_pair(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'original')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                run_batch(source, out, keyon=False)
            def failed(command, **kwargs):
                if '--outdir' in command:
                    folder = Path(command[command.index('--outdir')+1]); (folder/'a.mml').write_text('new MML')
                    return subprocess.CompletedProcess(command, 0, b'', b'')
                return subprocess.CompletedProcess(command, 1, b'failed', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=failed):
                row = run_batch(source, out, keyon=False)[0]
            self.assertEqual(row['status'], 'compilation_failed')
            self.assertEqual(row['mml'], '')
            self.assertEqual((out/'tracks/a.mml').read_text(), '1 c4')
            self.assertEqual((out/'tracks/a.mgs').read_bytes(), b'MGS')
            entry = json.loads((out/'listening_manifest.json').read_text())['entries']['a.vgm']
            self.assertEqual(entry['status'], 'success')
            self.assertEqual(entry['latest_attempt_status'], 'compilation_failed')


    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_other_source_root_cannot_take_owned_package(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, other, out = root/'input/a.vgm', root/'other/a.vgm', root/'out'
            source.parent.mkdir(); other.parent.mkdir()
            source.write_bytes(b'original'); other.write_bytes(b'other source')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                run_batch(source, out, keyon=False)
            with patch('batch_vgm_to_mgs.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'different source'):
                    run_batch(other, out, keyon=False)
                run.assert_not_called()
            self.assertEqual((out/'_source_inputs/a.vgm').read_bytes(), b'original')

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_failed_new_source_revision_retains_published_source_hash(self, _which):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'original')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                run_batch(source, out, keyon=False)
            source.write_bytes(b'new revision')
            with patch('batch_vgm_to_mgs.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'failed', b'')):
                run_batch(source, out, keyon=False)
            entry = json.loads((out/'listening_manifest.json').read_text())['entries']['a.vgm']
            self.assertEqual(entry['source_sha256'], hashlib.sha256(b'original').hexdigest())
            self.assertEqual(entry['staged_sha256'], hashlib.sha256(b'new revision').hexdigest())
            self.assertEqual(entry['latest_attempt']['source_sha256'], entry['staged_sha256'])

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_publication_replace_error_rolls_back_bundle_and_manifest(self, _which):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, out = root/'a.vgm', root/'out'; source.write_bytes(b'original')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted):
                run_batch(source, out, keyon=False)
            before = {name: (out/name).read_bytes() for name in ('tracks/a.mml','tracks/a.mgs')}
            previous = json.loads((out/'listening_manifest.json').read_text())['entries']['a.vgm']['published']
            real_replace = os.replace
            def replace(source_path, target_path):
                if Path(source_path).name == 'new_1':
                    raise OSError('simulated publication failure')
                return real_replace(source_path, target_path)
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.converted), \
                 patch('batch_vgm_to_mgs.os.replace', side_effect=replace):
                with self.assertRaisesRegex(OSError, 'simulated publication failure'):
                    run_batch(source, out, keyon=False)
            self.assertEqual(before, {name: (out/name).read_bytes() for name in before})
            self.assertEqual(json.loads((out/'listening_manifest.json').read_text())['entries']['a.vgm']['published'], previous)
