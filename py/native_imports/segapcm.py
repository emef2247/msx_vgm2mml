"""SegaPCM source evidence and write-observed control intervals.

These intervals describe programmed configuration, not emulated audible gates.
Internal address advancement and natural stopping are deliberately unknown.
"""
import csv
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class SourceEvent:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    loop_iteration: int
    original_vgmticks: int
    chip_instance: int


@dataclass(frozen=True)
class RegisterWrite:
    source: SourceEvent
    offset_raw: int
    memory_offset: int
    ram_offset: int
    value: int
    channel: int | None
    role: str


@dataclass(frozen=True)
class RomBlock:
    source: SourceEvent
    block_id: int
    rom_generation: int
    length_raw: int
    declared_rom_size: int | None
    start_address: int | None
    header_hex: str
    payload: bytes
    malformed_header: bool


@dataclass(frozen=True)
class ChannelState:
    registers: tuple[int | None, ...] = (None,) * 9
    rom_generation: int = 0
    declared_rom_size: int | None = None


@dataclass(frozen=True)
class StateEvent:
    source: SourceEvent
    channel: int
    event_kind: str
    state: ChannelState


@dataclass(frozen=True)
class Segment:
    segment_id: int
    chip_instance: int
    channel: int
    start_vgmticks: int
    end_vgmticks: int
    start_event_id: int
    start_source_event_id: int
    loop_iteration: int
    original_start_vgmticks: int
    end_event_id: int | None
    end_reason: str
    state: ChannelState


_REGISTERS = (2, 3, 4, 5, 6, 7, 0x84, 0x85, 0x86)
_ROLES = ('volume_left', 'volume_right', 'loop_low', 'loop_high',
          'end_page', 'delta', 'programmed_address_low',
          'programmed_address_high', 'control')


def _source(event_id, event, instance):
    return SourceEvent(event_id, event.source_event_id, event.address,
                       event.vgmticks, event.loop_iteration,
                       event.original_vgmticks, instance)


