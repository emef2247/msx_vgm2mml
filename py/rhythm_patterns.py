"""Lossless tick grouping and exact adjacent repeats of OPLL rhythm Segments."""
import csv
import json
from dataclasses import dataclass
from pathlib import Path


INSTRUMENTS = {9: 'BD', 10: 'SD', 11: 'TOM', 12: 'CYM', 13: 'HH'}
# Shared pitch registers can affect rhythm timbre; do not match on volume alone.
STATE_FIELDS = ('vol', 'fnum', 'block', 'sus', 'fnum_ch6', 'block_ch6',
                'fnum_ch7', 'block_ch7', 'fnum_ch8', 'block_ch8')


@dataclass(frozen=True)
class Hit:
    instrument: str
    channel: int
    segment_index: int
    source_time: float
    interval: int
    state: tuple

    def signature(self):
        return self.instrument, self.interval, self.state


@dataclass(frozen=True)
class Group:
    tick: int
    gap: int | None
    hits: tuple

    def signature(self):
        return self.gap, tuple(hit.signature() for hit in self.hits)


@dataclass(frozen=True)
class Occurrence:
    pattern_id: int
    group_start: int
    repeats: int


def group_segments(segments):
    """Group at existing 60 Hz ticks; retain repeated hits and source references."""
    by_tick = {}
    for channel, instrument in INSTRUMENTS.items():
        for index, segment in enumerate(segments.get(channel, ())):
            if (segment.ev_type != 'rhythm_expand' or not segment.is_ryt
                    or not segment.keyon):
                continue
            hit = Hit(instrument, channel, index, segment.time,
                      segment.tick_end - segment.tick_start,
                      tuple(getattr(segment, field, None) for field in STATE_FIELDS))
            by_tick.setdefault(segment.tick_start, []).append(hit)
    ticks = sorted(by_tick)
    return tuple(Group(tick, ticks[i + 1] - tick if i + 1 < len(ticks) else None,
                       tuple(by_tick[tick])) for i, tick in enumerate(ticks))


def find_patterns(groups):
    """Greedy exact tandem repeats; no beat inference or timing tolerance.

    Choose the repeat saving most groups at each position, preferring the
    shorter unit on ties. Single groups cover unmatched material. Definitions
    are reused across non-adjacent occurrences. This is not optimal compression.
    """
    keys = tuple(group.signature() for group in groups)
    patterns, ids, occurrences = [], {}, []
    start = 0
    while start < len(keys):
        width, repeats, saving = 1, 1, 0
        for size in range(1, (len(keys) - start) // 2 + 1):
            if keys[start] != keys[start + size]:
                continue
            unit = keys[start:start + size]
            count = 1
            while keys[start + count * size:start + (count + 1) * size] == unit:
                count += 1
            benefit = size * (count - 1)
            if benefit > saving:
                width, repeats, saving = size, count, benefit
        unit = keys[start:start + width]
        if unit not in ids:
            ids[unit] = len(patterns)
            patterns.append(unit)
        occurrences.append(Occurrence(ids[unit], start, repeats))
        start += width * repeats
    return tuple(patterns), tuple(occurrences)


def dump_analysis(segments, output_dir, stem):
    """Write groups, relative pattern definitions, and ordered occurrences."""
    groups = group_segments(segments)
    patterns, occurrences = find_patterns(groups)
    prefix = Path(output_dir) / f'{stem}.opll.rhythm'

    def write(suffix, fields, rows):
        with open(f'{prefix}.{suffix}.csv', 'w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)

    def hits_json(hits):
        return json.dumps([dict(instrument=h.instrument, channel=h.channel,
                                segment_index=h.segment_index, source_time=h.source_time,
                                interval_ticks=h.interval, **dict(zip(STATE_FIELDS, h.state)))
                           for h in hits], separators=(',', ':'))

    write('groups', ('group_id', 'tick', 'gap_ticks', 'hits'),
          ((i, g.tick, g.gap, hits_json(g.hits)) for i, g in enumerate(groups)))
    definition_rows = []
    for pattern_id, pattern in enumerate(patterns):
        offset = 0
        for step, (gap, hits) in enumerate(pattern):
            payload = [dict(instrument=name, interval_ticks=interval,
                            **dict(zip(STATE_FIELDS, state))) for name, interval, state in hits]
            definition_rows.append((pattern_id, step, offset, gap,
                                    json.dumps(payload, separators=(',', ':'))))
            offset += gap or 0
    write('patterns', ('pattern_id', 'step', 'offset_ticks', 'gap_ticks', 'hits'),
          definition_rows)
    write('occurrences', ('pattern_id', 'group_start', 'tick_start', 'group_count', 'repeats'),
          ((o.pattern_id, o.group_start, groups[o.group_start].tick,
            len(patterns[o.pattern_id]), o.repeats) for o in occurrences))
    return groups, patterns, occurrences
