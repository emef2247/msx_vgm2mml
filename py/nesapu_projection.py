"""Inspectable NES APU projection to SCC, AY noise and passed-through chips.

Native evidence is never retimed or rewritten. The generated VGM is a target
adapter into the ordinary sounding-unit, loop, macro and envelope pipeline:
pulse and triangle voices become SCC waveforms (duty and the 32-step
triangle transfer directly), noise becomes the AY noise generator, and
non-APU commands already expressed in target chips (YM2413/VRC7, AY) are
passed through unchanged. DPCM sample playback and FDS voices have no
target in this revision and are omitted with explicit summary records.
"""
from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import json
import math
import struct

from nesapu import NOISE_PERIODS, SLICE_SAMPLES, analyze, lfsr_tick_cells
from vgm_io import read_vgm_bytes
from vgm_loop import read_loop_metadata
from vgm_timing import command_times

TARGET_CLOCK = 1789773
# RAM data block types owned by the NES APU route; mirrors
# native_source_music.BLOCK_CHIPS entries mapped to 'nesapu'.
NES_RAM_BLOCK_TYPES = {0xc0, 0xc1, 0xc2}
# SCC period whose waveform cycle is one 1/60 s slice tick.
SLICE_PERIOD = round(2 * TARGET_CLOCK / (32 * 60)) - 1
DUTY_HIGH_STEPS = (4, 8, 16, 24)
TRIANGLE_LEVELS = tuple(15 - i if i < 16 else i - 16 for i in range(32))


class ProjectionError(ValueError):
    pass


def has_nesapu(raw):
    return any(command.command == 0xb4 for command in command_times(raw))


def _csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def duty_wave(duty):
    high = DUTY_HIGH_STEPS[duty]
    return tuple(124 if i < high else -124 for i in range(32))


def triangle_wave():
    return tuple(round((level - 7.5) * 16) for level in TRIANGLE_LEVELS)


def _scc_period(source_hz):
    register = round(2 * TARGET_CLOCK / (32 * source_hz)) - 1
    clamped = min(4095, max(9, register))
    output_hz = 2 * TARGET_CLOCK / (32 * (clamped + 1))
    return clamped, output_hz


def _noise_period(source_rate_hz):
    register = round(TARGET_CLOCK / (16 * source_rate_hz))
    clamped = min(31, max(1, register))
    return clamped, TARGET_CLOCK / (16 * clamped)


@dataclass
class Projection:
    vgm: bytes
    allocation: dict
    controls: list
    writes: list
    gates: list
    summary: dict

    def dump(self, root, stem):
        root = Path(root)
        for name, rows, fields in (
            ('allocation', self.summary['allocation'],
             ['source_channel', 'target_chip', 'target_channel']),
            ('controls', self.controls, ['source_event_id', 'vgmticks',
                'source_channel', 'target_chip', 'target_channel',
                'source_period', 'target_period', 'source_hz', 'target_hz',
                'pitch_error_cents', 'target_volume', 'enabled', 'waveform']),
            ('target_writes', self.writes, ['source_event_id', 'vgmticks',
                'target_address', 'command_hex']),
            ('gates', self.gates, ['source_channel', 'start_vgmticks',
                'end_vgmticks', 'start_source_event_id', 'end_source_event_id'])):
            fields = list(dict.fromkeys(fields + [key for row in rows for key in row]))
            _csv(root / f'{stem}.nesapu.{name}.csv', rows, fields)


