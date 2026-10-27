"""Musical reference products publish independently of the MGS compiler."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'py')]
from batch_vgm_to_mgs import file_digest, reference_vgm_product, run_batch
import export_mgs
import export_vgm


class ReferenceVgmPublicationTests(unittest.TestCase):
    def process(self, *, conversion=0, compilation=0, reference=True, setup=0):
        def run(command, **kwargs):
            if '--check' in command:
                return subprocess.CompletedProcess(command, setup, b'compiler setup', b'')
            if '--outdir' not in command:
                if not compilation:
                    Path(command[2]).write_bytes(b'MGS')
                return subprocess.CompletedProcess(command, compilation, b'compiler failure', b'')
            self.assertEqual(command[command.index('--output-format')+1], 'both')
            folder = Path(command[command.index('--outdir')+1])
            stem = Path(command[2]).stem
            (folder/(stem+'.mml')).write_text('1 c4')
            blueprint = folder/'blueprint'/(stem+'.mml')
            blueprint.parent.mkdir(exist_ok=True)
            blueprint.write_text('1 v15 c4')
            report = dict(blueprint=dict(status='success', path=str(blueprint), sha256=file_digest(blueprint)))
            if reference:
                vgm = folder/'tracks'/(stem+'.vgm')
                vgm.parent.mkdir(exist_ok=True)
                vgm.write_bytes(b'authored musical reference')
                report['direct_vgm'] = dict(status='success', vgm=str(vgm), vgm_sha256=file_digest(vgm))
            else:
                report['direct_vgm'] = dict(status='failed', detail='authored writer failure')
            (folder/(stem+'.conversion.json')).write_text(json.dumps(report))
            return subprocess.CompletedProcess(command, conversion, b'conversion detail', b'')
        return run

    def test_compile_and_conversion_failures_still_publish_verified_reference(self):
        for conversion, compilation in ((0, 1), (1, 0)):
            with self.subTest(conversion=conversion), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source = root/'song.vgm'; source.write_bytes(b'authored')
                with patch('batch_vgm_to_mgs.shutil.which', return_value='mgsc'), patch(
                        'batch_vgm_to_mgs.subprocess.run', side_effect=self.process(conversion=conversion, compilation=compilation)):
                    row = run_batch(source, root/'out', keyon=False)[0]
                self.assertEqual(row['vgm_status'], 'success')
                self.assertEqual(row['vgm'], 'tracks/song.vgm')
                self.assertTrue((root/'out'/row['vgm']).is_file())
                self.assertTrue((root/'out/blueprint/song.mml').is_file())
                self.assertEqual(bool(row['mml']), not conversion)
                entry = json.loads((root/'out/listening_manifest.json').read_text())['entries']['song.vgm']
                self.assertEqual(entry['published']['tracks/song.vgm'], file_digest(root/'out/tracks/song.vgm'))

    def test_setup_failure_keeps_mml_reference_and_blueprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'song.vgm'; source.write_bytes(b'authored')
            with patch('batch_vgm_to_mgs.shutil.which', return_value=None), patch(
                    'batch_vgm_to_mgs.subprocess.run', side_effect=self.process(setup=2)):
                row = run_batch(source, root/'out', keyon=False)[0]
            self.assertEqual(row['error_code'], 'compiler_setup_error')
            self.assertTrue(row['mml'] and row['vgm'] and row['blueprint'])

    def test_reference_partial_failure_still_compiles_and_publishes_current_mml(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'song.vgm';source.write_bytes(b'authored')
            process=self.process(conversion=1,reference=False)
            def run(command,**kwargs):
                result=process(command,**kwargs)
                if '--outdir' in command:
                    folder=Path(command[command.index('--outdir')+1])
                    report=folder/'song.conversion.json';data=json.loads(report.read_text())
                    data.update(status='partial_failure',outputs=dict(mml=dict(
                        status='success',path=str(folder/'song.mml'))))
                    report.write_text(json.dumps(data))
                return result
            with patch('batch_vgm_to_mgs.shutil.which',return_value='mgsc'),patch(
                    'batch_vgm_to_mgs.subprocess.run',side_effect=run):
                row=run_batch(source,root/'out',keyon=False)[0]
            self.assertEqual(row['status'],'success')
            self.assertEqual(row['vgm_status'],'failed')
            self.assertTrue(row['mml'] and row['mgs'])

    def test_failed_reference_preserves_prior_hash_and_mml_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'song.vgm'; source.write_bytes(b'authored')
            with patch('batch_vgm_to_mgs.shutil.which', return_value='mgsc'):
                with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.process()):
                    run_batch(source, root/'out', keyon=False)
                target = root/'out/tracks/song.vgm'; digest = file_digest(target)
                source.write_bytes(b'new authored source')
                with patch('batch_vgm_to_mgs.subprocess.run', side_effect=self.process(reference=False)):
                    row = run_batch(source, root/'out', keyon=False)[0]
                self.assertEqual(row['status'], 'success')
                self.assertEqual(row['vgm'], '')
                self.assertEqual(row['vgm_status'], 'failed')
                self.assertEqual(file_digest(target), digest)
                entry = json.loads((root/'out/listening_manifest.json').read_text())['entries']['song.vgm']
                self.assertEqual(entry['published']['tracks/song.vgm'], digest)
                target.write_bytes(b'edited')
                with patch('batch_vgm_to_mgs.subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError, 'unowned or modified'):
                        run_batch(source, root/'out', keyon=False)
                    run.assert_not_called()

    def test_recursive_adjacent_reruns_skip_generated_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)/'album'; source.mkdir(); (source/'song.vgm').write_bytes(b'authored')
            with patch('batch_vgm_to_mgs.shutil.which', return_value='mgsc'), patch(
                    'batch_vgm_to_mgs.subprocess.run', side_effect=self.process()):
                self.assertEqual(len(run_batch(Path(temporary), keyon=False)), 1)
                rows = run_batch(Path(temporary), keyon=False)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['vgm'], 'album/tracks/song.vgm')
            result = json.loads((source/'results.json').read_text())[0]
            self.assertEqual(result['vgm'], 'tracks/song.vgm')

    def test_foreign_or_stale_reference_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); path = folder/'song.vgm'; path.write_bytes(b'authored')
            report = dict(direct_vgm=dict(status='success', vgm=str(path), vgm_sha256=file_digest(path)))
            self.assertEqual(reference_vgm_product(report, folder, 'song')[1], 'blocked')
            path = folder/'tracks/song.vgm'; path.parent.mkdir(); path.write_bytes(b'authored')
            report['direct_vgm'].update(vgm=str(path), vgm_sha256='stale')
            self.assertEqual(reference_vgm_product(report, folder, 'song')[1], 'blocked')

    def test_export_vgm_and_mgs_share_owned_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'song.vgm'; source.write_bytes(b'authored')
            output = root/'out'
            args = export_vgm.parser().parse_args([str(source), '--outdir', str(output)])
            def worker(command, **kwargs):
                folder = Path(command[command.index('--_worker')+1])
                generated = folder/'song.reconstructed.vgm'
                generated.write_bytes(b'authored reconstructed reference')
                (folder/'report.json').write_text(json.dumps(dict(status='success', vgm_bytes=generated.stat().st_size)))
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('export_vgm.subprocess.run', side_effect=worker):
                export_vgm.run_export(args)
            with patch('batch_vgm_to_mgs.shutil.which', return_value='mgsc'), patch(
                    'batch_vgm_to_mgs.subprocess.run', side_effect=self.process()):
                self.assertEqual(run_batch(source, output, keyon=False)[0]['vgm_status'], 'success')
            with patch('export_vgm.subprocess.run', side_effect=worker):
                export_vgm.run_export(args)
            entry = json.loads((output/'listening_manifest.json').read_text())['entries']['song.vgm']
            self.assertTrue({'tracks/song.vgm', 'tracks/song.mml', 'tracks/song.mgs'}.issubset(entry['published']))
            self.assertEqual(entry['published']['tracks/song.vgm'], file_digest(output/'tracks/song.vgm'))

    def test_cli_reports_reference_failure_despite_successful_mgs(self):
        row = dict(status='success', keyon_status='disabled', vgm_status='failed')
        with patch('export_mgs.run_batch', return_value=[row]):
            self.assertEqual(export_mgs.main(['authored.vgm']), 1)


if __name__ == '__main__':
    unittest.main()
