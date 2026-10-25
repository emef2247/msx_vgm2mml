"""Exact, opt-in fixed-pitch volume-curve projection over native performance IR.

A candidate is an inferred continuation, not a recovered hardware Key-On or
original score instruction. Native partitions/controls remain authoritative.
"""
import csv
from dataclasses import dataclass, replace
import json
from pathlib import Path

from psg_scc_performance import audible, settings


@dataclass(frozen=True)
class VolumeCurveProjection:
    original: object
    performance: object
    candidates: tuple
    decisions: tuple

    def summary(self):
        before = sum(len(notes) for _, notes in self.original.channels)
        after = sum(len(notes) for _, notes in self.performance.channels)
        return dict(enabled=True, chip=self.original.chip,
                    scope='fixed-tone continuation and single-attack software volume curves',
                    source_segments_unchanged=True, lossy=False,
                    equality_scope='performance timeline; not raw VGM replay',
                    tick_clock_hz=self.original.tick_clock_hz,
                    original_units=before, projected_units=after,
                    joined_boundaries=before - after,
                    accepted_curves=sum(c['action'] == 'join' and c['reason'] == 'volume_only_single_attack'
                                        for c in self.candidates),
                    inactive_reset_joins=sum(d['action'] == 'join' and
                                             d['reason'] == 'inactive_hardware_envelope_reset'
                                             for d in self.decisions),
                    unchanged_period_joins=sum(d['action'] == 'join' and
                                              d['reason'] == 'unchanged_period_write_release_continuation'
                                              for d in self.decisions),
                    retained_candidates=sum(c['action'] != 'join' for c in self.candidates),
                    maximum_volume_error=0, timing_shift_samples=0)


def _runs(notes):
    result = []
    for note in notes:
        for volume, duration in note.runs:
            if result and result[-1][0] == volume:
                result[-1] = (volume, result[-1][1] + duration)
            else:
                result.append((volume, duration))
    return tuple(result)


def _barrier(left, right, source, chip, *, inactive_reset=False, unchanged_period=False):
    if left.rest or right.rest:
        return 'rest_boundary'
    if left.start + left.length != right.start:
        return 'renderer_gap'
    if (len(left.gate_ids) != 1 or left.gate_ids != right.gate_ids
            or right.gate_ambiguity or left.gate_ambiguity):
        return 'source_audibility_boundary'
    if 'pitch_write' in right.boundary_reasons and not unchanged_period:
        return 'pitch_write'
    if 'hardware_envelope_reset' in right.boundary_reasons and not inactive_reset:
        return 'hardware_envelope_reset'
    if chip == 'psg' and (left.segment.envelope_enabled or right.segment.envelope_enabled
                          or left.segment.mode != 1 or right.segment.mode != 1):
        return 'hardware_or_noise_path'
    reference = settings(left.segment, chip)
    if settings(right.segment, chip) != reference:
        return 'pitch_or_settings_change'
    # evS has no immediate effect on fixed-volume tone output. The full ordered
    # scan below still rejects transient hardware-enable, noise and pitch changes.
    # Noise/period latches remain in native controls. While all rows below
    # prove fixed tone and HW-envelope-off, these global writes do not alter
    # this channel's effective sounding state. Other channels are unchanged.
    allowed = ({'v', 'aVC', 'evS', 'fCA', 'fCB', 'wNC', 'ePL', 'evM'}
               if chip == 'psg' else {'v', 'vCtrl'})
    first = left.segment_indices[0]
    last = right.segment_indices[-1]
    previous = None
    for index in range(first, last + 1):
        segment = source[index]
        if segment.vgmticks is None or segment.vgmticks_end is None:
            return 'unknown_source_time'
        if segment.vgmticks_end < segment.vgmticks:
            return 'invalid_source_time'
        if previous is not None and segment.vgmticks != previous.vgmticks_end:
            return 'source_time_discontinuity'
        if unchanged_period and previous is not None and segment.volume > previous.volume:
            return 'ordered_volume_rise'
        if not audible(segment, chip):
            return 'source_silence_or_disable'
        if settings(segment, chip) != reference:
            return 'ordered_settings_change'
        if chip == 'scc' and segment.waveform_hex != left.segment.waveform_hex:
            return 'ordered_waveform_change'
        if index != first and segment.ev_type not in allowed:
            return 'ordered_operation_barrier'
        previous = segment
    return ''


def _single_attack(runs):
    falling = False
    rise = fall = False
    for (left, _), (right, _) in zip(runs, runs[1:]):
        if right > left:
            if falling:
                return False
            rise = True
        elif right < left:
            falling = fall = True
    return rise and fall


