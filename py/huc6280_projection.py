"""Inspectable HuC6280 projection to SCC, AY and approximate OPLL spill.

Native evidence is never retimed or rewritten. The generated VGM is a target
adapter into the ordinary sounding-unit, loop, macro and envelope pipeline.
"""
from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import itertools
import json
import math
import struct

from huc6280 import analyze, attenuation_levels, VOLUME_TABLE
from vgm_io import read_vgm_bytes
from vgm_loop import read_loop_metadata
from vgm_timing import command_times

TARGET_CLOCK = 1789773
# Measured steady square-wave RMS in the libkss/MGSDRV target profile:
# SCC +/-124 versus AY at v15. This is a target mixer approximation, not a
# physical-chip output calibration. The reference captures are reproducible
# with @s0={80*16,78*16}, @0, v15 and the same PSG note.
PSG_RELATIVE_GAIN = 0.7968


class ProjectionError(ValueError):
    pass


def has_huc6280(raw):
    return any(command.command == 0xb9 for command in command_times(raw))


def square_wave(wave):
    """Accept only a 50% two-level square, including cyclic rotations."""
    if len(wave) != 32 or None in wave or len(set(wave)) != 2:
        return False
    low, high = sorted(set(wave))
    return (wave.count(low) == wave.count(high) == 16 and
            sum(wave[i] != wave[(i + 1) % 32] for i in range(32)) == 2)


def _csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _allocate(trace):
    waves = {}
    for segment in trace.segments:
        if not segment.active:
            continue
        state = segment.state
        if state.mode != 'wave' or segment.lfo_control & 3:
            raise ProjectionError(f'HuC6280 channel {segment.channel + 1}: active '
                                  f'{state.mode}/LFO is outside periodic SCC+PSG projection')
        if not state.waveform_complete:
            raise ProjectionError(f'HuC6280 channel {segment.channel + 1}: audible waveform RAM '
                                  f'is not fully observed at {segment.start_vgmticks}')
        waves.setdefault(segment.channel, set()).add(state.waveform)
    # Initial scope is static per-source timbre. RAM changes remain in native
    # evidence; they are not replaced by a final-state waveform at song start.
    for channel, versions in waves.items():
        if len(versions) != 1:
            raise ProjectionError(f'HuC6280 channel {channel + 1}: changing audible waveforms '
                                  'require a dynamic wave-memory allocator')
    channels = sorted(waves)
    for count in range(min(5, len(channels)), -1, -1):
        for selected in itertools.combinations(channels, count):
            spill = [ch for ch in channels if ch not in selected]
            if len(spill) > 3 or any(not square_wave(next(iter(waves[ch]))) for ch in spill):
                continue
            ordered = list(selected)
            if count == 5:
                pair = next(((a, b) for a, b in itertools.combinations(selected, 2)
                             if waves[a] == waves[b]), None)
                if pair is None:
                    continue
                ordered = [ch for ch in selected if ch not in pair] + list(pair)
            return {**{ch: ('scc', index) for index, ch in enumerate(ordered)},
                    **{ch: ('psg', index) for index, ch in enumerate(spill)}}
    raise ProjectionError('HuC6280 periodic voices do not fit ordinary SCC shared RAM '
                          'plus three square-wave PSG parts; OPLL spill is not implemented')


def _pitch(clock, period, target):
    source_hz = clock / (32 * (period or 4096))
    if target == 'scc':
        register = round(2 * TARGET_CLOCK / (32 * source_hz)) - 1
        if not 9 <= register <= 4095:
            raise ProjectionError(f'HuC6280 pitch {source_hz:.6f} Hz exceeds SCC period range')
        output_hz = 2 * TARGET_CLOCK / (32 * (register + 1))
    else:
        register = round(TARGET_CLOCK / (16 * source_hz))
        if not 1 <= register <= 4095:
            raise ProjectionError(f'HuC6280 pitch {source_hz:.6f} Hz exceeds PSG period range')
        output_hz = TARGET_CLOCK / (16 * register)
    return register, source_hz, output_hz


