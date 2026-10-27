"""Bounded target-only reuse of observed PSG/SCC software volume curves.

Source samples and renderer ticks are checked independently. This is not a
short-note filter: gates, pitch, settings, source controls and note boundaries
are immutable, and every replacement is compared directly with its original.
"""
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction
import json
from pathlib import Path

from mml_envelopes import envelope_data
from psg_scc_performance import audible, settings


MAX_CANDIDATES = 64


def _number(value, name):
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'{name} must be finite and nonnegative') from error
    if number < 0:
        raise ValueError(f'{name} must be finite and nonnegative')
    return number


def _runs(values):
    result = []
    for volume, duration in values:
        if duration <= 0:
            continue
        if result and result[-1][0] == volume:
            result[-1] = volume, result[-1][1] + duration
        else:
            result.append((volume, duration))
    return tuple(result)


def _metrics(left, right):
    """Piecewise comparison without expanding samples or renderer frames."""
    if not left or not right or sum(n for _, n in left) != sum(n for _, n in right):
        return None
    i = j = 0
    a = left[0][1]
    b = right[0][1]
    maximum = integral = changed = longest = run = 0
    silence_changed = False
    while i < len(left) and j < len(right):
        duration = min(a, b)
        x, y = left[i][0], right[j][0]
        error = abs(x-y)
        maximum = max(maximum, error)
        integral += error*duration
        silence_changed |= bool(x) != bool(y)
        if error:
            changed += duration
            run += duration
            longest = max(longest, run)
        else:
            run = 0
        a -= duration
        b -= duration
        if not a:
            i += 1
            if i < len(left):
                a = left[i][1]
        if not b:
            j += 1
            if j < len(right):
                b = right[j][1]
    return dict(maximum_error=maximum, integrated_error=integral,
                mean_error=Fraction(integral, sum(n for _, n in left)),
                changed_duration=changed, maximum_changed_duration=longest,
                silence_changed=silence_changed)


def _profile(performance, channel, note):
    if note.rest:
        return None, 'rest'
    if note.length <= 0 or not note.runs or sum(n for _, n in note.runs) != note.length:
        return None, 'invalid_renderer_curve'
    if len(note.gate_ids) != 1:
        return None, 'ambiguous_or_missing_gate'
    if not note.segment_indices:
        return None, 'missing_source_lineage'
    native = dict(performance.source_segments)[channel]
    first, last = note.segment_indices[0], note.segment_indices[-1]
    if tuple(sorted(set(note.segment_indices))) != note.segment_indices:
        return None, 'unordered_source_lineage'
    if first < 0 or last >= len(native):
        return None, 'invalid_source_lineage'
    rows = native[first:last+1]
    if any(row.l > 0 and index not in note.segment_indices
           for index, row in enumerate(native[first:last+1], first)):
        return None, 'incomplete_source_lineage'
    reference = settings(note.segment, performance.chip)
    if performance.chip == 'psg':
        if note.segment.mode != 1 or note.segment.envelope_enabled:
            return None, 'hardware_or_noise_path'
        allowed = {'v', 'aVC'}
    elif performance.chip == 'scc':
        if not note.segment.enabled:
            return None, 'disabled_source'
        allowed = {'v', 'vCtrl'}
    else:
        return None, 'unsupported_chip'
    source_runs = []
    previous_end = None
    for index, row in enumerate(rows):
        if row.l < 0:
            return None, 'invalid_renderer_source_duration'
        if row.vgmticks is None or row.vgmticks_end is None:
            return None, 'unknown_source_time'
        if row.vgmticks_end < row.vgmticks:
            return None, 'invalid_source_time'
        if previous_end is not None and row.vgmticks != previous_end:
            return None, 'source_time_discontinuity'
        previous_end = row.vgmticks_end
        if not audible(row, performance.chip):
            return None, 'source_silence_or_disable'
        if settings(row, performance.chip) != reference:
            return None, 'ordered_settings_change'
        if performance.chip == 'scc' and row.waveform_hex != note.segment.waveform_hex:
            return None, 'ordered_waveform_change'
        if index and row.ev_type not in allowed:
            return None, 'ordered_operation_barrier'
        if not isinstance(row.volume, int) or not 0 <= row.volume <= 15:
            return None, 'unknown_volume_domain'
        source_runs.append((row.volume, row.vgmticks_end-row.vgmticks))
    rendered = _runs((native[i].volume, native[i].l) for i in note.segment_indices)
    if rendered != tuple(note.runs):
        return None, 'renderer_source_curve_disagreement'
    source_runs = _runs(source_runs)
    if not source_runs:
        return None, 'zero_source_duration'
    if source_runs[0][0] != note.runs[0][0] or source_runs[-1][0] != note.runs[-1][0]:
        return None, 'source_renderer_endpoint_disagreement'
    waveform = note.segment.waveform_hex if performance.chip == 'scc' else None
    key = (note.length, sum(n for _, n in source_runs), reference, waveform,
           note.runs[0][0], note.runs[-1][0])
    return dict(key=key, runs=tuple(note.runs), source_runs=source_runs,
                sample_start=rows[0].vgmticks, sample_end=rows[-1].vgmticks_end), ''


