"""Exact per-channel Segment pattern candidates; no target MML rewriting."""
import csv
import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

from rhythm_patterns import find_patterns


FIELDS = {
    'opll': ('ev_type', 'keyon', 'onset', 'is_legato', 'is_vibrato',
             'is_portamento', 'is_envelope', 'fnum', 'block', 'inst', 'vol', 'sus'),
    'psg': ('ev_type', 'tone_period', 'volume', 'octave', 'scale', 'mode',
            'noise_period', 'envelope_enabled', 'envelope_period',
            'envelope_shape', 'mixer', 'amplitude_register'),
    'scc': ('ev_type', 'tone_period', 'volume', 'octave', 'scale', 'enabled',
            'waveform_hex', 'enable_register'),
}


@dataclass(frozen=True)
class Item:
    segment_index: int
    tick: int
    source_time: float
    duration: int
    advance: int
    state: tuple
    patch: str | None
    patch_changes: tuple

    def signature(self):
        return (self.duration, self.advance, self.state, self.patch, self.patch_changes)


def analyze(segments, chip, voice_csv_path=None):
    """Keep zero-length events and source order, matching only relative timing.

    Absolute timestamps, source indices, target voice IDs and analysis counters
    are evidence, not equality keys. Patch writes within OPLL intervals are
    retained so equal instrument-zero numbers alone cannot produce a match.
    Results are candidates: equal Segment state does not prove loop safety for
    running envelopes, oscillator phase or stateful target commands.
    """
    fields = FIELDS[chip]
    updates = []
    if chip == 'opll' and voice_csv_path:
        with open(voice_csv_path, newline='') as stream:
            updates = [(int(row['ticks']), row['patch_hex'])
                       for row in csv.DictReader(stream) if row['#type'] == 'patch']
        updates.sort(key=lambda row: row[0])  # stable same-tick write order
    times = [tick for tick, _ in updates]
    result = {}
    for ch, rows in sorted(segments.items()):
        if chip == 'opll' and ch not in range(9):
            continue
        items = []
        for index, seg in enumerate(rows):
            start, end = seg.tick_start, seg.tick_end
            following = rows[index + 1].tick_start if index + 1 < len(rows) else end
            if end < start or following < start:
                raise ValueError(f'{chip} ch{ch}: invalid Segment timing at {index}')
            patch, changes = None, ()
            if chip == 'opll' and seg.inst == 0:
                if not voice_csv_path:
                    # Unknown patches must never be inferred equal across rows.
                    patch = f'unknown:{ch}:{index}'
                else:
                    lo, hi = bisect_right(times, start), bisect_right(times, end - 1)
                    patch = updates[lo - 1][1] if lo else '0000000000000000'
                    changes = tuple((tick - start, value) for tick, value in updates[lo:hi])
            items.append(Item(index, start, seg.time, end - start, following - start,
                              tuple(getattr(seg, field, None) for field in fields), patch, changes))
        patterns, occurrences = find_patterns(items)
        result[ch] = (tuple(items), patterns, occurrences)
    return result


def dump_analysis(segments, chip, output_dir, stem, voice_csv_path=None):
    analysis = analyze(segments, chip, voice_csv_path)
    definitions, occurrences, markings = [], [], []
    for ch, (items, patterns, uses) in analysis.items():
        for number, pattern in enumerate(patterns):
            offset = 0
            for step, (duration, advance, state, patch, changes) in enumerate(pattern):
                payload = dict(zip(FIELDS[chip], state))
                payload.update(user_patch=patch, patch_changes=changes)
                definitions.append((ch, number, step, offset, duration, advance,
                                    json.dumps(payload, separators=(',', ':'))))
                offset += advance
        for occurrence_id, use in enumerate(uses):
            width = len(patterns[use.pattern_id])
            first = items[use.group_start]
            last = items[use.group_start + width * use.repeats - 1]
            occurrences.append((ch, occurrence_id, use.pattern_id, use.group_start,
                                first.tick, last.tick + last.duration, width, use.repeats))
            for repeat in range(use.repeats):
                for step in range(width):
                    item = items[use.group_start + repeat * width + step]
                    markings.append((ch, item.segment_index, item.source_time, item.tick,
                                     item.tick + item.duration, occurrence_id,
                                     use.pattern_id, repeat, step))
    prefix = Path(output_dir) / f'{stem}.{chip}.melody'
    for suffix, fields, rows in (
            ('patterns', ('ch', 'pattern_id', 'step', 'offset_ticks', 'duration_ticks',
                          'advance_ticks', 'state'), definitions),
            ('occurrences', ('ch', 'occurrence_id', 'pattern_id', 'segment_start',
                             'tick_start', 'tick_end', 'unit_segments', 'repeats'), occurrences),
            ('markings', ('ch', 'segment_index', 'source_time', 'tick_start', 'tick_end',
                          'occurrence_id', 'pattern_id', 'repeat_index', 'step'), markings)):
        with open(f'{prefix}.{suffix}.csv', 'w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)
    segment_path = Path(output_dir) / f'{stem}.{chip}.segments.csv'
    if segment_path.exists():
        annotate_segments(segment_path, analysis)
    return analysis


def annotate_segments(path, analysis):
    """Append analysis metadata to the existing dump without changing source cells."""
    columns = ('segment_index', 'pattern_id', 'occurrence_id', 'repeat_index',
               'pattern_step', 'pattern_segments', 'pattern_repeats')
    metadata = {}
    for ch, (items, patterns, uses) in analysis.items():
        for occurrence_id, use in enumerate(uses):
            width = len(patterns[use.pattern_id])
            for repeat in range(use.repeats):
                for step in range(width):
                    item = items[use.group_start + repeat * width + step]
                    metadata[ch, item.segment_index] = (use.pattern_id, occurrence_id,
                                                        repeat, step, width, use.repeats)
    with open(path, newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames)
        rows = list(reader)
    counts = defaultdict(int)
    for row in rows:
        ch = int(row['ch'])
        index = counts[ch]
        counts[ch] += 1
        values = metadata.get((ch, index), ('',) * (len(columns) - 1))
        row.update(zip(columns, (index, *values)))
    fields.extend(column for column in columns if column not in fields)
    # Analysis may be rerun; update columns rather than duplicating them.
    temporary = Path(str(path) + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