def _gain(state, global_balance, target):
    left, right = attenuation_levels(state.control, state.balance, global_balance)
    mono = (VOLUME_TABLE[left] + VOLUME_TABLE[right]) / (2 * VOLUME_TABLE[0])
    if target == 'scc':
        levels = [n / 15 for n in range(16)]
    else:
        # AY fixed-volume levels are logarithmic. A target approximation, not
        # a reinterpretation of native HuC attenuation or stereo controls.
        levels = [0.0] + [10 ** ((n - 15) * 3 / 20) for n in range(1, 16)]
        wave = state.waveform
        mono *= PSG_RELATIVE_GAIN * (max(wave) - min(wave)) / 31 if None not in wave else 0
    level = min(range(16), key=lambda index: abs(levels[index] - mono))
    return level, left, right, mono, levels[level]


def _validate_loop(raw, trace, commands, loop):
    """Require a stable second traversal before using first-pass target states.

    Wave upload pointers and partial register writes can depend on EOF state.
    Their native positive-duration consequences must agree on repeated entry;
    phase itself is deliberately outside this cross-chip approximation.
    """
    start = loop['loop_start_samples']
    length = trace.source_end_vgmticks - start
    if length <= 0:
        raise ProjectionError('HuC6280 loop has no positive duration')
    # A bounded number of traversals cannot prove that a phase-dependent RAM
    # write never reaches a different sample later. Require an observed reset
    # inside each loop before disabled RAM uploads; enabled writes are outside
    # the static-wave scope, even if their first two values happen to agree.
    reset_pointer = set()
    for event in trace.states:
        if event.write.address < loop['loop_address']:
            continue
        channel = event.selected_channel
        if channel >= 6:
            continue
        state = event.channels[channel]
        if event.write.register == 4:
            if state.enabled:
                reset_pointer.discard(channel)
            elif event.dda_reset_edge:
                reset_pointer.add(channel)
        if event.write.register == 6 and not state.dda_mode:
            if state.enabled or channel not in reset_pointer:
                raise ProjectionError('HuC6280 loop waveform write depends on oscillator phase; '
                                      'disabled upload with an explicit in-loop pointer reset is required')
    end_address = commands[-1].address
    expanded = bytearray(raw[:end_address] + raw[loop['loop_address']:end_address] + b'\x66')
    struct.pack_into('<I', expanded, 4, len(expanded) - 4)
    struct.pack_into('<I', expanded, 0x14, 0)
    repeated = analyze(bytes(expanded))

    def intervals(begin, end):
        result = []
        for channel in range(6):
            rows = []
            for segment in repeated.segments:
                if segment.channel != channel or segment.end_vgmticks <= begin or segment.start_vgmticks >= end:
                    continue
                state = segment.state
                values = ((state.frequency, state.control, state.balance, state.noise_control,
                           state.dda, state.waveform, state.waveform_known, segment.global_balance,
                           segment.lfo_frequency, segment.lfo_control) if segment.active else None)
                lo, hi = max(begin, segment.start_vgmticks) - begin, min(end, segment.end_vgmticks) - begin
                if rows and rows[-1][1] == lo and rows[-1][2] == values:
                    rows[-1] = (rows[-1][0], hi, values)
                else:
                    rows.append((lo, hi, values))
            result.append(rows)
        return result
    if intervals(start, trace.source_end_vgmticks) != intervals(trace.source_end_vgmticks,
                                                                trace.source_end_vgmticks + length):
        raise ProjectionError('HuC6280 loop state/waveform dependency changes on second traversal; '
                              'a dynamic loop-state projection is required')


