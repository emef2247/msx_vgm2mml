"""Mode-aware HuC target adapter, independent of immutable source evidence.

SCC RAM, the shared AY noise generator and OPLL ROM presets are explicit target
resources. Allocation stays stable for each source channel/mode for the song.
"""
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct

from huc6280 import attenuation_levels
from huc6280_projection import (Projection, ProjectionError, TARGET_CLOCK,
    PSG_RELATIVE_GAIN, _gain, _pitch, _validate_loop, _validate_target_loop, square_wave)
from vgm_loop import read_loop_metadata
from vgm_timing import command_times

OPLL_CLOCK = 3579545


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'data/huc_opll_presets.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=256)
def fit_preset(wave):
    """Fit normalized harmonics, never source phase or an imagined FM patch."""
    mean = sum(wave) / 32
    harmonics = [abs(sum((value - mean) * complex(math.cos(-2 * math.pi * h * i / 32),
        math.sin(-2 * math.pi * h * i / 32)) for i, value in enumerate(wave))) for h in range(1, 17)]
    norm = math.sqrt(sum(value * value for value in harmonics))
    target = [value / norm if norm else 0 for value in harmonics]
    candidates = []
    for row in catalog()['presets']:
        # Decaying ROM instruments are poor held-wave substitutes even when
        # their initial spectrum matches. No fabricated periodic retriggers.
        if min(p['sustain_ratio'] for p in row['profiles']) < .65:continue
        error = sum(sum((a - b) ** 2 for a, b in zip(target, p['harmonics']))
                    for p in row['profiles']) / len(row['profiles'])
        candidates.append((error, row['preset']))
    if not candidates:raise ProjectionError('OPLL catalog has no sustained ROM preset')
    error, preset = min(candidates)
    return preset, error, mean - 16


def noise_pitch(clock, control):
    # Pinned c6280_mame: step=(clock/rate)*32/(32-low5), threshold0x800.
    source = clock / (64 * (32 - (control & 31)))
    period = min(31, max(1, round(TARGET_CLOCK / (16 * source))))
    return period, source, TARGET_CLOCK / (16 * period)


def opll_best(hz):
    candidates = []
    for block in range(8):
        fnum = min(511, max(1, round(hz * 72 * 2 ** 19 / (OPLL_CLOCK * 2 ** block))))
        target = OPLL_CLOCK * fnum * 2 ** block / (72 * 2 ** 19)
        candidates.append((abs(math.log2(target / hz)), block, fnum, target))
    _, block, fnum, target = min(candidates)
    return (block << 9) | fnum, target, abs(1200 * math.log2(target / hz))


def opll_pitch(hz):
    # Out-of-range pitches clamp to the nearest representable OPLL pitch;
    # the error stays visible in the controls CSV pitch_error_cents.
    period, target, _ = opll_best(hz)
    return period, target


def _compatible_pair(trace, a, b):
    left = [s for s in trace.segments if s.channel == a and s.active and s.state.mode == 'wave']
    right = [s for s in trace.segments if s.channel == b and s.active and s.state.mode == 'wave']
    i = j = 0
    while i < len(left) and j < len(right):
        x, y = left[i], right[j]
        if max(x.start_vgmticks, y.start_vgmticks) < min(x.end_vgmticks, y.end_vgmticks) and x.waveform != y.waveform:
            return False
        if x.end_vgmticks <= y.end_vgmticks:i += 1
        else:j += 1
    return True


