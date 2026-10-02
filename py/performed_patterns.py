"""Conservative performed units and finite nested loops over complete notes.

Source signatures nominate repeats; exact emitted commands authorize replacement.
A noise-containing rest-delimited phrase is a percussion *candidate*, not a
claim that the original player invoked a drum macro.
"""
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rhythm_patterns import find_patterns, Occurrence


@dataclass(frozen=True)
class Unit:
    start: int
    end: int
    kind: str
    key: tuple

    def signature(self):
        return self.key


def group_notes(notes, chip):
    from mml_envelopes import settings

    def key(note):
        return (note.length, note.rest, () if note.rest else settings(note.segment, chip),
                tuple(note.runs), note.envelope)

    units = []
    i = 0
    while i < len(notes):
        end = i + 1
        kind = 'rest' if notes[i].rest else 'note'
        if chip == 'psg' and not notes[i].rest:
            # Only a silence-to-silence interval supports this coarse grouping.
            stop = i
            while stop < len(notes) and not notes[stop].rest:
                stop += 1
            if stop < len(notes) and any(n.segment.mode & 2 for n in notes[i:stop]):
                end, kind = stop + 1, 'percussion_candidate'
        first = notes[i].start
        signature = tuple((n.start - first, key(n)) for n in notes[i:end])
        units.append(Unit(i, end, kind, signature))
        i = end
    return units


