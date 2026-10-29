"""Immutable C140 command evidence; source controls are not target note boundaries.

Runtime interpretation follows libvgm bad50c571db45b872304bdcd0603dd2214f0663e
(emu/cores/c140.c, BSD-3-Clause, R. Belmont). No external core is bundled.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import hashlib
import json
import struct

from .vgm_timing import command_times
from .vgm_io import read_vgm_header

REFERENCE_REVISION = 'bad50c571db45b872304bdcd0603dd2214f0663e'


@dataclass(frozen=True)
class Write:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    loop_iteration: int
    register: int
    value: int
    chip_instance: int = 0


@dataclass(frozen=True)
class RomBlock:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    loop_iteration: int
    total: int
    start: int
    payload: bytes
    chip_instance: int = 0


@dataclass(frozen=True)
class StateEvent:
    write: Write
    registers: tuple[int, ...]


@dataclass(frozen=True)
class Segment:
    channel: int
    start_vgmticks: int
    end_vgmticks: int
    start_event_id: int
    end_event_id: int | None
    registers: tuple[int, ...]
    latched_start: int
    latched_end: int
    latched_loop: int
    key_request: bool
    termination: str


@dataclass(frozen=True)
class Trace:
    source_end_vgmticks: int
    clock_raw: int
    clock_hz: int
    clock_reason: str
    chip_type: int
    writes: tuple[Write, ...]
    rom_blocks: tuple[RomBlock, ...]
    state_events: tuple[StateEvent, ...]
    segments: tuple[Segment, ...]
    issues: tuple[str, ...]
    loop_count: int = 1

    def dump(self, outdir, stem):
        root = Path(outdir)
        root.mkdir(parents=True, exist_ok=True)
        for name, rows in (('writes', [asdict(x) for x in self.writes]),
                           ('segments', [asdict(x) for x in self.segments]),
                           ('states', [dict(event_id=x.write.event_id,
                            vgmticks=x.write.vgmticks, registers=' '.join(f'{v:02x}' for v in x.registers))
                            for x in self.state_events])):
            with (root / f'{stem}.c140.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['event_id'])
                writer.writeheader()
                writer.writerows(rows)
        blocks = []
        for index, block in enumerate(self.rom_blocks):
            filename = f'{stem}.c140.rom.{index:04d}.bin'
            (root / filename).write_bytes(block.payload)
            values = asdict(block)
            values.pop('payload')
            blocks.append(dict(**values, payload_file=filename, payload_bytes=len(block.payload),
                               sha256=hashlib.sha256(block.payload).hexdigest()))
        (root / f'{stem}.c140.source.json').write_text(json.dumps(dict(
            clock_raw=self.clock_raw, clock_hz=self.clock_hz, clock_reason=self.clock_reason,
            chip_type=self.chip_type, tick_clock_hz=44100, source_end_vgmticks=self.source_end_vgmticks,
            loop_count=self.loop_count, reference_revision=REFERENCE_REVISION,
            segment_semantics='write-observed controls, not emulated audible gates',
            initialization=dict(origin='reference_reset_assumption', observed=False,
                register_values='all zero', voice_key_state='all key-off',
                cursor_fraction_and_interpolation='all zero',
                detail='libvgm device reset; not inferred from observed source writes'),
            issues=self.issues, rom_blocks=blocks), indent=2) + '\n', encoding='utf-8')


def analyze(raw, *, loop_count=1):
    commands = command_times(raw, loop_count=loop_count)
    header = read_vgm_header(raw)
    clock_raw = header['c140_clock_raw']
    chip_type = header['c140_type']
    clock = clock_raw & 0x3fffffff
    reason = 'header_clock'
    if clock == 21390:
        clock, reason = 12288000, 'legacy_21390_compatibility'
    elif 0 < clock < 1000000:
        clock, reason = clock * 576, 'legacy_sample_rate_times_576'
    issues = []
    if clock_raw & 0x40000000:
        issues.append('dual_c140_header_unsupported')
    if chip_type not in (0, 1):
        issues.append(f'unsupported_chip_type_{chip_type}')
    registers = [0] * 512
    latched = [(0, 0, 0)] * 24
    pending = {}
    writes, blocks, states, segments = [], [], [], []
    end = 0

    def close(channel, tick, event_id, termination):
        previous = pending.pop(channel, None)
        if previous is not None:
            start, start_id, snapshot, addresses, key = previous
            segments.append(Segment(channel, start, tick, start_id, event_id,
                                    snapshot, *addresses, key, termination))

    for event_id, command in enumerate(commands):
        end = command.vgmticks + command.wait_samples
        offset = command.address
        if command.command == 0x67 and raw[offset + 2] == 0x8d:
            size_raw = struct.unpack_from('<I', raw, offset + 3)[0]
            size = size_raw & 0x7fffffff
            if size < 8:
                raise ValueError('C140 ROM block is shorter than its total/start header')
            total, start = struct.unpack_from('<II', raw, offset + 7)
            payload = bytes(raw[offset + 15:offset + 7 + size])
            if not total or start > total or len(payload) > total - start:
                raise ValueError('C140 ROM block range exceeds its declared size')
            blocks.append(RomBlock(event_id, command.source_event_id, offset, command.vgmticks,
                                   command.loop_iteration, total, start, payload, size_raw >> 31))
            if size_raw >> 31:
                issues.append('second_c140_rom_unsupported')
        elif command.command == 0xd4:
            address = (raw[offset + 1] << 8) | raw[offset + 2]
            instance = address >> 15
            register = address & 0x7fff
            write = Write(event_id, command.source_event_id, offset, command.vgmticks,
                          command.loop_iteration, register, raw[offset + 3], instance)
            writes.append(write)
            if instance:
                issues.append('second_c140_write_unsupported')
                continue
            if register > 0x1ff:
                issues.append(f'out_of_range_register_{register:04x}')
                continue
            if register < 0x180:
                channel = register >> 4
                close(channel, command.vgmticks, event_id, 'control_write')
            registers[register] = write.value
            states.append(StateEvent(write, tuple(registers)))
            if register < 0x180:
                base = channel * 16
                snapshot = tuple(registers[base:base + 16])
                if register & 15 == 5 and write.value & 0x80:
                    latched[channel] = tuple((snapshot[i] << 8) | snapshot[i + 1] for i in (6, 8, 10))
                pending[channel] = (command.vgmticks, event_id, snapshot, latched[channel], bool(snapshot[5] & 0x80))
    for channel in sorted(pending):
        close(channel, end, None, 'source_end')
    if not clock:
        issues.append('missing_c140_clock')
    return Trace(end, clock_raw, clock, reason, chip_type, tuple(writes), tuple(blocks), tuple(states),
                 tuple(segments), tuple(dict.fromkeys(issues)), loop_count)
