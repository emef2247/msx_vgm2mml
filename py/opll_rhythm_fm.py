"""OPLL percussion events projected to OPM FM one-shot voices.

Used by the FM-only SFG01 compositions, which have no PCM lane:
the fitted tables in data/presets/sfg01/rhythm_fm_*.json hold
OPM voices fitted to reference hits with IKAOPM in the loop
(IKAOPLL library hits for the plain sfg01 profile, the owner's
RX21 recordings for sfg01_rx21; fitted 2026-11-14).  At most two
OPM channels carry rhythm, per the owner's channel budget: at
one instant the two loudest hits sound, and a hit that arrives
while both channels ring cuts the oldest tail (the PCM lane's
retrigger discipline).  Only the TOM tracks pitch, following
the source rhythm-oscillator ratio; the other families are
fixed timbres played at timing and level, as measured on
IKAOPLL.  Event level (OPLL VOL steps) shifts carrier TL by
VOL << 2, the melody lane's convention.
"""
from collections import Counter
import json
import math
from pathlib import Path

from musical_wave_target import curve_value
from opll_fm_target import _OP_FIELDS, _OPM_SLOTS
from opll_rhythm_pcm import _pitch_at
from psg_scc_opm import opm_pitch

_PRESET_DIR = Path(__file__).resolve().parent.parent / 'data' / 'presets'
_TABLES = {'opll': 'rhythm_fm_opll.json', 'rx21': 'rhythm_fm_rx21.json'}
_cache = {}
# The YM2151 noise does not decay while NE is on, so a noise hit is
# emitted as a fixed-width pulse from its onset instead of ringing
# until the next ch7 hit.  The width matches the source SD noise:
# measured on IKAOPLL (isolated SD probe taken from a real song's
# register setup), it falls to 25% of its peak at about 52 ms
# (2026-11-15).
_NOISE_PULSE_SAMPLES = int(0.052 * 44100)
# Cartridge level correction (owner's decision, 2026-11-21): on
# the real SFG-01 the fitted FM rhythm comes out far hotter than
# the melody (ear-hurting on the default export of FMPAC02), so
# the lane sits +30 carrier TL steps below the fitted level
# (0.75 dB each, about -22.5 dB) in every level mode.  SoundCore
# mode previously added this same +30 on top of the fitted level,
# so folding it into the base leaves SoundCore output unchanged.
# The fitted tables themselves keep their IKAOPLL-anchored levels.
# This value is the default of the --v-offset-opm-rhythm option.
_BASE_TL_OFFSET = 30
# Audible register slots per algorithm, measured with a
# solo-carrier probe on IKAOPM (2026-11-14).
_CARRIERS_REG = {0: {3}, 1: {3}, 2: {3}, 3: {3}, 4: {2, 3},
                 5: {1, 2, 3}, 6: {1, 2, 3}, 7: {0, 1, 2, 3}}
_FAMILY_MAP = {'BD': 'BD', 'SD': 'SD', 'HH': 'CLOSEHH', 'CYM': 'CYM'}


def _table(name):
    if name not in _cache:
        doc = json.loads((_PRESET_DIR / 'sfg01' / _TABLES[name]).read_text())
        _cache[name] = (doc, {v['name']: v for v in doc['voices']})
    return _cache[name]


