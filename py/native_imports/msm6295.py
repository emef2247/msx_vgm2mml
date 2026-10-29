"""Immutable MSM6295 command evidence, independent of native voice inference."""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import hashlib
import json
import struct

from .vgm_timing import command_times
from .vgm_io import read_vgm_header

REFERENCE_REVISION = 'bad50c571db45b872304bdcd0603dd2214f0663e'
REFERENCE_CORE_SHA256 = '00778ea2bb630abf549ea25671e9d19df50d4ce4889be9e1fcfa6739b5ae6194'
REFERENCE_DECODER_SHA256 = '95ad62ea67fb3f239873abf79200ce11d3d548c40022ec02da0dd4a3abaf5af1'


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
    pending_sample: int | None
    command_kind: str
    voice_mask: int
    attenuation: int | None


@dataclass(frozen=True)
class Segment:
    start_vgmticks: int
    end_vgmticks: int
    start_event_id: int
    end_event_id: int | None
    register: int
    value: int
    pending_sample: int | None
    command_kind: str
    voice_mask: int
    attenuation: int | None


@dataclass(frozen=True)
class Trace:
    source_end_vgmticks: int
    clock_raw: int
    clock_hz: int
    pin7_high: bool
    writes: tuple[Write, ...]
    rom_blocks: tuple[RomBlock, ...]
    state_events: tuple[StateEvent, ...]
    segments: tuple[Segment, ...]
    issues: tuple[str, ...]
    loop_count: int = 1

    @property
    def divider(self):
        return 132 if self.pin7_high else 165

    @property
    def rate_hz(self):
        return self.clock_hz // self.divider

    def dump(self, outdir, stem):
        root = Path(outdir)
        root.mkdir(parents=True, exist_ok=True)
        for name, rows in (
            ('writes', [asdict(x) for x in self.writes]),
            ('states', [dict(event_id=x.write.event_id, source_event_id=x.write.source_event_id,
                vgmticks=x.write.vgmticks, loop_iteration=x.write.loop_iteration,
                registers=' '.join(f'{v:02x}' for v in x.registers), pending_sample=x.pending_sample,
                command_kind=x.command_kind, voice_mask=x.voice_mask, attenuation=x.attenuation)
                for x in self.state_events]),
            ('segments', [asdict(x) for x in self.segments])):
            with (root / f'{stem}.msm6295.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['event_id'])
                writer.writeheader()
                writer.writerows(rows)
        blocks = []
        for index, block in enumerate(self.rom_blocks):
            filename = f'{stem}.msm6295.rom.{index:04d}.bin'
            (root / filename).write_bytes(block.payload)
            values = asdict(block)
            values.pop('payload')
            blocks.append(dict(**values, payload_file=filename, payload_bytes=len(block.payload),
                sha256=hashlib.sha256(block.payload).hexdigest()))
        report = dict(clock_raw=self.clock_raw, clock_hz=self.clock_hz, pin7_high=self.pin7_high,
            divider=self.divider, reference_native_rate_hz=self.rate_hz,
            nominal_rate_num=self.clock_hz, nominal_rate_den=self.divider,
            tick_clock_hz=44100, source_end_vgmticks=self.source_end_vgmticks,
            loop_count=self.loop_count, reference_revision=REFERENCE_REVISION,
            reference_core_sha256=REFERENCE_CORE_SHA256, reference_decoder_sha256=REFERENCE_DECODER_SHA256,
            segment_semantics='ordered write-observed command intervals, not inferred audible gates',
            initialization=dict(origin='reference_reset_assumption', observed=False,
                pending_sample=None, voice_state='all idle', bank_base=0,
                decoder_signal=-2, decoder_step=0),
            pin7_origin='libvgm VGM header bit31 convention', issues=self.issues, rom_blocks=blocks)
        (root / f'{stem}.msm6295.source.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def analyze(raw, *, loop_count=1):
    header = read_vgm_header(raw)
    clock_raw = header.get('msm6295_clock_raw', 0)
    clock = clock_raw & 0x3fffffff
    registers = [0] * 128
    pending_sample = None
    writes, blocks, states, segments, issues = [], [], [], [], []
    end = 0
    if clock_raw & 0x40000000:
        issues.append('dual_msm6295_header_unsupported')
    for event_id, command in enumerate(command_times(raw, loop_count=loop_count)):
        end = command.vgmticks + command.wait_samples
        offset = command.address
        if command.command == 0x67 and raw[offset + 2] == 0x8b:
            size_raw = struct.unpack_from('<I', raw, offset + 3)[0]
            size = size_raw & 0x7fffffff
            if size < 8:
                raise ValueError('MSM6295 ROM block is shorter than its total/start header')
            total, start = struct.unpack_from('<II', raw, offset + 7)
            payload = bytes(raw[offset + 15:offset + 7 + size])
            if not total or start > total or len(payload) > total - start:
                raise ValueError('MSM6295 ROM block exceeds its declared range')
            instance = size_raw >> 31
            blocks.append(RomBlock(event_id, command.source_event_id, offset, command.vgmticks,
                command.loop_iteration, total, start, payload, instance))
            if instance:
                issues.append('second_msm6295_rom_unsupported')
        elif command.command == 0xb8:
            address, value = raw[offset + 1:offset + 3]
            instance, register = address >> 7, address & 127
            write = Write(event_id, command.source_event_id, offset, command.vgmticks,
                command.loop_iteration, register, value, instance)
            writes.append(write)
            if instance:
                issues.append('second_msm6295_write_unsupported')
                continue
            kind, mask, attenuation = 'extension_write', 0, None
            if register == 0:
                if pending_sample is not None:
                    kind, mask, attenuation = 'start_request', value >> 4, value & 15
                    pending_sample = None
                elif value & 128:
                    pending_sample, kind = value & 127, 'sample_select'
                else:
                    kind, mask = 'stop_request', (value >> 3) & 15
            registers[register] = value
            states.append(StateEvent(write, tuple(registers), pending_sample, kind, mask, attenuation))
    for index, state in enumerate(states):
        next_state = states[index + 1] if index + 1 < len(states) else None
        write = state.write
        segments.append(Segment(write.vgmticks, next_state.write.vgmticks if next_state else end,
            write.event_id, next_state.write.event_id if next_state else None,
            write.register, write.value, state.pending_sample, state.command_kind,
            state.voice_mask, state.attenuation))
    if writes and not clock:
        issues.append('missing_msm6295_clock')
    return Trace(end, clock_raw, clock, bool(clock_raw & 0x80000000), tuple(writes),
        tuple(blocks), tuple(states), tuple(segments), tuple(dict.fromkeys(issues)), loop_count)
