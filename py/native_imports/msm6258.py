"""Backend-neutral MSM6258 source evidence and encoded playback spans.

Byte supply is observed; decoder consumption is deliberately unknown. The
cadence check describes compatibility with continuous low-nibble-first ADPCM
delivery, not an emulated waveform. Data writes use packed immutable columns
instead of allocating a state snapshot for every byte.
"""
import csv
from array import array
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct

from .vgm_io import read_vgm_header
from .vgm_timing import command_times
from .pcm_stream import (PcmStreamControl, PcmStreamSupply, REFERENCE_REVISION, SCHEDULING_MODEL,
                        StreamDecoder, StreamSupplyLog, pack_supply)

DIVIDERS = (1024, 768, 512, 512)
_TRANSFER = struct.Struct('<QQQBBB')


@dataclass(frozen=True)
class PcmTransfer:
    source_event_id: int
    address: int
    vgmticks: int
    chip_instance: int
    register: int
    data: int


@dataclass(frozen=True)
class TransferLog:
    packed: bytes

    def __len__(self):
        return len(self.packed) // _TRANSFER.size

    def __iter__(self):
        return (PcmTransfer(*row) for row in _TRANSFER.iter_unpack(self.packed))

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return PcmTransfer(*_TRANSFER.unpack_from(self.packed, index * _TRANSFER.size))


@dataclass(frozen=True)
class PcmRawCommand:
    source_event_id: int
    address: int
    vgmticks: int
    command: int
    operands: bytes


@dataclass(frozen=True)
class PcmDataBlock:
    block_id: int
    block_type: int
    bank_offset: int | None
    source_event_id: int
    address: int
    vgmticks: int
    payload: bytes


@dataclass(frozen=True)
class PcmControl:
    source_event_id: int
    address: int
    vgmticks: int
    register: int
    data: int
    clock_hz: int
    divider: int
    pan: int | None
    playing: bool | None
    reset_observed: bool
    decoder_reset_known: bool


@dataclass(frozen=True)
class PcmIssue:
    code: str
    source_event_id: int | None
    vgmticks: int
    detail: str


@dataclass(frozen=True)
class PcmSample:
    sample_id: int
    codec: str
    encoded_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class PcmPlayback:
    playback_id: int
    chip_instance: int
    sample_id: int | None
    start_vgmticks: int
    end_vgmticks: int
    first_source_event_id: int
    last_source_event_id: int
    transfer_start: int
    transfer_end: int
    supplied_bytes: int
    clock_hz: int
    divider: int
    rate_num: int
    rate_den: int
    pan: int | None
    reset_observed: bool
    decoder_reset_known: bool
    reset_origin: str
    termination: str
    delivery_cadence_compatible: bool
    independently_playable: bool
    nominal_nibbles: int | None
    consumed_nibbles: int | None
    issues: tuple[str, ...]
    control_event_ids: tuple[int, ...]
    stream_transfer_start: int = 0
    stream_transfer_end: int = 0
    delivery_max_error_vgmticks: float | None = None
    unfed_tail_vgmticks: float | None = None

    @property
    def rate_hz(self):
        return Fraction(self.rate_num, self.rate_den)


