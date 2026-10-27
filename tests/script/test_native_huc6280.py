"""HuC source evidence survives a failed MSX target projection."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'py'),str(Path(__file__).parent)]
from test_huc6280 import make_vgm,wave,wait,write
from native_source_music import build_native_performance
from native_registers import encode_control
from native_vgm import write_native_vgm
from vgm_io import read_vgm_bytes
from vgm_timing import command_times
import vgm2mml


class NativeHuCTests(unittest.TestCase):
    def build(self,raw,folder):
        source=folder/'source.vgm';source.write_bytes(raw)
        return build_native_performance(source,folder/'out','source')

    def test_every_native_command_is_retained_once_with_dac_context(self):
        raw=make_vgm(write(1,255)+wave()+wait(735)+write(4,223)+write(6,31)+wait(735)+
                     write(6,3)+wait(735)+write(4,159)+wait(735))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);performance=self.build(raw,root)
            controls=performance.controls
            expected=[raw[e.address:e.address+3] for e in command_times(raw) if e.command==0xb9]
            self.assertEqual([encode_control(c,performance.devices[0]) for c in controls],expected)
            self.assertEqual(sum(c.kind=='huc_sample_data' for c in controls),2)
            self.assertEqual(performance.pcm_packets,())
            self.assertTrue(any(u.role=='pcm' for u in performance.units))
            self.assertTrue(any(u.role=='melody' for u in performance.units))
            target=root/'native.vgm';write_native_vgm(performance,target)
            out=target.read_bytes()
            self.assertEqual([out[e.address:e.address+3] for e in command_times(out) if e.command==0xb9],expected)
            self.assertEqual(list(command_times(out))[-1].vgmticks,list(command_times(raw))[-1].vgmticks)
            self.assertEqual(performance.source_sha256,hashlib.sha256(raw).hexdigest())

    def test_zero_time_native_retrigger_splits_units(self):
        raw=make_vgm(write(1,255)+wave()+wait(735)+write(4,0)+write(4,159)+wait(735))
        with tempfile.TemporaryDirectory() as temporary:
            performance=self.build(raw,Path(temporary))
            self.assertEqual([(u.start_sample,u.end_sample) for u in performance.units],[(0,735),(735,1470)])

    def test_projection_failure_still_publishes_original_native_vgm_and_score(self):
        raw=make_vgm(write(1,255)+wave(0)+write(0,5)+write(5,255)+write(4,223)+write(6,17)+wait(735))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'noise.vgm';source.write_bytes(raw);out=root/'out'
            args=['vgm2mml.py',str(source),'--outdir',str(out),'--dump-passes']
            with patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):vgm2mml.main()
            report=json.loads((out/'noise.conversion.json').read_text())
            self.assertEqual(report['blueprint']['status'],'success')
            self.assertEqual(report['direct_vgm']['status'],'success')
            output=read_vgm_bytes(out/'tracks/noise.vgm')
            self.assertTrue(any(e.command==0xb9 for e in command_times(output)))
            self.assertTrue((out/'noise.native_music.json').is_file())
            self.assertEqual(source.read_bytes(),raw)

    def test_successful_target_projection_still_uses_original_native_vgm(self):
        raw=make_vgm(write(1,255)+wave()+wait(735))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'song.vgm';source.write_bytes(raw);out=root/'out'
            args=['vgm2mml.py',str(source),'--outdir',str(out),'--dump-passes']
            with patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):vgm2mml.main()
            report=json.loads((out/'song.conversion.json').read_text())
            self.assertEqual(report['status'],'success')
            output=read_vgm_bytes(out/'tracks/song.vgm')
            def huc_commands(data):return [data[e.address:e.address+3] for e in command_times(data) if e.command==0xb9]
            self.assertEqual(huc_commands(output),huc_commands(raw))
            self.assertEqual(list(command_times(output))[-1].vgmticks,735)
            self.assertTrue((out/'song.mml').is_file())


if __name__=='__main__':unittest.main()
