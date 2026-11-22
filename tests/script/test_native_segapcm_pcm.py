"""Authored SegaPCM playback reconstruction check: a synthetic
VGM with one ROM block and one keyed channel must decode into a
single PCM asset at the programmed byte rate, stopping at the
end page."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_source_music import build_native_performance

CLOCK = 4194304  # 2**22: byte rate at delta 128 is exactly 16384


def synthetic_vgm():
    header = bytearray(256)
    header[0:4] = b'Vgm '
    struct.pack_into('<I', header, 0x08, 0x171)       # version 1.71
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)  # data offset
    struct.pack_into('<I', header, 0x38, CLOCK)       # SegaPCM clock
    struct.pack_into('<I', header, 0x3c, 0)           # interface
    payload = bytes(range(256))
    block_body = struct.pack('<II', 0x10000, 0) + payload
    block = b'\x67\x66\x80' + struct.pack('<I', len(block_body)) + block_body

    def write(offset, value):
        return bytes((0xc0, offset & 0xff, offset >> 8, value))

    stream = bytearray(block)
    stream += write(2, 0x7f)      # volume left
    stream += write(3, 0x7f)      # volume right
    stream += write(6, 0x00)      # end page register: stop at page 1
    stream += write(7, 0x80)      # delta 128
    stream += write(0x84, 0x00)   # start address low
    stream += write(0x85, 0x00)   # start address high
    stream += write(0x86, 0x02)   # key on, loop disabled
    stream += b'\x61\x44\xac'     # wait 44100 samples
    stream += b'\x66'
    struct.pack_into('<I', header, 0x04, 256 + len(stream) - 4)
    return bytes(header) + bytes(stream)


class SegaPcmDecodeTests(unittest.TestCase):
    def test_gate_decodes_to_asset_at_byte_rate(self):
        with tempfile.TemporaryDirectory() as td:
            perf = build_native_performance(synthetic_vgm(), td, 'sega')
        assets = [a for a in perf.pcm_assets if a.device_id == 'segapcm:0']
        self.assertEqual(len(assets), 1)
        asset = assets[0]
        self.assertEqual(asset.rate_hz, 16384.0)
        self.assertEqual(len(asset.samples), 256)
        self.assertEqual(asset.samples[0], (0 - 128) * 127)
        self.assertEqual(asset.samples[255], (255 - 128) * 127)
        # 256 bytes at 16384 B/s end near sample 689, not at the
        # 44100-sample source end: the end page stops the gate.
        self.assertTrue(600 < asset.end_sample < 800)


if __name__ == '__main__':
    unittest.main()