def allocate(trace):
    waves, noises, periods = {}, set(), {}
    for segment in trace.segments:
        if not segment.active:continue
        state = segment.state
        if state.mode == 'dda' or segment.lfo_control & 3:
            raise ProjectionError('HuC6280 DDA/LFO is preserved in native VGM; no MGSDRV projection is defined')
        if state.mode == 'noise':noises.add(segment.channel);continue
        if not state.waveform_complete:
            raise ProjectionError('HuC6280 audible waveform RAM is not fully observed')
        waves.setdefault(segment.channel, set()).add(state.waveform)
        periods.setdefault(segment.channel, set()).add(state.period)
    # Even muted enabled oscillators advance their write cursor. The target
    # adapter cannot safely turn such writes into a disabled whole-RAM upload.
    for event in trace.states:
        if event.write.register == 6 and event.selected_channel < 6:
            state = event.channels[event.selected_channel]
            if state.enabled and not state.dda_mode:
                raise ProjectionError('HuC6280 enabled waveform RAM writes require a phase-aware target projection')
    channels = sorted(waves)
    # A voice OPLL can only reproduce with a large pitch error prefers an
    # SCC/PSG home when that home's clamped error is smaller.
    def scc_error(hz):
        register = min(4095, max(9, round(2 * TARGET_CLOCK / (32 * hz)) - 1))
        return abs(1200 * math.log2((2 * TARGET_CLOCK / (32 * (register + 1))) / hz))
    prefer_analog = set()
    for ch in channels:
        for p in periods.get(ch, ()):
            hz = trace.clock_hz / (32 * (p or 4096))
            error = opll_best(hz)[2]
            if error > 100 and scc_error(hz) < error:prefer_analog.add(ch)
    noise_routes = {(ch, 'noise'): ('psg', i) for i, ch in enumerate(sorted(noises))}
    for count in range(min(5, len(channels)), -1, -1):
        combos = sorted(itertools.combinations(channels, count),
                        key=lambda sel: (-sum(ch in prefer_analog for ch in sel), sel))
        for selected in combos:
            ordered = list(selected)
            if count == 5:
                pair = next(((a, b) for a, b in itertools.combinations(selected, 2)
                             if _compatible_pair(trace, a, b)), None)
                if pair is None:continue
                ordered = [ch for ch in selected if ch not in pair] + list(pair)
            spill = [ch for ch in channels if ch not in selected]
            square = sorted((ch for ch in spill if all(square_wave(w) for w in waves[ch])),
                            key=lambda ch: (ch not in prefer_analog, ch))[:3 - len(noises)]
            fm = [ch for ch in spill if ch not in square]
            routes = {**noise_routes, **{(ch, 'wave'): ('scc', i) for i, ch in enumerate(ordered)},
                **{(ch, 'wave'): ('psg', len(noises) + i) for i, ch in enumerate(square)},
                **{(ch, 'wave'): ('opll', i) for i, ch in enumerate(fm)}}
            return routes
    raise ProjectionError('HuC6280 target resources cannot be allocated')


def _opll_gain(state, mono, preset, hz):
    mean = sum(state.waveform) / 32
    rms = math.sqrt(sum(((x - mean) * 8) ** 2 for x in state.waveform) / 32)
    desired = rms * catalog()['scc_rms_per_wave_unit'] * mono
    row = next(p for p in catalog()['presets'] if p['preset'] == preset)
    profile = min(row['profiles'], key=lambda p: abs(math.log2(hz / p['frequency_hz'])))
    base = profile['late_rms']
    values = [base * 10 ** (-attenuation * 3 / 20) for attenuation in range(16)]
    # OPLL attenuation15 is not silence. Key-off is needed for near-zero gain.
    attenuation = min(range(16), key=lambda i: abs(values[i] - desired))
    audible = desired >= values[15] / 2
    return attenuation, audible, desired, values[attenuation] if audible else 0


