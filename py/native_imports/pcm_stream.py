"""Inspectable finite MSM6258 DAC supplies, separate from raw chip writes.

Timing follows libvgm's 44.1 kHz, 32.32 DAC counter profile. Source commands
at a tick precede its DAC update. This models byte delivery, not consumption.
"""
from dataclasses import dataclass, replace
import struct

ONE = 1 << 32
SCHEDULING_MODEL = 'libvgm-44100hz-32.32-post-command'
REFERENCE_REVISION = '70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8'
_SUPPLY = struct.Struct('<QQQQBBBBBiQQ')


@dataclass(frozen=True)
class PcmStreamSupply:
    transfer_id: int
    source_event_id: int
    address: int
    vgmticks: int
    stream_id: int
    chip_instance: int
    register: int
    data: int
    bank_id: int
    block_id: int
    bank_offset: int
    byte_index: int


@dataclass(frozen=True)
class StreamSupplyLog:
    packed: bytes = b''

    def __len__(self):
        return len(self.packed) // _SUPPLY.size

    def __iter__(self):
        return (PcmStreamSupply(*row) for row in _SUPPLY.iter_unpack(self.packed))

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return PcmStreamSupply(*_SUPPLY.unpack_from(self.packed, index * _SUPPLY.size))


def pack_supply(row):
    return _SUPPLY.pack(*(getattr(row, field) for field in PcmStreamSupply.__dataclass_fields__))


@dataclass(frozen=True)
class PcmStreamControl:
    source_event_id: int
    address: int
    vgmticks: int
    command: int
    stream_id: int
    chip_instance: int | None
    register: int | None
    bank_id: int | None
    step_size: int | None
    step_base: int | None
    frequency_hz: int | None
    running: bool
    start_offset: int | None
    command_count: int | None


@dataclass(frozen=True)
class PcmStreamIssue:
    code: str
    source_event_id: int
    vgmticks: int
    detail: str