def _validate_target_loop(raw):
    """Check projected register dependencies across two actual loop traversals."""
    loop = read_loop_metadata(raw)
    if loop['loop_address'] is None:
        return
    commands = list(command_times(raw))
    ay, frequency, volume, waves, enabled = [0] * 16, [0] * 10, [0] * 5, [0] * 128, 0
    opll = [0] * 64

    def traverse(items):
        nonlocal enabled
        intervals = []
        for command in items:
            data = raw[command.address:command.address + 4]
            if data[0] == 0xa0:
                ay[data[1]] = data[2]
            elif data[0] == 0x51:
                opll[data[1]] = data[2]
            elif data[0] == 0xd2:
                port, register, value = data[1:]
                if port == 0:
                    waves[register] = value
                elif port == 1:
                    frequency[register] = value
                elif port == 2:
                    volume[register] = value
                elif port == 3:
                    enabled = value
            if command.wait_samples and command.address >= loop['loop_address']:
                scc = tuple((frequency[2 * ch] + 256 * frequency[2 * ch + 1], volume[ch],
                             tuple(waves[min(ch, 3) * 32:(min(ch, 3) + 1) * 32]))
                            if enabled & (1 << ch) and volume[ch] else None for ch in range(5))
                psg = tuple((ay[2 * ch] + 256 * ay[2 * ch + 1] if not ay[7] & (1 << ch) else None,
                             ay[6] if not ay[7] & (1 << (ch + 3)) else None, ay[8 + ch])
                            if ay[8 + ch] and ay[7] & (9 << ch) != 9 << ch else None for ch in range(3))
                fm = tuple((opll[0x10 + ch], opll[0x20 + ch], opll[0x30 + ch],
                            tuple(opll[:8]) if not opll[0x30 + ch] >> 4 else None)
                           if opll[0x20 + ch] & 16 else None for ch in range(9))
                intervals.append((command.wait_samples, scc, psg, fm, opll[14]))
        return intervals
    first = traverse(commands)
    second = traverse([c for c in commands if c.address >= loop['loop_address']])
    if first != second:
        raise ProjectionError('HuC6280 projected target loop register dependencies are not periodic')


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
            ('controls', self.controls, ['source_event_id', 'vgmticks', 'source_channel',
                'target_chip', 'target_channel', 'source_period', 'target_period',
                'source_hz', 'target_hz', 'pitch_error_cents', 'attenuation_left',
                'attenuation_right', 'mono_gain', 'target_volume', 'target_gain',
                'enabled', 'waveform_id', 'quiet_rounded_to_zero']),
            ('target_writes', self.writes, ['source_event_id', 'vgmticks',
                'target_address', 'command_hex']),
            ('gates', self.gates, ['source_channel', 'start_vgmticks', 'end_vgmticks',
                'start_source_event_id', 'end_source_event_id'])):
            fields = list(dict.fromkeys(fields + [key for row in rows for key in row]))
            _csv(root / f'{stem}.huc6280.{name}.csv', rows, fields)


