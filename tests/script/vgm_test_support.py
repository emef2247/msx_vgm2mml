"""Explicit test-only variants; never rewrite checked-in source fixtures."""
from pathlib import Path
import struct


def with_scc_clock(source, directory):
    """Create an explicit 1789773 Hz K051649 variant at the specified 0x9C field."""
    data = bytearray(Path(source).read_bytes())
    if len(data) < 0xA0 or struct.unpack_from('<I', data, 8)[0] < 0x161:
        raise ValueError('Fixture does not have a K051649 clock field')
    struct.pack_into('<I', data, 0x9C, 1789773)
    path = Path(directory) / Path(source).name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
