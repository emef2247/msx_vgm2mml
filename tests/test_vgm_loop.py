import csv
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_loop import read_loop_metadata
from vgm_reader import parse_vgm


def vgm(commands, loop=None, loop_samples=0):
    header = bytearray(0x100)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 4, len(header) + len(commands) - 4)
    struct.pack_into('<I', header, 8, 0x161)
    struct.pack_into('<I', header, 0x34, 0xcc)
    struct.pack_into('<I', header, 0x1c, 0 if loop is None else 0x100 + loop - 0x1c)
    struct.pack_into('<I', header, 0x20, loop_samples)
    return bytes(header) + commands


class VgmLoopTests(unittest.TestCase):
    def test_no_loop(self):
        self.assertEqual(read_loop_metadata(vgm(b'\x66'))['status'], 'no_loop')

    def test_loop_at_data_start(self):
        result = read_loop_metadata(vgm(b'\x62\x66', 0, 735))
        self.assertEqual(result['loop_address'], 0x100)
        self.assertEqual(result['loop_start_samples'], 0)
        self.assertEqual(result['decoded_loop_samples'], 735)

    def test_loop_on_wait_and_shared_clock(self):
        result = read_loop_metadata(vgm(bytes([0x77, 0x7a, 0x62, 0x61, 100, 0, 0x66]), 3, 100))
        self.assertEqual(result['status'], 'valid')
        self.assertEqual(result['loop_start_samples'], 754)
        self.assertAlmostEqual(result['loop_start_trace_seconds'], 754 / 44100)
        self.assertEqual(result['decoded_loop_samples'], 100)

    def test_offset_inside_write_is_not_a_boundary(self):
        result = read_loop_metadata(vgm(bytes([0x50, 0x62, 0x66]), 1))
        self.assertEqual(result['status'], 'inside_command')

    def test_data_block_payload_is_skipped(self):
        commands = bytes([0x67, 0x66, 0]) + struct.pack('<I', 2) + bytes([0x62, 0x66]) + b'\x66'
        self.assertEqual(read_loop_metadata(vgm(commands, 7))['status'], 'inside_command')
        self.assertEqual(read_loop_metadata(vgm(commands, 9))['loop_start_samples'], 0)

    def test_invalid_and_unsupported_stream(self):
        self.assertEqual(read_loop_metadata(vgm(b'\x66', 20))['status'], 'outside_data')
        self.assertEqual(read_loop_metadata(vgm(b'\x01\x66', 1))['status'], 'unsupported_command')
        self.assertEqual(read_loop_metadata(vgm(b'\x61', 0))['status'], 'truncated_command')

    def test_loop_observation_preserves_trace_and_key_writes(self):
        commands = bytes([0x51, 0x20, 0x10, 0x62, 0x51, 0x20, 0x10, 0x62, 0x66])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'loop.vgm'
            path.write_bytes(vgm(commands, 3, 1470))
            paths = parse_vgm(str(path), folder)
            original = [Path(p).read_bytes() for p in paths]
            self.assertFalse((Path(folder) / 'loop.vgm.loop.csv').exists())
            metadata = {}
            paths = parse_vgm(str(path), folder, loop_metadata=metadata, dump_loop=True)
            self.assertEqual(original, [Path(p).read_bytes() for p in paths])
            with (Path(folder) / 'loop.vgm.loop.csv').open() as fh:
                row = next(csv.DictReader(fh))
            self.assertEqual(row['status'], 'valid')
            self.assertEqual(row['loop_start_samples'], '0')
            self.assertEqual(metadata['decoded_loop_samples'], 1470)


if __name__ == '__main__':
    unittest.main()
