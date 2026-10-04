"""Batch source selection, unsupported clocks and retained failure evidence."""
import contextlib
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_opm_mdx_roundtrip as batch
from test_opm_reader import vgm


class OpmMdxBatchTests(unittest.TestCase):
    def test_expected_replays_are_not_reused_as_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('from_mdx/a/a.vgm', 'from_fm/b/b.VGZ',
                         'mdx_roundtrip/a.vgm', 'from_mdx/a/reference/expected.vgm'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual([p.relative_to(root).as_posix() for p in batch.source_files(root)],
                             ['from_fm/b/b.VGZ', 'from_mdx/a/a.vgm'])

    def test_gzip_header_preflight_uses_native_version_aware_clock_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'compressed.vgm'
            path.write_bytes(gzip.compress(vgm(b'\x54\x08\x08', 3579580)))
            self.assertEqual(batch.source_facts(path),
                             dict(clock_hz=3579580, chip_type='YM2151', dual_chip=False))
            path.write_bytes(vgm(b'\x54\x08\x08', 0xc0000000 | 4000000))
            self.assertEqual(batch.source_facts(path),
                             dict(clock_hz=4000000, chip_type='YM2164', dual_chip=True))

    def test_unsupported_sources_have_reports_without_building_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.vgm'
            source.write_bytes(vgm(b'\x54\x08\x08', 3579580))
            generator = root / 'generator'
            generator.touch()
            out = root / 'out'
            argv = ['verify', str(source), '--generator', str(generator), '--outdir', str(out)]
            with patch.object(sys, 'argv', argv), patch.object(batch, 'generate',
                    return_value=SimpleNamespace(events=[])), patch.object(batch, 'convert') as convert, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(batch.main(), 1)
                convert.assert_not_called()
            row = json.loads((out / 'results.json').read_text())[0]
            self.assertEqual(row['status'], 'unsupported_target')
            self.assertEqual(row['clock_hz'], 3579580)
            self.assertTrue((out / 'source/conversion.log').is_file())
            self.assertTrue((out / 'results.csv').is_file())

    def test_timeout_retains_both_compiler_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure = subprocess.TimeoutExpired(['generator'], 180,
                                                  output=b'compiled MDX\n', stderr=b'replay stalled\n')
            with patch.object(batch.subprocess, 'run', side_effect=failure):
                with self.assertRaises(subprocess.TimeoutExpired):
                    batch.generate(root / 'generator', root / 'input.mml', root, 'returned')
            log = (root / 'returned.compile.log').read_text()
            self.assertIn('compiled MDX', log)
            self.assertIn('replay stalled', log)
            self.assertIn('180 seconds', log)


if __name__ == '__main__':
    unittest.main()
