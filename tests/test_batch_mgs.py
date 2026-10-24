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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
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
                    if 'a.vgm' in ' '.join(command) and is_compile == (stage == 'compile'):
                        if is_compile:
                            Path(command[2]).write_bytes(b'incomplete')
                        raise subprocess.TimeoutExpired(command,17,output=b'partial stdout',stderr=b'partial stderr')
                    if is_compile:
                        Path(command[2]).write_bytes(b'MGS')
                    return subprocess.CompletedProcess(command,0,b'',b'')
                with patch('batch_vgm_to_mgs.subprocess.run',side_effect=run):
                    rows = run_batch(source,out,keyon=False,timeout=17)
                self.assertEqual([r['status'] for r in rows],['conversion_failed' if stage == 'convert' else 'compilation_failed','success'])
                log = (out/'_diagnostics/tracks/a.vgm'/f'{stage}.log').read_text()
                self.assertIn('partial stdout',log)
                self.assertIn('partial stderr',log)
                self.assertIn('timed out after 17 seconds',log)
                self.assertFalse((out/'_diagnostics/tracks/a.vgm/a.mgs').exists())
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
            self.assertIn('playback progress',(out/'_diagnostics/tracks/a.vgm/keyon.log').read_text())
            self.assertTrue((out/'a.mgs').exists())

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
            self.assertEqual(calls[1][1:], [str(out/'_diagnostics/tracks/a.vgm/a.mml'),str(out/'_diagnostics/tracks/a.vgm/a.mgs')])
            self.assertEqual(rows[0]['status'],'compilation_failed')
            self.assertIn('diagnostic',(out/'_diagnostics/tracks/a.vgm/compile.log').read_text())

    @patch('batch_vgm_to_mgs.shutil.which', return_value=None)
    def test_failure_continues_and_removes_stale_binary(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'input', Path(tmp)/'out'
            source.mkdir()
            for name in ('a','b'):
                (source/(name+'.vgm')).write_bytes(b'fixture')
            stale = out/'a.mgs'
            stale.parent.mkdir(parents=True); stale.write_bytes(b'stale')
            manifest = out/'_diagnostics/tracks/a.vgm/publication.json'
            manifest.parent.mkdir(parents=True)
            import hashlib
            manifest.write_text(json.dumps(dict(products={'a.mgs': hashlib.sha256(b'stale').hexdigest()})))
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
            self.assertFalse(stale.exists())
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
            self.assertEqual(compare.call_args_list[0].args[1], out/'_diagnostics/tracks/a.vgm/a.mgs')
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
                    (folder/'same.mgs.force.json').write_text(json.dumps(dict(
                        enabled=True, omission_count=2, omissions=[], csv_path='same.mgs.force.csv')))
                    if 'two' in str(folder):
                        self.assertEqual(len(json.loads((out/'_diagnostics/results.json').read_text())), 1)
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('batch_vgm_to_mgs.subprocess.run', side_effect=run), \
                 patch('sys.stdout', new_callable=io.StringIO) as console:
                rows = run_batch(source, out, keyon=False, force=True, fm_state_ms=4,
                                 normalization_ms=16, dump_passes=True)
            self.assertEqual([r['status'] for r in rows], ['success', 'success'])
            self.assertIn('2/2 exported', console.getvalue())
            self.assertIn('2 omitted target operations', console.getvalue())
            for command in calls[::2]:
                self.assertIn('--force', command)
                self.assertIn('--dump-passes', command)
                self.assertEqual(float(command[command.index('--fm-state-ms')+1]), 4)
                self.assertEqual(float(command[command.index('--normalization-ms')+1]), 16)
            for row in rows:
                report = json.loads((out/row['diagnostics']).read_text())
                self.assertTrue(report['options']['force'])
                self.assertEqual(row['normalization_status'], 'unchanged')
                self.assertEqual(row['normalization_reason'], 'no confident shared clock')
                self.assertFalse(report['summaries']['fm_states']['applied'])
                self.assertEqual(report['result']['status'], 'success')
                self.assertEqual(len(report['commands']), 2)
                self.assertTrue((out/row['report']).is_file())
            self.assertNotEqual(rows[0]['mgs'], rows[1]['mgs'])

    @patch('batch_vgm_to_mgs.shutil.which', return_value='/usr/local/bin/mgsc')
    def test_rerun_cleans_only_owned_artifacts_before_conversion(self, _which):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp)/'a.vgm', Path(tmp)/'out'
            source.write_bytes(b'fixture')
            folder = out/'_diagnostics/tracks/a.vgm'; folder.mkdir(parents=True)
            names = ['a.mml', 'a.mgs', 'a.roundtrip.vgm', 'report.json', 'report.txt',
                     'a.normalization.json', 'a.mgs.force.json', 'a.mgs.force.csv', 'compile.log',
                     'a.psg.selection.json', 'a.psg.selection.candidates.csv', 'a.psg.selection.mask.csv']
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
                expected = mode/'nested'/(basename+'.mml')
                self.assertEqual(Path(row['mml']), expected)
                self.assertEqual(Path(row['mgs']), expected.with_suffix('.mgs'))
                diagnostic = Path('_diagnostics')/mode/'tracks/nested'/(basename+'.vgz')
                self.assertEqual(Path(row['diagnostics']), diagnostic/'report.json')
                self.assertTrue((out/'_diagnostics'/mode/'results.json').is_file())
                self.assertEqual(sorted(p.suffix for p in (out/mode/'nested').iterdir()), ['.mgs', '.mml'])
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
    def test_owned_publications_removed_on_failure_but_old_layout_preserved(self, _which):
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
            self.assertTrue((out/'a.mgs').is_file())
            with patch('batch_vgm_to_mgs.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'failed', b'')):
                row = run_batch(source, out, keyon=False)[0]
            self.assertEqual(row['mml'], '')
            self.assertFalse((out/'a.mml').exists()); self.assertFalse((out/'a.mgs').exists())
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
            self.assertEqual(row['mml'], 'a.mml'); self.assertEqual(row['mgs'], '')
            self.assertEqual((out/'a.mml').read_text(), '1 c4'); self.assertFalse((out/'a.mgs').exists())

    def test_collisions_fail_before_any_mutation_or_setup(self):
        cases = [('foo.vgm', 'foo.vgz'), ('Foo.vgm', 'foo.vgm'),
                 ('_diagnostics/a.vgm',), ('psg_melody/a.vgm',),
                 ('a.vgm', 'a.mml/b.vgm')]
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
                final = out/'a.mgs'; final.write_bytes(b'personal')
                if recorded:
                    manifest = out/'_diagnostics/tracks/a.vgm/publication.json'
                    manifest.parent.mkdir(parents=True); manifest.write_text(json.dumps(dict(products={'a.mgs': recorded})))
                with patch('batch_vgm_to_mgs.subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError, 'unowned or modified'):
                        run_batch(source, out, keyon=False)
                    run.assert_not_called()
                self.assertEqual(final.read_bytes(), b'personal')

    def test_batch_parser_aliases_and_mutual_exclusion(self):
        from batch_vgm_to_mgs import build_parser
        parser = build_parser()
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
