import gzip
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from gd3 import title_from_gd3
from vgm_reader import parse_vgm
from vgm_io import read_vgm_header


class VgmInputTests(unittest.TestCase):
    def test_short_extended_header_does_not_read_scc_clock_from_commands(self):
        raw = bytearray(0x100)
        raw[:4] = b'Vgm '
        struct.pack_into('<I', raw, 8, 0x151)
        struct.pack_into('<I', raw, 0x34, 0x80-0x34)
        struct.pack_into('<I', raw, 0x74, 1789772)
        raw[0x79] = 1
        raw[0x9c:0xa0] = b'ABCD'
        facts = read_vgm_header(raw)
        self.assertEqual(facts['ay_clock_raw'], 1789772)
        self.assertEqual(facts['ay_flags'], 1)
        self.assertEqual(facts['scc_clock_raw'], 0)
        struct.pack_into('<I', raw, 8, 0x171)
        self.assertEqual(read_vgm_header(raw)['scc_clock_raw'], 0)

    def fixture(self, version=0x150):
        data = bytearray(0x40)
        data[:4] = b'Vgm '
        struct.pack_into('<I', data, 8, version)
        struct.pack_into('<I', data, 0x10, 3579545)
        if version < 0x150:
            # Older headers do not define the data-offset field.
            struct.pack_into('<I', data, 0x34, 0xffffffff)
        data += bytes([0x51, 0x10, 0x80, 0x51, 0x20, 0x15, 0x62,
                       0x51, 0x20, 0x05, 0x62, 0x66])
        start = len(data)
        struct.pack_into('<I', data, 0x14, start - 0x14)
        fields = ['Track', '曲', 'Game', 'ゲーム', 'SMS', '', 'Author', '作者', '1987', '', '']
        payload = ('\0'.join(fields) + '\0').encode('utf-16-le')
        data += b'Gd3 ' + struct.pack('<II', 0x100, len(payload)) + payload
        struct.pack_into('<I', data, 4, len(data) - 4)
        return data

    def test_compressed_vgm_and_vgz_match_plain_traces_and_gd3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'plain.vgm'
            data = self.fixture()
            source.write_bytes(data)
            expected = [Path(p).read_bytes() for p in parse_vgm(str(source), str(root / 'plain'))]
            self.assertGreater(len(expected[-1].splitlines()), 1)
            for suffix in ('.vgm', '.vgz'):
                packed = root / ('packed' + suffix)
                packed.write_bytes(gzip.compress(data))
                actual = [Path(p).read_bytes() for p in parse_vgm(str(packed), str(root / suffix[1:]))]
                self.assertEqual(actual, expected)
                self.assertEqual(title_from_gd3(packed, 'fallback'), '[SMS]ゲーム(1987) 曲 作者')

    def test_old_header_ignores_undefined_data_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'old.vgm'
            path.write_bytes(self.fixture(0x110))
            regs = Path(parse_vgm(str(path), tmp)[-1]).read_text()
            self.assertGreater(len(regs.splitlines()), 1)

    def test_invalid_input_fails_instead_of_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.vgm'
            path.write_bytes(bytes(0x40))
            with self.assertRaisesRegex(ValueError, 'header'):
                parse_vgm(str(path), tmp)
            data = self.fixture()
            struct.pack_into('<I', data, 0x34, 0xffff)
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'offset'):
                parse_vgm(str(path), tmp)
