"""Reversible Segment children beneath OPLL continuous-note source loops."""
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path

from source_loop_plan import SourceLoopPlan, expanded_tokens


@dataclass
class OpllLoopPlan:
    outer: SourceLoopPlan
    members: tuple
    inner: tuple
    inner_reports: list = field(default_factory=list)
    selection: str = 'outer_only'

    @classmethod
    def build(cls, members, units, items, strategy='structural'):
        outer = SourceLoopPlan.build(((u.kind, u.duration, u.validation_key) for u in units),
                                     strategy=strategy)
        cache, children = {}, []
        for note in members:
            keys = tuple(items[i].signature() for i in note.segment_indices)
            if keys not in cache:
                cache[keys] = SourceLoopPlan.build(keys, strategy=strategy)
            children.append(cache[keys])
        return cls(outer, tuple(tuple(n.segment_indices) for n in members), tuple(children))

    def render(self, body, boundaries):
        plain, nested, reports = [], [], []
        for indices, child in zip(self.members, self.inner):
            commands = [' '.join(body[boundaries[i]:boundaries[i + 1]]) for i in indices]
            plain.append(' '.join(commands))
            text, rows = child.render(commands)
            nested.append(text)
            reports.append(rows)
        baseline, baseline_rows = self.outer.render(plain)
        result, rows = self.outer.render(nested)
        # Different inner spellings must not hide an otherwise usable parent.
        if len(result) <= len(baseline):
            self.selection = 'inner'
        else:
            result, rows = baseline, baseline_rows
            self.selection = 'outer_only'
        self.inner_reports = reports
        if expanded_tokens(result) != expanded_tokens(' '.join(plain)):
            raise AssertionError('OPLL inner loops changed emitted commands')
        return result, rows

    def marker_rows(self):
        patterns, result = {}, []
        for note_id, (indices, plan, reports) in enumerate(zip(self.members, self.inner, self.inner_reports)):
            offset = len(result)
            for row in reports:
                width, pattern = row['unit_width'], row['pattern_id']
                signature = plan.keys[pattern:pattern + width]
                pattern_id = patterns.setdefault(signature, len(patterns))
                start, end = row['unit_start'], row['unit_end']
                result.append(dict(note_unit_id=note_id, pattern_id=pattern_id,
                    occurrence_id=offset + row['occurrence_id'],
                    parent_occurrence_id='' if row['parent_id'] == '' else offset + row['parent_id'],
                    depth=row['depth'], segment_start=indices[start], segment_end=indices[end - 1] + 1,
                    segment_width=width, repeats=row['repeats'], emitted_repeats=row['emitted_repeats'],
                    status=row['status'], target_selected=self.selection == 'inner'))
        return result

    def annotations(self):
        paths = {i: dict(opll_note_unit_id=note_id, opll_inner_loop_path=[])
                 for note_id, indices in enumerate(self.members) for i in indices}
        for row in self.marker_rows():
            for index in range(row['segment_start'], row['segment_end']):
                position = index - row['segment_start']
                paths[index]['opll_inner_loop_path'].append(dict(
                    pattern_id=row['pattern_id'], occurrence_id=row['occurrence_id'],
                    parent_occurrence_id=row['parent_occurrence_id'], depth=row['depth'],
                    repeat_index=position // row['segment_width'],
                    pattern_step=position % row['segment_width'], status=row['status'],
                    target_selected=row['target_selected']))
        return paths

    def dump(self, path, members, report):
        self.outer.dump(path, members, report)
        prefix = str(path).removesuffix('.csv')
        rows = self.marker_rows()
        columns = ('note_unit_id', 'pattern_id', 'occurrence_id', 'parent_occurrence_id',
                   'depth', 'segment_start', 'segment_end', 'segment_width', 'repeats',
                   'emitted_repeats', 'status', 'target_selected')
        with Path(prefix + '.inner_loops.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        with Path(prefix + '.inner_repeat_candidates.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('note_unit_id', 'segment_start', 'segment_width', 'min_repeats',
                             'max_repeats', 'max_segment_end'))
            for note_id, (indices, plan) in enumerate(zip(self.members, self.inner)):
                if plan.structure is not None:
                    for candidates in plan.structure.catalog:
                        for candidate in candidates:
                            writer.writerow((note_id, indices[candidate.start], candidate.width, 2,
                                             candidate.max_repeats, indices[candidate.end - 1] + 1))


def annotate_segments(path, plans):
    """Append note/inner-marker paths without rewriting native Segment cells."""
    path = Path(path)
    if not path.exists():
        return
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields, rows = list(reader.fieldnames), list(reader)
    for column in ('opll_note_unit_id', 'opll_inner_loop_path'):
        if column not in fields:
            fields.append(column)
    annotations = {ch: plan.annotations() for ch, plan in plans.items()}
    indices = {}
    for row in rows:
        ch = int(row['ch'])
        index = indices.get(ch, 0)
        indices[ch] = index + 1
        values = annotations.get(ch, {}).get(index, {})
        row['opll_note_unit_id'] = values.get('opll_note_unit_id', '')
        row['opll_inner_loop_path'] = json.dumps(values.get('opll_inner_loop_path', []))
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
