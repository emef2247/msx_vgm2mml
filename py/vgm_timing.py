"""Integer source wait clock, shared across all source chips."""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class CommandTime:
    address: int
    command: int
    vgmticks: int
    wait_samples: int


def command_times(raw):
    """Decode command boundaries; never interpret payload bytes as waits.

    One vgmtick is one 44100 Hz sample. All short waits count, including
    0x77/0x7a. No chip-specific origin or floating-point accumulation is used.
    Unknown/truncated commands are rejected rather than inventing timestamps.
    """
    if len(raw) < 0x40 or raw[:4] != b'Vgm ':
        raise ValueError('Invalid or truncated VGM header')
    version = struct.unpack_from('<I', raw, 8)[0]
    offset = struct.unpack_from('<I', raw, 0x34)[0] if version >= 0x150 else 0
    pos = 0x34 + offset if offset else 0x40
    eof = struct.unpack_from('<I', raw, 4)[0]
    end = min(len(raw), eof + 4) if eof else len(raw)
    if not 0x40 <= pos < end:
        raise ValueError('VGM data offset is outside the file')
    samples = 0
    waits = {0x62: 735, 0x63: 882}
    while pos < end:
        cmd = raw[pos]
        size, wait = 1, 0
        if cmd == 0x61:
            size = 3
            if pos + size <= end:
                wait = struct.unpack_from('<H', raw, pos + 1)[0]
        elif cmd in waits:
            wait = waits[cmd]
        elif 0x70 <= cmd <= 0x7f:
            wait = (cmd & 15) + 1
        elif 0x80 <= cmd <= 0x8f:
            wait = cmd & 15
        elif cmd == 0x64:
            size = 4
            if pos + size <= end:
                target = raw[pos + 1]
                if target not in waits:
                    raise ValueError(f'Invalid wait override at {pos:#x}')
                waits[target] = struct.unpack_from('<H', raw, pos + 2)[0]
        elif cmd == 0x67:
            size = 7
            if pos + size > end or raw[pos + 1] != 0x66:
                raise ValueError(f'Invalid data block at {pos:#x}')
            size += struct.unpack_from('<I', raw, pos + 3)[0] & 0x7fffffff
        elif cmd == 0x68:
            size = 12
        elif cmd in (0x4f, 0x50) or 0x30 <= cmd <= 0x3f:
            size = 2
        elif 0x51 <= cmd <= 0x5f or 0xa0 <= cmd <= 0xbf:
            size = 3
        elif 0xc0 <= cmd <= 0xdf:
            size = 4
        elif cmd in (0xe0, 0xe1):
            size = 5
        elif 0x90 <= cmd <= 0x95:
            size = {0x90: 5, 0x91: 5, 0x92: 6, 0x93: 11,
                    0x94: 2, 0x95: 5}[cmd]
        elif cmd != 0x66:
            raise ValueError(f'Unsupported VGM command {cmd:#x} at {pos:#x}')
        if pos + size > end:
            raise ValueError(f'Truncated VGM command at {pos:#x}')
        yield CommandTime(pos, cmd, samples, wait)
        if cmd == 0x66:
            return
        samples += wait
        pos += size
    raise ValueError('VGM stream has no end command')
