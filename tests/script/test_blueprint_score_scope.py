"""Blueprint spelling cannot retime production or drive loop selection."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'py'), str(Path(__file__).parent)]
from test_huc6280 import make_vgm, wave, wait, write


@unittest.skipUnless(shutil.which('mgsc'), 'Native MGSC required')
class BlueprintScopeTests(unittest.TestCase):
    def test_default_export_blueprint_timing_preserves_production_mml_reference_and_guide(self):
        raw = make_vgm(write(1,255)+wave()+wait(4000)+write(4,0)+wait(1000)+
            wave()+wait(4000)+write(4,0)+wait(1000))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'song.vgm';source.write_bytes(raw)
            low_level=['--fm-state-ms','24','--normalization-ms','8']
            for name,entry,flags in (('plain','batch_vgm_to_mgs.py',low_level),('score','export_mgs.py',[])):
                proc=subprocess.run([sys.executable,str(ROOT/'scripts'/entry),str(source),
                    '--outdir',str(root/name),'--score-guided-loops','--software-volume-curves','--skip-keyon-counts',*flags],
                    capture_output=True,timeout=120)
                self.assertEqual(proc.returncode,0,(proc.stdout+proc.stderr).decode(errors='replace'))
            for suffix in ('mml','mgs','vgm'):
                self.assertEqual((root/f'plain/tracks/song.{suffix}').read_bytes(),
                                 (root/f'score/tracks/song.{suffix}').read_bytes())
            self.assertNotEqual((root/'plain/blueprint/song.mml').read_bytes(),
                                (root/'score/blueprint/song.mml').read_bytes())
            for name in ('plain','score'):
                self.assertFalse((root/name/'_diagnostics/song/_score_normalized').exists())
            guides=[json.loads((root/name/'_diagnostics/song/song.score_guide.json').read_text())
                    for name in ('plain','score')]
            self.assertEqual(guides[0],guides[1])
            self.assertTrue((root/'score/_diagnostics/song/blueprint_score_timing/song.score_normalization.json').is_file())


if __name__=='__main__':unittest.main()
