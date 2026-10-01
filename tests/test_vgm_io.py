import gzip
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from gd3 import title_from_gd3
from vgm_reader import parse_vgm


class VgmInputTests(unittest.TestCase):
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
