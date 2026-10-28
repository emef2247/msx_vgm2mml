"""Export defaults, overrides and diagnostic status delegation."""
import json
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
    def test_defaults_use_existing_batch_runner(self, run):
        self.assertEqual(export_mgs.main(['input', '--outdir', 'output', '--skip-keyon-counts']), 0)
        self.assertEqual(run.call_args.args, (Path('input'), Path('output')))
        self.assertEqual(run.call_args.kwargs['fm_state_ms'], 24)
        self.assertEqual(run.call_args.kwargs['normalization_ms'], 8)
        self.assertEqual(run.call_args.kwargs['timeout'], 1200)
        self.assertFalse(run.call_args.kwargs['keyon'])
        self.assertTrue(run.call_args.kwargs['software_volume_curves'])

    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='compared')])
    def test_explicit_thresholds_and_existing_options_are_forwarded(self, run):
        result = export_mgs.main(['input.vgm', '--outdir', 'output', '--fm-state-ms', '4',
                                 '--normalization-ms', '16', '--force', '--dump-passes',
                                 '--legacy-macros', '--legacy-loops', '--enhance-drums', '--timeout', '90'])
        self.assertEqual(result, 0)
        settings = run.call_args.kwargs
        self.assertEqual((settings['fm_state_ms'], settings['normalization_ms']), (4, 16))
        self.assertTrue(settings['force']); self.assertTrue(settings['dump_passes'])
        self.assertTrue(settings['enhance_drums'])
        self.assertFalse(settings['enhance_macros']); self.assertTrue(settings['legacy_loops'])
        self.assertTrue(settings['keyon']); self.assertEqual(settings['timeout'], 90)

    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='disabled')])
    def test_rhythm_aliases_and_solo_modes(self, run):
        for rhythm in ('--enhance-rhythm', '--enhance-drums'):
            for flag, part in (('--psg-melody-only', 'melody'), ('--psg-melody_only', 'melody'),
                               ('--psg-rhythm-only', 'rhythm')):
                self.assertEqual(export_mgs.main(['input', '--outdir', 'out', rhythm, flag]), 0)
                self.assertEqual(run.call_args.kwargs['psg_part'], part)
                self.assertTrue(run.call_args.kwargs['enhance_drums'])
        with self.assertRaises(SystemExit):
            export_mgs.main(['input', '--outdir', 'out', '--psg-melody-only', '--psg-rhythm-only'])

    @patch('export_mgs.run_batch', return_value=[dict(status='success', keyon_status='selection_only')])
    def test_completed_solo_selection_verification_has_success_exit(self, run):
        self.assertEqual(export_mgs.main(['input', '--outdir', 'out', '--psg-melody-only']), 0)
        self.assertEqual(run.call_args.kwargs['psg_part'], 'melody')

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

    @patch('export_mgs.run_batch',return_value=[dict(status='success',keyon_status='disabled')])
    def test_boolean_values_and_negative_switch_meanings(self,run):
        for value in ('yes','y','Y','1','true','TRUE'):
            export_mgs.main(['input','--legacy-macros',value,'--no-software-volume-curves',value])
            self.assertFalse(run.call_args.kwargs['enhance_macros'])
            self.assertFalse(run.call_args.kwargs['software_volume_curves'])
        for value in ('no','n','N','0','false','FALSE'):
            export_mgs.main(['input','--legacy-macros',value,'--no-software-volume-curves',value])
            self.assertTrue(run.call_args.kwargs['enhance_macros'])
            self.assertTrue(run.call_args.kwargs['software_volume_curves'])
        with self.assertRaises(SystemExit):export_mgs.main(['input','--legacy-macros','maybe'])
        export_mgs.main(['--legacy-macros','--no-software-volume-curves','input'])
        self.assertFalse(run.call_args.kwargs['enhance_macros'])
        self.assertFalse(run.call_args.kwargs['software_volume_curves'])

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
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/export_mgs.py'),
                                     str(fixture), '--outdir', folder, '--skip-keyon-counts'],
                                    capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            report = json.loads((Path(folder) / '_diagnostics/scale_rom1/report.json').read_text())
            self.assertEqual(report['options']['fm_state_ms'], 24)
            self.assertEqual(report['options']['normalization_ms'], 8)
            self.assertTrue(report['options']['normalization_enabled'])
            self.assertEqual(report['result']['status'], 'success')
            self.assertEqual(report['result']['normalization_status'], 'unchanged')
            self.assertIn('no confident shared clock', report['result']['normalization_reason'])





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