def _project_volume_curves(performance):
    """Join supported volume-only partitions without changing any volume holds."""
    channels, candidates, decisions = [], [], []
    native = dict(performance.source_segments)
    chip = performance.chip
    for channel, notes in performance.channels:
        projected = []
        block, identities = [], []

        def finish():
            if not block:
                return
            runs = _runs(block)
            accepted = len(block) > 1 and _single_attack(runs)
            if len(block) > 1:
                candidates.append(dict(channel=channel, candidate_id=len(candidates),
                    original_note_ids=tuple(identities),
                    segment_indices=tuple(i for note in block for i in note.segment_indices),
                    tick_start=block[0].start, tick_end=block[-1].start + block[-1].length,
                    volume_runs=runs, action='join' if accepted else 'retain',
                    reason='volume_only_single_attack' if accepted else 'unresolved_curve_shape',
                    interpretation='inferred_continuation'))
            if accepted:
                projected.append(replace(block[0], length=sum(n.length for n in block),
                    runs=runs, segment_indices=tuple(i for n in block for i in n.segment_indices),
                    boundary_reasons=block[0].boundary_reasons))
            else:
                projected.extend(block)
            for left_id, right_id in zip(identities, identities[1:]):
                decisions.append(dict(channel=channel, left_note=left_id, right_note=right_id,
                    action='join' if accepted else 'retain',
                    reason='volume_only_single_attack' if accepted else 'unresolved_curve_shape'))
            block.clear()
            identities.clear()

        for number, note in enumerate(notes):
            if block:
                reason = _barrier(block[-1], note, native[channel], chip)
                if reason:
                    previous = identities[-1]
                    finish()
                    decisions.append(dict(channel=channel, left_note=previous, right_note=number,
                                          action='protect', reason=reason))
            block.append(note)
            identities.append(number)
        finish()
        channels.append((channel, tuple(projected)))
    result = replace(performance, channels=tuple(channels))
    # Native source membership and every positive-duration hold remain unchanged.
    result.validate(dict(performance.source_segments))
    return VolumeCurveProjection(performance, result, tuple(candidates), tuple(decisions))



def project(performance):
    """Coalesce fixed-tone continuations, then interpret volume-only attacks.

    Original note IDs in every decision refer to the unchanged input performance.
    Native pitch writes, global envelope state and zero-duration controls remain.
    A period-write join is inferred continuation, not recovered note-off/release.
    """
    channels, candidates, decisions, lineage = [], [], [], {}
    native = dict(performance.source_segments)
    for channel, notes in performance.channels:
        projected, groups = [], []
        for number, note in enumerate(notes):
            pure_reset = note.boundary_reasons == ('hardware_envelope_reset',)
            pure_period = note.boundary_reasons == ('pitch_write',)
            if performance.chip == 'psg' and projected and (pure_reset or pure_period):
                previous = projected[-1]
                reason = _barrier(previous, note, native[channel], 'psg',
                                  inactive_reset=pure_reset, unchanged_period=pure_period)
                runs = _runs((previous, note))
                if not reason and pure_period and any(b > a for (a, _), (b, _) in zip(runs, runs[1:])):
                    reason = 'volume_rise'
                joined_reason = ('inactive_hardware_envelope_reset' if pure_reset else
                                 'unchanged_period_write_release_continuation')
                decisions.append(dict(channel=channel, left_note=groups[-1][-1], right_note=number,
                    action='protect' if reason else 'join', reason=reason or joined_reason))
                if not reason:
                    projected[-1] = replace(previous, length=previous.length + note.length,
                        runs=runs, segment_indices=previous.segment_indices + note.segment_indices)
                    groups[-1] += (number,)
                    continue
            projected.append(note)
            groups.append((number,))
        for group, note in zip(groups, projected):
            if len(group) > 1:
                candidates.append(dict(channel=channel, candidate_id=len(candidates),
                    original_note_ids=group, segment_indices=note.segment_indices,
                    tick_start=note.start, tick_end=note.start + note.length,
                    volume_runs=note.runs, action='join',
                    reason='fixed_tone_continuation', interpretation='inferred_continuation'))
        channels.append((channel, tuple(projected)))
        lineage[channel] = groups
    coalesced = replace(performance, channels=tuple(channels))
    coalesced.validate(dict(performance.source_segments))
    curves = _project_volume_curves(coalesced)
    for candidate in curves.candidates:
        group = lineage[candidate['channel']]
        candidates.append(dict(candidate, candidate_id=len(candidates),
            original_note_ids=tuple(n for index in candidate['original_note_ids'] for n in group[index])))
    for decision in curves.decisions:
        group = lineage[decision['channel']]
        decisions.append(dict(decision, left_note=group[decision['left_note']][-1],
                              right_note=group[decision['right_note']][0]))
    return VolumeCurveProjection(performance, curves.performance, tuple(candidates), tuple(decisions))


def dump(projection, prefix, details=False):
    """Keep original performance dumps separate from projected curve evidence."""
    prefix = str(prefix)
    Path(prefix + '.json').write_text(json.dumps(projection.summary(), indent=2) + '\n', encoding='utf-8')
    if not details:
        return
    note_rows = [dict(channel=channel, projected_note=index, tick_start=note.start,
                     tick_end=note.start + note.length, rest=note.rest,
                     segment_indices=note.segment_indices, gate_ids=note.gate_ids,
                     volume_runs=note.runs)
                 for channel, notes in projection.performance.channels for index, note in enumerate(notes)]
    for suffix, rows, fields in (
            ('candidates', projection.candidates, ('channel', 'candidate_id', 'original_note_ids',
                'segment_indices', 'tick_start', 'tick_end', 'volume_runs', 'action', 'reason', 'interpretation')),
            ('notes', note_rows, ('channel', 'projected_note', 'tick_start', 'tick_end', 'rest',
                'segment_indices', 'gate_ids', 'volume_runs')),
            ('decisions', projection.decisions, ('channel', 'left_note', 'right_note', 'action', 'reason'))):
        with Path(prefix + '.' + suffix + '.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v) if isinstance(v, tuple) else v for k, v in row.items()})