class SegaPcmTrace:
    """Collect in the reader's shared command traversal, without ROM allocation."""
    def __init__(self, header):
        self.clock_raw = header['segapcm_clock_raw']
        self.interface_raw = header['segapcm_interface_raw']
        self.clock_hz = self.clock_raw & 0x3fffffff
        self.dual_chip = bool(self.clock_raw & 0x40000000)
        self.extra_header_offset = header.get('extra_header_offset', 0)
        self.writes = []
        self.rom_blocks = []
        self.state_events = []
        self.states = {}
        self.rom_context = {}
        self.issues = []

    def issue(self, message):
        if message not in self.issues:
            self.issues.append(message)

    def write(self, event_id, event, offset_raw, value):
        instance = (offset_raw >> 15) & 1
        memory_offset = offset_raw & 0x7fff
        ram_offset = memory_offset & 0x7ff
        channel = (ram_offset & 0x7f) // 8 if ram_offset < 0x100 else None
        register = (ram_offset & 7) | (ram_offset & 0x80)
        index = _REGISTERS.index(register) if channel is not None and register in _REGISTERS else None
        role = _ROLES[index] if index is not None else 'unmodeled_ram'
        source = _source(event_id, event, instance)
        self.writes.append(RegisterWrite(source, offset_raw, memory_offset,
                                         ram_offset, value, channel, role))
        if index is None:
            self.issue('Unmodeled RAM writes retained in raw register CSV')
            return
        key = (instance, channel)
        generation, size = self.rom_context.get(instance, (0, None))
        previous = self.states.get(key, ChannelState(rom_generation=generation,
                                                     declared_rom_size=size))
        registers = list(previous.registers)
        registers[index] = value
        state = ChannelState(tuple(registers), generation, size)
        kind = role + '_write'
        if register == 0x86:
            old = previous.registers[8]
            kind = 'disable_request' if value & 1 else 'enable_request'
            if old is not None and (old & 1) != (value & 1):
                kind = 'observed_disable' if value & 1 else 'observed_enable'
        self.states[key] = state
        self.state_events.append(StateEvent(source, channel, kind, state))

    def rom_block(self, event_id, event, length_raw, body):
        instance = (length_raw >> 31) & 1
        malformed = len(body) < 8
        size = None if malformed else int.from_bytes(body[:4], 'little')
        start = None if malformed else int.from_bytes(body[4:8], 'little')
        payload = bytes(body if malformed else body[8:])
        generation = self.rom_context.get(instance, (0, None))[0] + 1
        self.rom_context[instance] = generation, size
        source = _source(event_id, event, instance)
        self.rom_blocks.append(RomBlock(source, len(self.rom_blocks), generation,
                                       length_raw, size, start, body[:8].hex(),
                                       payload, malformed))
        if malformed:
            self.issue('Malformed SegaPCM ROM block header retained as opaque bytes')
        elif start + len(payload) > size:
            self.issue('ROM block extends beyond its declared ROM size; bytes retained')
        for (chip, channel), previous in sorted(self.states.items()):
            if chip == instance:
                state = ChannelState(previous.registers, generation, size)
                self.states[(chip, channel)] = state
                self.state_events.append(StateEvent(source, channel, 'rom_update', state))

    def segments(self, end_vgmticks):
        result = []
        grouped = {}
        for event in self.state_events:
            grouped.setdefault((event.source.chip_instance, event.channel), []).append(event)
        for (instance, channel), events in sorted(grouped.items()):
            for index, event in enumerate(events):
                following = events[index + 1] if index + 1 < len(events) else None
                result.append(Segment(len(result), instance, channel,
                                      event.source.vgmticks,
                                      following.source.vgmticks if following else end_vgmticks,
                                      event.source.event_id,
                                      event.source.source_event_id,
                                      event.source.loop_iteration,
                                      event.source.original_vgmticks,
                                      following.source.event_id if following else None,
                                      'next_observation' if following else 'source_end', event.state))
        return tuple(result)

    def state_fields(self, state, instance):
        values = dict(zip(_ROLES, state.registers))
        for name in ('volume_left', 'volume_right'):
            values[name + '_effective'] = None if values[name] is None else values[name] & 0x7f
        control = state.registers[8]
        low, high = state.registers[6:8]
        values.update(rom_generation=state.rom_generation,
                      declared_rom_size=state.declared_rom_size,
                      enabled_configuration=None if control is None else not bool(control & 1),
                      loop_enabled_configuration=None if control is None else not bool(control & 2),
                      programmed_address=None if low is None or high is None else (high << 8) | low,
                      runtime_address=None, natural_end_vgmticks=None)
        loop_low, loop_high = state.registers[2:4]
        values['loop_address'] = None if loop_low is None or loop_high is None else (loop_high << 8) | loop_low
        end = state.registers[4]
        values['end_page_boundary'] = None if end is None else ((end + 1) & 0xff) << 8
        shift = self.interface_raw & 0xff
        mask = (self.interface_raw >> 16) & 0xff
        values['bank_shift'] = shift
        values['bank_mask_declared'] = mask
        values['bank_mask_default_assumed'] = mask == 0
        values['bank_base'] = None
        if control is not None and state.declared_rom_size and shift < 32:
            rom_mask = (1 << (state.declared_rom_size - 1).bit_length()) - 1
            effective = (mask or 0x70) & (rom_mask >> shift)
            values['bank_base'] = (control & effective) << shift
        rate = None
        if (self.clock_hz and not self.clock_raw & 0x80000000
                and state.registers[5] is not None
                and not (instance and (self.extra_header_offset or not self.dual_chip))):
            rate = Fraction(self.clock_hz * state.registers[5], 32768)
        values['nominal_byte_rate_numerator'] = None if rate is None else rate.numerator
        values['nominal_byte_rate_denominator'] = None if rate is None else rate.denominator
        return values

    def dump(self, output_dir, stem, end_vgmticks):
        root = Path(output_dir)
        instances = {w.source.chip_instance for w in self.writes} | {b.source.chip_instance for b in self.rom_blocks}
        if instances and not self.clock_hz:
            self.issue('SegaPCM commands present without a declared clock; rate is unknown')
        if self.clock_raw & 0x80000000:
            self.issue('Unmodeled SegaPCM clock flag; nominal rate is unknown')
        if 1 in instances and not self.dual_chip:
            self.issue('Second SegaPCM instance used without a dual-chip declaration')
        if 1 in instances and self.extra_header_offset:
            self.issue('Second-instance extra-header clock is not interpreted; rate is unknown')
        if self.interface_raw & 0xff >= 32:
            self.issue('Unsupported interface bank shift; bank base is unknown')
        segments = self.segments(end_vgmticks)
        paths = dict(csv_path=str(root / f'{stem}_trace.segapcm_regs.csv'),
                     rom_blocks_csv_path=str(root / f'{stem}.segapcm.rom_blocks.csv'),
                     state_csv_path=str(root / f'{stem}_trace.segapcm.csv'),
                     segments_csv_path=str(root / f'{stem}.segapcm.segments.csv'),
                     analysis_json_path=str(root / f'{stem}.segapcm.analysis.json'))
        raw_rows = [dict(**asdict(w.source), **{k: v for k, v in asdict(w).items() if k != 'source'}) for w in self.writes]
        rom_rows, payload_paths = [], []
        for block in self.rom_blocks:
            path = root / f'{stem}.segapcm.rom_blocks' / f'block{block.block_id:04d}.bin'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(block.payload)
            payload_paths.append(str(path))
            rom_rows.append(dict(**asdict(block.source), block_id=block.block_id,
                                 rom_generation=block.rom_generation, length_raw=block.length_raw,
                                 declared_rom_size=block.declared_rom_size, start_address=block.start_address,
                                 header_hex=block.header_hex, malformed_header=block.malformed_header,
                                 payload_size=len(block.payload), payload_path=str(path)))
        state_rows = [dict(**asdict(e.source), channel=e.channel, event_kind=e.event_kind,
                           **self.state_fields(e.state, e.source.chip_instance)) for e in self.state_events]
        segment_rows = [dict(**{k: v for k, v in asdict(s).items() if k != 'state'},
                             **self.state_fields(s.state, s.chip_instance)) for s in segments]
        fallback = dict(**asdict(SourceEvent(0, 0, 0, 0, 0, 0, 0)), channel=0,
                        event_kind='', **self.state_fields(ChannelState(), 0))
        _csv(paths['csv_path'], raw_rows, (*SourceEvent.__dataclass_fields__, 'offset_raw', 'memory_offset', 'ram_offset', 'value', 'channel', 'role'))
        _csv(paths['rom_blocks_csv_path'], rom_rows, (*SourceEvent.__dataclass_fields__, 'block_id', 'rom_generation', 'length_raw', 'declared_rom_size', 'start_address', 'header_hex', 'malformed_header', 'payload_size', 'payload_path'))
        _csv(paths['state_csv_path'], state_rows, tuple(fallback))
        _csv(paths['segments_csv_path'], segment_rows,
             (*[k for k in Segment.__dataclass_fields__ if k != 'state'], *self.state_fields(ChannelState(), 0)))
        summary = dict(source_only=True, actual_usage=bool(instances),
                       clock_raw=self.clock_raw, interface_raw=self.interface_raw,
                       clock_hz=self.clock_hz, dual_chip=self.dual_chip,
                       write_count=len(self.writes), rom_block_count=len(self.rom_blocks),
                       state_event_count=len(self.state_events), segment_count=len(segments),
                       source_end_vgmticks=end_vgmticks, issues=self.issues,
                       payload_paths=payload_paths, **paths,
                       limitations=['Write-observed control intervals are not audible gates',
                                    'Runtime address advancement and natural stopping are not emulated',
                                    'EOF closes observation intervals without synthesizing disable writes'],
                       current_files=[*paths.values(), *payload_paths])
        Path(paths['analysis_json_path']).write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        return summary


def _csv(path, rows, fields):
    with open(path, 'w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(fields))
        writer.writeheader()
        writer.writerows(rows)
