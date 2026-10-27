"""Opt-in score/curve options reach canonical workers without changing defaults."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts')]
from mgs_conversion_config import MgsOptions, add_curve_arguments, curve_option_values
import batch_vgm_to_mgs
import export_mgs
import export_vgm


CURVES=dict(score_guided_loops=True,psg_state_ms=24,scc_state_ms=32,
            curve_volume_error=1,curve_mean_error=.25)


class CurveOptionTests(unittest.TestCase):
    def test_old_default_flags_and_positional_arguments_are_preserved(self):
        self.assertEqual(MgsOptions().cli_args(),['--no-software-volume-curves'])
        options=MgsOptions(False,None,None,True,False,False,'all',True)
        self.assertEqual(options.cli_args(),['--force','--software-volume-curves'])
        self.assertFalse(options.enabled)
        self.assertFalse(options.score_guided_loops)
        self.assertEqual(options.curve_approx_options,{})
        self.assertFalse(MgsOptions(score_guided_loops=True).enabled)
        self.assertEqual(MgsOptions(psg_state_ms=0,scc_state_ms=0).curve_approx_options,{})

    def test_curve_options_are_independent_of_musical_clock_normalization(self):
        options=MgsOptions(software_volume_curves=True,**CURVES)
        self.assertFalse(options.enabled)
        self.assertEqual(options.curve_approx_options,dict(
            psg=dict(state_ms=24,max_volume_error=1,max_mean_error=.25),
            scc=dict(state_ms=32,max_volume_error=1,max_mean_error=.25)))
        values=options.as_dict()
        self.assertTrue(values['score_guided_loops'])
        self.assertIn('register',values['curve_error_units'])
        self.assertIn('not acoustic',values['curve_error_units'])
        self.assertIn('volume only',values['curve_approximation_scope'])
        self.assertEqual(values['curve_approximation'],options.curve_approx_options)

    def test_invalid_configs_and_missing_explicit_error_budgets_are_rejected(self):
        base=dict(software_volume_curves=True,**CURVES)
        invalid=[dict(psg_state_ms=-1),dict(scc_state_ms=float('nan')),
                 dict(psg_state_ms=float('inf')),dict(curve_volume_error=-1),
                 dict(curve_volume_error=16),dict(curve_mean_error=16),
                 dict(curve_mean_error=float('nan')),dict(curve_volume_error=None),
                 dict(curve_mean_error=None)]
        for update in invalid:
            with self.subTest(update=update),self.assertRaises(ValueError):
                MgsOptions(**dict(base,**update))
        uncoalesced=MgsOptions(psg_state_ms=24,curve_volume_error=1,curve_mean_error=.25)
        self.assertFalse(uncoalesced.software_volume_curves)
        self.assertIn('psg',uncoalesced.curve_approx_options)
        self.assertEqual(MgsOptions(software_volume_curves=True,scc_state_ms=24,
            curve_volume_error=0,curve_mean_error=0).curve_approx_options['scc']['max_volume_error'],0)

    def test_shared_argument_roundtrip_and_only_active_chip_is_forwarded_to_projection(self):
        options=MgsOptions(software_volume_curves=True,**dict(CURVES,scc_state_ms=0))
        parser=batch_vgm_to_mgs.build_parser()
        args=parser.parse_args(['input']+options.cli_args())
        rebuilt=MgsOptions(software_volume_curves=args.software_volume_curves,**curve_option_values(args))
        self.assertEqual(rebuilt.curve_approx_options,options.curve_approx_options)
        self.assertNotIn('scc',rebuilt.curve_approx_options)
        self.assertEqual(curve_option_values(parser.parse_args(['input']+rebuilt.cli_args())),
                         curve_option_values(args))
        plain=argparse.ArgumentParser();add_curve_arguments(plain)
        self.assertEqual(curve_option_values(plain.parse_args(options.curve_cli_args())),
                         curve_option_values(args))

    def test_export_mgs_forwards_explicit_curve_and_guide_settings(self):
        options=MgsOptions(software_volume_curves=True,**CURVES)
        with patch.object(export_mgs,'run_batch',return_value=[] ) as run:
            self.assertEqual(export_mgs.main(['input']+options.curve_cli_args()),0)
        for name,value in CURVES.items():
            self.assertEqual(run.call_args.kwargs[name],value)
        self.assertTrue(run.call_args.kwargs['software_volume_curves'])
        defaults=export_mgs.build_parser().parse_args(['input'])
        self.assertIsNone(defaults.psg_state_ms)
        self.assertFalse(defaults.score_guided_loops)

    def test_nested_batch_worker_and_diagnostics_receive_settings(self):
        commands=[]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'inputs/site/game';source.mkdir(parents=True)
            (source/'song.vgm').write_bytes(b'authored')
            def run(command,**kwargs):
                commands.append(command)
                if '--outdir' in command:
                    folder=Path(command[command.index('--outdir')+1])
                    (folder/'song.mml').write_text('1 c4')
                else:
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('batch_vgm_to_mgs.shutil.which',return_value='mgsc'),patch(
                    'batch_vgm_to_mgs.subprocess.run',side_effect=run):
                rows=batch_vgm_to_mgs.run_batch(root/'inputs',root/'out',keyon=False,
                    software_volume_curves=True,**CURVES)
            self.assertEqual(rows[0]['status'],'success')
            conversion=next(c for c in commands if '--outdir' in c)
            self.assertIn('--score-guided-loops',conversion)
            for flag,value in (('--psg-state-ms','24'),('--scc-state-ms','32'),
                               ('--curve-volume-error','1'),('--curve-mean-error','0.25')):
                self.assertEqual(conversion[conversion.index(flag)+1],value)
            report=json.loads((root/'out/site/game/_diagnostics/song/report.json').read_text())
            self.assertEqual(report['options']['curve_approximation']['psg']['state_ms'],24)
            self.assertTrue(report['options']['score_guided_loops'])

    def test_vgm_worker_flags_roundtrip_and_validation(self):
        options=MgsOptions(software_volume_curves=True,**CURVES)
        args=export_vgm.parser().parse_args(['input']+options.curve_cli_args())
        flags=export_vgm._flags(args)
        rebuilt=export_vgm.parser().parse_args(['input']+flags)
        self.assertEqual(curve_option_values(args),curve_option_values(rebuilt))
        self.assertNotIn('--normalize-lengths',flags)
        defaults=export_vgm.parser().parse_args(['input'])
        self.assertEqual(export_vgm._flags(defaults),
            ['--normalization-ms','8','--fm-state-ms','24','--song-loop','none'])
        invalid=export_vgm.parser().parse_args(['input','--psg-state-ms','24'])
        with self.assertRaisesRegex(ValueError,'curve-volume-error'):
            export_vgm._flags(invalid)

    def test_vgm_worker_projects_validated_options_to_plan_api(self):
        options=MgsOptions(software_volume_curves=True,**CURVES)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            args=export_vgm.parser().parse_args(['input.vgm','--_worker',str(root)]+options.curve_cli_args())
            with patch.object(export_vgm,'build_plan',side_effect=ValueError('authored stop')) as build:
                self.assertEqual(export_vgm._worker(args),1)
            values=build.call_args.kwargs
            self.assertTrue(values['score_guided_loops'])
            self.assertEqual(values['curve_approx_options'],options.curve_approx_options)
            self.assertNotIn('psg_state_ms',values)
            self.assertNotIn('curve_volume_error',values)


if __name__=='__main__':
    unittest.main()