def project_opll_rhythm_fm(performance, table, reserved, *, force=False,
                           soundcore_levels=False, tl_offset=_BASE_TL_OFFSET):
    """Returns (rows, losses, info)."""
    doc, voices = _table(table)
    # soundcore_levels no longer changes this lane: the cartridge
    # correction above is part of the base level (2026-11-21).
    rows, losses = [], Counter()
    devices = [d for d in performance.devices if d.chip == 'opll']
    if not devices:
        return rows, losses, {}
    device = devices[0]
    events = [e for e in performance.percussion
              if e.device_id == device.device_id]
    if len(devices) > 1 and any(e.device_id != device.device_id
                                for e in performance.percussion):
        losses['opll_rhythm_fm_second_device_omitted'] += 1
    if not events:
        return rows, losses, {}
    free = [ch for ch in range(8) if ch not in reserved]
    needs_noise = any(v['noise'] is not None for v in voices.values())
    channels = free[:2]
    if needs_noise and 7 in free and 7 not in channels:
        channels = [7] + channels[:1]
    if not channels:
        if not force:
            raise ValueError('No OPM channel available for FM rhythm; '
                             'force permits explicitly reported omission')
        losses['opll_rhythm_fm_no_channel'] += len(events)
        return rows, losses, {}
    snapshots = _pitch_at(performance, device)
    osc_ref = doc.get('tom_osc_ref_hz') or doc.get('opll_tom_osc_hz') or 42.5

    def tom_ratio(event):
        hz = None
        for sample, state in snapshots:
            if sample > event.start_sample:
                break
            hz = state.get(8, hz)
        if hz is None or hz <= 0:
            losses['opll_rhythm_fm_tom_pitch_unknown'] += 1
            return 1.0
        return hz / osc_ref

    def resolve(event):
        family = event.instrument_family
        if table == 'opll':
            return (voices.get(family), 1.0) if family in voices else (None, 1.0)
        if family == 'TOM':
            ratio = tom_ratio(event)
            anchor = doc['opll_tom_nominal_hz']
            dominant = anchor * ratio
            doms = doc['tom_dominant_hz']
            name = min(doms, key=lambda n: abs(math.log2(dominant / doms[n])))
            voice = voices[name]
            return voice, dominant / doms[name]
        name = _FAMILY_MAP.get(family)
        return (voices.get(name), 1.0) if name else (None, 1.0)

    def level_of(event):
        level = curve_value(event.volume_curve, event.start_sample)
        return 0 if level is None else max(0, min(15, int(level)))

    # Group simultaneous hits: keep the loudest per channel budget.
    by_start = {}
    for event in events:
        by_start.setdefault(event.start_sample, []).append(event)
    hits = []
    for start in sorted(by_start):
        group = sorted(by_start[start], key=level_of)
        for event in group[len(channels):]:
            losses['opll_rhythm_fm_simultaneous_omitted'] += 1
        hits.extend(group[:len(channels)])
    hits.sort(key=lambda e: e.start_sample)

    def emit(event, sample, order, register, value, reason):
        rows.append(dict(sample=sample, order=order,
                         command=bytes((0x54, register, value & 255)),
                         unit_id=event.event_id,
                         device_id=device.device_id,
                         source_indices=event.control_ids, reason=reason))

    busy = {}  # channel -> (start, end, event)
    noise_state = [None]
    noise_due = [None]  # sample at which the running noise pulse ends
    noise_event = [None]  # hit that started the running pulse

    def set_noise(event, sample, value):
        if noise_state[0] != value:
            noise_state[0] = value
            emit(event, sample, -0.7, 0x0F, value, 'OPM noise control')

    def flush_noise(upto):
        if noise_state[0] and noise_due[0] is not None \
                and noise_due[0] <= upto:
            due, on_event = noise_due[0], noise_event[0]
            noise_state[0] = 0
            noise_due[0] = None
            emit(on_event, due, -0.7, 0x0F, 0, 'OPM noise pulse end')

    for event in hits:
        flush_noise(event.start_sample)
        voice, pitch_scale = resolve(event)
        if voice is None:
            losses['opll_rhythm_fm_unsupported_family'] += 1
            continue
        start = event.start_sample
        gate = int(voice['gate_s'] * 44100)
        end = min(performance.end_sample, start + gate)
        if event.stop_sample is not None:
            end = min(end, event.stop_sample)
        level = level_of(event)
        use_noise = voice['noise'] is not None and 7 in channels
        if voice['noise'] is not None and not use_noise:
            losses['opll_rhythm_fm_noise_channel_unavailable'] += 1
        candidates = [ch for ch in channels
                      if busy.get(ch, (0, -1, None))[1] <= start]
        if not candidates:
            ch = min(channels, key=lambda c: busy[c][0])
            prev = busy[ch][2]
            emit(prev, start, -0.6, 8, ch, 'OPM rhythm tail cut')
            losses['opll_rhythm_fm_tail_cut'] += 1
        elif use_noise and 7 in candidates:
            ch = 7
        elif use_noise and 7 in channels and busy.get(7, (0, -1, None))[1] > start:
            ch = candidates[0]
            use_noise = False
            losses['opll_rhythm_fm_noise_channel_unavailable'] += 1
        else:
            ch = candidates[0]
        if ch == 7:
            if use_noise:
                set_noise(event, start, 0x80 | voice['noise'])
                noise_due[0] = start + _NOISE_PULSE_SAMPLES
                noise_event[0] = event
            else:
                set_noise(event, start, 0x00)
                noise_due[0] = None
        ops = [tuple(o[f] for f in _OP_FIELDS) for o in voice['ops']]
        carriers = {logical for logical in range(4)
                    if _OPM_SLOTS[logical] in _CARRIERS_REG[voice['alg']]}
        emit(event, start, -0.5, 0x20 + ch,
             0xC0 | (voice['fb'] << 3) | voice['alg'],
             'OPLL rhythm FM voice algorithm/feedback')
        emit(event, start, -0.5, 0x38 + ch, 0,
             'OPLL rhythm FM no LFO modulation')
        for logical, op in enumerate(ops):
            mul, tl, ks, ar, d1r, d2r, sl, rr, dt, am = op
            if logical in carriers:
                tl = max(0, min(127, tl + (level << 2) + tl_offset))
            off = _OPM_SLOTS[logical] * 8 + ch
            for base, value in ((0x40, (dt << 4) | mul), (0x60, tl),
                                (0x80, (ks << 6) | ar),
                                (0xA0, (am << 7) | d1r), (0xC0, d2r),
                                (0xE0, (sl << 4) | rr)):
                emit(event, start, -0.5, base + off, value,
                     'OPLL rhythm FM voice operator')
        if event.instrument_family == 'TOM':
            if table == 'opll':
                hz = voice['nominal_hz'] * tom_ratio(event)
            else:
                hz = voice['nominal_hz'] * pitch_scale
            kc, kf, _ = opm_pitch(hz, 3579545, clamp=True)
        else:
            kc, kf = voice['kc'], voice['kf']
        emit(event, start, -0.5, 0x28 + ch, kc, 'OPLL rhythm FM pitch')
        emit(event, start, -0.5, 0x30 + ch, kf, 'OPLL rhythm FM pitch')
        emit(event, start, 0, 8, 0x78 | ch, 'OPLL rhythm FM key on')
        # Mid-hit level curve points retune the carriers in place.
        for at, vol in event.volume_curve:
            if not start < at < end:
                continue
            vol = max(0, min(15, int(vol)))
            if vol == level:
                continue
            for logical, op in enumerate(ops):
                if logical not in carriers:
                    continue
                off = _OPM_SLOTS[logical] * 8 + ch
                emit(event, at, -0.1, 0x60 + off,
                     max(0, min(127, op[1] + (vol << 2) + tl_offset)),
                     'OPLL rhythm FM carrier level curve')
        emit(event, end, 0.5, 8, ch, 'OPLL rhythm FM key off')
        busy[ch] = (start, end, event)
    if noise_state[0] and noise_due[0] is not None:
        emit(noise_event[0], min(noise_due[0], performance.end_sample),
             -0.7, 0x0F, 0, 'OPM noise pulse end')
    return rows, losses, {'channels': channels, 'table': table}
