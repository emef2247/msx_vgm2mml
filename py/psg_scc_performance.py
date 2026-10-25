"""Lossless Segment lineage and inferred PSG/SCC performance partitions.

Audibility gates are not observed Key-Ons. Score partitions deliberately retain
the established renderer policy; sub-tick source silence can therefore separate
two gates inside one score partition. Source samples and clock-tagged ticks never
substitute for each other. This representation does not reconstruct raw VGM.
"""
import csv
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path


def audible(segment, chip):
    if segment.scale == 'r':
        return False
    if chip == 'psg':
        return bool(segment.mode and (segment.volume or segment.envelope_enabled))
    return bool(segment.enabled and segment.volume)


def settings(segment, chip):
    pitch = (segment.tone_period, segment.octave, segment.scale)
    if chip == 'scc':
        return pitch + (segment.waveform_id, segment.enabled)
    return pitch + (segment.mode, segment.noise_period if segment.mode & 2 else 0,
                    segment.envelope_enabled,
                    segment.envelope_period if segment.envelope_enabled else 0,
                    segment.envelope_shape if segment.envelope_enabled else 0)


@dataclass(frozen=True)
class ScoreNote:
    segment: object
    start: int
    length: int
    rest: bool
    runs: tuple
    segment_indices: tuple
    gate_ids: tuple
    boundary_reasons: tuple
    chip: str

    @property
    def structural_key(self):
        return (self.length, self.rest, () if self.rest else settings(self.segment, self.chip),
                self.runs)

    def structural_equality_key(self):
        return self.structural_key

    @property
    def gate_ambiguity(self):
        return len(self.gate_ids) > 1


@dataclass(frozen=True)
class SoundGate:
    gate_id: str
    chip: str
    channel: int
    segment_indices: tuple
    source_sample_start: int | None
    source_sample_end: int | None
    tick_start: int
    tick_end: int
    boundary_reason: str
    # Explicitly interpreted from state; neither an observed nor invented Key-On.
    interpretation: str = 'source_audibility'


@dataclass(frozen=True)
class ControlPoint:
    chip: str
    channel: int
    segment_index: int
    source_event: str
    kind: str
    native_value: tuple
    source_sample: int | None
    relative_source_sample: int | None
    tick: int
    relative_tick: int | None
    gate_id: str | None


@dataclass(frozen=True)
class Boundary:
    chip: str
    channel: int
    segment_index: int
    source_sample: int | None
    tick: int
    reasons: tuple
    interpretation: str = 'inferred_score_partition'


@dataclass(frozen=True)
class PerformanceIR:
    chip: str
    source_segments: tuple
    channels: tuple
    gates: tuple
    controls: tuple
    boundaries: tuple
    tick_clock_hz: int = 60

    def to_notes(self, note_type):
        """Adapt immutable partitions to the existing mutable renderer Note."""
        return {ch: [note_type(n.segment, n.start, n.length, n.rest,
                              runs=list(n.runs), segment_indices=list(n.segment_indices))
                     for n in notes] for ch, notes in self.channels}

    def reconstruct_segments(self):
        """Recover every input Segment in channel/row order, including zero rows."""
        return {ch: list(rows) for ch, rows in self.source_segments}

    def validate(self, segments=None):
        """Check retained native Segment order/state, not raw-register replay."""
        if segments is not None:
            if tuple((ch, tuple(rows)) for ch, rows in segments.items()) != self.source_segments:
                raise ValueError('Retained native Segment order/state differs')
        native = dict(self.source_segments)
        gates = {g.gate_id: g for g in self.gates}
        for ch, notes in self.channels:
            for note in notes:
                if sum(native[ch][i].l for i in note.segment_indices) != note.length:
                    raise ValueError('Score partition length differs from Segment lineage')
                if any(g not in gates for g in note.gate_ids):
                    raise ValueError('Unknown gate lineage')
        expected = [(ch, i) for ch, rows in self.source_segments for i in range(len(rows))]
        observed = list(dict.fromkeys((p.channel, p.segment_index) for p in self.controls))
        if observed != expected:
            raise ValueError('Control curves omit or reorder a native Segment')
        return True


def _source_duration(segment):
    start, end = segment.vgmticks, segment.vgmticks_end
    return None if start is None or end is None else end - start


