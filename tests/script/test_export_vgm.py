"""Authored direct VGM export: isolation, ownership and failure-safe publication."""
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import export_vgm


def psg_vgm():
    raw=bytearray(256);raw[:4]=b'Vgm '
    for offset,value in ((8,0x171),(0x34,256-0x34),(0x74,1789773),(0x18,5145)):
        struct.pack_into('<I',raw,offset,value)
    raw+=bytes([0xa0,0,0xab,0xa0,1,1,0xa0,7,62,0xa0,8,12,
                0x61,0x3a,0x11,0xa0,8,0,0x61,0xdf,2,0x66])
    struct.pack_into('<I',raw,4,len(raw)-4)
    return bytes(raw)


def read_json(path):return json.loads(path.read_text())


class ExportVgmTests(unittest.TestCase):
    def args(self,source,out=None):
        flags=[str(source)]
        if out is not None:flags+=['--outdir',str(out)]
        return export_vgm.parser().parse_args(flags)

    def source(self,root,name='song.vgm'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(psg_vgm())
        return path

    def export(self,source,out=None):return export_vgm.run_export(self.args(source,out))

    def test_recursive_layout_is_flat_per_package_and_compiler_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=root/'inputs';out=root/'out'
            self.source(inputs,'site/pack/one.vgm');self.source(inputs,'site/pack/two.vgm')
            environment=dict(os.environ,PATH='')
            process=subprocess.run([sys.executable,str(ROOT/'scripts/export_vgm.py'),str(inputs),'--outdir',str(out)],
                                   capture_output=True,timeout=90,env=environment)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            package=out/'site/pack'
            self.assertEqual(sorted(p.name for p in (package/'tracks').iterdir()),['one.vgm','two.vgm'])
            self.assertEqual((package/'_source_inputs/one.vgm').read_bytes(),psg_vgm())
            report=read_json(package/'_diagnostics/one/report.json')
            self.assertFalse(report['mml_generated']);self.assertFalse(report['compiler_invoked'])
            self.assertIsNone(report.get('compiler'))
            plan=read_json(package/'_diagnostics/one/one.musical_plan.json')
            self.assertTrue(any(not unit['rest'] for unit in plan['units']))
            self.assertTrue(any(control['kind']=='pitch' for control in plan['controls']))
            self.assertFalse(plan['patterns_executable'])
            self.assertTrue((package/'blueprint/one.mml').is_file())
            self.assertTrue((package/'blueprint/two.mml').is_file())
            self.assertFalse(list((package/'tracks').glob('*.mml')))
            self.assertFalse(list(out.rglob('*.mgs')))
            self.assertTrue((package/'results.csv').exists())
            self.assertEqual(len(read_json(out/'_diagnostics/results.json')),2)

    def test_adjacent_rerun_does_not_rediscover_its_own_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root)
            self.assertEqual(len(self.export(root)),1)
            rows=self.export(root)
            self.assertEqual([r['input'] for r in rows],['song.vgm'])
            self.assertEqual(source.read_bytes(),psg_vgm())
            self.assertEqual(sorted(p.name for p in (root/'tracks').iterdir()),['song.vgm'])
            self.assertFalse((root/'tracks/tracks').exists())

    def test_same_stem_collision_is_rejected_before_any_output_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=root/'in';out=root/'out'
            self.source(inputs)
            (inputs/'song.vgz').write_bytes(gzip.compress(psg_vgm()))
            with self.assertRaisesRegex(ValueError,'Colliding VGM target'):
                self.export(inputs,out)
            self.assertFalse(out.exists())

    def test_unowned_final_is_never_overwritten_or_staged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root/'in');out=root/'out'
            target=out/'tracks/song.vgm';target.parent.mkdir(parents=True);target.write_bytes(b'unowned')
            with self.assertRaisesRegex(ValueError,'unowned or modified'):
                self.export(source,out)
            self.assertEqual(target.read_bytes(),b'unowned')
            self.assertFalse((out/'_source_inputs').exists())

    def test_hand_edited_blueprint_is_preserved_without_blocking_vgm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root/'in');out=root/'out'
            self.export(source,out)
            target=out/'blueprint/song.mml';target.write_text('my editable score')
            before=(out/'tracks/song.vgm').read_bytes()
            rows=self.export(source,out)
            self.assertEqual(rows[0]['status'],'success')
            self.assertEqual(rows[0]['blueprint_status'],'blocked')
            self.assertIn('preserved',rows[0]['blueprint_detail'])
            self.assertEqual(target.read_text(),'my editable score')
            self.assertEqual((out/'tracks/song.vgm').read_bytes(),before)

    def test_blocked_blueprint_is_not_reported_as_latest_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root/'in');out=root/'out'
            self.export(source,out)
            target=out/'blueprint/song.mml';before=target.read_bytes()
            # Exercise worker failure isolation directly, then package publication.
            def worker(command,**kwargs):
                folder=Path(command[command.index('--_worker')+1])
                generated=folder/'song.reconstructed.vgm';generated.write_bytes(psg_vgm())
                export_vgm.save_json(folder/'report.json',dict(status='success',
                    blueprint=dict(status='blocked',detail='authored lane capacity'),vgm_bytes=generated.stat().st_size))
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('export_vgm.subprocess.run',side_effect=worker):
                rows=self.export(source,out)
            self.assertEqual(rows[0]['status'],'success')
            self.assertEqual(rows[0]['blueprint_status'],'blocked')
            self.assertEqual(rows[0]['blueprint'],'')
            self.assertEqual(target.read_bytes(),before)

    def test_modified_final_and_staged_source_are_protected(self):
        for kind in ('final','staged'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);source=self.source(root/'in');out=root/'out'
                self.export(source,out)
                target=out/('tracks/song.vgm' if kind=='final' else '_source_inputs/song.vgm')
                target.write_bytes(b'edited by user')
                with self.assertRaisesRegex(ValueError,'unowned or modified'):
                    self.export(source,out)
                self.assertEqual(target.read_bytes(),b'edited by user')

    def test_failed_worker_report_preserves_last_published_vgm_and_manifest_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root/'in');out=root/'out'
            self.export(source,out);target=out/'tracks/song.vgm';before=target.read_bytes()
            owned=read_json(out/'listening_manifest.json')['entries']['song.vgm']['published']
            def failed(command,**kwargs):
                folder=Path(command[command.index('--_worker')+1])
                export_vgm.save_json(folder/'report.json',dict(status='conversion_failed',detail='authored failure'))
                return subprocess.CompletedProcess(command,1,b'',b'failed')
            with patch('export_vgm.subprocess.run',side_effect=failed):rows=self.export(source,out)
            self.assertEqual(rows[0]['status'],'conversion_failed')
            self.assertEqual(target.read_bytes(),before)
            entry=read_json(out/'listening_manifest.json')['entries']['song.vgm']
            self.assertEqual(entry['published'],owned)
            self.assertEqual(entry['last_status'],'conversion_failed')

    def test_nonzero_worker_cannot_republish_stale_success_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root/'in');out=root/'out'
            self.export(source,out);target=out/'tracks/song.vgm';before=target.read_bytes()
            with patch('export_vgm.subprocess.run',return_value=subprocess.CompletedProcess([],1,b'',b'crashed')):
                rows=self.export(source,out)
            self.assertEqual(rows[0]['status'],'conversion_failed')
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(rows[0]['detail'],'Worker exited unsuccessfully')

    def test_timeout_and_missing_worker_report_are_diagnostic_failures(self):
        for timeout in (False,True):
            with self.subTest(timeout=timeout),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);source=self.source(root/'in');out=root/'out'
                if timeout:
                    effect=subprocess.TimeoutExpired(['worker'],1,output=b'partial',stderr=b'timeout')
                    context=patch('export_vgm.subprocess.run',side_effect=effect)
                else:
                    context=patch('export_vgm.subprocess.run',return_value=subprocess.CompletedProcess([],1,b'',b'failed'))
                with context:rows=self.export(source,out)
                self.assertEqual(rows[0]['status'],'timeout' if timeout else 'conversion_failed')
                self.assertFalse((out/'tracks/song.vgm').exists())
                self.assertEqual(read_json(out/'_diagnostics/song/report.json')['status'],rows[0]['status'])
                self.assertTrue((out/'_diagnostics/song/convert.log').exists())

    def test_existing_mgs_manifest_products_coexist_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=self.source(root/'in');out=root/'out'
            tracks=out/'tracks';tracks.mkdir(parents=True)
            products={'tracks/song.mml':b'authored source mml','tracks/song.mgs':b'authored compiled mgs'}
            for name,data in products.items():(out/name).write_bytes(data)
            staged=out/'_source_inputs/song.vgm';staged.parent.mkdir();staged.write_bytes(source.read_bytes())
            entry=dict(source_path=str(source.resolve()),staged_sha256=export_vgm.file_digest(staged),
                       published={name:export_vgm.file_digest(out/name) for name in products},output='mgs')
            export_vgm.save_json(out/'listening_manifest.json',dict(schema_version=1,entries={'song.vgm':entry}))
            self.assertEqual(self.export(source,out)[0]['status'],'success')
            result=read_json(out/'listening_manifest.json')['entries']['song.vgm']['published']
            self.assertEqual(set(result),set(products)|{'tracks/song.vgm','blueprint/song.mml'})
            for name,data in products.items():self.assertEqual((out/name).read_bytes(),data)


if __name__=='__main__':unittest.main()
