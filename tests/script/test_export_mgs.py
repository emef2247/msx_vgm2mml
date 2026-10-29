"""Export defaults, overrides and diagnostic status delegation."""
import json
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import export_mgs


class ExportMgsTests(unittest.TestCase):
    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='disabled')])
    def test_independent_blueprint_timing_forwarding(self, run):
        export_mgs.main(['input', '--score-guided-loops',
                         '--score-tempo', '180'])
        options = run.call_args.kwargs
        self.assertTrue(options['blueprint_score_normalize'])
        self.assertFalse(options['score_normalize'])
        self.assertTrue(options['score_guided_loops'])
        self.assertEqual(options['score_tempo'], 180)
        self.assertTrue(options['keyon'])

    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='disabled')])
    def test_defaults_use_existing_batch_runner(self, run):
        self.assertEqual(export_mgs.main(['input', '--outdir', 'output', '--skip-keyon-counts']), 0)
        self.assertEqual(run.call_args.args, (Path('input'), Path('output')))
        self.assertEqual(run.call_args.kwargs['fm_state_ms'], 24)
        self.assertIsNone(run.call_args.kwargs['psg_state_ms'])
        self.assertIsNone(run.call_args.kwargs['scc_state_ms'])
        self.assertIsNone(run.call_args.kwargs['curve_volume_error'])
        self.assertIsNone(run.call_args.kwargs['curve_mean_error'])
        self.assertFalse(run.call_args.kwargs['normalize_lengths'])
        self.assertFalse(run.call_args.kwargs['enhance_drums'])
        self.assertEqual(run.call_args.kwargs['psg_part'], 'all')
        self.assertEqual(run.call_args.kwargs['normalization_ms'], 8)
        self.assertEqual(run.call_args.kwargs['timeout'], 1200)
        self.assertFalse(run.call_args.kwargs['keyon'])
        self.assertTrue(run.call_args.kwargs['software_volume_curves'])

    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='compared')])
    def test_explicit_thresholds_and_existing_options_are_forwarded(self, run):
        result = export_mgs.main(['input.vgm', '--outdir', 'output', '--fm-state-ms', '4',
                                 '--normalization-ms', '16', '--force', '--dump-passes',
                                 '--legacy-macros', '--legacy-loops', '--timeout', '90'])
        self.assertEqual(result, 0)
        settings = run.call_args.kwargs
        self.assertEqual((settings['fm_state_ms'], settings['normalization_ms']), (4, 16))
        self.assertTrue(settings['force']); self.assertTrue(settings['dump_passes'])
        self.assertIsNone(settings['psg_state_ms'])
        self.assertIsNone(settings['scc_state_ms'])
        self.assertFalse(settings['enhance_drums'])
        self.assertFalse(settings['enhance_macros']); self.assertTrue(settings['legacy_loops'])
        self.assertTrue(settings['keyon']); self.assertEqual(settings['timeout'], 90)

    @patch('export_mgs.run_batch')
    def test_removed_export_options_are_rejected(self, run):
        flags = [('--state-ms','4'),('--psg-state-ms','4'),('--scc-state-ms','4'),
                 ('--curve-volume-error','1'),('--curve-mean-error','0.25'),
                 ('--enhance-rhythm',),('--enhance-drums',),('--normalize-lengths',),
                 ('--psg-melody-only',),('--psg-rhythm-only',),
                 ('--psg-melody_only',),('--psg-rhythm_only',),('--blueprint-score-normalize',)]
        for arguments in flags:
            with self.subTest(arguments=arguments),patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit):
                export_mgs.main(['input',*arguments])
        run.assert_not_called()

    @patch('export_mgs.run_batch')
    def test_invalid_fm_state_never_starts_conversion(self, run):
        for value in ('0','-1','nan','inf','0.001'):
            with self.subTest(value=value),patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit):
                export_mgs.main(['input','--fm-state-ms',value])
        run.assert_not_called()

    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='disabled')])
    def test_software_volume_curves_are_forwarded(self, run):
        self.assertEqual(export_mgs.main(['input', '--software-volume-curves']), 0)
        self.assertTrue(run.call_args.kwargs['software_volume_curves'])
        self.assertEqual(export_mgs.main(['input', '--no-software-volume-curves']), 0)
        self.assertFalse(run.call_args.kwargs['software_volume_curves'])
        export_mgs.main(['--','--legacy-macros'])
        self.assertEqual(run.call_args.args[0],Path('--legacy-macros'))
        self.assertTrue(run.call_args.kwargs['enhance_macros'])
        with self.assertRaises(SystemExit):
            export_mgs.main(['input', '--software-volume-curves', '--no-software-volume-curves'])

    def test_help_has_one_visible_switch_per_default_enabled_feature(self):
        help_text=export_mgs.build_parser().format_help()
        self.assertNotIn('--enhance-macros',help_text)
        self.assertNotIn(' --software-volume-curves',help_text)
        self.assertIn('--legacy-macros',help_text)
        self.assertIn('--no-software-volume-curves',help_text)
        self.assertIn('--fm-state-ms',help_text)
        self.assertNotIn('--state-ms',help_text)
        self.assertNotIn('--psg-state-ms',help_text)
        self.assertNotIn('--scc-state-ms',help_text)
        self.assertNotIn('--curve-volume-error',help_text)
        self.assertNotIn('--curve-mean-error',help_text)
        self.assertNotIn('--enhance-rhythm',help_text)
        self.assertNotIn('--psg-melody-only',help_text)
        self.assertNotIn('--psg-rhythm-only',help_text)
        self.assertNotIn('--normalize-lengths',help_text)
        self.assertNotIn('--legacy-macros [',help_text)
        self.assertNotIn('--no-software-volume-curves [',help_text)
        self.assertNotIn('BOOL',help_text)
        self.assertNotIn('--skip-keyon-counts',help_text)
        self.assertNotIn('--blueprint-score-normalize',help_text)

    @patch('export_mgs.run_batch',return_value=[dict(status='success',keyon_status='disabled')])
    def test_value_free_switches_and_positional_input(self,run):
        export_mgs.main(['input'])
        self.assertTrue(run.call_args.kwargs['software_volume_curves'])
        self.assertTrue(run.call_args.kwargs['enhance_macros'])
        export_mgs.main(['--no-software-volume-curves','false'])
        self.assertEqual(run.call_args.args[0],Path('false'))
        self.assertFalse(run.call_args.kwargs['software_volume_curves'])
        with self.assertRaises(SystemExit):export_mgs.main(['input','--legacy-macros','maybe'])
        export_mgs.main(['--legacy-macros','--no-software-volume-curves','input'])
        self.assertFalse(run.call_args.kwargs['enhance_macros'])
        self.assertFalse(run.call_args.kwargs['software_volume_curves'])
        export_mgs.main(['input','--enhance-macros'])
        self.assertTrue(run.call_args.kwargs['enhance_macros'])
        for flag in ('--legacy-macros','--no-software-volume-curves','--software-volume-curves'):
            for value in ('yes','no','true','false','1','0'):
                with self.subTest(flag=flag,value=value),patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit):
                    export_mgs.main(['input',flag,value])
                with self.subTest(flag=flag,value=value),patch('sys.stderr',new=io.StringIO()),self.assertRaises(SystemExit):
                    export_mgs.main(['input',flag+'='+value])

    def test_exit_status_keeps_compilation_and_verification_failures(self):
        for row in [dict(status='compilation_failed', keyon_status='not_compiled'),
                    dict(status='success', keyon_status='error'),
                    dict(status='success', keyon_status='mismatch')]:
            with self.subTest(row=row), patch('export_mgs.run_batch', return_value=[row]):
                self.assertEqual(export_mgs.main(['input', '--outdir', 'output']), 1)
        with patch('export_mgs.run_batch', side_effect=ValueError('invalid source')):
            with self.assertRaises(SystemExit) as error:
                export_mgs.main(['input', '--outdir', 'output'])
            self.assertEqual(error.exception.code, 2)

    def test_real_public_conversion_records_export_defaults(self):
        fixture = ROOT / 'tests/fixtures/public/psg/scale_rom1/scale_rom1.vgm'
        with tempfile.TemporaryDirectory() as folder:
            diag=Path(folder)/'_diagnostics/scale_rom1'
            diag.mkdir(parents=True)
            for chip in ('psg','scc'):
                for suffix in ('json','decisions.csv'):
                    (diag/f'scale_rom1.{chip}.curve_approx.{suffix}').write_text('old run')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/export_mgs.py'),
                                     str(fixture), '--outdir', folder, '--skip-keyon-counts'],
                                    capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            report = json.loads((Path(folder) / '_diagnostics/scale_rom1/report.json').read_text())
            self.assertEqual(report['options']['fm_state_ms'], 24)
            self.assertIsNone(report['options']['psg_state_ms'])
            self.assertIsNone(report['options']['scc_state_ms'])
            self.assertIsNone(report['options']['curve_volume_error'])
            self.assertIsNone(report['options']['curve_mean_error'])
            self.assertEqual(report['options']['curve_approximation'],{})
            self.assertEqual(report['options']['normalization_ms'], 8)
            self.assertTrue(report['options']['normalization_enabled'])
            self.assertTrue(report['options']['blueprint_score_normalize'])
            blueprint=(Path(folder)/'blueprint/scale_rom1.mml').read_text(encoding='cp932')
            self.assertIn('#tempo 225',blueprint)
            self.assertNotIn('%', '\n'.join(line.split(';',1)[0] for line in blueprint.splitlines()))
            midi=Path(folder)/'blueprint/scale_rom1.midi'
            self.assertTrue(midi.read_bytes().startswith(b'MThd'))
            self.assertEqual(report['result']['blueprint_midi_files'],['blueprint/scale_rom1.midi'])
            manifest=json.loads((Path(folder)/'listening_manifest.json').read_text())
            self.assertIn('blueprint/scale_rom1.midi',manifest['entries']['scale_rom1.vgm']['published'])
            self.assertEqual(report['result']['status'], 'success')
            self.assertEqual(report['result']['normalization_status'], 'unchanged')
            self.assertIn('no confident shared clock', report['result']['normalization_reason'])
            self.assertFalse((Path(folder)/'_diagnostics/scale_rom1/scale_rom1.psg.curve_approx.json').exists())
            self.assertFalse((diag/'scale_rom1.psg.curve_approx.decisions.csv').exists())
            self.assertFalse((diag/'scale_rom1.scc.curve_approx.json').exists())
            self.assertFalse((diag/'scale_rom1.scc.curve_approx.decisions.csv').exists())