def project(raw, trace=None, *, force=False):
    trace = analyze(raw) if trace is None else trace
    commands = list(command_times(raw))
    # Data blocks are accounted, never emitted: NES RAM blocks carry the
    # DPCM sample data this revision omits (recorded in the summary);
    # any other chip's block still blocks the route.
    blocks = []
    for command in commands:
        if command.command != 0x67:
            continue
        address = command.address
        block_type = raw[address + 2]
        block_size = struct.unpack_from('<I', raw, address + 3)[0]
        start = (struct.unpack_from('<H', raw, address + 7)[0]
                 if 0xc0 <= block_type <= 0xdf and block_size >= 2 else None)
        blocks.append(dict(type=f'{block_type:#x}', address=address,
                           size_bytes=block_size, start_address=start,
                           data_bytes=block_size - 2 if start is not None
                           else block_size))
    foreign_block = next((b for b in blocks
                          if int(b['type'], 16) not in NES_RAM_BLOCK_TYPES),
                         None)
    if foreign_block:
        raise ProjectionError(
            f'NES APU route cannot silently omit data block type '
            f"{foreign_block['type']} at {foreign_block['address']:#x}")
    present = {command.command for command in commands}
    passthrough = present & {0x51, 0xa1}
    ay_present = 0xa0 in present
    if ay_present:
        passthrough.add(0xa0)
    supported = {0xb4, 0x61, 0x62, 0x63, 0x64, 0x66, 0x67,
                 *range(0x70, 0x80), *passthrough}
    unknown = next((c for c in commands if c.command not in supported), None)
    if unknown:
        raise ProjectionError(
            f'NES APU route cannot silently omit mixed/unsupported command '
            f'{unknown.command:#x} at {unknown.address:#x}')

    noise_route = 'scc_only_ay_present' if ay_present else 'psg+scc'
    allocation = {0: ('scc', 0), 1: ('scc', 1), 2: ('scc', 2),
                  3: ('psg', 2)}
    # Complementary lanes share the one spare SCC waveform (channel 3;
    # the MGSDRV decoder range covers four waveforms, as on the
    # original SCC where channels 4/5 share): 4 = DPCM slices take
    # priority, 5 = slow-LFSR noise slices when no DPCM is present.
    lanes = {**allocation, 4: ('scc', 3), 5: ('scc', 3)}
    events = []  # (sample, sequence, command bytes, source_event_id)
    sequence = 0

    def emit(sample, command, event_id=None):
        nonlocal sequence
        events.append((sample, sequence, bytes(command), event_id))
        sequence += 1

    def scc(sample, port, register, value, event_id=None):
        emit(sample, (0xd2, port, register, value & 255), event_id)

    # Initial target state: PSG all disabled, SCC silent.
    emit(0, (0xa0, 7, 63))
    for dest in range(3):
        emit(0, (0xa0, 8 + dest, 0))
    scc(0, 3, 0, 0)
    waves = {0: duty_wave(0), 1: duty_wave(0), 2: triangle_wave()}
    for dest in range(3):
        for index, value in enumerate(waves[dest]):
            scc(0, 0, dest * 32 + index, value)
    if trace.dpcm_slices:
        scc(0, 1, 6, SLICE_PERIOD & 255)
        scc(0, 1, 7, SLICE_PERIOD >> 8)
        scc(0, 2, 3, 0)
        for index in range(32):
            scc(0, 0, 96 + index, 0)

    controls, gates = [], []
    clamped_pitches = 0
    for channel in range(3):
        chip, dest = allocation[channel]
        segments = [s for s in trace.segments if s.channel == channel]
        cache = {}
        gate_start = None
        loaded_wave = waves.get(dest) if chip == 'scc' else None
        for segment in segments:
            view = segment.state
            at = segment.start_vgmticks
            if chip == 'omitted':
                continue
            if not view.audible:
                if gate_start is not None:
                    gates.append(dict(source_channel=channel,
                        start_vgmticks=gate_start[0], end_vgmticks=at,
                        start_source_event_id=gate_start[1],
                        end_source_event_id=segment.start_event_id))
                    gate_start = None
                    if chip == 'scc':
                        scc(at, 2, dest, 0, segment.start_event_id)
                    else:
                        emit(at, (0xa0, 8 + dest, 0), segment.start_event_id)
                    cache['sounding'] = False
                continue
            if gate_start is None:
                gate_start = (at, segment.start_event_id)
            if chip == 'scc':
                source_hz = trace.clock_hz / ((16 if channel < 2 else 32)
                                              * (view.period + 1))
                register, target_hz = _scc_period(source_hz)
                if register != round(2 * TARGET_CLOCK / (32 * source_hz)) - 1:
                    clamped_pitches += 1
                wave = duty_wave(view.duty) if channel < 2 else triangle_wave()
                if wave != loaded_wave:
                    for index, value in enumerate(wave):
                        scc(at, 0, dest * 32 + index, value,
                            segment.start_event_id)
                    loaded_wave = wave
                key = (register, view.volume, True)
                if cache.get('key') != key:
                    if cache.get('period') != register:
                        scc(at, 1, dest * 2, register & 255,
                            segment.start_event_id)
                        scc(at, 1, dest * 2 + 1, register >> 8,
                            segment.start_event_id)
                    scc(at, 2, dest, view.volume, segment.start_event_id)
                    cache.update(key=key, period=register, sounding=True)
                waveform = f'duty{view.duty}' if channel < 2 else 'triangle'
            else:  # channel 3 (noise) is handled in its own block below
                continue
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=channel, target_chip=chip,
                target_channel=dest,
                source_period=view.period if chip == 'scc'
                else view.noise_period_index,
                target_period=register, source_hz=source_hz,
                target_hz=target_hz,
                pitch_error_cents=1200 * math.log2(target_hz / source_hz),
                target_volume=view.volume, enabled=True, waveform=waveform))
        if gate_start is not None:
            gates.append(dict(source_channel=channel,
                start_vgmticks=gate_start[0],
                end_vgmticks=trace.source_end_vgmticks,
                start_source_event_id=gate_start[1], end_source_event_id=None))

    # Noise, dually routed: the PSG noise generator covers APU rates
    # within 50 cents; slower LFSR rates are rendered as SCC waveform
    # slices on the spare waveform lane (SCC channel 3) when DPCM does
    # not claim it. When an AY part owns the PSG, in-range segments
    # are omitted (recorded) and out-of-range segments still render
    # on SCC when the lane is free.
    noise_scc_segments = 0
    noise_omitted_segments = 0
    noise_lane_deferred = 0
    psg_cache = {}
    scc_wave_loaded = None
    scc_noise_volume = None
    scc_noise_period_set = False
    active_route = None
    noise_gate = None

    def close_noise_gate(at, event_id):
        nonlocal noise_gate
        if noise_gate is not None:
            source_channel, start, start_id = noise_gate
            gates.append(dict(source_channel=source_channel,
                start_vgmticks=start, end_vgmticks=at,
                start_source_event_id=start_id, end_source_event_id=event_id))
            noise_gate = None

    def silence_noise(at, event_id):
        nonlocal active_route, scc_noise_volume
        if active_route == 'psg':
            emit(at, (0xa0, 8 + 2, 0), event_id)
            psg_cache.clear()
            psg_cache['sounding'] = False
        elif active_route == 'scc':
            scc(at, 2, 3, 0, event_id)
            scc_noise_volume = 0
        active_route = None

    for segment in [s for s in trace.segments if s.channel == 3]:
        view = segment.state
        at = segment.start_vgmticks
        if not view.audible:
            close_noise_gate(at, segment.start_event_id)
            silence_noise(at, segment.start_event_id)
            continue
        rate = trace.clock_hz / NOISE_PERIODS[view.noise_period_index]
        np_reg = round(TARGET_CLOCK / (16 * rate))
        cents = (1200 * math.log2((TARGET_CLOCK / (16 * np_reg)) / rate)
                 if 1 <= np_reg <= 31 else math.inf)
        route = 'psg' if abs(cents) <= 50 else 'scc'
        if route == 'scc' and trace.dpcm_slices:
            # Waveform lane 3 is taken by DPCM slices; degrade to the
            # clamped PSG rendering (or omission under AY) and record.
            route = 'psg'
            noise_lane_deferred += 1
        if ay_present and route == 'psg':
            route = 'omitted'
        if route != active_route:
            close_noise_gate(at, segment.start_event_id)
            silence_noise(at, segment.start_event_id)
            active_route = route
            if route != 'omitted':
                noise_gate = (3 if route == 'psg' else 5, at,
                              segment.start_event_id)
        if route == 'omitted':
            noise_omitted_segments += 1
            continue
        if route == 'psg':
            register, target_hz = _noise_period(rate)
            key = (register, view.volume, view.lfsr_mode, True)
            if psg_cache.get('key') != key:
                if psg_cache.get('period') != register:
                    emit(at, (0xa0, 6, register), segment.start_event_id)
                emit(at, (0xa0, 7, 63 & ~(1 << 5) | (1 << 2)),
                     segment.start_event_id)
                emit(at, (0xa0, 8 + 2, view.volume), segment.start_event_id)
                psg_cache.update(key=key, period=register, sounding=True)
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=3, target_chip='psg',
                target_channel=2, source_period=view.noise_period_index,
                target_period=register, source_hz=rate, target_hz=target_hz,
                pitch_error_cents=1200 * math.log2(target_hz / rate),
                target_volume=view.volume, enabled=True,
                waveform=f'noise_mode{view.lfsr_mode}'))
        else:
            noise_scc_segments += 1
            if not scc_noise_period_set:
                scc(at, 1, 6, SLICE_PERIOD & 255, segment.start_event_id)
                scc(at, 1, 7, SLICE_PERIOD >> 8, segment.start_event_id)
                scc_noise_period_set = True
            tick_count = -(-(segment.end_vgmticks - at) // SLICE_SAMPLES)
            for k, cells in enumerate(lfsr_tick_cells(
                    trace.clock_hz, view.noise_period_index, view.lfsr_mode,
                    tick_count)):
                t = at + k * SLICE_SAMPLES
                if t >= segment.end_vgmticks:
                    break
                if cells != scc_wave_loaded:
                    for index, value in enumerate(cells):
                        scc(t, 0, 96 + index, value,
                            segment.start_event_id)
                    scc_wave_loaded = cells
                if scc_noise_volume != view.volume:
                    scc(t, 2, 3, view.volume, segment.start_event_id)
                    scc_noise_volume = view.volume
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=3, target_chip='scc',
                target_channel=3, source_period=view.noise_period_index,
                target_period=SLICE_PERIOD, source_hz=rate, target_hz=rate,
                pitch_error_cents=0.0, target_volume=view.volume,
                enabled=True,
                waveform=f'lfsr_mode{view.lfsr_mode}_slice'))
    close_noise_gate(trace.source_end_vgmticks, None)

    # DPCM slices on SCC channel 3.
    if trace.dpcm_slices:
        loaded = (0,) * 32
        volume = 0
        previous_end = None
        gate = None
        for slice_ in trace.dpcm_slices:
            if gate is not None and slice_.event_index != gate[0]:
                gates.append(dict(source_channel=4,
                    start_vgmticks=gate[1], end_vgmticks=previous_end,
                    start_source_event_id=None, end_source_event_id=None))
                gate = None
            if (previous_end is not None
                    and slice_.start_vgmticks > previous_end and volume):
                scc(previous_end, 2, 3, 0)
                volume = 0
            if gate is None:
                gate = (slice_.event_index, slice_.start_vgmticks)
            if slice_.cells != loaded:
                for index, value in enumerate(slice_.cells):
                    scc(slice_.start_vgmticks, 0, 96 + index, value)
                loaded = slice_.cells
            if slice_.volume != volume:
                scc(slice_.start_vgmticks, 2, 3, slice_.volume)
                volume = slice_.volume
            previous_end = slice_.end_vgmticks
        if gate is not None:
            gates.append(dict(source_channel=4, start_vgmticks=gate[1],
                end_vgmticks=previous_end, start_source_event_id=None,
                end_source_event_id=None))
        if volume:
            scc(previous_end, 2, 3, 0)

    # SCC enable mask follows the union of the SCC gates.
    mask_events = []
    for gate in gates:
        chip, dest = lanes[gate['source_channel']]
        if chip != 'scc':
            continue
        mask_events.append((gate['start_vgmticks'], 1, dest))
        mask_events.append((gate['end_vgmticks'], 0, dest))
    mask = 0
    for sample, on, dest in sorted(mask_events,
                                   key=lambda row: (row[0], row[1])):
        mask = (mask | (1 << dest)) if on else (mask & ~(1 << dest))
        scc(sample, 3, 0, mask)

    for index, command in enumerate(commands):
        if command.command in passthrough:
            emit(command.vgmticks,
                 raw[command.address:command.address + 3], index)

    events.sort(key=lambda row: (row[0], row[1]))
    loop = read_loop_metadata(raw)
    if loop['loop_address'] is not None and loop['status'] != 'valid':
        raise ProjectionError('NES APU source loop is not a valid command boundary')
    loop_start = loop['loop_start_samples'] if loop['loop_address'] is not None else None
    body = bytearray()
    target_writes = []
    cursor = 0
    loop_address = 256 if loop_start == 0 else None
    for sample, _, command, event_id in events:
        while cursor < sample:
            step = min(sample - cursor, 65535)
            if loop_start is not None and cursor < loop_start <= cursor + step:
                head = loop_start - cursor
                if head:
                    body.extend(b'\x61' + struct.pack('<H', head))
                    cursor += head
                loop_address = 256 + len(body)
                step -= head
                if not step:
                    break
            body.extend(b'\x61' + struct.pack('<H', step))
            cursor += step
        target_writes.append(dict(source_event_id=event_id, vgmticks=sample,
            target_address=256 + len(body), command_hex=command.hex()))
        body.extend(command)
    while cursor < trace.source_end_vgmticks:
        step = min(trace.source_end_vgmticks - cursor, 65535)
        if loop_start is not None and cursor < loop_start <= cursor + step:
            head = loop_start - cursor
            if head:
                body.extend(b'\x61' + struct.pack('<H', head))
                cursor += head
            loop_address = 256 + len(body)
            step -= head
            if not step:
                break
        body.extend(b'\x61' + struct.pack('<H', step))
        cursor += step
    if loop_start is not None and loop_address is None:
        loop_address = 256 + len(body)
    body.append(0x66)

    header = bytearray(256)
    header[:4] = b'Vgm '
    opll_clock = int.from_bytes(raw[0x10:0x14], 'little') & 0x3fffffff \
        if passthrough & {0x51, 0xa1} else 0
    for offset, value in ((8, 0x171), (0x34, 256 - 0x34),
                          (0x18, trace.source_end_vgmticks),
                          (0x74, TARGET_CLOCK), (0x9c, TARGET_CLOCK),
                          (0x10, opll_clock)):
        struct.pack_into('<I', header, offset, value)
    header[0x78] = 0x10  # YM2149: the MSX PSG target profile.
    if loop_address is not None:
        struct.pack_into('<I', header, 0x1c, loop_address - 0x1c)
        struct.pack_into('<I', header, 0x20,
                         trace.source_end_vgmticks - loop_start)
    result = header + body
    gd3_relative = int.from_bytes(raw[0x14:0x18], 'little')
    if gd3_relative:
        start = 0x14 + gd3_relative
        if raw[start:start + 4] == b'Gd3 ' and start + 12 <= len(raw):
            length = int.from_bytes(raw[start + 8:start + 12], 'little')
            if start + 12 + length > len(raw):
                raise ProjectionError('Truncated source GD3 metadata')
            struct.pack_into('<I', result, 0x14, len(result) - 0x14)
            result.extend(raw[start:start + 12 + length])
    struct.pack_into('<I', result, 4, len(result) - 4)
    summary = dict(source='nesapu', target='scc_plus_psg_noise',
        allocation=[dict(source_channel=ch, target_chip=chip, target_channel=dest)
                    for ch, (chip, dest) in sorted(lanes.items())
                    if ch < 4 or (ch == 4 and trace.dpcm_slices)
                    or (ch == 5 and noise_scc_segments)],
        source_sha256=hashlib.sha256(raw).hexdigest(),
        target_sha256=hashlib.sha256(result).hexdigest(),
        source_end_vgmticks=trace.source_end_vgmticks,
        target_clock_hz=TARGET_CLOCK,
        clamped_pitches=clamped_pitches,
        dpcm_events_rendered=len({s.event_index
                                  for s in trace.dpcm_slices}),
        dpcm_events_omitted=(len(trace.dpcm_events)
                             - len({s.event_index
                                    for s in trace.dpcm_slices})),
        dpcm_slices=len(trace.dpcm_slices),
        dpcm_distinct_states=len({(s.cells, s.volume)
                                  for s in trace.dpcm_slices}),
        noise_scc_segments=noise_scc_segments,
        noise_omitted_segments=noise_omitted_segments,
        noise_lane_deferred=noise_lane_deferred,
        data_blocks_omitted=blocks,
        fds_omitted='fds_registers_present_not_analyzed' in trace.issues,
        noise_route=noise_route,
        passthrough_commands=sorted(hex(c) for c in passthrough),
        loop_validation='positional only in this revision; loop-entry '
                          'register state is not yet traversal-validated',
        limits=['dpcm samples render as 1/60 s scc waveform slices '
            '(effective 1.92 khz resample) on scc channel 3; triggers '
            'without sample data stay omitted and are recorded',
            'fds voices omitted (recorded in summary)',
            'psg noise covers apu lfsr rates within 50 cents; slower '
            'rates render as scc lfsr waveform slices (lfsr phase '
            'restarts per segment) on the spare scc waveform lane, '
            'which dpcm slices claim first; deferred slow noise falls '
            'back to the clamped psg rendering and is counted',
            'scc period clamped to 9..4095 with the error recorded',
            'when a source ay part owns the psg, in-range noise is '
            'omitted (recorded); out-of-range noise still renders on scc'])
    return Projection(bytes(result), allocation, controls, target_writes,
                      gates, summary)


