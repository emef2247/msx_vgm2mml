"""Read optional GD3 metadata without changing the VGM event pipeline."""
from pathlib import Path
import struct
import warnings


def read_gd3(path):
    data = Path(path).read_bytes()
    if len(data) < 0x18 or data[:4] != b'Vgm ':
        return None
    relative = struct.unpack_from('<I', data, 0x14)[0]
    if not relative:
        return None
    start = 0x14 + relative
    try:
        if data[start:start+4] != b'Gd3 ' or start+12 > len(data):
            raise ValueError('invalid GD3 header')
        version, size = struct.unpack_from('<II', data, start+4)
        if version != 0x100 or size % 2 or start+12+size > len(data):
            raise ValueError('invalid GD3 version or length')
        fields = data[start+12:start+12+size].decode('utf-16-le').split('\0')
        if len(fields) < 12:
            raise ValueError('incomplete GD3 fields')
        return fields[:11]
    except (ValueError, UnicodeError) as error:
        warnings.warn(f'Ignoring malformed GD3: {error}')
        return None


def title_from_gd3(path, fallback, language='ja'):
    fields = read_gd3(path)
    if not fields:
        return fallback
    def choose(index):
        first, second = (index+1, index) if language == 'ja' else (index, index+1)
        return fields[first].strip() or fields[second].strip()
    track, game, author = (choose(i) for i in (0, 2, 6))
    # System always uses English; GD3 has only one release-date field.
    # Normalize full-width ASCII without changing unrelated metadata characters.
    def ascii_width(value):
        return ''.join(chr(ord(c)-0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E
                       else ' ' if c == '\u3000' else c for c in value).strip()
    system = ascii_width(fields[4])
    date = ascii_width(fields[8])
    prefix = (f'[{system}]' if system else '') + game + (f'({date})' if date else '')
    title = ' '.join(x for x in (prefix, track, author) if x) or fallback
    # GD3 is untrusted text, not MML syntax. Keep generated headers single-line.
    title = ' '.join(title.split()).translate(str.maketrans({'"': "'", ';':'；', '{':'（', '}':'）'}))
    title = ''.join(c for c in title if ord(c) >= 32 and ord(c) != 127)
    # MGSC 1.11 has a physical-line limit; reserve space for #title syntax.
    safe, size = [], 0
    for char in title:
        length = len(char.encode('cp932', errors='replace'))
        if size + length > 240:
            warnings.warn('GD3 title shortened to 240 Shift-JIS bytes for MGSC')
            break
        safe.append(char); size += length
    return ''.join(safe)
