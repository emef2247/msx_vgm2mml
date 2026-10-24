"""Audition-only target masks from the native PSG percussion catalog.

Uncertain gestures remain melody. Native Segments and the inference catalog are
never rewritten. Neither branch removes time or replaces a PSG sound by OPLL.
"""
from bisect import bisect_left
import csv
from dataclasses import asdict, replace
import json
from pathlib import Path

from drum_inference import infer
from psg_scc_performance import audible


def _hardware_windows(performance):
    windows, unknown = [], False
    for _, rows in performance.source_segments:
        for row in rows:
            if not row.envelope_enabled or not audible(row, 'psg'):
                continue
            if row.vgmticks is None or row.vgmticks_end is None:
                unknown = True
            elif row.vgmticks_end > row.vgmticks:
                windows.append((row.vgmticks, row.vgmticks_end))
    merged = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged, unknown


def select(performance, part):
    """Return target copies, eligible native candidates, and inspectable decisions.

    All original rows, including zero-time controls, retain their positions and
    durations. Shared PSG hardware-envelope overlap is conservatively excluded:
    auditioning a slice must not pretend a new envelope reset preserves phase.
    """
    if performance.chip != 'psg' or part not in ('melody', 'rhythm'):
        raise ValueError('PSG selection requires a PSG performance and melody/rhythm part')
    candidates = infer((performance,))
    windows, unknown_hardware = _hardware_windows(performance)
    starts = [start for start, _ in windows]
    owners, decisions, selected = {}, [], []
    for candidate in candidates:
        reason = 'classified_percussion' if candidate.instrument else 'insufficient_percussion_evidence'
        eligible = candidate.instrument is not None
        if eligible:
            end = candidate.source_end
            index = bisect_left(starts, end) - 1
            overlap = index >= 0 and windows[index][1] > candidate.source_sample
            if unknown_hardware or overlap:
                eligible = False
                reason = 'shared_hardware_envelope_phase_unverified'
        if eligible:
            selected.append(candidate)
            for index in candidate.segment_indices:
                key = candidate.channel, index
                if key in owners:
                    raise ValueError('Overlapping PSG percussion ownership')
                owners[key] = candidate.candidate_id
        decisions.append(dict(**asdict(candidate), selection_class='rhythm' if eligible else 'melody',
                              selection_reason=reason))
    projected, membership = {}, []
    for channel, rows in performance.source_segments:
        target = []
        for index, row in enumerate(rows):
            classification = 'rhythm' if (channel, index) in owners else 'melody'
            keep = classification == part
            proxy = row if keep else replace(row, scale='r', mode=0, volume=0,
                       envelope_enabled=0, amplitude_register=0,
                       mixer=row.mixer | (1 << channel) | (1 << (channel + 3)))
            target.append(proxy)
            membership.append(dict(channel=channel, segment_index=index,
                source_sample=row.vgmticks, source_end=row.vgmticks_end,
                tick_start=row.tick_start, tick_end=row.tick_end,
                source_audible=audible(row, 'psg'), positive_duration=bool(row.l > 0 or
                    (row.vgmticks is not None and row.vgmticks_end is not None and row.vgmticks_end > row.vgmticks)),
                classification=classification,
                candidate_id=owners.get((channel, index), ''), kept=keep,
                target_audible=audible(proxy, 'psg')))
            if (proxy.ticks, proxy.l, proxy.vgmticks, proxy.vgmticks_end) != (row.ticks, row.l, row.vgmticks, row.vgmticks_end):
                raise ValueError('PSG selection changed source timing')
            if not keep and audible(proxy, 'psg'):
                raise ValueError('Masked PSG interval remains audible')
        projected[channel] = target
    summary = dict(enabled=True, part=part, interpretation='experimental percussion classification; audition target only',
        source_segments_unchanged=True, durations_unchanged=True, other_source_parts_soloed_out=True,
        candidates=len(candidates), classified=sum(c.instrument is not None for c in candidates),
        eligible_rhythm_candidates=len(selected),
        hardware_phase_abstentions=sum(d['selection_reason']=='shared_hardware_envelope_phase_unverified' for d in decisions),
        source_audible_intervals=sum(r['source_audible'] and r['positive_duration'] for r in membership),
        selected_audible_intervals=sum(r['target_audible'] and r['positive_duration'] for r in membership),
        rhythm_segment_intervals=sum(r['classification']=='rhythm' for r in membership))
    return projected, tuple(selected), summary, decisions, membership


def dump(output_dir, stem, summary, decisions, membership):
    prefix = Path(output_dir) / (stem + '.psg.selection')
    Path(str(prefix)+'.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    for suffix, rows in (('candidates', decisions), ('mask', membership)):
        fields = list(rows[0]) if rows else (['candidate_id', 'selection_class', 'selection_reason']
                  if suffix=='candidates' else ['channel', 'segment_index', 'classification', 'kept'])
        with Path(str(prefix)+'.'+suffix+'.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
            for row in rows:
                writer.writerow({k:json.dumps(v) if isinstance(v, (tuple, list, dict)) else v for k,v in row.items()})
