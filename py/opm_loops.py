"""OPM source phrase structure, derived only from immutable native Segments.

No MDX ticks, note spelling, voice IDs or output commands participate in keys.
Held/released describe gate state, not acoustic silence. All source intervals,
including zero-duration transitions, remain members of a reversible plan.
"""
from dataclasses import dataclass
from source_loop_plan import SourceLoopPlan, expanded_tokens


def segment_key(segment):
    # Test/LFO reset and timer writes can have effects beyond stored state.
    effect = (segment.register, segment.data) if segment.register in (1, 0x14) else None
    return (segment.duration_samples, segment.state, segment.rising_mask,
            segment.falling_mask, effect)


@dataclass(frozen=True)
class OpmPhraseUnit:
    start: int
    end: int
    members: tuple
    kind: str
    key: tuple


@dataclass
class OpmSourceLoops:
    rows: tuple
    units: tuple
    outer: SourceLoopPlan
    inner: tuple

    @classmethod
    def build(cls, rows):
        rows = tuple(sorted(rows, key=lambda s: (s.vgmticks,
                     -1 if s.source_event_id is None else s.source_event_id, s.segment_id)))
        if len({(s.chip_instance, s.ch) for s in rows}) > 1:
            raise ValueError('OPM loop analysis requires one chip/channel lane')
        cuts = [0]
        for i in range(1, len(rows)):
            previous, current = rows[i-1], rows[i]
            if (current.rising_mask or bool(current.state.key_mask) != bool(previous.state.key_mask)
                    or current.vgmticks != previous.vgmticks_end):
                cuts.append(i)
        if rows:
            cuts.append(len(rows))
        groups = []
        for start, stop in zip(cuts, cuts[1:]):
            first, last = rows[start], rows[stop-1]
            members = tuple(range(start, stop))
            # Zero-time released setup is not an additional musical rest.
            # Keep every member with the preceding note (or initial setup).
            if (groups and not first.state.key_mask and last.vgmticks_end == first.vgmticks
                    and not any(rows[i].rising_mask for i in members)
                    and not any(rows[i].register in (1, 0x14) for i in members)):
                groups[-1] = (*groups[-1], *members)
            else:
                groups.append(members)
        units, children, cache = [], [], {}
        for members in groups:
            first = rows[members[0]]
            held = bool(first.state.key_mask)
            positive = [rows[i] for i in members if rows[i].state.key_mask] if held else []
            end = max((s.vgmticks_end for s in positive), default=rows[members[-1]].vgmticks_end)
            trajectory = []
            for i in members:
                segment = rows[i]
                if held and not segment.state.key_mask and segment.duration_samples == 0:
                    # Off edges still participate; inactive same-sample pitch
                    # setup has no sounding duration and stays in the inner plan.
                    if segment.rising_mask or segment.falling_mask:
                        trajectory.append((segment.vgmticks-first.vgmticks,
                                           (0, segment.state, segment.rising_mask, segment.falling_mask, None)))
                    continue
                trajectory.append((segment.vgmticks-first.vgmticks, segment_key(segment)))
            following = members[-1]+1
            if (held and following < len(rows) and rows[following].falling_mask
                    and rows[following].vgmticks == end):
                off = rows[following]
                trajectory.append((end-first.vgmticks, (0, off.state, off.rising_mask, off.falling_mask, None)))
            kind = 'held' if held else 'released'
            key = (kind, end-first.vgmticks, tuple(trajectory))
            units.append(OpmPhraseUnit(first.vgmticks, end, members, kind, key))
            keys = tuple(segment_key(rows[i]) for i in members)
            if keys not in cache:
                cache[keys] = SourceLoopPlan.build(keys, strategy='structural')
            children.append(cache[keys])
        outer = SourceLoopPlan.build((unit.key for unit in units), strategy='structural')
        return cls(rows, tuple(units), outer, tuple(children))

    def annotations(self):
        result = {s.segment_id: dict(opm_phrase_unit_id=number, opm_source_loop_path=[])
                  for number, unit in enumerate(self.units) for s in (self.rows[i] for i in unit.members)}
        def visit(plan, membership, level, phrase_id=None):
            patterns, next_id = {}, [0]
            def walk(nodes, offset=0, parent=None, depth=0):
                for node in nodes:
                    if not node.children:
                        continue
                    width = (node.end-node.start)//node.repeats
                    pattern = patterns.setdefault(plan.keys[node.start:node.start+width], len(patterns))
                    occurrence = next_id[0]; next_id[0] += 1
                    for position in range(node.start+offset, node.end+offset):
                        for index in membership[position]:
                            result[self.rows[index].segment_id]['opm_source_loop_path'].append(dict(
                                level=level, phrase_unit_id=phrase_id, pattern_id=pattern,
                                occurrence_id=occurrence, parent_occurrence_id=parent,
                                depth=depth+1, repeat_index=(position-node.start-offset)//width,
                                pattern_step=(position-node.start-offset)%width, repeats=node.repeats))
                    for iteration in range(node.repeats):
                        walk(node.children, offset+iteration*width, occurrence, depth+1)
            walk(plan.tree)
        visit(self.outer, tuple(u.members for u in self.units), 'phrase')
        for number, (unit, plan) in enumerate(zip(self.units, self.inner)):
            visit(plan, tuple((i,) for i in unit.members), 'segment', number)
        return result


