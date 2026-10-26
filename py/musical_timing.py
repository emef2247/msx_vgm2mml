"""Accepted timing and OPLL state decisions shared by text and direct outputs.

Source samples are retained; accepted steps use the existing inferred clock.
Serialization into 44100-Hz samples uses the declared output tempo exactly.
No MML is generated or parsed while constructing these decisions.
"""
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
import csv
import json
import statistics


@dataclass(frozen=True)
class AcceptedTimingMapper:
    plan: object | None = None
    melody: object | None = None
    report: object | None = None

    @property
    def applied(self):
        return self.plan is not None

    @property
    def tempo(self):
        return self.plan.tempo if self.plan else 225

    def step_sample(self, step):
        """Map declared musical steps without accumulated floating-point drift."""
        return round(Fraction(str(step)) * Fraction(44100 * 60, self.tempo * 48))

    def source_step(self, source_sample):
        if self.plan:
            step = max(0, round(self.plan.position(source_sample)))
            shift = abs(step - self.plan.position(source_sample)) * self.plan.samples_per_step
            if shift > self.plan.tolerance_samples:
                raise ValueError('A musical boundary would exceed the correction tolerance')
            return step
        from mml_utils import get_ticks
        return get_ticks(source_sample / 44100) * 3

    def source_sample(self, source_sample):
        return self.step_sample(self.source_step(source_sample))

    def sample(self, tick, source_sample=None):
        if not self.plan:
            return round(Fraction(str(tick)) * 735)
        original = tick * 735 if source_sample is None else source_sample
        return self.source_sample(original)

    def boundaries(self, ticks, source_samples=None):
        """Map ordered score ends with the same minimum and tolerance as MML."""
        ticks = tuple(ticks)
        source_samples = (tuple(source_samples) if source_samples is not None else (None,) * len(ticks))
        if len(ticks) != len(source_samples):
            raise ValueError('Boundary/source lengths differ')
        if not self.plan:
            return tuple(self.sample(tick) for tick in ticks)
        previous, samples = 0, []
        for tick, original in zip(ticks, source_samples):
            previous = control_boundary_step(tick, self.plan, previous, original)
            samples.append(self.step_sample(previous))
        return tuple(samples)


