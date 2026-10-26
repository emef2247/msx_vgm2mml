"""Blueprint publication is additional and independent of the listening pair."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'py')]
from batch_vgm_to_mgs import blueprint_product, run_batch


class BlueprintPublicationTests(unittest.TestCase):
    def test_conversion_failure_can_publish_blueprint_and_keep_old_listening_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'input';source.mkdir();(source/'song.vgm').write_bytes(b'authored')
            out=root/'out'
            def process(command,**kwargs):
                if '--outdir' in command:
                    folder=Path(command[command.index('--outdir')+1])
                    (folder/'song.mml').write_text('1 c4')
                else:
                    Path(command[2]).write_bytes(b'listening mgs')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('batch_vgm_to_mgs.shutil.which',return_value='mgsc'),patch('batch_vgm_to_mgs.subprocess.run',side_effect=process):
                run_batch(source,out,keyon=False)
            old=(out/'tracks/song.mgs').read_bytes()
            returncode=[1]
            def failure(command,**kwargs):
                if '--outdir' not in command:
                    Path(command[2]).write_bytes(b'listening mgs')
                    return subprocess.CompletedProcess(command,0,b'',b'')
                folder=Path(command[command.index('--outdir')+1]);target=folder/'blueprint/song.mml'
                target.parent.mkdir(exist_ok=True);target.write_text('1 v15 c4 v9 d4')
                (folder/'song.mml').write_text('1 c4')
                report=dict(blueprint=dict(status='success',path=str(target.resolve()),
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
                (folder/'song.conversion.json').write_text(json.dumps(report))
                return subprocess.CompletedProcess(command,returncode[0],b'authored text capacity failure',b'')
            with patch('batch_vgm_to_mgs.shutil.which',return_value='mgsc'),patch('batch_vgm_to_mgs.subprocess.run',side_effect=failure):
                rows=run_batch(source,out,keyon=False)
            self.assertEqual(rows[0]['status'],'conversion_failed')
            self.assertEqual(rows[0]['blueprint_status'],'success')
            self.assertEqual((out/'blueprint/song.mml').read_text(),'1 v15 c4 v9 d4')
            self.assertEqual((out/'tracks/song.mgs').read_bytes(),old)
            entry=json.loads((out/'listening_manifest.json').read_text())['entries']['song.vgm']
            self.assertEqual(set(entry['published']),{'tracks/song.mgs','tracks/song.mml','blueprint/song.mml'})
            (out/'blueprint/song.mml').write_text('my score')
            returncode[0]=0
            with patch('batch_vgm_to_mgs.shutil.which',return_value='mgsc'),patch('batch_vgm_to_mgs.subprocess.run',side_effect=failure):
                rows=run_batch(source,out,keyon=False)
            self.assertEqual(rows[0]['status'],'success')
            self.assertEqual(rows[0]['blueprint_status'],'blocked')
            self.assertEqual((out/'blueprint/song.mml').read_text(),'my score')

    def test_no_stale_or_foreign_blueprint_is_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'blueprint/song.mml';target.parent.mkdir();target.write_text('old')
            digest=hashlib.sha256(target.read_bytes()).hexdigest()
            report=dict(blueprint=dict(status='blocked',path=str(target),sha256=digest))
            self.assertIsNone(blueprint_product(report,root,'song'))
            report['blueprint']['status']='success';report['blueprint']['sha256']='stale'
            self.assertIsNone(blueprint_product(report,root,'song'))
            report['blueprint'].update(path=str(root.parent/'foreign.mml'),sha256=digest)
            self.assertIsNone(blueprint_product(report,root,'song'))


if __name__ == '__main__': unittest.main()
