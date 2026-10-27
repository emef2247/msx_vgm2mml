"""Read VGM bytes independently of the filename extension."""
import gzip
from pathlib import Path


def read_vgm_bytes(path):
    data = Path(path).read_bytes()
    if data.startswith(b'\x1f\x8b'):
        data = gzip.decompress(data)
    return data


def read_vgm_header(raw):
    """Common header facts, bounded by version and the start of command data."""
    if len(raw) < 0x40 or raw[:4] != b'Vgm ':
        raise ValueError('Invalid or truncated VGM header')
    version = int.from_bytes(raw[8:12], 'little')
    offset = int.from_bytes(raw[0x34:0x38], 'little') if version >= 0x150 else 0
    start = 0x34 + offset if offset else 0x40
    if not 0x40 <= start < len(raw):
        raise ValueError('VGM data offset is outside the file')
    def field(off, size, since):
        if version < since or off + size > start:
            return 0
        return int.from_bytes(raw[off:off + size], 'little')
    return dict(version=version, data_start=start,
                segapcm_clock_raw=field(0x38, 4, 0x151),
                segapcm_interface_raw=field(0x3c, 4, 0x151),
                opna_clock_raw=field(0x48, 4, 0x151),
                opna_ssg_flags=field(0x7b, 1, 0x151),
                extra_header_offset=field(0xbc, 4, 0x170),
                ay_clock_raw=field(0x74, 4, 0x151),
                ay_type=field(0x78, 1, 0x151), ay_flags=field(0x79, 1, 0x151),
                msm6295_clock_raw=field(0x98, 4, 0x161),
                c140_clock_raw=field(0xa8, 4, 0x161),
                c140_type=field(0x96, 1, 0x161),
                msm6258_clock_raw=field(0x90, 4, 0x161),
                msm6258_flags=field(0x94, 1, 0x161),
                scc_clock_raw=field(0x9c, 4, 0x161))
