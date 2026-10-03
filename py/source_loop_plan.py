"""Executable source-note loop plans, created before target envelope assignment."""
import csv
from dataclasses import dataclass
from pathlib import Path
import re

from hierarchical_loops import experiment
from performed_patterns import Unit


def expanded_tokens(text):
    """Expand finite emitted loops for exact token preservation checks."""
    stack = [[]]
    for token in re.findall(r'\[|\]\d*|[^\s\[\]]+', text):
        if token == '[':
            stack.append([])
        elif token.startswith(']'):
            if len(stack) == 1:
                raise ValueError('Unmatched loop end')
            count = int(token[1:] or 2)
            if not 1 <= count <= 255:
                raise ValueError('Invalid finite repeat count')
            body = stack.pop()
            stack[-1].extend(body * count)
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError('Unmatched loop start')
    return tuple(stack[0])


@dataclass
class SourceLoopPlan:
    tree: tuple
    keys: tuple
    structure: object = None

    @classmethod
    def build(cls, keys, max_phrase=128, max_depth=3, strategy='retained'):
        keys = tuple(keys)
        if strategy == 'structural':
            from loop_structure import LoopStructure
            structure = LoopStructure.build(keys)
            return cls(structure.tree, keys, structure)
        units = [Unit(i, i + 1, 'source_note', key) for i, key in enumerate(keys)]
        # Equal costs per source note: no envelope IDs or MML spelling participate.
        tree = experiment(units, ['NOTEUNIT'] * len(keys), strategy,
                          max_phrase, max_depth, return_tree=True)
        return cls(tree, keys)

    def representatives(self):
        def visit(nodes):
            for node in nodes:
                if node.children:
                    yield from visit(node.children)
                else:
                    yield node.start
        return tuple(visit(self.tree))

    def render(self, commands):
        if len(commands) != len(self.keys):
            raise ValueError('Source plan no longer matches rendered notes')
        report = []

        def visit(nodes, offset=0, parent='', depth=0):
            output = []
            for node in nodes:
                if not node.children:
                    output.append(commands[node.start + offset])
                    continue
                width = (node.end - node.start) // node.repeats
                identity = len(report)
                row = dict(occurrence_id=identity, parent_id=parent, depth=depth,
                           pattern_id=node.start, unit_start=node.start + offset,
                           unit_end=node.end + offset, unit_width=width,
                           repeats=node.repeats, emitted_repeats=0,
                           status='expanded_different_commands', strategy='source_plan')
                report.append(row)
                iterations = [visit(node.children, offset + repeat * width, identity, depth + 1)
                              for repeat in range(node.repeats)]
                # An initializing first pass may differ. All passes still follow
                # this pre-existing tree, including nested children and controls.
                first = 0
                while first < len(iterations):
                    end = first + 1
                    while end < len(iterations) and iterations[end] == iterations[first]:
                        end += 1
                    plain = ' '.join(iterations[first:end])
                    # Target repeat limits do not limit the source structure.
                    chunks = []
                    remaining = end - first
                    while remaining:
                        count = min(255, remaining)
                        chunks.append(f'[{iterations[first]}]{count}' if count > 1 else iterations[first])
                        remaining -= count
                    loop = ' '.join(chunks)
                    if end - first > 1 and len(loop) < len(plain):
                        output.append(loop)
                        row['emitted_repeats'] += end - first
                        row['status'] = 'applied'
                    else:
                        output.append(plain)
                    first = end
            return ' '.join(output)

        text = visit(self.tree)
        for row in report:
            row['candidate_status'] = row['status']
        if expanded_tokens(text) != expanded_tokens(' '.join(commands)):
            raise AssertionError('Source loop projection changed emitted commands')
        return text, report

    def dump(self, path, members, report=()):
        """Keep all source members, structural markers and actual projection status."""
        if self.structure is not None:
            self.structure.dump(str(path).removesuffix('.csv'))
        if report:
            with Path(str(path).replace('.csv', '.projection.csv')).open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(report[0]))
                writer.writeheader()
                writer.writerows(report)
        representatives = set(self.representatives())
        with Path(path).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('note_index', 'segment_indices', 'structural_representative',
                             'source_key', 'projected_occurrences'))
            for i, key in enumerate(self.keys):
                markers = [(r['occurrence_id'], r['status']) for r in report
                           if r['unit_start'] <= i < r['unit_end']]
                writer.writerow((i, str(members[i]), int(i in representatives), str(key), str(markers)))
