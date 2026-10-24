"""Conservative percussion hypotheses from retained PSG/SCC control curves.

These are inferred gestures, never source Key-On facts. No native Segment is
changed, and rejected gestures stay in the catalog. Thresholds are experimental
classification choices rather than chip specifications.
"""
from dataclasses import dataclass
from functools import lru_cache
import math


@dataclass(frozen=True)
class DrumCandidate:
    candidate_id: str
    chip: str
    channel: int
    segment_indices: tuple
    source_sample: int | None
    source_end: int | None
    tick_start: int
    tick_end: int
    instrument: str | None
    volume: int
    reasons: tuple
    features: tuple


def _duration(row):
    if row.vgmticks is None or row.vgmticks_end is None:
        return None
    return row.vgmticks_end - row.vgmticks


def _units(rows, indices):
    """Keep same-sample setup writes with their effective sounding state."""
    units = []
    for index in indices:
        row = rows[index]
        key = ('sample', row.vgmticks) if row.vgmticks is not None else ('tick', row.ticks)
        if not units or units[-1][0] != key:
            units.append((key, []))
        units[-1][1].append(index)
    return [indices for _, indices in units]


def _chunks(rows, gate, chip):
    active, previous, previous_sounded = [], None, False
    boundary = 'source_audibility_gate'
    for unit in _units(rows, gate.segment_indices):
        positive = [rows[i] for i in unit if (_duration(rows[i]) or 0) > 0 or rows[i].l > 0]
        effective = positive[-1] if positive else rows[unit[-1]]
        trigger = None
        if previous is not None and previous_sounded and positive:
            if effective.volume >= previous.volume + 3:
                trigger = 'strong_volume_rise'
            elif chip == 'psg' and effective.envelope_enabled and any(rows[i].ev_type == 'evS' for i in unit):
                trigger = 'hardware_envelope_reset'
            elif chip == 'psg' and effective.mode & 2 and not previous.mode & 2:
                trigger = 'transition_into_noise'
        if trigger and active:
            yield tuple(active), boundary
            active = []
            boundary = trigger
        active.extend(unit)
        if positive:
            previous = effective
            previous_sounded = True
    if active:
        yield tuple(active), boundary


@lru_cache(maxsize=1024)
def _spectrum(waveform_hex):
    """Return AC spectral flatness/high-band energy for the native 32 samples."""
    try:
        raw = bytes.fromhex(waveform_hex)
    except (TypeError, ValueError):
        return None
    if len(raw) != 32:
        return None
    values = [value if value < 128 else value - 256 for value in raw]
    mean = sum(values) / 32
    values = [value - mean for value in values]
    powers = []
    for harmonic in range(1, 17):
        real = sum(value * math.cos(2 * math.pi * harmonic * i / 32) for i, value in enumerate(values))
        imag = sum(value * math.sin(2 * math.pi * harmonic * i / 32) for i, value in enumerate(values))
        powers.append(real * real + imag * imag)
    total = sum(powers)
    if total <= 1e-12:
        return (0.0, 0.0)
    floor = total * 1e-12
    flatness = math.exp(sum(math.log(max(power, floor)) for power in powers) / 16) / (total / 16)
    return flatness, sum(powers[7:]) / total


def _classify(rows, indices, chip, boundary, candidate_id, channel):
    selected = [rows[i] for i in indices]
    sounding = [row for row in selected if (_duration(row) or 0) > 0 or row.l > 0]
    first, last = selected[0], selected[-1]
    known = all(row.vgmticks is not None and row.vgmticks_end is not None for row in selected)
    start, end = first.vgmticks, last.vgmticks_end
    duration_ms = (end - start) * 1000 / 44100 if known else None
    peak = max((row.volume for row in sounding), default=0)
    tail = sounding[-1].volume if sounding else 0
    decay = peak - tail
    periods = [row.tone_period for row in sounding if row.tone_period > 0]
    sweep = (12 * math.log2(periods[-1] / periods[0])) if len(periods) >= 2 else 0.0
    # Reject a bounced/vibrato contour, even if its last period is lower pitched.
    downward = sweep >= 3 and all(b >= a for a, b in zip(periods, periods[1:]))
    noise = chip == 'psg' and any(row.mode & 2 for row in sounding)
    tonal = chip != 'psg' or any(row.mode & 1 for row in sounding)
    hardware_envelope = chip == 'psg' and any(row.envelope_enabled for row in sounding)
    reasons = [boundary, 'heuristic_not_source_key_on']
    features = [('duration_ms', duration_ms), ('peak_volume', peak), ('tail_volume', tail),
                ('decay', decay), ('downward_semitones', sweep), ('noise', bool(noise))]
    broad = False
    if chip == 'scc':
        spectra = [(_spectrum(row.waveform_hex), _duration(row)) for row in sounding]
        valid = [(spectrum, duration) for spectrum, duration in spectra if spectrum is not None and duration is not None and duration > 0]
        total = sum(duration for _, duration in valid)
        broadband = sum(duration for (flatness, high), duration in valid if flatness >= .25 and high >= .30)
        broad = bool(total and broadband * 2 >= total and len(valid) == len(sounding))
        features.extend([('broadband_fraction', broadband / total if total else None),
                         ('spectral_flatness_max', max((s[0] for s, _ in valid), default=None)),
                         ('highband_fraction_max', max((s[1] for s, _ in valid), default=None))])
    instrument = None
    if not known:
        reasons.append('unknown_source_sample_timing')
    elif not sounding or duration_ms <= 0:
        reasons.append('no_positive_source_duration')
    elif any(_duration(row) is not None and _duration(row) < 0 for row in selected):
        reasons.append('invalid_source_duration')
    elif duration_ms > 350:
        reasons.append('gesture_exceeds_350ms')
    elif tonal and not hardware_envelope and downward and decay >= 3 and duration_ms <= 250:
        instrument = 'BD' if periods[-1] >= 512 else 'TOM'
        reasons.append('downward_pitch_sweep_with_decay')
    elif noise:
        instrument = 'HH' if duration_ms <= 80 else 'SD' if duration_ms <= 220 else 'CYM'
        reasons.append('short_psg_noise_gesture')
    elif chip == 'scc' and broad and decay >= 3:
        instrument = 'HH' if duration_ms <= 80 else 'SD' if duration_ms <= 220 else 'CYM'
        reasons.append('broadband_scc_waveform_with_decay')
    else:
        reasons.append('insufficient_percussion_evidence')
    if hardware_envelope:
        reasons.append('hardware_envelope_curve_not_observed_as_fixed_volume')
    return DrumCandidate(candidate_id, chip, channel, indices, start, end,
                         first.ticks, last.ticks + last.l, instrument,
                         max(1, min(15, round(peak * 2 / 3))), tuple(reasons), tuple(features))


def infer(performances):
    """Catalog accepted and rejected gestures from PSG/SCC PerformanceIRs.

    Native clocks and controls remain untouched. Input order, gate order and
    source Segment lineage determine deterministic IDs; no channel is reserved
    as a percussion channel and no fixture identity participates in inference.
    """
    candidates = []
    for performance in performances:
        if performance.chip not in ('psg', 'scc'):
            raise ValueError('Percussion inference supports PSG/SCC PerformanceIR only')
        native = dict(performance.source_segments)
        for gate in performance.gates:
            rows = native[gate.channel]
            for indices, boundary in _chunks(rows, gate, performance.chip):
                candidate_id = f'{performance.chip}:{gate.channel}:drum{len(candidates)}'
                candidates.append(_classify(rows, indices, performance.chip, boundary,
                                            candidate_id, gate.channel))
    return tuple(candidates)