def project_extended(raw, trace):
    if trace.issues:raise ProjectionError('HuC6280 source issues: ' + ', '.join(trace.issues))
    commands = list(command_times(raw))
    allowed = {0xb9, 0x61, 0x62, 0x63, 0x64, 0x66, *range(0x70, 0x80)}
    if any(c.command not in allowed for c in commands):
        raise ProjectionError('HuC6280 hybrid route cannot silently omit mixed/unsupported commands')
    if any(s.active and (s.state.mode == 'dda' or s.lfo_control & 3) for s in trace.segments):
        raise ProjectionError('HuC6280 DDA/LFO is preserved in native VGM; no MGSDRV projection is defined')
    loop = read_loop_metadata(raw)
    if loop['loop_address'] is not None:
        if loop['status'] != 'valid':raise ProjectionError('HuC6280 source loop is not a valid command boundary')
        _validate_loop(raw, trace, commands, loop)
    routes = allocate(trace)
    events = {event.write.source_event_id: event for event in trace.states}
    body, writes, controls, gates = bytearray(), [], [], []
    loaded, cache, starts, opll_periods = {}, {}, {}, {}
    enable, mixer, loop_address, current_event = 0, 63, None, None
    noise_loaded, shared_restorations = None, 0
    noise_since, noise_conflicts, open_conflict = {}, [], None
    fits = {}

    def emit(command, tick=0, source_id=None):
        writes.append(dict(source_event_id=source_id, vgmticks=tick,
            target_address=256 + len(body), command_hex=command.hex()))
        body.extend(command)

    def scc(port, register, value, tick, source_id):
        emit(bytes((0xd2, port, register, value & 255)), tick, source_id)

    emit(bytes((0xa0, 7, mixer)))
    for dest in range(3):emit(bytes((0xa0, 8 + dest, 0)))
    scc(3, 0, 0, 0, None)
    for source_id, command in enumerate(commands):
        tick = command.vgmticks
        if command.address == loop['loop_address']:loop_address = 256 + len(body)
        if command.command == 0xb9:
            event = current_event = events[source_id]
            def route_order(item):
                (channel, mode), _ = item
                state = event.channels[channel]
                return (state.mode == mode and state.enabled, channel, mode)
            for route, (chip, dest) in sorted(routes.items(), key=route_order):
                channel, mode = route
                state = event.channels[channel]
                source_active = state.enabled and min(attenuation_levels(state.control, state.balance, event.global_balance)) < 31
                active = source_active and state.mode == mode
                if active and mode == 'wave' and not state.waveform_complete:continue
                previous = cache.get(route)
                affected = event.write.register == 1 or (event.selected_channel == channel and event.write.register in (2, 3, 4, 5, 6, 7))
                replay = loop_address is not None and affected
                level, left, right, mono, gain = _gain(state, event.global_balance, 'scc')
                period = source_hz = target_hz = preset = error = dc = 0
                attenuation, target_active, target_gain = 15, active, gain
                if active:
                    if mode == 'noise':
                        period, source_hz, target_hz = noise_pitch(trace.clock_hz, state.noise_control)
                        values = [0] + [10 ** ((n - 15) * 3 / 20) for n in range(1, 16)]
                        level = min(range(16), key=lambda i: abs(values[i] - mono * PSG_RELATIVE_GAIN))
                        target_gain = values[level]
                    elif chip == 'opll':
                        source_hz = trace.clock_hz / (32 * (state.period or 4096))
                        period, target_hz = opll_pitch(source_hz)
                        preset, error, dc = fit_preset(state.waveform)
                        attenuation, target_active, _, target_gain = _opll_gain(state, mono, preset, source_hz)
                        fits[state.waveform_id] = dict(waveform_id=state.waveform_id, preset=preset,
                            harmonic_error=error, removed_dc_u5=dc)
                    else:
                        period, source_hz, target_hz = _pitch(trace.clock_hz, state.period, chip)
                        level, left, right, mono, target_gain = _gain(state, event.global_balance, chip)
                key = (active, period, level, state.waveform if active and mode == 'wave' else None,
                       preset, attenuation, target_active)
                if key == previous and not replay:continue
                cache[route] = key
                if active and route not in starts:starts[route] = (tick, source_id)
                if not active and route in starts:
                    start, start_id = starts.pop(route)
                    gates.append(dict(source_channel=channel, source_mode=mode, start_vgmticks=start,
                        end_vgmticks=tick, start_source_event_id=start_id, end_source_event_id=source_id))
                if chip == 'scc':
                    if active:
                        slot = min(dest, 3)
                        wave = tuple((n - 16) * 8 for n in state.waveform)
                        if loaded.get(slot) != wave or replay and event.write.register in (1, 4, 5, 6):
                            for i, value in enumerate(wave):scc(0, slot * 32 + i, value, tick, source_id)
                            loaded[slot] = wave
                        if replay or previous is None or previous[:2] != key[:2]:
                            scc(1, dest * 2, period & 255, tick, source_id)
                            scc(1, dest * 2 + 1, period >> 8, tick, source_id)
                    scc(2, dest, level if active else 0, tick, source_id)
                    enable = enable | (1 << dest) if active else enable & ~(1 << dest)
                    scc(3, 0, enable, tick, source_id)
                elif chip == 'psg':
                    if active:
                        if mode == 'noise':
                            emit(bytes((0xa0, 6, period)), tick, source_id)
                            noise_loaded = period
                        else:
                            emit(bytes((0xa0, dest * 2, period & 255)), tick, source_id)
                            emit(bytes((0xa0, dest * 2 + 1, period >> 8)), tick, source_id)
                    emit(bytes((0xa0, 8 + dest, level if active else 0)), tick, source_id)
                    tone, noise = 1 << dest, 1 << (dest + 3)
                    mixer |= tone | noise
                    if active:mixer &= ~(noise if mode == 'noise' else tone)
                    emit(bytes((0xa0, 7, mixer)), tick, source_id)
                else:
                    if active:
                        emit(bytes((0x51, 0x30 + dest, (preset << 4) | attenuation)), tick, source_id)
                        emit(bytes((0x51, 0x10 + dest, period & 255)), tick, source_id)
                        opll_periods[dest] = period
                    # Key-off releases the existing voice; changing its pitch
                    # here would transpose the still-audible FM release tail.
                    release_period = opll_periods.get(dest, 0)
                    high = ((release_period >> 8) & 15) | 0x20 | (0x10 if target_active else 0)
                    emit(bytes((0x51, 0x20 + dest, high)), tick, source_id)
                controls.append(dict(source_event_id=source_id, vgmticks=tick, source_channel=channel,
                    source_mode=mode, target_chip=chip, target_channel=dest, source_period=state.period,
                    target_period=period, source_hz=source_hz, target_hz=target_hz,
                    pitch_error_cents=1200 * math.log2(target_hz / source_hz) if active else 0,
                    attenuation_left=left, attenuation_right=right, mono_gain=mono,
                    target_volume=15 - attenuation if chip == 'opll' else level if active else 0,
                    target_gain=target_gain if target_active else 0, enabled=active,
                    waveform_id=state.waveform_id, quiet_rounded_to_zero=active and
                    (not target_active if chip == 'opll' else not level),
                    opll_preset=preset, harmonic_error=error))
        elif command.wait_samples:
            if current_event:
                # The AY noise generator is shared. The first audibly
                # demanding channel owns its rate; a later channel with a
                # different rate still sounds, at the owner's rate, and the
                # conflict window is recorded instead of failing the song.
                demands = {channel: noise_pitch(trace.clock_hz, state.noise_control)[0]
                    for channel, state in enumerate(current_event.channels)
                    if channel >= 4 and state.mode == 'noise' and
                    min(attenuation_levels(state.control, state.balance, current_event.global_balance)) < 31}
                for channel in demands:noise_since.setdefault(channel, tick)
                for channel in list(noise_since):
                    if channel not in demands:del noise_since[channel]
                if demands:
                    owner = min(demands, key=lambda ch: (noise_since[ch], ch))
                    chosen = demands[owner]
                    if len(set(demands.values())) > 1:
                        if open_conflict is None:
                            open_conflict = dict(start_vgmticks=tick, end_vgmticks=None,
                                owner_channel=owner, demanded_periods=dict(demands),
                                chosen_period=chosen)
                            noise_conflicts.append(open_conflict)
                    elif open_conflict is not None:
                        open_conflict['end_vgmticks'] = tick;open_conflict = None
                    # A zero-time owner may have touched a shared register/RAM
                    # and released it again. Reconcile the final positive-time
                    # demand, not only each route's unchanged cache key.
                    if noise_loaded != chosen:
                        if noise_loaded is not None:shared_restorations += 1
                        noise_loaded = chosen
                        emit(bytes((0xa0, 6, noise_loaded)), tick, current_event.write.source_event_id)
                elif open_conflict is not None:
                    open_conflict['end_vgmticks'] = tick;open_conflict = None
                for (channel, mode), (chip, dest) in routes.items():
                    state = current_event.channels[channel]
                    if chip != 'scc' or state.mode != mode or not state.enabled or min(attenuation_levels(
                            state.control, state.balance, current_event.global_balance)) == 31:continue
                    wave = tuple((n - 16) * 8 for n in state.waveform)
                    slot = min(dest, 3)
                    if loaded.get(slot) != wave:
                        for i, value in enumerate(wave):scc(0, slot * 32 + i, value, tick, current_event.write.source_event_id)
                        loaded[slot] = wave
                        shared_restorations += 1
            remaining = command.wait_samples
            while remaining:
                length = min(remaining, 65535);body.extend(b'\x61' + struct.pack('<H', length));remaining -= length
        elif command.command == 0x66:body.append(0x66)
    if open_conflict is not None:open_conflict['end_vgmticks'] = trace.source_end_vgmticks
    for (channel, mode), (start, source_id) in starts.items():
        gates.append(dict(source_channel=channel, source_mode=mode, start_vgmticks=start,
            end_vgmticks=trace.source_end_vgmticks, start_source_event_id=source_id, end_source_event_id=None))
    header = bytearray(256);header[:4] = b'Vgm '
    for offset, value in ((8, 0x171), (0x34, 256 - 0x34), (0x18, trace.source_end_vgmticks),
                          (0x74, TARGET_CLOCK), (0x9c, TARGET_CLOCK),
                          (0x10, OPLL_CLOCK if any(chip == 'opll' for chip, _ in routes.values()) else 0)):
        struct.pack_into('<I', header, offset, value)
    header[0x78] = 0x10
    if loop_address is not None:
        struct.pack_into('<I', header, 0x1c, loop_address - 0x1c)
        struct.pack_into('<I', header, 0x20, trace.source_end_vgmticks - loop['loop_start_samples'])
    result = header + body
    gd3 = int.from_bytes(raw[0x14:0x18], 'little')
    if gd3:
        start = 0x14 + gd3
        if raw[start:start + 4] == b'Gd3 ' and start + 12 <= len(raw):
            end = start + 12 + int.from_bytes(raw[start + 8:start + 12], 'little')
            if end > len(raw):raise ProjectionError('Truncated source GD3 metadata')
            struct.pack_into('<I', result, 0x14, len(result) - 0x14);result.extend(raw[start:end])
    struct.pack_into('<I', result, 4, len(result) - 4)
    _validate_target_loop(bytes(result))
    allocation = [dict(source_channel=ch, source_mode=mode, source_device='huc6280:0',
        target_chip=chip, target_channel=dest) for (ch, mode), (chip, dest) in sorted(routes.items())]
    summary = dict(source='huc6280', target='ordinary_scc_psg_opll', allocation=allocation,
        source_sha256=hashlib.sha256(raw).hexdigest(), target_sha256=hashlib.sha256(result).hexdigest(),
        source_end_vgmticks=trace.source_end_vgmticks, target_clock_hz=TARGET_CLOCK,
        source_channels=len({ch for ch, _ in routes}),
        **{chip + '_channels': sum(c == chip for c, _ in routes.values()) for chip in ('scc', 'psg', 'opll')},
        waveform_fits=list(fits.values()), noise_rate_policy='nearest AY shift rate; shared generator; first audible channel owns the rate during a conflict and the other channel sounds at that rate; conflict windows are recorded; spectrum differs',
        noise_rate_conflicts=noise_conflicts,
        shared_resource_restorations=shared_restorations,
        gain_policy='SCC/PSG fixed gain; OPLL nearest 3dB attenuation using pinned reference RMS',
        loop_validation='source and target repeated traversal' if loop_address else 'no declared loop',
        limits=['OPLL is a harmonic-amplitude approximation, not waveform/phase equivalence',
                'noise sequence and stereo fold differ', 'DDA/LFO remain native VGM only',
                'enabled waveform writes and mixed-chip MGS lowering remain unsupported'])
    return Projection(bytes(result), routes, controls, writes, gates, summary)