def _project_static(raw, trace=None):
    trace = analyze(raw) if trace is None else trace
    if trace.issues:
        raise ProjectionError('HuC6280 source issues: ' + ', '.join(trace.issues))
    commands = list(command_times(raw))
    allowed = {0xb9, 0x61, 0x62, 0x63, 0x64, 0x66, *range(0x70, 0x80)}
    unknown = next((c for c in commands if c.command not in allowed), None)
    if unknown:
        raise ProjectionError(f'HuC6280 hybrid route cannot silently omit mixed/unsupported '
                              f'command {unknown.command:#x} at {unknown.address:#x}')
    allocation = _allocate(trace)
    audible_waves = {segment.channel: segment.waveform for segment in trace.segments if segment.active}
    events = {event.write.source_event_id: event for event in trace.states}
    body, target_writes, controls = bytearray(), [], []
    enable_scc, mixer_psg = 0, 63
    cache, loaded, gate_start, gates = {}, {}, {}, []
    loop_gain_pitch_restored = set()

    def emit(command, tick=0, event_id=None):
        target_writes.append(dict(source_event_id=event_id, vgmticks=tick,
            target_address=256 + len(body), command_hex=command.hex()))
        body.extend(command)

    def scc(port, register, value, tick, event_id):
        emit(bytes((0xd2, port, register, value & 255)), tick, event_id)

    emit(bytes((0xa0, 7, 63)))
    for dest in range(3):
        emit(bytes((0xa0, 8 + dest, 0)))
    scc(3, 0, 0, 0, None)
    loop = read_loop_metadata(raw)
    if loop['loop_address'] is not None and loop['status'] != 'valid':
        raise ProjectionError('HuC6280 source loop is not a valid command boundary')
    if loop['loop_address'] is not None:
        _validate_loop(raw, trace, commands, loop)
    loop_address = None
    for source_id, command in enumerate(commands):
        tick = command.vgmticks
        if command.address == loop['loop_address']:
            loop_address = 256 + len(body)
        if command.command == 0xb9:
            event = events[source_id]
            for channel, (chip, dest) in allocation.items():
                state = event.channels[channel]
                active = state.enabled and min(attenuation_levels(
                    state.control, state.balance, event.global_balance)) < 31
                # Zero-time uploads may expose partial RAM before the next
                # audible interval. Never upload that incomplete future wave.
                ready = (state.waveform_complete and state.mode == 'wave' and
                         state.waveform == audible_waves[channel])
                if active and not ready:
                    continue
                period, source_hz, target_hz = _pitch(trace.clock_hz, state.period, chip) if active else (0, 0, 0)
                volume, left, right, mono, target_gain = _gain(state, event.global_balance, chip)
                key = (active, period, volume, state.waveform if ready else None)
                previous = cache.get(channel)
                # A redundant first-pass source write can restore a different
                # EOF state on the next loop. Retain its own dependencies,
                # without resetting unrelated held voices at loop entry.
                in_loop = loop_address is not None
                affected = (event.write.register == 1 or
                            event.selected_channel == channel and event.write.register in (2, 3, 4, 5, 7))
                replay_write = in_loop and affected
                restore_audibility = (replay_write and active and event.write.register in (1, 4, 5)
                                      and channel not in loop_gain_pitch_restored)
                if restore_audibility:
                    loop_gain_pitch_restored.add(channel)
                replay_pitch = replay_write and event.write.register in (2, 3) or restore_audibility
                if key == previous and not replay_write:
                    continue
                cache[channel] = key
                if active and channel not in gate_start:
                    gate_start[channel] = (tick, source_id)
                elif not active and channel in gate_start:
                    start, start_id = gate_start.pop(channel)
                    gates.append(dict(source_channel=channel, start_vgmticks=start,
                        end_vgmticks=tick, start_source_event_id=start_id, end_source_event_id=source_id))
                if active and ready and chip == 'scc':
                    slot = min(dest, 3)
                    wave = tuple((n - 16) * 8 for n in state.waveform)
                    if loaded.get(slot) != wave:
                        for index, value in enumerate(wave):
                            scc(0, slot * 32 + index, value, tick, source_id)
                        loaded[slot] = wave
                if active and (replay_pitch or previous is None or not previous[0] or previous[1] != period):
                    if chip == 'scc':
                        if replay_pitch or previous is None or not previous[0] or previous[1] & 255 != period & 255:
                            scc(1, dest * 2, period & 255, tick, source_id)
                        if replay_pitch or previous is None or not previous[0] or previous[1] >> 8 != period >> 8:
                            scc(1, dest * 2 + 1, period >> 8, tick, source_id)
                    else:
                        if replay_pitch or previous is None or not previous[0] or previous[1] & 255 != period & 255:
                            emit(bytes((0xa0, dest * 2, period & 255)), tick, source_id)
                        if replay_pitch or previous is None or not previous[0] or previous[1] >> 8 != period >> 8:
                            emit(bytes((0xa0, dest * 2 + 1, period >> 8)), tick, source_id)
                if chip == 'scc':
                    scc(2, dest, volume if active else 0, tick, source_id)
                    enable_scc = (enable_scc | (1 << dest)) if active else (enable_scc & ~(1 << dest))
                    scc(3, 0, enable_scc, tick, source_id)
                else:
                    emit(bytes((0xa0, 8 + dest, volume if active else 0)), tick, source_id)
                    mixer_psg = (mixer_psg & ~(1 << dest)) if active else (mixer_psg | (1 << dest))
                    emit(bytes((0xa0, 7, mixer_psg)), tick, source_id)
                controls.append(dict(source_event_id=source_id, vgmticks=tick, source_channel=channel,
                    target_chip=chip, target_channel=dest, source_period=state.period,
                    target_period=period, source_hz=source_hz, target_hz=target_hz,
                    pitch_error_cents=1200 * math.log2(target_hz / source_hz) if active else 0,
                    attenuation_left=left, attenuation_right=right, mono_gain=mono,
                    target_volume=volume if active else 0, target_gain=target_gain if active else 0,
                    enabled=active, waveform_id=state.waveform_id,
                    quiet_rounded_to_zero=active and volume == 0))
        elif command.wait_samples:
            remaining = command.wait_samples
            while remaining:
                length = min(remaining, 65535)
                body.extend(b'\x61' + struct.pack('<H', length))
                remaining -= length
        elif command.command == 0x66:
            body.append(0x66)
    for channel, (start, source_id) in gate_start.items():
        gates.append(dict(source_channel=channel, start_vgmticks=start,
            end_vgmticks=trace.source_end_vgmticks, start_source_event_id=source_id,
            end_source_event_id=None))
    header = bytearray(256)
    header[:4] = b'Vgm '
    for offset, value in ((8, 0x171), (0x34, 256 - 0x34),
                          (0x18, trace.source_end_vgmticks), (0x74, TARGET_CLOCK),
                          (0x9c, TARGET_CLOCK)):
        struct.pack_into('<I', header, offset, value)
    header[0x78] = 0x10  # YM2149: the MSX PSG target profile.
    if loop_address is not None:
        struct.pack_into('<I', header, 0x1c, loop_address - 0x1c)
        struct.pack_into('<I', header, 0x20, trace.source_end_vgmticks - loop['loop_start_samples'])
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
    _validate_target_loop(bytes(result))
    summary = dict(source='huc6280', target='ordinary_scc_plus_psg',
        allocation=[dict(source_channel=ch, target_chip=chip, target_channel=dest)
                    for ch, (chip, dest) in sorted(allocation.items())],
        source_sha256=hashlib.sha256(raw).hexdigest(),
        target_sha256=hashlib.sha256(result).hexdigest(),
        source_end_vgmticks=trace.source_end_vgmticks, target_clock_hz=TARGET_CLOCK,
        source_channels=len(allocation), scc_channels=sum(c == 'scc' for c, _ in allocation.values()),
        psg_channels=sum(c == 'psg' for c, _ in allocation.values()),
        stereo_fold='arithmetic mean of native left/right linear gain',
        gain_policy='nearest SCC linear / AY approximate 3-dB fixed volume; no per-wave normalization',
        psg_relative_gain=PSG_RELATIVE_GAIN,
        loop_validation='two native traversals; ordered dependent writes retained' if loop_address is not None else 'no declared loop',
        limits=['static audible wave per source channel', 'PSG spill requires 50% square',
                'phase/reset and target mixer gain are approximate',
                'active noise, DDA, LFO, mixed chips and OPLL spill unsupported'])
    return Projection(bytes(result), allocation, controls, target_writes, gates, summary)


