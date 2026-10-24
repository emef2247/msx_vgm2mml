"""Optional target-only OPLL percussion overlay with source-linked decisions."""
import csv
from dataclasses import asdict
import json
from pathlib import Path

from rhythm_patterns import Group, Hit, group_segments
from rhythm_mml import render_groups
from rhythm_notation import optimize


def project(candidates, native_segments, performances, *, timing=None, raw_ticks=False, target_boundaries=None):
    """Merge inferred hits with native rhythm; never steal native melody voices."""
    blocked = any(s.keyon and s.fnum for ch in (6, 7, 8)
                  for s in native_segments.get(ch, ()))
    minimum = max(1, timing.tempo // 75) if timing else 1
    if timing and not blocked:
        from note_normalization import retime_rhythm
        target_native, _ = retime_rhythm(native_segments, timing)
    else:
        target_native = native_segments
    native_groups = group_segments(target_native)
    by_tick = {g.tick: list(g.hits) for g in native_groups}
    native_keys = {(g.tick, h.instrument) for g in native_groups for h in g.hits}
    end = max((s.tick_end for rows in target_native.values() for s in rows), default=0)
    for performance in performances:
        for _, rows in performance.source_segments:
            for s in rows:
                if timing:
                    if s.vgmticks_end is not None:
                        end = max(end, round(timing.position(s.vgmticks_end)))
                else:
                    end = max(end, s.tick_end)
    decisions = []
    winners = {}
    proposed = []
    for candidate in candidates:
        row = dict(candidate_id=candidate.candidate_id, source_chip=candidate.chip,
                   source_channel=candidate.channel, segment_indices=candidate.segment_indices,
                   source_sample=candidate.source_sample, source_tick=candidate.tick_start,
                   target_tick=None, source_shift_samples=None, target_reference=None,
                   instrument=candidate.instrument, volume=candidate.volume,
                   status='rejected', reason=';'.join(candidate.reasons))
        decisions.append(row)
        if candidate.instrument is None:
            continue
        if blocked:
            row.update(status='blocked', reason='native_opll_melody_channels_6_8')
            continue
        if candidate.source_sample is None:
            row['reason'] = 'unknown_source_onset'
            continue
        if timing:
            key = candidate.chip, candidate.channel, candidate.tick_start
            if target_boundaries is not None and key not in target_boundaries:
                row['reason'] = 'unmatched_source_target_boundary'
                continue
            tick = (target_boundaries[key] if target_boundaries is not None
                    else max(0, round(timing.position(candidate.source_sample))))
            row['source_shift_samples'] = (tick - timing.position(candidate.source_sample)) * timing.samples_per_step
            row['target_reference'] = 'projected_control_boundary' if target_boundaries is not None else 'source_position'
        else:
            tick = candidate.tick_start
            row['source_shift_samples'] = tick * 735 - candidate.source_sample
            row['target_reference'] = 'native_renderer_tick'
        row['target_tick'] = tick
        if tick < 0 or (timing and abs(tick - timing.position(candidate.source_sample))
                        * timing.samples_per_step > timing.tolerance_samples):
            row['reason'] = 'timing_tolerance'
            continue
        key = tick, candidate.instrument
        if key in native_keys:
            row.update(status='omitted', reason='native_rhythm_priority')
            continue
        proposed.append((tick, candidate, row))
    # A native hit wins over all proposals. Among duplicate inferred hits, keep
    # the stronger target level and deterministic source order; never add both.
    for tick, candidate, row in sorted(proposed, key=lambda x: (x[0], -x[1].volume,
                                                               x[1].candidate_id)):
        key = tick, candidate.instrument
        if key in winners:
            row.update(status='omitted', reason='duplicate_inferred_instrument_tick')
            continue
        if (tick > 0 and tick < minimum) or any(0 < abs(tick - t) < minimum for t in by_tick):
            row.update(status='omitted', reason='target_minimum_interval')
            continue
        hit = Hit(candidate.instrument, -1, len(winners), candidate.source_sample / 44100,
                  0, (15 - candidate.volume,) + (None,) * 9)
        by_tick.setdefault(tick, []).append(hit)
        winners[key] = row
        row.update(status='added', reason='inferred_percussion_overlay')
    ticks = sorted(by_tick)
    groups = tuple(Group(tick, ticks[i+1] - tick if i+1 < len(ticks) else None,
                         tuple(by_tick[tick])) for i, tick in enumerate(ticks))
    if ticks:
        end = max(end, ticks[-1] + minimum)
    added = len(winners)
    text = (optimize(render_groups(groups, raw_ticks=True if timing else raw_ticks,
                                   end_tick=end, minimum_steps=minimum),
                     raw_ticks=True if timing else raw_ticks) if added else '')
    summary = dict(enabled=True, status='applied' if added else 'unchanged',
                   reason='native_opll_melody_channels_6_8' if blocked else
                          'inferred_percussion_overlay' if added else 'no_projectable_candidates',
                   source_segments_unchanged=True, source_parts_preserved=True,
                   interpretation='heuristic augmentation; not observed source Key-On',
                   candidates=len(candidates), classified=sum(c.instrument is not None for c in candidates),
                   added_hits=added, omitted_hits=sum(r['status'] == 'omitted' for r in decisions),
                   blocked_hits=sum(r['status'] == 'blocked' for r in decisions),
                   normalized_clock=timing is not None,
                   instruments={name: sum(r['status'] == 'added' and r['instrument'] == name
                                          for r in decisions)
                                for name in ('BD', 'SD', 'TOM', 'CYM', 'HH')})
    return text, summary, decisions


def apply(candidates, native_segments, performances, output_dir, stem, *,
          native_mode, normalization, raw_ticks=False, dump_passes=False, control_sources=None):
    """Commit only a successfully rendered overlay after native normalization."""
    timing = None
    if normalization.get('applied'):
        from note_normalization import TimingPlan
        timing = TimingPlan(**normalization['timing'])
    root = Path(output_dir)
    boundaries = None
    if timing:
        from mml_sync import analyze_mml, _leaves, _NOTE
        boundaries = {}
        for chip in ('psg', 'scc'):
            before_path = root / f'{stem}.{chip}.before.normalize.mml'
            after_path = root / f'{stem}.{chip}.target.mml'
            original_text = (control_sources or {}).get(chip)
            if original_text is None and before_path.exists():
                original_text = before_path.read_text()
            if original_text is None or not after_path.exists():
                continue
            before_tracks = analyze_mml(original_text)[0]
            after_tracks = analyze_mml(after_path.read_text())[0]
            for track, nodes in before_tracks.items():
                original = [n for n in _leaves(nodes) if _NOTE.fullmatch(n.text.lower())]
                projected = [n for n in _leaves(after_tracks.get(track, ())) if _NOTE.fullmatch(n.text.lower())]
                if len(original) != len(projected):
                    continue
                channel = int(track) - (1 if chip == 'psg' else 4)
                for first, second in zip(original, projected):
                    boundaries[chip, channel, first.start / 3] = second.start
    text, summary, decisions = project(candidates, native_segments, performances,
                                       timing=timing, raw_ticks=raw_ticks, target_boundaries=boundaries)
    path = root / f'{stem}.opll.target.mml'
    before = path.read_text(encoding='utf-8')
    if text:
        # In melody mode, the layout guard guarantees there are no active f/g/h
        # melody lanes. Native rhythm mode already uses a single complete f line.
        body = '\n'.join(line for line in before.splitlines()
                         if not (line.startswith('f ') or line.startswith('#opll_mode ')))
        after = body + '\n' + text
        path.write_text(after, encoding='utf-8', newline='\n')
    else:
        after = before
    mode = 1 if text else native_mode
    summary.update(native_opll_mode=native_mode, target_opll_mode=mode)
    (root / f'{stem}.drums.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    for name, rows, fields in (
        ('candidates', [asdict(c) for c in candidates],
         ('candidate_id','chip','channel','segment_indices','source_sample','source_end',
          'tick_start','tick_end','instrument','volume','reasons','features')),
        ('projection', decisions, ('candidate_id','source_chip','source_channel','segment_indices',
                                 'source_sample','source_tick','target_tick','source_shift_samples','target_reference','instrument','volume',
                                 'status','reason'))):
        with (root/f'{stem}.drums.{name}.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
            for row in rows:
                writer.writerow({k:json.dumps(v) if isinstance(v,(tuple,list,dict)) else v
                                 for k,v in row.items()})
    if dump_passes:
        (root/f'{stem}.drums.before.target.mml').write_text(before, encoding='utf-8')
        (root/f'{stem}.drums.after.target.mml').write_text(after, encoding='utf-8')
    return mode, summary
