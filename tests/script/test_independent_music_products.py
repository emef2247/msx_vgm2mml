"""Source products survive MGS-specific policy and lowering failures."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'py'))
import vgm2mml
import musical_conversion


def authored(path,opll=False):
    raw=bytearray(256);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x171);struct.pack_into('<I',raw,0x34,256-0x34)
    if opll:
        struct.pack_into('<I',raw,0x10,3579545)
        commands=bytes.fromhex('51 30 10 51 10 ac 51 20 15 51 45 00 62 51 20 05 66')
    else:
        struct.pack_into('<I',raw,0x74,1789773)
        commands=bytes.fromhex('a0 00 ac a0 01 01 a0 07 3e a0 08 0f 62 a0 08 00 66')
    raw.extend(commands);struct.pack_into('<I',raw,4,len(raw)-4);struct.pack_into('<I',raw,0x18,735)
    path.write_bytes(raw)


class IndependentMusicProductsTests(unittest.TestCase):
    def run_cli(self,source,out):
        with patch.object(sys,'argv',['vgm2mml.py',str(source),'--outdir',str(out),'--dump-passes']),contextlib.redirect_stdout(io.StringIO()):
            vgm2mml.main()

    def test_source_survives_accepted_timing_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'score.vgm';authored(source)
            with patch.object(musical_conversion,'_build_accepted_plan',side_effect=ValueError('target timing rejected')):
                with self.assertRaisesRegex(ValueError,'target timing rejected'):self.run_cli(source,root/'out')
            report=json.loads((root/'out/score.conversion.json').read_text())
            self.assertEqual(report['direct_vgm']['status'],'success')
            self.assertEqual(report['blueprint']['status'],'success')
            self.assertTrue((root/'out/tracks/score.vgm').is_file())
            native=json.loads((root/'out/score.native_music.json').read_text())
            self.assertFalse(native['projection_applied']);self.assertTrue(native['units'])

    def test_mgs_policy_rejection_keeps_opll_source_controls_and_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'score.vgm';authored(source,opll=True)
            with self.assertRaisesRegex(ValueError,'OPLL register'):self.run_cli(source,root/'out')
            report=json.loads((root/'out/score.conversion.json').read_text())
            self.assertEqual(report['direct_vgm']['status'],'success')
            self.assertEqual(report['blueprint']['status'],'success')
            raw=(root/'out/tracks/score.vgm').read_bytes()
            self.assertIn(bytes.fromhex('51 45 00'),raw)
            self.assertTrue((root/'out/blueprint/score.mml').is_file())


if __name__=='__main__':unittest.main()
