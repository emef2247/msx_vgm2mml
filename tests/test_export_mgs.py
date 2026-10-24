"""Export defaults, overrides and diagnostic status delegation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
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
            report = json.loads((Path(folder) / '_diagnostics/tracks/scale_rom1.vgm/report.json').read_text())
            self.assertEqual(report['options']['fm_state_ms'], 24)
            self.assertEqual(report['options']['normalization_ms'], 8)
            self.assertTrue(report['options']['normalization_enabled'])
            self.assertEqual(report['result']['status'], 'success')
            self.assertEqual(report['result']['normalization_status'], 'unchanged')
            self.assertIn('no confident shared clock', report['result']['normalization_reason'])


if __name__ == '__main__':
    unittest.main()
