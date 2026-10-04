"""OPM source capture must preserve order and share the existing VGM clock."""
import csv
import gzip
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_reader import parse_vgm


def vgm(commands, clock=4000000, version=0x171):
    raw = bytearray(0xa0)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, version)
    struct.pack_into('<I', raw, 0x30 if version >= 0x110 else 0x10, clock)
    if version >= 0x150:
        struct.pack_into('<I', raw, 0x34, len(raw) - 0x34)
    else:
        raw = raw[:0x40]
    raw += commands + b'\x66'
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return raw


def read_rows(path):
    with open(path, encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


class OpmReaderTests(unittest.TestCase):
    def parse(self, root, raw, packed=False):
        source = root / 'source.vgm'
        source.write_bytes(gzip.compress(raw) if packed else raw)
        metadata = {}
        paths = parse_vgm(str(source), str(root / 'traces'), opm_metadata=metadata)
        self.assertEqual(len(paths), 8)
        return paths, metadata

    def test_shared_time_same_sample_order_and_all_raw_writes(self):
        # Keep unchanged key writes, a zero-time off/on pulse, and both depths.
        commands = (b'\x62\xa0\x08\x0a\x77\x54\x08\x78'
                    b'\x54\x08\x78\x54\x08\x00\x54\x08\x78'
                    b'\x54\x19\x12\x54\x19\x93\x7a\x54\x30\xff'
                    b'\x51\x20\x10\x63')
        with tempfile.TemporaryDirectory() as tmp:
            paths, metadata = self.parse(Path(tmp), vgm(commands))
            rows = read_rows(metadata['csv_path'])
            self.assertEqual([int(r['event_id']) for r in rows], [3, 4, 5, 6, 7, 8, 10])
            self.assertEqual([int(r['vgmticks']) for r in rows], [743] * 6 + [754])
            self.assertEqual([int(r['register']) for r in rows], [8] * 4 + [0x19, 0x19, 0x30])
            self.assertEqual([int(r['data']) for r in rows], [0x78, 0x78, 0, 0x78, 0x12, 0x93, 0xff])
            self.assertEqual([int(r['address']) for r in rows], [165, 168, 171, 174, 177, 180, 184])
            self.assertEqual(float(rows[0]['time']), 743 / 44100)
            self.assertEqual(float(read_rows(paths[5])[0]['time']), 754 / 44100)
            self.assertEqual(float(read_rows(paths[2])[0]['time']), 735 / 44100)
            self.assertEqual(metadata['source_end_vgmticks'], 754 + 882)
            self.assertEqual(metadata['write_count'], 7)

    def test_dual_instance_and_variant_flags(self):
        commands = b'\x54\x08\x78\xa4\x08\x08\x70\xa4\x28\x4e'
        with tempfile.TemporaryDirectory() as tmp:
            _, metadata = self.parse(Path(tmp), vgm(commands, 0xc0000000 | 4000000))
            rows = read_rows(metadata['csv_path'])
            self.assertEqual([int(r['chip_instance']) for r in rows], [0, 1, 1])
            self.assertEqual([int(r['command']) for r in rows], [0x54, 0xa4, 0xa4])
            self.assertEqual([int(r['vgmticks']) for r in rows], [0, 0, 1])
            self.assertTrue(metadata['dual_chip'])
            self.assertEqual(metadata['chip_type'], 'YM2164')
            self.assertEqual(metadata['clock_hz'], 4000000)
            self.assertEqual(int(rows[0]['clock_raw']), 0xc0000000 | 4000000)

    def test_zero_clock_and_undeclared_second_instance_are_ignored(self):
        commands = b'\x54\x08\x78\xa4\x08\x78\x62'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, metadata = self.parse(root, vgm(commands, 0))
            self.assertIsNone(metadata['csv_path'])
            self.assertEqual(metadata['write_count'], 0)
            self.assertFalse((root / 'traces/source_trace.opm_regs.csv').exists())
            _, metadata = self.parse(root, vgm(commands))
            self.assertEqual(metadata['write_count'], 1)
            self.assertEqual(read_rows(metadata['csv_path'])[0]['chip_instance'], '0')

    def test_versioned_clock_field_and_flags(self):
        for version in (0x101, 0x110, 0x150):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                raw = vgm(b'\x54\x28\x4e\xa4\x28\x4e', 0xc0000000 | 3579545, version)
                if version == 0x101:
                    struct.pack_into('<I', raw, 0x30, 1234567)
                _, metadata = self.parse(Path(tmp), raw)
                self.assertEqual(metadata['clock_hz'], 3579545)
                self.assertFalse(metadata['dual_chip'])
                self.assertEqual(metadata['chip_type'], 'YM2151')
                self.assertEqual(metadata['write_count'], 1)

    def test_compressed_input_and_existing_chip_trace_parity(self):
        # OPM dispatch must not alter any of the eight existing chip CSVs.
        legacy = b'\x62\xa0\x08\x0a\x51\x20\x10\xd2\x02\x00\x0f\x77\x51\x20\x00'
        extended = legacy[:1] + b'\x54\x08\x78' + legacy[1:] + b'\x54\x08\x00'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = None
            opm_rows = None
            for name, commands, packed in (('legacy', legacy, False), ('opm', extended, False),
                                           ('gzip', extended, True)):
                folder = root / name
                folder.mkdir()
                raw = vgm(commands)
                struct.pack_into('<I', raw, 0x9c, 3579545)
                paths, metadata = self.parse(folder, raw, packed)
                actual = [Path(p).read_bytes() for p in paths]
                if expected is None:
                    expected = actual
                else:
                    self.assertEqual(actual, expected)
                    rows = read_rows(metadata['csv_path'])
                    if opm_rows is None:
                        opm_rows = rows
                    else:
                        self.assertEqual(rows, opm_rows)

    def test_main_dump_retains_trace_and_default_remains_mml_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'mixed.vgm'
            source.write_bytes(vgm(b'\x54\x08\x78\x51\x10\x80\x51\x20\x15\x62\x51\x20\x05'))
            for dump in (False, True):
                target = root / ('dump' if dump else 'default')
                result = subprocess.run([sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                                         '--outdir', str(target)] + (['--dump-passes'] if dump else []),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if dump:
                    self.assertEqual(len(read_rows(target / 'mixed_trace.opm_regs.csv')), 1)
                else:
                    self.assertEqual([p.name for p in target.iterdir()], ['mixed.mml'])


if __name__ == '__main__':
    unittest.main()