def control_boundary_step(tick, plan, previous=0, source_sample=None):
    """One existing PSG/SCC retiming decision, independent of text notation."""
    sample = tick * 735 if source_sample is None else source_sample
    minimum = max(1, plan.tempo // 75)
    end = max(previous + minimum, round(plan.position(sample)))
    if abs(end - plan.position(sample)) * plan.samples_per_step > plan.tolerance_samples:
        raise ValueError('A PSG/SCC boundary would exceed the correction tolerance')
    return end


@dataclass(frozen=True)
class NormalizedState:
    source_start: int
    source_end: int
    start_step: int
    end_step: int
    gate_end_step: float
    gate: int
    value: tuple
    source_indices: tuple


@dataclass(frozen=True)
class NormalizedNote:
    note_index: int
    source_start: int
    source_end: int | None
    start_step: int
    end_step: int
    gate_end_step: float
    states: tuple
    source_indices: tuple


@dataclass(frozen=True)
class NormalizedTrack:
    channel: int
    default_gate: int
    default_volume: int
    constant_voice: bool
    constant_volume: bool
    voice: int
    notes: tuple


@dataclass(frozen=True)
class NormalizedMelody:
    tracks: tuple
    patches: tuple
    evidence: tuple
    state_evidence: tuple


def plan_melody(segments, voice_path, plan, num_channels=6, *, fm_state_ms=1, state_evidence=None):
    """Extract the established normalized melody decisions before encoding.

    Internal voice IDs identify shared patch values for notation only. Their
    MGSDRV range limit is deliberately checked by the MML lowering, not here.
    """
    from note_normalization import _notes, _gate
    from opll_target import target_note
    from mgs_conversion_config import sample_threshold
    from fm_state_runs import select_state_runs
    threshold = sample_threshold(fm_state_ms, '--fm-state-ms')
    updates = []
    if voice_path is not None:
        with open(voice_path, newline='') as stream:
            for row in csv.DictReader(stream):
                if row['#type'] == 'patch':
                    updates.append((int(row['vgmticks']), bytes.fromhex(row['patch_hex'])))
    times = [sample for sample, _ in updates]
    patches, tracks, evidence = {}, [], []
    if state_evidence is None:
        state_evidence = []
    minimum = max(1, plan.tempo // 75)

    def state(seg):
        octave, note = target_note(seg.fnum, seg.block)
        patch = None
        if seg.inst:
            voice = seg.inst - 1
        else:
            position = bisect_right(times, seg.vgmticks) - 1
            patch = updates[position][1] if position >= 0 else bytes(8)
            if patch not in patches:
                patches[patch] = 16 + len(patches)
            voice = patches[patch]
        return octave, note, voice, 15 - seg.vol, seg.sus, patch.hex() if patch else ''

    if num_channels == 6 and any(s.keyon and s.vgmticks_end > s.vgmticks for ch in (6, 7, 8)
                               for s in segments.get(ch, ())):
        raise ValueError('Nine-channel melodic OPLL is outside the current target renderer')
    for channel in range(num_channels):
        notes = _notes(segments.get(channel, ()))
        usable = [note for note in notes if note.members and (note.end is None or note.end > note.start)]
        if not usable:
            continue
        runs_by_note = []
        for note in usable:
            runs = []
            for index, seg in note.members:
                stop = seg.vgmticks_end
                if stop is None or stop <= seg.vgmticks:
                    continue
                value = state(seg)
                if runs and runs[-1][2] == value and runs[-1][1] == seg.vgmticks:
                    runs[-1] = (runs[-1][0], stop, value)
                else:
                    runs.append((seg.vgmticks, stop, value))
            runs_by_note.append(runs)
        gates = []
        for note, runs in zip(usable, runs_by_note):
            if note.end is None or not runs:
                continue
            observed = (note.end - runs[-1][0]) / plan.samples_per_step
            options = [(abs(length * q / 8 - observed), -q, q)
                       for length in (12, 24, 48, 96, 192) for q in range(1, 9)
                       if abs(length * q / 8 - observed) * plan.samples_per_step <= plan.tolerance_samples]
            if options:
                gates.append(min(options)[-1])
        default_gate = statistics.mode(gates) if gates else 8
        all_states = [run[2] for runs in runs_by_note for run in runs]
        if not all_states:
            continue
        constant_voice = len({value[2] for value in all_states}) == 1
        default_volume = statistics.mode(value[3] for value in all_states)
        closed_states = [run[2] for note, runs in zip(usable, runs_by_note)
                         if note.end is not None for run in runs]
        constant_volume = len({value[3] for value in closed_states or all_states}) == 1
        accepted, cursor = [], 0
        for ordinal, (note, runs) in enumerate(zip(usable, runs_by_note)):
            if not runs:
                continue
            start = plan.onset(note.start)
            if start < cursor:
                raise ValueError(f'Normalization would overlap an attack on channel {channel}')
            if start > cursor and start - cursor < minimum:
                raise ValueError('A normalized note must have positive length')
            next_start = (plan.onset(usable[ordinal + 1].start) if ordinal + 1 < len(usable)
                          else max(start + minimum, round(plan.position(runs[-1][1]))))
            if next_start <= start:
                raise ValueError(f'Normalization would merge attacks on channel {channel}')
            protected = {len(runs) - 1}
            for index in range(1, len(runs)):
                previous, current = runs[index - 1][2], runs[index][2]
                if (previous[2], previous[4], previous[5]) != (current[2], current[4], current[5]):
                    protected.update((index - 1, index))
            retained_indices, dropped_indices = select_state_runs(runs, threshold, protected)
            dropped = list(dropped_indices)
            for index, (a, b, value) in enumerate(runs):
                state_evidence.append(dict(ch=channel, note_index=ordinal, run_index=index,
                    source_start_samples=a, source_end_samples=b, duration_samples=b-a,
                    source_segment_indices=';'.join(str(i) for i, seg in note.members
                        if seg.vgmticks < b and seg.vgmticks_end > a),
                    state=json.dumps(value), action='omit_internal_state' if index in dropped else 'retain',
                    protected=index in protected, threshold_samples=threshold))
            retained = [runs[index] for index in retained_indices]
            if not retained:
                raise ValueError('An attack contains only unrepresentable intermediate states')
            positions = [start]
            for a, b, value in retained[1:]:
                positions.append(max(positions[-1] + minimum, round(plan.position(a))))
            states, gate_end, nominal_end, kept = [], start, start, []
            for index, (a, b, value) in enumerate(retained):
                at = positions[index]
                end = positions[index + 1] if index + 1 < len(retained) else None
                if end is not None and end <= at:
                    raise ValueError('Distinct state intervals would collapse')
                if at >= next_start:
                    raise ValueError('Distinct state intervals would exceed the next attack')
                if end is not None:
                    length, gate = min(end, next_start) - at, 0
                else:
                    observed = (b - a) / plan.samples_per_step
                    length, gate, fitted = _gate(observed, next_start - at, default_gate, plan)
                if length < minimum or nominal_end > at:
                    raise ValueError('Distinct state intervals have no MGSC-representable length')
                if abs(at - plan.position(a)) * plan.samples_per_step > plan.tolerance_samples:
                    raise ValueError('A state boundary would exceed the correction tolerance')
                if value[1] == 'r':
                    raise ValueError('Keyed zero-frequency material requires unchanged target projection')
                gate_end = at + length * (gate / 8 if gate else 1)
                nominal_end = at + length
                indices = tuple(i for i, seg in note.members if seg.vgmticks < b and seg.vgmticks_end > a)
                states.append(NormalizedState(a, b, at, nominal_end, gate_end, gate, value, indices))
                kept.append((at - start, gate_end - start, value))
            if not states:
                raise ValueError('A positive source attack became unrepresentable')
            source_indices = tuple(i for i, _ in note.members)
            accepted.append(NormalizedNote(ordinal, note.start, note.end, start, nominal_end,
                                           gate_end, tuple(states), source_indices))
            cursor = nominal_end
            record = dict(ch=channel, note_index=ordinal,
                segment_indices=';'.join(str(i) for i in source_indices),
                source_start_samples=note.start, source_end_samples=note.end,
                target_start_step=start, target_gate_end_step=gate_end, target_end_step=nominal_end,
                onset_delta_samples=(start - plan.position(note.start)) * plan.samples_per_step,
                gate_delta_samples='' if note.end is None else (gate_end - plan.position(note.end)) * plan.samples_per_step,
                terminal_unclosed=note.end is None, quantized_state_runs=json.dumps(dropped),
                target_state_runs=json.dumps(kept))
            evidence.append(record)
            if note.end is not None and abs(record['gate_delta_samples']) > plan.tolerance_samples:
                raise ValueError('A gate boundary would exceed the correction tolerance')
        tracks.append(NormalizedTrack(channel, default_gate, default_volume, constant_voice,
                                      constant_volume, all_states[0][2], tuple(accepted)))
    return NormalizedMelody(tuple(tracks), tuple(patches.items()), tuple(evidence), tuple(state_evidence))


def choose_timing(segments, voice_path=None, *, enabled=True, normalization_ms=8,
                  fm_state_ms=24, num_channels=9):
    """Accept or abstain from pure melody/rhythm timing before any encoding."""
    from note_normalization import infer_timing, retime_rhythm
    from dataclasses import asdict
    report = dict(enabled=bool(enabled), applied=False, status='unchanged',
                  reason='optional normalization not requested' if not enabled else 'no confident shared clock',
                  normalization_ms=float(normalization_ms), fm_state_ms=float(fm_state_ms),
                  source_segments_unchanged=True)
    if not enabled:
        return AcceptedTimingMapper(report=report)
    plan = infer_timing(segments, normalization_ms=normalization_ms)
    if plan is None:
        return AcceptedTimingMapper(report=report)
    report['timing'] = asdict(plan)
    try:
        melody = plan_melody(segments, voice_path, plan, num_channels, fm_state_ms=fm_state_ms)
        _, maximum = retime_rhythm(segments, plan)
    except ValueError as error:
        report.update(reason=str(error))
        return AcceptedTimingMapper(report=report)
    report.update(applied=True, status='applied', reason='', target_note_count=len(melody.evidence),
                  maximum_rhythm_shift_samples=maximum,
                  omitted_states=sum(row['action'] == 'omit_internal_state' for row in melody.state_evidence))
    return AcceptedTimingMapper(plan, melody, report)