def project(raw, trace=None):
    trace = analyze(raw) if trace is None else trace
    try:
        return _project_static(raw, trace)
    except ProjectionError:
        from huc6280_extended import project_extended
        return project_extended(raw, trace)


def prepare(source, outdir, stem):
    """Save native evidence before checking target eligibility; never own inputs."""
    raw = read_vgm_bytes(source)
    if not has_huc6280(raw):
        return Path(source), None
    root = Path(outdir)
    trace = analyze(raw)
    trace.dump(root, stem)
    report_path = root / f'{stem}.huc6280.projection.json'
    target_path = root / '_huc6280_target' / f'{stem}.vgm'
    report = dict(status='projecting', source='huc6280', source_path=str(Path(source).resolve()))
    try:
        if not target_path.resolve().is_relative_to(root.resolve()):
            raise ProjectionError(f'HuC6280 target path escapes the output directory: {target_path}')
        if target_path.exists():
            try:
                previous = json.loads(report_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                previous = {}
            if (previous.get('target_sha256') != hashlib.sha256(target_path.read_bytes()).hexdigest()
                    or Path(source).resolve() == target_path.resolve()):
                # Keep the ownership digest so restoring the original file
                # permits a later retry, while the latest status is blocked.
                if previous.get('target_sha256'):
                    report['target_sha256'] = previous['target_sha256']
                raise ProjectionError(f'Refusing to overwrite unowned HuC6280 target: {target_path}')
            target_path.unlink()
        for name in ('allocation', 'controls', 'target_writes', 'gates'):
            (root / f'{stem}.huc6280.{name}.csv').unlink(missing_ok=True)
        projected = project(raw, trace)
        projected.dump(root, stem)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(projected.vgm)
        report.update(projected.summary, status='projected', target_path=str(target_path.resolve()))
    except Exception as error:
        report.update(status='blocked', detail=str(error))
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return target_path, report
