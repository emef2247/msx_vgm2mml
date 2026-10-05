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
                ay_clock_raw=field(0x74, 4, 0x151),
                ay_type=field(0x78, 1, 0x151), ay_flags=field(0x79, 1, 0x151),
                scc_clock_raw=field(0x9c, 4, 0x161))