@dataclass(frozen=True)
class CurveApproximation:
    original: object
    performance: object
    decisions: tuple
    config: tuple

    def summary(self):
        values = dict(self.config)
        accepted = [row for row in self.decisions if row['action'] == 'replace']
        original_curves = {tuple(n.runs) for _, notes in self.original.channels for n in notes if not n.rest}
        projected_curves = {tuple(n.runs) for _, notes in self.performance.channels for n in notes if not n.rest}
        return dict(values, chip=self.original.chip, source_segments_unchanged=True,
                    scope='fixed-tone/fixed-wave observed volume-curve reuse; target only',
                    replaced_notes=len(accepted), lossy=bool(accepted),
                    unique_curves_before=len(original_curves), unique_curves_after=len(projected_curves),
                    maximum_volume_error=max((row['source_maximum_error'] for row in accepted), default=0),
                    maximum_mean_error=max((row['source_mean_error'] for row in accepted), default=0),
                    maximum_changed_samples=max((row['source_maximum_changed_samples'] for row in accepted), default=0),
                    decisions=dict(Counter(row['action'] for row in self.decisions)),
                    candidate_limit=MAX_CANDIDATES, native_controls_unchanged=True,
                    note_boundaries_unchanged=True)


def project(performance, *, state_ms=None, max_volume_error=None, max_mean_error=None):
    """Reuse a simpler observed curve only within all explicit error budgets.

    ``max_mean_error`` is a duration-weighted mean absolute register-level
    deviation, not a relative percentage. Zero/None ``state_ms`` disables this
    projection. Enabled use requires both error budgets explicitly.
    """
    threshold = Fraction(0) if state_ms is None else _number(state_ms, 'state_ms')
    if not threshold:
        return CurveApproximation(performance, performance, (), (('enabled', False), ('state_ms', 0)))
    if max_volume_error is None or max_mean_error is None:
        raise ValueError('Enabled curve approximation requires max_volume_error and max_mean_error')
    point = _number(max_volume_error, 'max_volume_error')
    mean = _number(max_mean_error, 'max_mean_error')
    if point > 15 or mean > 15:
        raise ValueError('Volume error budgets must be in the native 0..15 register range')
    samples = threshold*Fraction(441, 10)
    config = (('enabled', True), ('state_ms', float(threshold)),
              ('max_volume_error', float(point)), ('max_mean_error', float(mean)))
    tick_hz = performance.tick_clock_hz
    if not isinstance(tick_hz, int) or tick_hz <= 0:
        raise ValueError('Renderer tick clock must be a positive integer')
    groups = defaultdict(dict)
    profiles, decisions = {}, []
    for channel, notes in performance.channels:
        for index, note in enumerate(notes):
            profile, reason = _profile(performance, channel, note)
            identity = channel, index
            row = dict(channel=channel, note_index=index, segment_indices=note.segment_indices,
                       gate_ids=note.gate_ids, tick_start=note.start, tick_end=note.start+note.length,
                       original_runs=note.runs, projected_runs=note.runs,
                       action='retain', reason=reason)
            if profile is None:
                row['action'] = 'protect'
                decisions.append(row)
                continue
            row.update(sample_start=profile['sample_start'], sample_end=profile['sample_end'],
                       original_source_runs=profile['source_runs'])
            profile=dict(profile,origin=dict(channel=channel,note_index=index,
                source_segment_indices=note.segment_indices,gate_ids=note.gate_ids,
                sample_start=profile['sample_start'],sample_end=profile['sample_end']))
            signature = profile['runs'], profile['source_runs']
            existing=groups[profile['key']].get(signature)
            if existing is None or (channel,index)<(existing['origin']['channel'],existing['origin']['note_index']):
                groups[profile['key']][signature]=profile
            profiles[identity] = profile, row
    def rank(profile):
        return (len(profile['runs']), len(envelope_data(profile['runs'])),
                profile['runs'], profile['source_runs'])
    candidates = {key: sorted(values.values(), key=rank)[:MAX_CANDIDATES]
                  for key, values in groups.items()}
    replacements, cache = {}, {}
    for identity, (original, row) in profiles.items():
        checked, rejected, attempts = 0, Counter(), []
        for candidate in candidates[original['key']]:
            if rank(candidate) >= rank(original):
                break
            if candidate['runs'] == original['runs']:
                continue
            checked += 1
            pair = original['runs'], original['source_runs'], candidate['runs'], candidate['source_runs']
            if pair not in cache:
                source = _metrics(original['source_runs'], candidate['source_runs'])
                rendered = _metrics(original['runs'], candidate['runs'])
                reason = ''
                if source is None or rendered is None:
                    reason = 'duration_mismatch'
                elif source['silence_changed'] or rendered['silence_changed']:
                    reason = 'audibility_changed'
                elif source['maximum_error'] > point or rendered['maximum_error'] > point:
                    reason = 'maximum_volume_error'
                elif source['mean_error'] > mean or rendered['mean_error'] > mean:
                    reason = 'mean_volume_error'
                elif source['maximum_changed_duration'] > samples:
                    reason = 'source_changed_interval_too_long'
                elif Fraction(rendered['maximum_changed_duration']*44100, tick_hz) > samples:
                    reason = 'renderer_changed_interval_too_long'
                cache[pair] = source, rendered, reason
            source, rendered, reason = cache[pair]
            attempts.append(dict(projected_runs=candidate['runs'], representative_source_runs=candidate['source_runs'],
                representative_origin=candidate['origin'],
                reason=reason or 'accepted',
                source_metrics=None if source is None else {key: float(value) if isinstance(value, Fraction) else value
                                                           for key, value in source.items()},
                renderer_metrics=None if rendered is None else {key: float(value) if isinstance(value, Fraction) else value
                                                               for key, value in rendered.items()}))
            if reason:
                rejected[reason] += 1
                continue
            replacements[identity] = candidate['runs']
            row.update(action='replace', reason='bounded_observed_curve', projected_runs=candidate['runs'],
                       representative_origin=candidate['origin'],
                       representative_source_runs=candidate['source_runs'],
                       source_maximum_error=source['maximum_error'], source_mean_error=float(source['mean_error']),
                       source_integrated_error=source['integrated_error'],
                       source_changed_samples=source['changed_duration'],
                       source_maximum_changed_samples=source['maximum_changed_duration'],
                       renderer_maximum_error=rendered['maximum_error'],
                       renderer_mean_error=float(rendered['mean_error']),
                       renderer_integrated_error=rendered['integrated_error'],
                       renderer_changed_ticks=rendered['changed_duration'],
                       renderer_maximum_changed_ticks=rendered['maximum_changed_duration'])
            break
        row.update(candidates_checked=checked, rejected_candidates=dict(rejected),
                   candidate_attempts=attempts,
                   candidate_search_truncated=len(groups[original['key']]) > MAX_CANDIDATES)
        if row['action'] != 'replace':
            row['reason'] = 'no_bounded_simpler_observed_curve'
        decisions.append(row)
    channels = tuple((channel, tuple(replace(note, runs=replacements[channel, index])
                        if (channel, index) in replacements else note
                        for index, note in enumerate(notes)))
                     for channel, notes in performance.channels)
    projected = replace(performance, channels=channels) if replacements else performance
    projected.validate(dict(performance.source_segments))
    return CurveApproximation(performance, projected,
                              tuple(sorted(decisions, key=lambda row: (row['channel'], row['note_index']))), config)


def abstain(projection,reason):
    """Retain a proposed comparison when a later target clock is unverified."""
    decisions=[]
    for row in projection.decisions:
        row=dict(row)
        if row['action']=='replace':
            row.update(action='retain',reason=reason,candidate_projected_runs=row['projected_runs'],
                       projected_runs=row['original_runs'])
        decisions.append(row)
    return replace(projection,performance=projection.original,decisions=tuple(decisions),
                   config=projection.config+(('applied',False),('status','abstained'),('reason',reason)))


def dump(projection, prefix, details=True):
    """Expose native-to-target curve decisions independently of final MML."""
    prefix = str(prefix)
    Path(prefix+'.json').write_text(json.dumps(projection.summary(), indent=2)+'\n', encoding='utf-8', newline='\n')
    if not details:
        return
    rows = projection.decisions
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(prefix+'.decisions.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or ['channel', 'note_index', 'action', 'reason'])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (tuple, list, dict)) else value
                             for key, value in row.items()})