@dataclass(frozen=True)
class PcmAnalysis:
    source_end_vgmticks: int
    samples: tuple[PcmSample, ...]
    playbacks: tuple[PcmPlayback, ...]
    controls: tuple[PcmControl, ...]
    issues: tuple[PcmIssue, ...]
    transfers: TransferLog
    raw_commands: tuple[PcmRawCommand, ...]
    source_raw: bytes
    clock_hz: int
    options: int
    initialization: str
    source_loop_vgmticks: int | None
    blocks: tuple[PcmDataBlock, ...]
    stream_supplies: StreamSupplyLog = StreamSupplyLog()
    stream_controls: tuple[PcmStreamControl, ...] = ()
    observations: tuple[PcmIssue, ...] = ()
    loop_count: int = 1

    @property
    def command_provenance(self):
        return command_times(self.source_raw, loop_count=self.loop_count)

    @property
    def segments(self):
        return self.playbacks

    def dump(self, outdir, stem):
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        def rows_csv(name, rows, fields):
            with (out / f'{stem}.pcm_{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        rows_csv('timing', (dict(event_id=i, **asdict(row)) for i, row in enumerate(self.command_provenance)),
                 ('event_id', 'address', 'command', 'vgmticks', 'wait_samples',
                  'source_event_id', 'loop_iteration', 'original_vgmticks'))
        rows_csv('raw', (asdict(row) for row in self.transfers), tuple(PcmTransfer.__dataclass_fields__))
        rows_csv('commands', ({**asdict(row), 'operands': row.operands.hex()} for row in self.raw_commands),
                 tuple(PcmRawCommand.__dataclass_fields__))
        rows_csv('state', (asdict(row) for row in self.controls), tuple(PcmControl.__dataclass_fields__))
        rows_csv('segments', (asdict(row) for row in self.playbacks), tuple(PcmPlayback.__dataclass_fields__))
        rows_csv('issues', (asdict(row) for row in self.issues), tuple(PcmIssue.__dataclass_fields__))
        rows_csv('observations', (asdict(row) for row in self.observations), tuple(PcmIssue.__dataclass_fields__))
        rows_csv('stream_supplies', (asdict(row) for row in self.stream_supplies),
                 tuple(PcmStreamSupply.__dataclass_fields__))
        rows_csv('stream_controls', (asdict(row) for row in self.stream_controls),
                 tuple(PcmStreamControl.__dataclass_fields__))
        sample_dir = out / f'{stem}.pcm_samples'
        sample_dir.mkdir(exist_ok=True)
        sample_rows = []
        for sample in self.samples:
            filename = f'sample_{sample.sample_id:04d}.adpcm'
            (sample_dir / filename).write_bytes(sample.encoded_bytes)
            sample_rows.append(dict(sample_id=sample.sample_id, codec=sample.codec,
                                    byte_length=len(sample.encoded_bytes), sha256=sample.sha256,
                                    filename=f'{sample_dir.name}/{filename}'))
        rows_csv('samples', sample_rows, ('sample_id', 'codec', 'byte_length', 'sha256', 'filename'))
        block_rows = []
        if self.blocks:
            block_dir = out / f'{stem}.pcm_blocks'
            block_dir.mkdir(exist_ok=True)
            for block in self.blocks:
                filename = f'block_{block.block_id:04d}_{block.block_type:02x}.bin'
                (block_dir / filename).write_bytes(block.payload)
                block_rows.append(dict(block_id=block.block_id, block_type=block.block_type,
                    bank_offset=block.bank_offset, source_event_id=block.source_event_id,
                    address=block.address, vgmticks=block.vgmticks, byte_length=len(block.payload),
                    filename=f'{block_dir.name}/{filename}'))
        rows_csv('blocks', block_rows, ('block_id', 'block_type', 'bank_offset',
                 'source_event_id', 'address', 'vgmticks', 'byte_length', 'filename'))
        (out / f'{stem}.pcm_source.json').write_text(json.dumps(dict(
            source_end_vgmticks=self.source_end_vgmticks, clock_hz=self.clock_hz,
            options=self.options, initialization=self.initialization,
            source_loop_vgmticks=self.source_loop_vgmticks, loop_count=self.loop_count,
            consumption_origin='unknown_not_emulated', cadence_tolerance_vgmticks=1,
            stream_scheduling_model=SCHEDULING_MODEL,
            stream_reference_revision=REFERENCE_REVISION,
            register_interpretation_profile='libvgm-msm6258-pan-low2-unmapped17',
            register_reference_revision=REFERENCE_REVISION,
            codec_flag_profile='libvgm-bit2-set-is-adpcm4',
            stream_transfer_count=len(self.stream_supplies),
            transfer_count=len(self.transfers), sample_count=len(self.samples),
            playback_count=len(self.playbacks), issues=[asdict(issue) for issue in self.issues],
            observations=[asdict(issue) for issue in self.observations]),
            indent=2) + '\n', encoding='utf-8')


