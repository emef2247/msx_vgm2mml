"""Reversible exact-repeat structure, independent of target notation and macros.

All adjacent repeat candidates survive in the catalog, including overlapping
alternatives. A compact source tree is one view of that catalog, not a promise
to emit brackets for every marker. Width/depth/repeat counts have no target cap.
"""
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from hierarchical_loops import Node


@dataclass(frozen=True)
class Repeat:
    start: int
    width: int
    max_repeats: int

    @property
    def end(self):
        return self.start + self.width * self.max_repeats


def candidates(keys):
    """Find every (start, body width) with at least two equal adjacent bodies.

    Diagonal common-prefix scans cost O(n**2) scalar comparisons. A row encodes
    every repeat count from 2 through max_repeats, rather than discarding shorter
    choices. This comparison always sees expanded source units, not marker IDs.
    """
    intern = {}
    symbols = [intern.setdefault(key, len(intern)) for key in keys]
    n = len(symbols)
    by_start = [[] for _ in symbols]
    for width in range(1, n // 2 + 1):
        common = 0
        for start in range(n - width - 1, -1, -1):
            common = common + 1 if symbols[start] == symbols[start + width] else 0
            if common >= width:
                by_start[start].append(Repeat(start, width, 1 + common // width))
    return tuple(tuple(rows) for rows in by_start)


def expanded_indices(nodes):
    for node in nodes:
        if not node.children:
            yield node.start
        else:
            body = tuple(expanded_indices(node.children))
            for _ in range(node.repeats):
                yield from body


def unroll(node):
    """Restore original source positions for one marker, preserving occurrences."""
    return tuple(Node(i, i + 1) for i in range(node.start, node.end))


@dataclass
class LoopStructure:
    keys: tuple
    catalog: tuple
    tree: tuple

    @classmethod
    def build(cls, keys):
        keys = tuple(keys)
        catalog = candidates(keys)

        @lru_cache(None)
        def solve(lo, hi):
            if lo == hi:
                return (), (0, 0)
            # A repeated body of distinct symbols reaches the lower bound of
            # one stored leaf per symbol and one repeat node; avoid a cubic
            # interval search for long constant/ABAB-like tracks.
            for repeat in catalog[lo]:
                if repeat.end >= hi and (hi - lo) % repeat.width == 0:
                    count = (hi - lo) // repeat.width
                    body = keys[lo:lo + repeat.width]
                    if count > 1 and len(set(body)) == repeat.width:
                        children = tuple(Node(i, i + 1) for i in range(lo, lo + repeat.width))
                        return (Node(lo, hi, children, count),), (repeat.width, 1)
            costs = {hi: (0, 0)}
            choices = {}
            for start in range(hi - 1, lo - 1, -1):
                suffix = costs[start + 1]
                costs[start] = (suffix[0] + 1, suffix[1])
                choices[start] = (Node(start, start + 1), start + 1)
                for repeat in catalog[start]:
                    maximum = min(repeat.max_repeats, (hi - start) // repeat.width)
                    if maximum < 2:
                        continue
                    body, body_cost = solve(start, start + repeat.width)
                    for count in range(2, maximum + 1):
                        stop = start + repeat.width * count
                        tail = costs[stop]
                        cost = (body_cost[0] + tail[0], body_cost[1] + tail[1] + 1)
                        if cost < costs[start]:
                            costs[start] = cost
                            choices[start] = (Node(start, stop, body, count), stop)
            result, start = [], lo
            while start < hi:
                node, start = choices[start]
                result.append(node)
            return tuple(result), costs[lo]

        tree, _ = solve(0, len(keys))
        if tuple(keys[i] for i in expanded_indices(tree)) != keys:
            raise AssertionError('Structural loops changed the source sequence')
        return cls(keys, catalog, tree)

    def dump(self, prefix):
        prefix = str(prefix)
        with Path(prefix + '.repeat_candidates.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('start_unit', 'body_units', 'min_repeats', 'max_repeats', 'max_end_unit'))
            for rows in self.catalog:
                writer.writerows((r.start, r.width, 2, r.max_repeats, r.end) for r in rows)
        patterns, markers = {}, []
        def visit(nodes, parent='', depth=1):
            for node in nodes:
                if not node.children:
                    continue
                width = (node.end - node.start) // node.repeats
                signature = self.keys[node.start:node.start + width]
                pattern_id = patterns.setdefault(signature, len(patterns))
                identity = len(markers)
                markers.append((identity, pattern_id, parent, depth, node.start, node.end, width, node.repeats))
                visit(node.children, identity, depth + 1)
        visit(self.tree)
        with Path(prefix + '.loop_structure.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('marker_id', 'pattern_id', 'parent_marker_id', 'depth',
                             'start_unit', 'end_unit', 'body_units', 'repeats'))
            writer.writerows(markers)
