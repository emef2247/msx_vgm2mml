"""Inspectable NES APU projection to SCC, AY noise and passed-through chips.

Native evidence is never retimed or rewritten. The generated VGM is a target
adapter into the ordinary sounding-unit, loop, macro and envelope pipeline:
pulse and triangle voices become SCC waveforms (duty and the 32-step
triangle transfer directly), noise becomes the AY noise generator, DPCM
playback and slow LFSR noise render as SCC waveform slices, FDS takes the
SCC waveform lane or a layered OPLL preset, and non-APU commands already
expressed in target chips (YM2413/VRC7, AY) are passed through unchanged.
Every loss is an explicit summary record.
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
# Per-kind volume gains for the NES -> SCC/PSG mapping. The source
# segments stay exact; these factors only restyle how the mapping
# expresses them, compensating the NES mixer's relative channel gains
# (pulses capped at 10 in much game data, triangle fixed full, noise
# bursts near full) against the SCC/PSG mix. Selected with
# --nes-balance; individual factors can be overridden.
BALANCE_GAINS = {'pulse': 1.3, 'triangle': 0.75, 'noise': 0.8,
                 'dpcm': 1.25, 'fds': 1.0}
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


def _opll_pitch(hz):
    """Nearest YM2413 fnum/block for a frequency (49716 = 3579545/72)."""
    for block in range(8):
        fnum = round(hz * 2**19 / (49716 * 2**block))
        if fnum <= 511:
            fnum = max(1, fnum)
            return fnum, block, 49716 * fnum * 2**block / 2**19
    return 511, 7, 49716 * 511 * 2**7 / 2**19


def _loop_intervals(trace, begin, end):
    """State rows per channel plus DPCM slice rows inside [begin, end),
    times relativized to begin, adjacent equal states merged."""
    channels = {}
    for channel in range(5):
        rows = []
        for segment in trace.segments:
            if segment.channel != channel \
                    or segment.end_vgmticks <= begin \
                    or segment.start_vgmticks >= end:
                continue
            state = segment.state
            # Only audible dependencies are compared (the HuC6280
            # convention): a silent channel's held period or control
            # registers do not change what the next traversal sounds
            # like, but an envelope or counter that evolved through
            # the loop point does.
            values = (state.kind, state.period, state.duty,
                      state.volume, state.lfsr_mode,
                      state.noise_period_index, state.control, state.sweep,
                      state.wave_id, state.mod_ratio) if state.audible \
                else None
            lo = max(begin, segment.start_vgmticks) - begin
            hi = min(end, segment.end_vgmticks) - begin
            if rows and rows[-1][1] == lo and rows[-1][2] == values:
                rows[-1] = (rows[-1][0], hi, values)
            else:
                rows.append((lo, hi, values))
        channels[channel] = rows
    slices = []
    for item in trace.dpcm_slices:
        if item.end_vgmticks <= begin or item.start_vgmticks >= end:
            continue
        lo = max(begin, item.start_vgmticks) - begin
        hi = min(end, item.end_vgmticks) - begin
        values = (item.cells, item.volume)
        if slices and slices[-1][1] == lo and slices[-1][2] == values:
            slices[-1] = (slices[-1][0], hi, values)
        else:
            slices.append((lo, hi, values))
    return channels, slices


def _rows_match(first, second, tolerance):
    """Same states in the same order, durations within one frame step.

    Envelope, length and linear counters are clocked by the free-
    running frame sequencer, whose phase the VGM loop does not reset;
    on hardware their step boundaries jitter by up to a quarter frame
    between iterations, so exact boundary equality is below the
    machine's own noise floor. State sequences and durations beyond
    that jitter remain meaningful differences.
    """
    if len(first) != len(second):
        return False
    return all(a[2] == b[2]
               and abs((a[1] - a[0]) - (b[1] - b[0])) <= tolerance
               for a, b in zip(first, second))


def _validate_loop(raw, trace, loop):
    """Compare the loop body's analyzed state across two traversals.

    The source stream is expanded to intro + body + body and re-analyzed;
    envelope, counter, DPCM and modulator history can make the second
    traversal differ from the first. Returns the differing channel
    labels (empty when the loop is state-periodic); oscillator and
    envelope phase inside an unchanged state row are out of scope.
    """
    start = loop['loop_start_samples']
    end = trace.source_end_vgmticks
    if end - start <= 0:
        raise ProjectionError('NES APU loop has no positive duration')
    commands = list(command_times(raw))
    end_address = commands[-1].address
    expanded = bytearray(raw[:end_address]
                         + raw[loop['loop_address']:end_address] + b'\x66')
    struct.pack_into('<I', expanded, 4, len(expanded) - 4)
    struct.pack_into('<I', expanded, 0x14, 0)
    struct.pack_into('<I', expanded, 0x1c, 0)
    repeated = analyze(bytes(expanded))
    tolerance = math.ceil(7457 * 44100 / trace.clock_hz) \
        if trace.clock_hz else 184
    first = _loop_intervals(repeated, start, end)
    second = _loop_intervals(repeated, end, end + (end - start))
    differing = [channel for channel in range(5)
                 if not _rows_match(first[0][channel],
                                    second[0][channel], tolerance)]
    if not _rows_match(first[1], second[1], tolerance):
        differing.append('dpcm')
    return differing


def _validate_target_loop(raw):
    """Check projected register dependencies across two loop traversals.

    Snapshots hold only audible dependencies (periods, volumes,
    waveforms, keyed voices); phase is outside the comparison, as in
    the HuC6280 target check.
    """
    loop = read_loop_metadata(raw)
    if loop['loop_address'] is None:
        return True
    commands = list(command_times(raw))
    ay, opll, scc = [0] * 16, [0] * 64, {}

    def snapshot():
        psg = tuple(
            (ay[ch * 2] + 256 * ay[ch * 2 + 1], ay[ch + 8],
             ay[6] if not ay[7] & (1 << (ch + 3)) else None)
            if ay[ch + 8] and (ay[7] & (9 << ch)) != (9 << ch) else None
            for ch in range(3))
        voices = tuple(
            (scc.get((1, ch * 2), 0) + 256 * scc.get((1, ch * 2 + 1), 0),
             scc.get((2, ch), 0),
             tuple(scc.get((0, min(ch, 3) * 32 + n), 0) for n in range(32)))
            if scc.get((3, 0), 0) & (1 << ch) and scc.get((2, ch), 0)
            else None for ch in range(5))
        fm = tuple(
            (opll[0x10 + ch], opll[0x20 + ch], opll[0x30 + ch],
             tuple(opll[:8]) if not opll[0x30 + ch] >> 4 else ())
            if opll[0x20 + ch] & 16 else None for ch in range(9))
        return psg, voices, fm

    def traverse(items):
        result = []
        for command in items:
            pos = command.address
            if command.command == 0xa0:
                ay[raw[pos + 1]] = raw[pos + 2]
            elif command.command == 0x51:
                opll[raw[pos + 1]] = raw[pos + 2]
            elif command.command == 0xd2:
                scc[(raw[pos + 1], raw[pos + 2])] = raw[pos + 3]
            if command.wait_samples \
                    and command.address >= loop['loop_address']:
                result.append((command.wait_samples, snapshot()))
        return result

    first = traverse(commands)
    second = traverse([c for c in commands
                       if c.address >= loop['loop_address']])
    return first == second


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


def project(raw, trace=None, *, force=False, gains=None):
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
    # original SCC where channels 4/5 share). Claim priority:
    # 4 = DPCM slices, then 6/7 = the melodic FDS voice, then
    # 5 = slow-LFSR noise slices; the loser degrades and is counted.
    lanes = {**allocation, 4: ('scc', 3), 5: ('scc', 3)}
    fds_audible = any(s.state.audible for s in trace.segments
                      if s.channel == 4)
    events = []  # (sample, sequence, command bytes, source_event_id)
    sequence = 0

    def emit(sample, command, event_id=None):
        nonlocal sequence
        events.append((sample, sequence, bytes(command), event_id))
        sequence += 1

    def scc(sample, port, register, value, event_id=None):
        emit(sample, (0xd2, port, register, value & 255), event_id)

    def scaled(kind, volume):
        gain = (gains or {}).get(kind, 1.0)
        if gain == 1.0 or volume <= 0:
            return volume
        return max(1, min(15, round(volume * gain)))

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
                    # The gate-close write changed the chip's volume, so
                    # the cached key must not suppress the next gate's
                    # volume write when the same note returns.
                    cache.pop('key', None)
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
                mapped = scaled('pulse' if channel < 2 else 'triangle',
                                view.volume)
                key = (register, mapped, True)
                if cache.get('key') != key:
                    if cache.get('period') != register:
                        scc(at, 1, dest * 2, register & 255,
                            segment.start_event_id)
                        scc(at, 1, dest * 2 + 1, register >> 8,
                            segment.start_event_id)
                    scc(at, 2, dest, mapped, segment.start_event_id)
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
                target_volume=mapped, enabled=True, waveform=waveform))
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
        mapped = scaled('noise', view.volume)
        rate = trace.clock_hz / NOISE_PERIODS[view.noise_period_index]
        np_reg = round(TARGET_CLOCK / (16 * rate))
        cents = (1200 * math.log2((TARGET_CLOCK / (16 * np_reg)) / rate)
                 if 1 <= np_reg <= 31 else math.inf)
        route = 'psg' if abs(cents) <= 50 else 'scc'
        if route == 'scc' and (trace.dpcm_slices or fds_audible):
            # Waveform lane 3 is claimed by DPCM slices or by the
            # melodic FDS voice; degrade to the clamped PSG rendering
            # (or omission under AY) and record.
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
            key = (register, mapped, view.lfsr_mode, True)
            if psg_cache.get('key') != key:
                if psg_cache.get('period') != register:
                    emit(at, (0xa0, 6, register), segment.start_event_id)
                emit(at, (0xa0, 7, 63 & ~(1 << 5) | (1 << 2)),
                     segment.start_event_id)
                emit(at, (0xa0, 8 + 2, mapped), segment.start_event_id)
                psg_cache.update(key=key, period=register, sounding=True)
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=3, target_chip='psg',
                target_channel=2, source_period=view.noise_period_index,
                target_period=register, source_hz=rate, target_hz=target_hz,
                pitch_error_cents=1200 * math.log2(target_hz / rate),
                target_volume=mapped, enabled=True,
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
                if scc_noise_volume != mapped:
                    scc(t, 2, 3, mapped, segment.start_event_id)
                    scc_noise_volume = mapped
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=3, target_chip='scc',
                target_channel=3, source_period=view.noise_period_index,
                target_period=SLICE_PERIOD, source_hz=rate, target_hz=rate,
                pitch_error_cents=0.0, target_volume=mapped,
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
            slice_volume = scaled('dpcm', slice_.volume)
            if slice_volume != volume:
                scc(slice_.start_vgmticks, 2, 3, slice_volume)
                volume = slice_volume
            previous_end = slice_.end_vgmticks
        if gate is not None:
            gates.append(dict(source_channel=4, start_vgmticks=gate[1],
                end_vgmticks=previous_end, start_source_event_id=None,
                end_source_event_id=None))
        if volume:
            scc(previous_end, 2, 3, 0)

    # FDS: SCC waveform lane when free (DPCM claims it first, then
    # slow noise), else an OPLL preset approximation (two layered
    # channels when available), else a recorded omission.
    fds_segments = [s for s in trace.segments if s.channel == 4]
    fds_route = 'none'
    fds_presets = {}
    fds_opll_channels = ()
    if any(s.state.audible for s in fds_segments):
        if not trace.dpcm_slices and not noise_scc_segments:
            fds_route = 'scc'
            lanes[6] = ('scc', 3)
        else:
            used = set()
            for command in commands:
                if command.command != 0x51:
                    continue
                register = raw[command.address + 1]
                if register == 0x0e and raw[command.address + 2] & 0x20:
                    used.update((6, 7, 8))
                elif 0x10 <= register <= 0x38:
                    used.add(register % 0x10 if register < 0x20
                             else (register - 0x20) if register < 0x30
                             else register - 0x30)
            free = [c for c in range(9) if c not in used]
            if free:
                fds_route = 'opll'
                fds_opll_channels = tuple(free[:2])
                lanes[7] = ('opll', fds_opll_channels[0])
            else:
                fds_route = 'omitted'
    if fds_route == 'scc':
        wave_cells = {}
        loaded = None
        current = {}
        gate_start = None
        for segment in fds_segments:
            view = segment.state
            at = segment.start_vgmticks
            if not view.audible:
                if gate_start is not None:
                    gates.append(dict(source_channel=6,
                        start_vgmticks=gate_start[0],
                        end_vgmticks=at,
                        start_source_event_id=gate_start[1],
                        end_source_event_id=segment.start_event_id))
                    gate_start = None
                    scc(at, 2, 3, 0, segment.start_event_id)
                    current.pop('key', None)
                continue
            if gate_start is None:
                gate_start = (at, segment.start_event_id)
            if view.wave_id not in wave_cells:
                wave = trace.fds_waves[view.wave_id]
                mean = sum(wave) / 64
                peak = max(abs(v - mean) for v in wave) or 1
                wave_cells[view.wave_id] = tuple(
                    round(((wave[2 * i] + wave[2 * i + 1]) / 2 - mean)
                          * 124 / peak) for i in range(32))
            cells = wave_cells[view.wave_id]
            if cells != loaded:
                for index, value in enumerate(cells):
                    scc(at, 0, 96 + index, value, segment.start_event_id)
                loaded = cells
            source_hz = (trace.clock_hz * view.period * view.mod_ratio
                         / 2**22)
            register, target_hz = _scc_period(source_hz)
            if register != round(2 * TARGET_CLOCK / (32 * source_hz)) - 1:
                clamped_pitches += 1
            mapped = scaled('fds', view.volume)
            key = (register, mapped, True)
            if current.get('key') != key:
                if current.get('period') != register:
                    scc(at, 1, 6, register & 255, segment.start_event_id)
                    scc(at, 1, 7, register >> 8, segment.start_event_id)
                scc(at, 2, 3, mapped, segment.start_event_id)
                current.update(key=key, period=register)
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=4, target_chip='scc',
                target_channel=3, source_period=view.period,
                target_period=register, source_hz=source_hz,
                target_hz=target_hz,
                pitch_error_cents=1200 * math.log2(target_hz / source_hz),
                target_volume=mapped, enabled=True,
                waveform=f'fds_wave{view.wave_id}'))
        if gate_start is not None:
            gates.append(dict(source_channel=6,
                start_vgmticks=gate_start[0],
                end_vgmticks=trace.source_end_vgmticks,
                start_source_event_id=gate_start[1],
                end_source_event_id=None))
    elif fds_route == 'opll':
        def classify(wave):
            mean = sum(wave) / 64
            centered = [v - mean for v in wave]
            if max(centered) - min(centered) < 2:
                return (8, 4)
            mags = []
            for k in range(1, 7):
                re = sum(centered[t] * math.cos(2 * math.pi * k * t / 64)
                         for t in range(64))
                im = -sum(centered[t] * math.sin(2 * math.pi * k * t / 64)
                          for t in range(64))
                mags.append(math.hypot(re, im))
            h1 = mags[0] or 1e-9
            ratios = [m / h1 for m in mags]
            if len(set(wave)) <= 3:
                return (5, 10)
            if ratios[1] < 0.15 and ratios[2] < 0.15 and sum(ratios[3:]) < 0.2:
                return (4, 8)
            if ratios[2] > 0.4 and ratios[1] < 0.3:
                return (5, 10)
            if ratios[1] > 0.5:
                return (8, 4)
            return (10, 1)

        for wave_id, wave in enumerate(trace.fds_waves):
            fds_presets[wave_id] = classify(wave)
        state = {c: dict(key=False, fnum=None, block=None, inst=None,
                         vol=None) for c in fds_opll_channels}
        gate_start = None
        for segment in fds_segments:
            view = segment.state
            at = segment.start_vgmticks
            if not view.audible:
                if gate_start is not None:
                    gates.append(dict(source_channel=7,
                        start_vgmticks=gate_start[0], end_vgmticks=at,
                        start_source_event_id=gate_start[1],
                        end_source_event_id=segment.start_event_id))
                    gate_start = None
                for c in fds_opll_channels:
                    if state[c]['key']:
                        emit(at, (0x51, 0x10 + c, state[c]['fnum'] & 255),
                             segment.start_event_id)
                        emit(at, (0x51, 0x20 + c,
                                  (state[c]['fnum'] >> 8 & 1)
                                  | (state[c]['block'] << 1)),
                             segment.start_event_id)
                        state[c]['key'] = False
                continue
            if gate_start is None:
                gate_start = (at, segment.start_event_id)
            source_hz = (trace.clock_hz * view.period * view.mod_ratio
                         / 2**22)
            fnum, block, target_hz = _opll_pitch(source_hz)
            primary, layer = fds_presets[view.wave_id]
            for depth, c in enumerate(fds_opll_channels):
                inst = primary if depth == 0 else layer
                base = scaled('fds', view.volume)
                level = base if depth == 0 else max(0, base - 5)
                slot = state[c]
                if slot['inst'] != inst or slot['vol'] != level:
                    emit(at, (0x51, 0x30 + c, (inst << 4) | (15 - level)),
                         segment.start_event_id)
                    slot.update(inst=inst, vol=level)
                if (slot['fnum'], slot['block']) != (fnum, block) \
                        or not slot['key']:
                    emit(at, (0x51, 0x10 + c, fnum & 255),
                         segment.start_event_id)
                    emit(at, (0x51, 0x20 + c, (fnum >> 8 & 1)
                              | (block << 1) | 0x10),
                         segment.start_event_id)
                    slot.update(fnum=fnum, block=block, key=True)
            controls.append(dict(source_event_id=segment.start_event_id,
                vgmticks=at, source_channel=4, target_chip='opll',
                target_channel=fds_opll_channels[0],
                source_period=view.period, target_period=fnum,
                source_hz=source_hz, target_hz=target_hz,
                pitch_error_cents=1200 * math.log2(target_hz / source_hz),
                target_volume=view.volume, enabled=True,
                waveform=f'fds_wave{view.wave_id}_preset{primary}'))
        if gate_start is not None:
            gates.append(dict(source_channel=7,
                start_vgmticks=gate_start[0],
                end_vgmticks=trace.source_end_vgmticks,
                start_source_event_id=gate_start[1],
                end_source_event_id=None))
        for c in fds_opll_channels:
            if state[c]['key']:
                emit(trace.source_end_vgmticks,
                     (0x51, 0x20 + c, (state[c]['fnum'] >> 8 & 1)
                      | (state[c]['block'] << 1)))

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
    loop_differences = _validate_loop(raw, trace, loop) \
        if loop['loop_address'] is not None else None
    loop_start = loop['loop_start_samples'] if loop['loop_address'] is not None else None
    # Loop-point restoration: a register whose end-of-song value differs
    # from its value at the loop point is rewritten at the loop point,
    # so the projected loop repeats with the register state of the
    # first traversal. Periodic songs restore nothing.
    loop_restored = 0
    if loop_start is not None:
        def register_write(command):
            if command[0] == 0xd2:
                return ('scc', command[1], command[2]), command[3]
            if command[0] in (0x51, 0xa1, 0xa0):
                return (command[0], command[1]), command[2]
            return None, None

        at_loop, at_end = {}, {}
        for sample, _, command, _ in events:
            key, value = register_write(command)
            if key is None:
                continue
            if sample < loop_start:
                at_loop[key] = value
            at_end[key] = value
        differing = [key for key in at_end
                     if at_end[key] != at_loop.get(key, 0)]
        # SCC waveform RAM is restored as whole 32-cell waveforms:
        # the downstream SCC segment builder assembles wavetables
        # from block-aligned uploads only, so a partial-cell restore
        # would corrupt its offsets.
        wave_slots = {key[2] // 32 for key in differing
                      if key[0] == 'scc' and key[1] == 0}
        payloads = []
        for slot in sorted(wave_slots):
            for index in range(32):
                register = slot * 32 + index
                payloads.append(bytes((0xd2, 0, register,
                    at_loop.get(('scc', 0, register), 0))))
        for key in sorted(differing, key=str):
            if key[0] == 'scc' and key[1] == 0:
                continue
            value = at_loop.get(key, 0)
            payloads.append(bytes((0xd2, key[1], key[2], value))
                            if key[0] == 'scc'
                            else bytes((key[0], key[1], value)))
        # Negative sequences sort the block before the body's own
        # loop-point events while preserving payload order (ascending
        # -count..-1 in emission order; the SCC wavetable assembler
        # requires ascending registers within a waveform upload).
        for index, payload in enumerate(payloads):
            events.append((loop_start, index - len(payloads), payload,
                           None))
        loop_restored += len(payloads)
        if loop_restored:
            events.sort(key=lambda row: (row[0], row[1]))
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
    if fds_route == 'opll' and not opll_clock:
        opll_clock = 3579545
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
    target_loop_periodic = _validate_target_loop(bytes(result)) \
        if loop_address is not None else None
    summary = dict(source='nesapu', target='scc_plus_psg_noise',
        mapping_gains=dict(gains) if gains else {},
        allocation=[dict(source_channel=ch, target_chip=chip, target_channel=dest)
                    for ch, (chip, dest) in sorted(lanes.items())
                    if ch < 4 or (ch == 4 and trace.dpcm_slices)
                    or (ch == 5 and noise_scc_segments)
                    or (ch == 6 and fds_route == 'scc')
                    or (ch == 7 and fds_route == 'opll')],
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
        fds_omitted=fds_route == 'omitted',
        fds_route=fds_route,
        fds_presets={str(k): v for k, v in fds_presets.items()},
        noise_route=noise_route,
        passthrough_commands=sorted(hex(c) for c in passthrough),
        loop_validation='two-traversal comparison of analyzed source '
                          'state and projected register state',
        loop_second_traversal_differences=loop_differences,
        loop_restored_registers=loop_restored,
        target_loop_periodic=target_loop_periodic,
        limits=['a source loop whose analyzed state differs on the '
            'second traversal is recorded in '
            'loop_second_traversal_differences; the target loop '
            'repeats the first traversal, with register state restored '
            'at the loop point (loop_restored_registers)',
            'dpcm samples render as 1/60 s scc waveform slices '
            '(effective 1.92 khz resample) on scc channel 3; triggers '
            'without sample data stay omitted and are recorded',
            'fds renders on the scc waveform lane when free, else as '
            'a layered opll preset approximation chosen from the '
            'waveform spectrum; omitted only when neither is free',
            'psg noise covers apu lfsr rates within 50 cents; slower '
            'rates render as scc lfsr waveform slices (lfsr phase '
            'restarts per segment) on the spare scc waveform lane, '
            'which dpcm slices and the fds voice claim first; '
            'deferred slow noise falls '
            'back to the clamped psg rendering and is counted',
            'scc period clamped to 9..4095 with the error recorded',
            'when a source ay part owns the psg, in-range noise is '
            'omitted (recorded); out-of-range noise still renders on scc'])
    return Projection(bytes(result), allocation, controls, target_writes,
                      gates, summary)


def prepare(source, outdir, stem, *, force=False, gains=None):
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
        projected = project(raw, trace, force=force, gains=gains)
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
