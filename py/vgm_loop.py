"""Observe a declared VGM loop boundary without replaying or resetting chips."""
import csv
import struct


def read_loop_metadata(raw):
    """Observe samples on the same global clock used by the reader.

    Unsupported commands stop inspection: a payload byte must never be
    mistaken for a command boundary. This does not change trace decoding.
    """
    version = struct.unpack_from('<I', raw, 8)[0]
    offset = struct.unpack_from('<I', raw, 0x34)[0] if version >= 0x150 else 0
    start = 0x34 + offset if offset else 0x40
    relative = struct.unpack_from('<I', raw, 0x1c)[0]
    address = 0x1c + relative if relative else None
    result = dict(loop_offset=relative, loop_address=address,
                  header_loop_samples=struct.unpack_from('<I', raw, 0x20)[0],
                  status='no_loop' if address is None else 'not_reached',
                  loop_start_samples=None, loop_start_seconds=None,
                  loop_start_trace_seconds=None, decoded_end_samples=None,
                  decoded_loop_samples=None)
    if address is None:
        return result
    eof = struct.unpack_from('<I', raw, 4)[0]
    end = min(len(raw), eof + 4) if eof else len(raw)
    if not start <= address < end:
        result['status'] = 'outside_data'
        return result
    pos, samples, trace_samples = start, 0, 0
    waits = {0x62: 735, 0x63: 882}
    while pos < end:
        if pos == address:
            result.update(status='valid', loop_start_samples=samples,
                          loop_start_seconds=samples / 44100,
                          loop_start_trace_seconds=trace_samples / 44100)
        cmd = raw[pos]
        size, wait = 1, 0
        if cmd == 0x66:
            result['decoded_end_samples'] = samples
            if result['status'] == 'valid':
                result['decoded_loop_samples'] = samples - result['loop_start_samples']
            return result
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
        elif cmd == 0x67:
            size = 7
            if pos + size <= end and raw[pos + 1] == 0x66:
                size += struct.unpack_from('<I', raw, pos + 3)[0] & 0x7fffffff
            else:
                result['status'] = 'invalid_data_block'
                return result
        elif cmd == 0x68:
            size = 12
        elif cmd == 0x64:
            size = 4
            if pos + size <= end and raw[pos + 1] in waits:
                waits[raw[pos + 1]] = struct.unpack_from('<H', raw, pos + 2)[0]
        elif cmd in (0x4f, 0x50) or 0x30 <= cmd <= 0x3f:
            size = 2
        elif 0x51 <= cmd <= 0x5f or 0xa0 <= cmd <= 0xbf:
            size = 3
        elif 0xc0 <= cmd <= 0xdf:
            size = 4
        elif cmd in (0xe0, 0xe1):
            size = 5
        elif cmd in (0x90, 0x91, 0x92, 0x93, 0x94, 0x95):
            size = {0x90: 5, 0x91: 5, 0x92: 6, 0x93: 11, 0x94: 2, 0x95: 5}[cmd]
        else:
            result['status'] = 'unsupported_command'
            return result
        if pos + size > end:
            result['status'] = 'truncated_command'
            return result
        if pos < address < pos + size:
            result['status'] = 'inside_command'
            return result
        samples += wait
        trace_samples += wait
        pos += size
    result['status'] = 'missing_end_command'
    return result


def dump_loop_metadata(path, metadata):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(metadata))
        writer.writeheader()
        writer.writerow(metadata)