class AdjacentExportTests(unittest.TestCase):
    @patch('export_mgs.run_batch', return_value=[dict(status='success',keyon_status='disabled')])
    def test_omitted_outdir_delegates_adjacent_output_without_changing_defaults(self, run):
        self.assertEqual(export_mgs.main(['input','--skip-keyon-counts']),0)
        self.assertEqual(run.call_args.args,(Path('input'),None))
        self.assertEqual(run.call_args.kwargs['fm_state_ms'],24)
        self.assertEqual(run.call_args.kwargs['normalization_ms'],8)
        self.assertTrue(run.call_args.kwargs['software_volume_curves'])

    def test_both_entrypoints_publish_adjacent_products_and_preserve_public_source(self):
        fixture=ROOT/'tests/fixtures/public/opll/ym2413_retrigger/ym2413_retrigger.vgm'
        original=fixture.read_bytes()
        for entry in ('export_mgs.py','batch_vgm_to_mgs.py'):
            with self.subTest(entry=entry),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);source=folder/'SONG01.vgm';source.write_bytes(original)
                run=subprocess.run([sys.executable,str(ROOT/'scripts'/entry),str(source)],
                                   capture_output=True,timeout=120)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.assertEqual(source.read_bytes(),original)
                self.assertEqual(sorted(p.name for p in folder.iterdir()),
                                 ['SONG01.vgm','_diagnostics','_source_inputs','blueprint','listening_manifest.json','results.csv','results.json','tracks'])
                self.assertTrue((folder/'blueprint/SONG01.mml').is_file())
                report=json.loads((folder/'_diagnostics/SONG01/report.json').read_text())
                self.assertTrue(report['adjacent_output'])
                self.assertEqual(report['result']['reference_keyon'],report['result']['actual_keyon'])
                self.assertGreater(report['result']['actual_keyon'],0)
                self.assertEqual(report['result']['keyon_status'],'compared')


if __name__ == '__main__':
    unittest.main()