def analyze(raw, *, initialization='reset', loop_count=1):
    """Read actual command boundaries, preserving unsupported PCM evidence.

    ``explicit`` leaves initial play/pan state unknown; ``reset`` assumes a
    stopped chip and stereo pan at file origin, and records that assumption.
    Finite bank-4 streams retain their commands and separately derived byte
    supplies. Stream exhaustion/STOP never introduces a chip STOP or reset.
    """
    if initialization not in ('explicit', 'reset'):
        raise ValueError('PCM initialization must be explicit or reset')
    raw = bytes(raw)
    header = read_vgm_header(raw)
    # Header reader supplies these fields; fallback uses the same version/data bound.
    bounded = header['version'] >= 0x161 and header['data_start'] >= 0x95
    raw_clock = header.get('msm6258_clock_raw', int.from_bytes(raw[0x90:0x94], 'little') if bounded else 0)
    options = header.get('msm6258_flags', raw[0x94] if bounded else 0)
    original_clock = clock = raw_clock & 0x3fffffff
    divider = DIVIDERS[options & 3]
    clock_buffer = list(clock.to_bytes(4, 'little'))
    playing = False if initialization == 'reset' else None
    pan = 0 if initialization == 'reset' else None
    controls, commands, issues, playbacks, samples = [], [], [], [], []
    blocks, bank_length = [], 0
    repeated_issue_counts = {}
    transfers = bytearray()
    stream_supplies = bytearray()
    decoder = StreamDecoder(raw)
    observations = []
    stopped_stream_supply = []
    stopped_direct_supply = []
    buckets = {}
    active = None
    end = 0
    loop_offset = int.from_bytes(raw[0x1c:0x20], 'little')
    loop_address = 0x1c + loop_offset if loop_offset else None
    loop_tick = None
    missing_clock_reported = False

    def issue(code, event_id, tick, detail):
        # The raw transfer table already preserves every byte and event ID.
        # Summarize recurring errors rather than allocating millions of issues.
        if code in ('data_outside_known_playback', 'unsupported_chip_instance'):
            count, index = repeated_issue_counts.get(code, (0, len(issues)))
            repeated_issue_counts[code] = (count + 1, index)
            if count:
                return
        issues.append(PcmIssue(code, event_id, tick, detail))

    def begin(tick, event_id, reset, origin, observed=False):
        return dict(start=tick, first=event_id, last=event_id, bytes=bytearray(),
                    transfer_start=len(transfers) // _TRANSFER.size, clock=clock,
                    stream_start=decoder.transfer_count,
                    divider=divider, pan=pan, reset=reset, observed=observed,
                    origin=origin, ticks=array('Q'), issues=[], controls=[])

    def finish(tick, reason):
        nonlocal active
        if active is None:
            return
        a = active
        data = bytes(a['bytes'])
        codec = 'msm6258-adpcm4-low-first' if options & 4 else 'msm6258-adpcm3'
        sample_id = None
        if data:
            digest = hashlib.sha256(data).hexdigest()
            key = (codec, digest)
            for candidate in buckets.get(key, ()):
                if samples[candidate].encoded_bytes == data:
                    sample_id = candidate
                    break
            if sample_id is None:
                sample_id = len(samples)
                samples.append(PcmSample(sample_id, codec, data, digest))
                buckets.setdefault(key, []).append(sample_id)
        rate = Fraction(a['clock'], a['divider'])
        cadence = bool(data and rate)
        max_error = tail = None
        if cadence:
            first = a['ticks'][0]
            max_error = max(abs(Fraction(t - first) - Fraction(i * 88200, 1) / rate)
                            for i, t in enumerate(a['ticks']))
            tail = Fraction(tick - first) - Fraction(len(data) * 88200, 1) / rate
            cadence = abs(first - a['start']) <= 1 and max_error <= 1 and tail <= 1
        codes = list(a['issues'])
        if not a['reset']:
            codes.append('decoder_start_unknown_or_continuation')
        if a['pan'] is None:
            codes.append('pan_unknown')
        if not cadence and data:
            codes.append('irregular_byte_supply')
        if not data:
            codes.append('play_without_data')
        if not options & 4:
            codes.append('unsupported_adpcm3')
        if not a['clock']:
            codes.append('clock_unknown')
        if raw_clock & 0xc0000000:
            codes.append('unsupported_clock_flags')
        if options & 0xf0:
            codes.append('reserved_options')
        nominal = int(Fraction(max(0, tick - a['start']), 44100) * rate) if rate else None
        playbacks.append(PcmPlayback(len(playbacks), 0, sample_id, a['start'], tick,
                                    a['first'], a['last'], a['transfer_start'],
                                    len(transfers) // _TRANSFER.size, len(data),
                                    a['clock'], a['divider'], rate.numerator, rate.denominator,
                                    a['pan'], a['observed'], a['reset'], a['origin'], reason, cadence,
                                    bool(data and not codes), nominal, None, tuple(codes),
                                    tuple(a['controls']), a['stream_start'], decoder.transfer_count,
                                    float(max_error) if max_error is not None else None,
                                    float(tail) if tail is not None else None))
        active = None

    if raw_clock & 0xc0000000:
        issue('unsupported_clock_flags', None, 0, f'MSM6258 clock flags {raw_clock >> 30:#x}')
    if options & 0xf0:
        issue('reserved_options', None, 0, f'MSM6258 options {options:#x}')
    def chip_write(event_id, pos, tick, instance, reg, value, *, derived=False):
        nonlocal missing_clock_reported, active, playing, clock, divider, pan
        if not original_clock and not missing_clock_reported:
            issue('absent_chip_declaration', event_id, tick,
                  'PCM supplies retained, but the VGM header declares no MSM6258')
            missing_clock_reported = True
        if instance:
            issue('unsupported_chip_instance', event_id, tick, 'Second MSM6258 write retained')
            return
        if reg == 1:
            if active is not None:
                active['bytes'].append(value)
                active['ticks'].append(tick)
                active['last'] = event_id
            elif playing is False:
                (stopped_stream_supply if derived else stopped_direct_supply).append((event_id, tick))
            else:
                issue('data_outside_known_playback', event_id, tick,
                      'Data supplied with unknown play state')
            return
        reset = False
        if reg == 0:
            if value & 1 or not value & 2:
                if active is not None:
                    active['last'] = event_id
                finish(tick, 'stop_control')
                playing = False
            elif playing is not True:
                reset = playing is False
                observed = any(c.register == 0 and c.playing is False for c in controls)
                active = begin(tick, event_id, reset,
                               'observed_stop_then_play' if reset and observed else
                               'vgm_initialization' if reset else 'unknown_initial_play_state',
                               observed=bool(reset and observed))
                playing = True
            if value & 4 and not value & 1:
                issue('unsupported_recording', event_id, tick, 'Recording control observed')
                if active is not None:
                    active['issues'].append('unsupported_recording')
        elif reg in (2, 0x0b, 0x0c):
            if active is not None:
                active['last'] = event_id
            old_clock, old_divider = clock, divider
            if reg == 2:
                pan = value & 3
                if active is not None and not active['bytes']:
                    active['pan'] = pan
                if value & ~3:
                    observations.append(PcmIssue('pan_non_audio_bits', event_id, tick,
                        f'Raw pan {value:#x}; effective disable bits {pan:#x}; '
                        'libvgm output uses only bits 0 and 1; raw value retained'))
            elif reg == 0x0b:
                clock_buffer[3] = value
                clock = int.from_bytes(bytes(clock_buffer), 'little')
            else:
                divider = DIVIDERS[value & 3]
                if value & ~3:
                    issue('reserved_divider_bits', event_id, tick, f'Divider {value:#x}')
            if active is not None and (clock, divider) != (old_clock, old_divider):
                if active['bytes']:
                    active['issues'].append('rate_change_during_playback')
                else:
                    active['clock'], active['divider'] = clock, divider
        elif 8 <= reg <= 10:
            clock_buffer[reg - 8] = value
        elif reg == 0x17:
            observations.append(PcmIssue('unmapped_register_17', event_id, tick,
                f'Register 0x17 data {value:#x} has no handler in the libvgm MSM6258 '
                'write dispatcher; no hardware alias inferred; raw write retained'))
        else:
            issue('unsupported_register', event_id, tick, f'MSM6258 register {reg:#x}')
            if active is not None:
                active['issues'].append('unsupported_register')
        controls.append(PcmControl(event_id, pos, tick, reg, value, clock, divider, pan, playing,
                                   bool(reset and observed), reset))
        if active is not None:
            active['controls'].append(event_id)

    def supply_until(tick):
        for supply in decoder.advance(tick):
            stream_supplies.extend(pack_supply(supply))
            chip_write(supply.source_event_id, supply.address, supply.vgmticks,
                       supply.chip_instance, supply.register, supply.data, derived=True)

    for event_id, event in enumerate(command_times(raw, loop_count=loop_count)):
        supply_until(event.vgmticks)
        end = event.vgmticks + event.wait_samples
        if event.address == loop_address and event.loop_iteration == 0:
            loop_tick = event.vgmticks
        cmd, pos, tick = event.command, event.address, event.vgmticks
        # Data banks are loaded once; crossing the loop does not append them
        # again or change the stream block numbering.
        if not (cmd == 0x67 and event.loop_iteration):
            decoder.process(event_id, event)
        if cmd == 0x67:
            kind = raw[pos + 2]
            if kind in (4, 0x44):
                size = int.from_bytes(raw[pos + 3:pos + 7], 'little') & 0x7fffffff
                commands.append(PcmRawCommand(event_id, pos, tick, cmd, raw[pos + 1:pos + 7]))
                if event.loop_iteration:
                    continue
                blocks.append(PcmDataBlock(len(blocks), kind, bank_length if kind == 4 else None,
                              event_id, pos, tick, raw[pos + 7:pos + 7 + size]))
                if kind == 4:
                    bank_length += size
            continue
        if 0x90 <= cmd <= 0x95:
            size = {0x90:5, 0x91:5, 0x92:6, 0x93:11, 0x94:2, 0x95:5}[cmd]
            commands.append(PcmRawCommand(event_id, pos, tick, cmd, raw[pos + 1:pos + size]))
            continue
        if cmd == 0xb7:
            addr, value = raw[pos + 1:pos + 3]
            instance, reg = addr >> 7, addr & 0x7f
            transfers.extend(_TRANSFER.pack(event_id, pos, tick, instance, reg, value))
            chip_write(event_id, pos, tick, instance, reg, value)
    supply_until(end)
    issues.extend(PcmIssue(row.code, row.source_event_id, row.vgmticks, row.detail)
                  for row in decoder.issues)
    finish(end, 'source_end')
    if stopped_stream_supply:
        first_id, first_tick = stopped_stream_supply[0]
        observations.append(PcmIssue('stream_supply_while_stopped', first_id, first_tick,
            f'{len(stopped_stream_supply)} derived supplies while known/assumed stopped; '
            f'last tick {stopped_stream_supply[-1][1]}; all supplies retained. '
            'libvgm stop-to-play clears its FIFO; native buffered-data behavior is unverified'))
    if stopped_direct_supply:
        first_id, first_tick = stopped_direct_supply[0]
        observations.append(PcmIssue('direct_supply_while_stopped', first_id, first_tick,
            f'{len(stopped_direct_supply)} direct B7 supplies while known/assumed stopped; '
            f'last tick {stopped_direct_supply[-1][1]}; all transfers retained. '
            'libvgm stop-to-play clears its FIFO; native buffered-data behavior is unverified'))
    if loop_address is not None and loop_tick is None:
        issue('invalid_loop_address', None, end, 'Loop offset does not address a command boundary')
    if loop_tick is not None and any(p.start_vgmticks <= loop_tick < p.end_vgmticks for p in playbacks):
        observations.append(PcmIssue('decoder_continuation_at_song_loop', None, loop_tick,
                                    'Song loop enters active ADPCM state; no independent reset inferred'))
    for code, (count, index) in repeated_issue_counts.items():
        if count > 1:
            first = issues[index]
            issues[index] = PcmIssue(code, first.source_event_id, first.vgmticks,
                                    f'{first.detail}; {count} writes (all raw rows retained)')
    return PcmAnalysis(end, tuple(samples), tuple(playbacks), tuple(controls), tuple(issues),
                       TransferLog(bytes(transfers)), tuple(commands), raw, original_clock,
                       options, initialization, loop_tick, tuple(blocks),
                       StreamSupplyLog(bytes(stream_supplies)), tuple(decoder.controls),
                       tuple(observations), loop_count)