def prepare(source, outdir, stem, *, force=False):
    """Save native evidence before checking target eligibility; never own inputs."""
    raw = read_vgm_bytes(source)
    if not has_nesapu(raw):
        return Path(source), None
    root = Path(outdir)
    trace = analyze(raw)
    trace.dump(root, stem)
    report_path = root / f'{stem}.nesapu.projection.json'
    target_path = root / '_nesapu_target' / f'{stem}.vgm'
    report = dict(status='projecting', source='nesapu',
                  source_path=str(Path(source).resolve()))
    try:
        if not target_path.resolve().is_relative_to(root.resolve()):
            raise ProjectionError(
                f'NES APU target path escapes the output directory: {target_path}')
        if target_path.exists():
            try:
                previous = json.loads(report_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                previous = {}
            if (previous.get('target_sha256')
                    != hashlib.sha256(target_path.read_bytes()).hexdigest()
                    or Path(source).resolve() == target_path.resolve()):
                if previous.get('target_sha256'):
                    report['target_sha256'] = previous['target_sha256']
                raise ProjectionError(
                    f'Refusing to overwrite unowned NES APU target: {target_path}')
            target_path.unlink()
        for name in ('allocation', 'controls', 'target_writes', 'gates'):
            (root / f'{stem}.nesapu.{name}.csv').unlink(missing_ok=True)
        projected = project(raw, trace, force=force)
        projected.dump(root, stem)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(projected.vgm)
        report.update(projected.summary, status='projected',
                      target_path=str(target_path.resolve()))
    except Exception as error:
        report.update(status='blocked', detail=str(error))
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n',
                               encoding='utf-8')
    return target_path, report