def weighted_patterns(units, commands):
    """Choose non-overlapping repeats by total emitted text cost, not unit count.

    Equality still comes from source units. Repeats with different command
    initialization are left for subsequent positions rather than hiding a better
    overlapping repeat. Dynamic programming considers shorter repeat counts too.
    """
    keys = [u.signature() for u in units]
    validation = [getattr(u, 'validation_key', u.signature()) for u in units]
    n = len(keys)
    cost = [0] * (n + 1)
    choices = [(1, 1)] * n
    lengths = [0]
    for text in commands:
        lengths.append(lengths[-1] + len(text) + 1)
    for start in range(n - 1, -1, -1):
        cost[start] = len(commands[start]) + 1 + cost[start + 1]
        for width in range(1, (n - start) // 2 + 1):
            if keys[start] != keys[start + width]:
                continue
            count = 2
            while start + width * count <= n:
                a = start + width * (count - 1)
                if (keys[start:start + width] != keys[a:a + width] or
                        validation[start:start + width] != validation[a:a + width] or
                        commands[start:start + width] != commands[a:a + width]):
                    break
                # Splitting counts above 255 is supported by the renderer.
                full, tail = divmod(count, 255)
                unit_length = lengths[start + width] - lengths[start] - 1
                encoded = full * (unit_length + 6)
                if tail:
                    encoded += unit_length + (len(str(tail)) + 3 if tail > 1 else 1)
                candidate = encoded + cost[start + width * count]
                if candidate < cost[start]:
                    cost[start] = candidate
                    choices[start] = (width, count)
                count += 1
    patterns, uses = [], []
    start = 0
    while start < n:
        width, count = choices[start]
        patterns.append(tuple(keys[start:start + width]))
        uses.append(Occurrence(len(patterns) - 1, start, count))
        start += width * count
    return patterns, uses


def _compress(units, commands, max_depth, weighted):
    """Return text and a hierarchy report; loops never change expanded tokens.

    Limit depth to two, and repeat counts to 255. Relative state changes are
    safe because the original command stream, not just sounding notes, repeats.
    """
    report, ids = [], {}

    def visit(lo, hi, depth, parent):
        if depth >= max_depth:
            return ' '.join(commands[lo:hi])
        patterns, uses = (weighted_patterns(units[lo:hi], commands[lo:hi]) if weighted
                          else find_patterns(units[lo:hi]))
        output = []
        for use in uses:
            width = len(patterns[use.pattern_id])
            start = lo + use.group_start
            stop = start + width * use.repeats
            if use.repeats == 1:
                output.append(commands[start])
                continue
            signature = tuple(u.signature() for u in units[start:start + width])
            pattern_id = ids.setdefault(signature, len(ids))
            occurrence = len(report)
            row = dict(occurrence_id=occurrence, parent_id=parent, depth=depth,
                       pattern_id=pattern_id, unit_start=start, unit_end=stop,
                       unit_width=width, repeats=use.repeats, status='candidate')
            report.append(row)
            iterations = []
            validations = []
            for repeat in range(use.repeats):
                a = start + repeat * width
                iterations.append(visit(a, a + width, depth + 1, occurrence))
                validations.append(tuple(getattr(u, 'validation_key', u.signature())
                                         for u in units[a:a + width]))
            # Initialization may make the first iteration different. Compress
            # only consecutive equal emitted iterations, retaining the others.
            pieces, applied = [], False
            a = 0
            while a < len(iterations):
                b = a + 1
                while (b < len(iterations) and iterations[b] == iterations[a]
                       and validations[b] == validations[a]):
                    b += 1
                plain = ' '.join(iterations[a:b])
                remaining, chunks = b - a, []
                while remaining:
                    count = min(255, remaining)
                    chunks.append(f'[{iterations[a]}]{count}' if count > 1 else iterations[a])
                    remaining -= count
                loop = ' '.join(chunks)
                if b - a > 1 and len(loop) < len(plain):
                    pieces.append(loop)
                    applied = True
                else:
                    pieces.append(plain)
                a = b
            row['status'] = ('applied' if applied else 'different_state'
                             if len(set(validations)) > 1 else 'different_commands_or_no_saving')
            output.append(' '.join(pieces))
        return ' '.join(output)

    return visit(0, len(units), 0, ''), report


def compress(units, commands, max_depth=2):
    """Keep the shorter of greedy hierarchy and cost-aware repeat placement."""
    greedy = _compress(units, commands, max_depth, False)
    weighted = _compress(units, commands, max_depth, True)
    chosen, strategy = (weighted, 'text_cost') if len(weighted[0]) < len(greedy[0]) else (greedy, 'unit_count')
    for row in chosen[1]:
        row['strategy'] = strategy
        row['candidate_status'] = row['status']
    return chosen


def project_notes(notes, chip, body, note_cuts):
    units = group_notes(notes, chip)
    commands = [' '.join(body[note_cuts[u.start]:note_cuts[u.end]]) for u in units]
    text, report = compress(units, commands)
    return text, units, report


def dump_units(dump_path, channels):
    if not dump_path:
        return
    prefix = str(dump_path).removesuffix('.target_notes.csv') + '.performed'
    unit_rows, loop_rows, metadata = [], [], {}
    for ch, (notes, units, report) in channels.items():
        for row in report:
            loop_rows.append(dict(ch=ch, **row))
        for unit_id, unit in enumerate(units):
            members = notes[unit.start:unit.end]
            paths = [dict(occurrence_id=r['occurrence_id'], pattern_id=r['pattern_id'],
                          depth=r['depth'], status=r['status'], strategy=r['strategy'],
                          candidate_status=r['candidate_status']) for r in report
                     if r['unit_start'] <= unit_id < r['unit_end']]
            indices = [index for n in members for index in n.segment_indices]
            unit_rows.append((ch, unit_id, unit.kind, members[0].start,
                              members[-1].start + members[-1].length,
                              json.dumps(indices), json.dumps(unit.key), json.dumps(paths)))
            for index in indices:
                metadata[ch, index] = (unit_id, unit.kind, json.dumps(paths))
    with open(prefix + '.units.csv', 'w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('ch', 'unit_id', 'kind', 'tick_start', 'tick_end',
                         'segment_indices', 'signature', 'loop_path'))
        writer.writerows(unit_rows)
    fields = ('ch', 'occurrence_id', 'parent_id', 'depth', 'pattern_id', 'unit_start',
              'unit_end', 'unit_width', 'repeats', 'status', 'strategy', 'candidate_status')
    with open(prefix + '.loops.csv', 'w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(loop_rows)
    path = Path(str(dump_path).replace('.target_notes.csv', '.segments.csv'))
    if not path.exists():
        return
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields, rows = list(reader.fieldnames), list(reader)
    columns = ('performed_unit_id', 'performed_unit_kind', 'performed_loop_path')
    counts = Counter()
    for row in rows:
        ch = int(row['ch'])
        values = metadata.get((ch, counts[ch]), ('', '', '[]'))
        counts[ch] += 1
        row.update(zip(columns, values))
    fields.extend(c for c in columns if c not in fields)
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