def _gates(rows, chip, channel):
    gates, active = [], []
    reason = 'initial_audibility'

    def finish():
        if not active:
            return
        first, last = rows[active[0]], rows[active[-1]]
        gates.append(SoundGate(f'{chip}:{channel}:gate{len(gates)}', chip, channel,
                               tuple(active), first.vgmticks, last.vgmticks_end,
                               first.ticks, last.ticks + last.l, reason))
        active.clear()

    for index, seg in enumerate(rows):
        if not audible(seg, chip):
            duration = _source_duration(seg)
            # Known positive source silence matters even when rounded to zero ticks.
            if (duration is not None and duration > 0) or (duration is None and seg.l > 0):
                finish()
                reason = 'audibility_after_silence'
            continue
        if active:
            previous = rows[active[-1]]
            if (previous.vgmticks_end is not None and seg.vgmticks is not None
                    and seg.vgmticks > previous.vgmticks_end):
                finish()
                reason = 'audibility_after_source_gap'
            elif ((previous.vgmticks_end is None or seg.vgmticks is None)
                  and seg.ticks > previous.ticks + previous.l):
                finish()
                reason = 'audibility_after_tick_gap'
        active.append(index)
    finish()
    return gates


def _notes(rows, chip, channel, gates):
    """Exactly the existing extract_notes partition policy, with reasons."""
    notes, boundaries = [], []
    pitch_events = {'fCA', 'fCB'} if chip == 'psg' else {'f1Ctrl', 'f2Ctrl'}
    pending = []
    for index, seg in enumerate(rows):
        if seg.ev_type in pitch_events:
            pending.append('pitch_write')
        if chip == 'psg' and seg.ev_type == 'evS':
            pending.append('hardware_envelope_reset')
        if seg.l <= 0:
            continue
        rest = not audible(seg, chip)
        previous = notes[-1] if notes else None
        contiguous = previous is not None and previous['start'] + previous['length'] == seg.ticks
        same = contiguous and previous['rest'] == rest
        reasons = []
        if previous is None:
            reasons.append('initial_partition')
        elif not contiguous:
            reasons.append('tick_discontinuity')
        elif previous['rest'] != rest:
            reasons.append('audibility_transition')
        if same and not rest:
            reasons.extend(pending)
            if settings(previous['segment'], chip) != settings(seg, chip):
                reasons.append('settings_change')
            if seg.volume > previous['runs'][-1][0]:
                reasons.append('volume_rise')
            same = not reasons
        if not same:
            reasons = tuple(dict.fromkeys(reasons + pending))
            boundaries.append(Boundary(chip, channel, index, seg.vgmticks, seg.ticks, reasons))
            notes.append(dict(segment=seg, start=seg.ticks, length=0, rest=rest,
                              runs=[], segment_indices=[], boundary_reasons=reasons))
        note = notes[-1]
        note['segment_indices'].append(index)
        note['length'] += seg.l
        if not rest:
            if note['runs'] and note['runs'][-1][0] == seg.volume:
                volume, length = note['runs'][-1]
                note['runs'][-1] = (volume, length + seg.l)
            else:
                note['runs'].append((seg.volume, seg.l))
        pending.clear()
    result = []
    gate_by_index = {i: g.gate_id for g in gates for i in g.segment_indices}
    for note in notes:
        indices = tuple(note.pop('segment_indices'))
        gate_ids = tuple(dict.fromkeys(gate_by_index[i] for i in indices if i in gate_by_index))
        result.append(ScoreNote(**{**note, 'runs': tuple(note['runs'])},
                                segment_indices=indices, gate_ids=gate_ids, chip=chip))
    return result if any(not n.rest for n in result) else [], boundaries


def _values(seg, chip):
    yield 'pitch', (('tone_period', seg.tone_period), ('octave', seg.octave), ('scale', seg.scale))
    yield 'volume', (('volume', seg.volume), ('volume_delta', seg.volume_delta))
    if chip == 'scc':
        yield 'timbre', (('waveform_id', seg.waveform_id), ('waveform_hex', seg.waveform_hex))
        yield 'mode_noise', (('enabled', seg.enabled), ('enable_register', seg.enable_register))
    else:
        yield 'mode_noise', (('mode', seg.mode), ('noise_period', seg.noise_period), ('mixer', seg.mixer))
        yield 'hardware_envelope', (('enabled', seg.envelope_enabled),
                                   ('period', seg.envelope_period), ('shape', seg.envelope_shape),
                                   ('amplitude_register', seg.amplitude_register),
                                   ('reset_event', seg.ev_type == 'evS'))


