"""Read VGM bytes independently of the filename extension."""
import gzip
from pathlib import Path


def read_vgm_bytes(path):
    data = Path(path).read_bytes()
    if data.startswith(b'\x1f\x8b'):
        data = gzip.decompress(data)
    return data
