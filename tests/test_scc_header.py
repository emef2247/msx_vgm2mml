"""SCC detection follows the VGM specification, not an old-output snapshot."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_reader import parse_vgm


class SccHeaderTests(unittest.TestCase):
    def test_unmodified_public_scc_fixture_generates_mml(self):
        source = ROOT / 'tests/fixtures/public/scc/scale_chromatic/scale_chromatic.vgm'
        data = source.read_bytes()
        self.assertEqual(data[0x9C:0xA0], bytes.fromhex('4d 4f 1b 00'))
        self.assertEqual(data[0xCC:0xD0], bytes(4))
        with tempfile.TemporaryDirectory() as folder:
            run = subprocess.run([sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                                  '--outdir', folder, '--dump-passes'],
                                 capture_output=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            text = (Path(folder) / 'scale_chromatic.mml').read_text()
            self.assertRegex(text, r'#alloc\s*\{[^}]*\b4=\d+')
            self.assertRegex(text, r'(?m)^4 .*\b[a-g][+#]?\d')
            segments = (Path(folder) / 'scale_chromatic.scc.segments.csv').read_text()
            self.assertGreater(len(segments.splitlines()), 1)

    def trace(self, directory, clock, es5503=0, data_start=0x100, version=0x170):
        header = bytearray(data_start)
        header[:4] = b'Vgm '
        struct.pack_into('<I', header, 8, version)
        struct.pack_into('<I', header, 0x34, data_start - 0x34)
        if data_start >= 0xA0:
            struct.pack_into('<I', header, 0x9C, clock)
        if data_start >= 0xD0:
            struct.pack_into('<I', header, 0xCC, es5503)
        # Write channel 0 volume through the SCC register command.
        commands = bytes([0xD2, 2, 0, 15, 0x66])
        # Long command stream makes the physical file larger than the header.
        commands += b'\0' * 256
        struct.pack_into('<I', header, 4, len(header) + len(commands) - 4)
        path = Path(directory) / 'header.vgm'
        path.write_bytes(header + commands)
        lines = Path(parse_vgm(str(path), directory)[3]).read_text().splitlines()
        return '\n'.join(line for line in lines if not line.startswith('#'))

    def test_scc_clock_is_at_9c_and_flags_do_not_replace_clock(self):
        for clock in (1789773, 0x80000000 | 1789773, 0x40000000 | 1789773):
            with self.subTest(clock=clock), tempfile.TemporaryDirectory() as folder:
                self.assertIn('vCtrl,', self.trace(folder, clock))

    def test_es5503_clock_does_not_enable_scc(self):
        for clock in (0, 0x80000000, 0x40000000):
            with self.subTest(clock=clock), tempfile.TemporaryDirectory() as folder:
                self.assertNotIn('vCtrl,', self.trace(folder, clock, es5503=7159090))

    def test_short_extended_header_is_enough_for_scc(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn('vCtrl,', self.trace(folder, 1789773, data_start=0xA0))

    def test_command_bytes_are_not_a_clock_field(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertNotIn('vCtrl,', self.trace(folder, 0, data_start=0x40))

    def test_older_version_does_not_declare_scc(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertNotIn('vCtrl,', self.trace(folder, 1789773, version=0x150))


if __name__ == '__main__':
    unittest.main()