def analyze(segments, chip, *, tick_clock_hz=60):
    """Separate audibility, renderer partitions and complete ordered control state."""
    if not isinstance(tick_clock_hz, int) or tick_clock_hz <= 0:
        raise ValueError('Performance tick clock must be a positive integer')
    if chip not in ('psg', 'scc'):
        raise ValueError('Performance analysis supports PSG and SCC only')
    native = tuple((ch, tuple(rows)) for ch, rows in segments.items())
    channels, gates, controls, boundaries = [], [], [], []
    for ch, rows in native:
        local_gates = _gates(rows, chip, ch)
        gates.extend(local_gates)
        notes, local_boundaries = _notes(rows, chip, ch, local_gates)
        if notes:
            channels.append((ch, tuple(notes)))
        boundaries.extend(local_boundaries)
        gate_by_index = {i: g for g in local_gates for i in g.segment_indices}
        for index, seg in enumerate(rows):
            gate = gate_by_index.get(index)
            relative = (None if gate is None or gate.source_sample_start is None or seg.vgmticks is None
                        else seg.vgmticks - gate.source_sample_start)
            for kind, value in _values(seg, chip):
                controls.append(ControlPoint(chip, ch, index, seg.ev_type, kind, value,
                                             seg.vgmticks, relative, seg.ticks,
                                             None if gate is None else seg.ticks - gate.tick_start,
                                             None if gate is None else gate.gate_id))
    result = PerformanceIR(chip, native, tuple(channels), tuple(gates), tuple(controls), tuple(boundaries), tick_clock_hz)
    result.validate(segments)
    return result


def dump(performance, prefix):
    """Dump source-preserving state and explicitly inferred partitions separately."""
    prefix = str(prefix)
    Path(prefix).parent.mkdir(parents=True, exist_ok=True)

    def write(suffix, fields, rows):
        path = prefix + '.performance.' + suffix + '.csv'
        with open(path, 'w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (tuple, list, dict))
                                 else v for k, v in row.items()})

    note_rows = []
    for ch, notes in performance.channels:
        for index, n in enumerate(notes):
            source = dict(performance.source_segments)[ch]
            note_rows.append(dict(chip=performance.chip, channel=ch, note_id=f'{ch}:{index}',
                                  tick_start=n.start, tick_end=n.start + n.length, rest=n.rest,
                                  source_sample_start=source[n.segment_indices[0]].vgmticks,
                                  source_sample_end=source[n.segment_indices[-1]].vgmticks_end,
                                  segment_indices=n.segment_indices, volume_runs=n.runs,
                                  gate_ids=n.gate_ids, gate_ambiguity=n.gate_ambiguity,
                                  boundary_reasons=n.boundary_reasons,
                                  structural_key=n.structural_key))
    write('notes', ('chip', 'channel', 'note_id', 'tick_start', 'tick_end', 'rest',
                    'source_sample_start', 'source_sample_end', 'segment_indices', 'volume_runs',
                    'gate_ids', 'gate_ambiguity', 'boundary_reasons', 'structural_key'), note_rows)
    for name in ('gates', 'controls', 'boundaries'):
        rows = getattr(performance, name)
        cls = {'gates': SoundGate, 'controls': ControlPoint, 'boundaries': Boundary}[name]
        write(name, tuple(cls.__dataclass_fields__), (asdict(row) for row in rows))
    source_rows = [dict(channel=ch, segment_index=i, **asdict(seg))
                   for ch, rows in performance.source_segments for i, seg in enumerate(rows)]
    write('segments', ('channel', 'segment_index') + tuple(source_rows[0].keys())[2:] if source_rows
          else ('channel', 'segment_index'), source_rows)
    Path(prefix + '.performance.json').write_text(json.dumps(dict(
        chip=performance.chip, source_clock_hz=44100, tick_clock_hz=performance.tick_clock_hz,
        validation_scope='retained native Segment state/order; not raw VGM replay',
        source_samples_unknown=sum(s.vgmticks is None or s.vgmticks_end is None
                                   for _, rows in performance.source_segments for s in rows),
        segments=len(source_rows), gates=len(performance.gates), notes=len(note_rows),
        controls=len(performance.controls),
        control_kind_counts=dict(Counter(p.kind for p in performance.controls)),
        boundary_reason_counts=dict(Counter(reason for b in performance.boundaries for reason in b.reasons)),
        ambiguous_score_partitions=sum(n['gate_ambiguity'] for n in note_rows),
        valid=performance.validate()), indent=2) + '\n', encoding='utf-8')