def build_source_loops(segments):
    lanes = {}
    for segment in segments:
        lanes.setdefault((segment.chip_instance, segment.ch), []).append(segment)
    return {lane: OpmSourceLoops.build(rows) for lane, rows in lanes.items()}


@dataclass
class OpmLoopProjection:
    source: OpmSourceLoops
    target_rows: tuple
    status: str
    inner_reports: tuple = ()

    @classmethod
    def build(cls, source, target_units, tick):
        # Only mapping uses target ticks. The source structure was built earlier.
        by_event = {s.source_event_id: i for i, s in enumerate(source.rows) if s.source_event_id is not None}
        owner = {i: number for number, unit in enumerate(source.units) for i in unit.members}
        positions, previous = [], -1
        for unit in target_units:
            index = by_event.get(unit.source_event_ids[0]) if unit.source_event_ids else None
            if unit.kind == 'note':
                index = next((by_event[event] for event in unit.source_event_ids
                              if event in by_event and source.rows[by_event[event]].rising_mask), index)
            if index is None:
                index = next((i for i, s in enumerate(source.rows)
                              if tick(s.vgmticks) <= unit.start_tick < tick(s.vgmticks_end)), None)
            if index is None:
                return cls(source, (), 'unmapped_time_boundary')
            phrase = source.units[owner[index]]
            if (index < previous or unit.start_tick < tick(phrase.start)
                    or unit.end_tick > tick(phrase.end)):
                return cls(source, (), 'target_crosses_source_phrase')
            for event_id in unit.source_event_ids[1:]:
                other = by_event.get(event_id)
                # A note command includes its terminal KeyOff, at the next
                # released unit's boundary. That is its end, not a new attack.
                terminal_off = (unit.kind == 'note' and other is not None
                                and source.rows[other].state.key_mask == 0
                                and tick(source.rows[other].vgmticks) == unit.end_tick)
                pitch_setup = (unit.kind == 'note' and other is not None
                               and source.rows[other].duration_samples == 0
                               and source.rows[other].register in (0x28+source.rows[other].ch,
                                                                  0x30+source.rows[other].ch)
                               and tick(source.rows[other].vgmticks) == unit.start_tick)
                if other is None or (owner[other] != owner[index] and not terminal_off and not pitch_setup):
                    return cls(source, (), 'target_combines_source_edges')
            positions.append(index); previous = index
        return cls(source, tuple(positions), 'mapped')

    def render(self, commands):
        if self.status != 'mapped':
            return ' '.join(commands), []
        if len(commands) != len(self.target_rows):
            raise ValueError('OPM target units no longer match source-loop projection')
        rows = [[] for _ in self.source.rows]
        for index, command in zip(self.target_rows, commands):
            rows[index].append(command)
        plain, nested, inner_reports = [], [], []
        for unit, child in zip(self.source.units, self.source.inner):
            body = [' '.join(rows[i]) for i in unit.members]
            plain.append(' '.join(' '.join(body).split()))
            text, reports = child.render(body)
            nested.append(' '.join(text.split()))
            inner_reports.append(reports)
        baseline, baseline_report = self.source.outer.render(plain)
        result, report = self.source.outer.render(nested)
        if len(result) > len(baseline):
            result, report = baseline, baseline_report
            inner_reports = [[] for _ in self.source.units]
        self.inner_reports = tuple(inner_reports)
        if expanded_tokens(result) != expanded_tokens(' '.join(commands)):
            raise AssertionError('OPM source-loop projection reordered target commands')
        report = [dict(row, level='phrase') for row in report]
        report.extend(dict(row, level='segment', phrase_unit_id=number)
                      for number, rows in enumerate(inner_reports) for row in rows)
        return result, report