class StreamDecoder:
    def __init__(self, raw):
        self.raw = raw
        self.bank = bytearray()
        self.blocks = []
        self.compressed = False
        self.streams = {}
        self.controls, self.issues = [], []
        self.cursor = self.transfer_count = 0

    def issue(self, code, event_id, event, detail):
        self.issues.append(PcmStreamIssue(code, event_id, event.vgmticks, detail))

    def process(self, event_id, event):
        cmd, pos = event.command, event.address
        if cmd == 0x67:
            kind = self.raw[pos + 2]
            length = int.from_bytes(self.raw[pos + 3:pos + 7], 'little') & 0x7fffffff
            if kind == 4:
                self.blocks.append((len(self.bank), length))
                self.bank.extend(self.raw[pos + 7:pos + 7 + length])
            elif kind == 0x44:
                self.compressed = True
                self.blocks.append(None)
                self.issue('unsupported_pcm_data_bank', event_id, event,
                           'Compressed MSM6258 bank retained; decompression is not implemented')
            return
        if not 0x90 <= cmd <= 0x95:
            return
        sid = self.raw[pos + 1]
        if sid == 255:
            if cmd == 0x94:
                for stream in self.streams.values():
                    stream['running'] = False
                self.controls.append(PcmStreamControl(event_id, pos, event.vgmticks, cmd,
                                     sid, None, None, None, None, None, None, False, None, None))
            return
        stream = self.streams.get(sid)
        if cmd == 0x90:
            target, port, reg = self.raw[pos + 2:pos + 5]
            valid = target == 0x17 and port == 0 and reg == 1
            if stream is None:
                stream = dict(bank=None, step=None, base=None, frequency=None,
                              offset=None, count=None, phase=0, index=0, start_base=None)
            stream.update(instance=target >> 7, reg=reg, valid=valid, running=False)
            self.streams[sid] = stream
            if not valid:
                self.issue('unsupported_stream_control', event_id, event,
                           f'Stream {sid} target {target:#x}, port {port}, register {reg} is unsupported')
        elif stream is None:
            self.issue('stream_configuration_incomplete', event_id, event,
                       f'Stream {sid} has no setup command')
            return
        elif cmd == 0x91:
            bank, step, base = self.raw[pos + 2:pos + 5]
            if stream['running']:
                self.issue('unsupported_stream_control', event_id, event,
                           f'Stream {sid} data setup changes during active supply are not implemented')
                stream['running'] = False
            stream.update(bank=bank, step=step or 1, base=base)
            if bank != 4:
                self.issue('invalid_stream_reference', event_id, event,
                           f'Stream {sid} selects unsupported data bank {bank:#x}')
                stream['running'] = False
        elif cmd == 0x92:
            frequency = int.from_bytes(self.raw[pos + 2:pos + 6], 'little')
            stream['frequency'] = frequency
            if frequency > 44100:
                self.issue('unsupported_stream_control', event_id, event,
                           f'Stream {sid} frequency exceeds the one-write-per-tick scheduling profile')
                stream['running'] = False
        elif cmd == 0x94:
            stream['running'] = False
        elif cmd in (0x93, 0x95):
            stream['running'] = False
            if not stream['valid']:
                pass
            elif any(stream[key] is None for key in ('bank', 'step', 'base', 'frequency')):
                self.issue('stream_configuration_incomplete', event_id, event,
                           f'Stream {sid} start requires data and frequency configuration')
            elif stream['bank'] != 4 or self.compressed:
                self.issue('invalid_stream_reference', event_id, event,
                           f'Stream {sid} has no fully decoded MSM6258 data bank')
            elif stream['frequency'] > 44100:
                pass
            elif not stream['frequency']:
                self.issue('unsupported_stream_control', event_id, event,
                           f'Stream {sid} zero-frequency start pre-step behavior is not implemented')
            else:
                offset = count = None
                if cmd == 0x95:
                    block = int.from_bytes(self.raw[pos + 2:pos + 4], 'little')
                    flags = self.raw[pos + 4]
                    if flags:
                        self.issue('unsupported_stream_control', event_id, event,
                                   f'Stream {sid} reverse/loop/reserved flags {flags:#x} are not implemented')
                    elif block >= len(self.blocks) or self.blocks[block] is None:
                        self.issue('invalid_stream_reference', event_id, event,
                                   f'Stream {sid} block {block} is not present in bank 4')
                    else:
                        offset, length = self.blocks[block]
                        count = length // stream['step']
                else:
                    offset = int.from_bytes(self.raw[pos + 2:pos + 6], 'little')
                    mode = self.raw[pos + 6]
                    length = int.from_bytes(self.raw[pos + 7:pos + 11], 'little')
                    if offset == 0xffffffff:
                        offset = stream['offset']
                        if offset is None:
                            self.issue('stream_configuration_incomplete', event_id, event,
                                       f'Stream {sid} has no previous start offset')
                        else:
                            # libvgm retains its absolute DataStart, including
                            # the previous base, when offset is unspecified.
                            offset += stream['start_base'] - stream['base']
                    if mode not in (1, 3):
                        self.issue('unsupported_stream_control', event_id, event,
                                   f'Stream {sid} length mode {mode:#x} is not implemented')
                        offset = None
                    elif offset is not None:
                        count = length if mode == 1 else (len(self.bank) - offset) // stream['step']
                if offset is not None and count is not None:
                    start = offset + stream['base']
                    final = start + (count - 1) * stream['step']
                    if count <= 0 or not 0 <= start <= final < len(self.bank):
                        self.issue('invalid_stream_reference', event_id, event,
                                   f'Stream {sid} start/count exceeds the available bank bytes')
                    else:
                        increment = (stream['frequency'] * ONE + 22050) // 44100
                        stream.update(offset=offset, count=count, index=0, running=True,
                                      phase=ONE - increment, start_event=event_id, start_address=pos,
                                      start_base=stream['base'])
        self.controls.append(PcmStreamControl(event_id, pos, event.vgmticks, cmd, sid,
                            stream['instance'], stream['reg'], stream['bank'], stream['step'],
                            stream['base'], stream['frequency'], stream['running'],
                            stream['offset'], stream['count']))

    def advance(self, end):
        """Expand DAC phases [cursor, end); never emit a chip STOP/reset."""
        supplies = []
        for order, (sid, stream) in enumerate(self.streams.items()):
            frequency = stream['frequency']
            if not stream['running'] or not frequency or frequency > 44100:
                continue
            increment = (frequency * ONE + 22050) // 44100
            cursor = self.cursor
            while cursor < end and stream['running']:
                steps = max(1, (ONE - stream['phase'] + increment - 1) // increment)
                if steps > end - cursor:
                    stream['phase'] += (end - cursor) * increment
                    break
                stream['phase'] += steps * increment - ONE
                tick = cursor + steps - 1
                index = stream['index']
                bank_offset = stream['offset'] + stream['base'] + index * stream['step']
                if not 0 <= bank_offset < len(self.bank):
                    self.issues.append(PcmStreamIssue('invalid_stream_reference',
                        stream['start_event'], tick, f'Stream {sid} left its available bank range'))
                    stream['running'] = False
                    break
                block_id = next(i for i, block in enumerate(self.blocks)
                                if block is not None and block[0] <= bank_offset < block[0] + block[1])
                row = PcmStreamSupply(0, stream['start_event'], stream['start_address'], tick,
                                      sid, stream['instance'], stream['reg'], self.bank[bank_offset],
                                      stream['bank'], block_id, bank_offset, index)
                supplies.append((tick, order, row))
                stream['index'] += 1
                if stream['index'] == stream['count']:
                    stream['running'] = False
                cursor += steps
        supplies.sort(key=lambda item: item[:2])
        self.cursor = end
        result = []
        for _, _, row in supplies:
            result.append(replace(row, transfer_id=self.transfer_count))
            self.transfer_count += 1
        return result
