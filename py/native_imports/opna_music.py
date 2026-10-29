"""Native OPNA musical gates retaining ordered source Segment membership.

An FM gate owns all internal control slices. Repeated identical snapshots are
not separate notes; raw/native dumps retain zero-time edges and released state.
"""
from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import csv
import json
from pathlib import Path


@dataclass(frozen=True)
class Control:
    start: int
    end: int
    state: object
    segment_ids: tuple
    event_ids: tuple


@dataclass(frozen=True)
class Gate:
    part: str
    channel: int
    continuity_id: int
    start: int
    end: int
    controls: tuple
    source_segment_ids: tuple
    source_event_ids: tuple

    @property
    def key(self):
        return ('fm', self.end-self.start,
                tuple((c.start-self.start,c.end-c.start,semantic_state(c.state))
                      for c in self.controls))


def semantic_state(state):
    return (state.key_mask,state.fnum,state.block,state.algorithm,state.feedback,
            state.left_enabled,state.right_enabled,state.ams,state.pms,
            state.operators,state.lfo_enabled,state.lfo_rate,
            state.fm_prescale_divisor,state.channel3_special_enabled,state.csm_enabled)


def _evidence_index(records, key_events=None):
    buckets = {}
    for ordinal, record in enumerate(records):
        if (key_events is not None and record.chip_instance == 0
                and getattr(record, 'register', None) == 0x28):
            key_events[record.ch].append(record)
        buckets.setdefault((record.ch, record.continuity_id), []).append((ordinal, record))
    result = {}
    for identity, members in buckets.items():
        ordered = all(a[1].vgmticks <= b[1].vgmticks
                      for a, b in zip(members, members[1:]))
        if not ordered:
            members.sort(key=lambda member: member[1].vgmticks)
        result[identity] = ([member[1].vgmticks for member in members], members, ordered)
    return result


def _evidence_between(index, identity, start, end):
    times, members, ordered = index.get(identity, ((), (), True))
    selected = members[bisect_left(times, start):bisect_right(times, end)]
    if not ordered:
        selected = sorted(selected, key=lambda member: member[0])
    return [member[1] for member in selected]


def build_fm_gates(analysis):
    result={}
    segment_index = _evidence_index(analysis.segments)
    key_events = {channel: [] for channel in range(6)}
    event_index = _evidence_index(analysis.events, key_events)
    positive = {channel: [] for channel in range(6)}
    for segment in analysis.segments:
        if (segment.ch in positive and segment.chip_instance == 0
                and segment.state.key_mask and segment.duration_samples > 0):
            positive[segment.ch].append(segment)
    key_event_times = {channel: [event.vgmticks for event in events]
                       for channel, events in key_events.items()}
    partial_change_times = {channel: sorted(event.vgmticks for event in events
                         if event.state.key_mask and
                         event.state.key_mask ^ event.rising_mask ^ event.falling_mask)
                            for channel, events in key_events.items()}
    full_off_times = {channel: sorted(event.vgmticks for event in events
                                     if event.falling_mask and not event.state.key_mask)
                      for channel, events in key_events.items()}
    for channel in range(6):
        segments = positive[channel]
        groups=[]
        for segment in segments:
            if (not groups or groups[-1][-1].vgmticks_end != segment.vgmticks
                    or (groups[-1][-1].continuity_id != segment.continuity_id
                        and (bisect_left(full_off_times[channel], segment.vgmticks)
                             != bisect_right(full_off_times[channel], segment.vgmticks)
                             or bisect_left(partial_change_times[channel], segment.vgmticks)
                             == bisect_right(partial_change_times[channel], segment.vgmticks)))):
                groups.append([])
            groups[-1].append(segment)
        gates=[]
        for group in groups:
            slices=[]
            for s in group:
                if slices and semantic_state(slices[-1].state)==semantic_state(s.state):
                    previous=slices.pop()
                    slices.append(Control(previous.start,s.vgmticks_end,previous.state,
                                          previous.segment_ids+(s.segment_id,),
                                          previous.event_ids+(s.source_event_id,)))
                else:
                    slices.append(Control(s.vgmticks,s.vgmticks_end,s.state,
                                          (s.segment_id,),(s.source_event_id,)))
            start,end=group[0].vgmticks,group[-1].vgmticks_end
            # Include zero-duration native members and ordered operator edges.
            identities = {(channel, member.continuity_id) for member in group}
            keys = key_events[channel]
            times = key_event_times[channel]
            gate_keys = keys[bisect_left(times, start):bisect_right(times, end)]
            starting_off = max((event.source_event_id for event in gate_keys
                                if event.vgmticks == start and not event.state.key_mask
                                and event.falling_mask), default=-1)
            for event in gate_keys:
                if (event.state.key_mask and event.vgmticks < end
                        and (event.vgmticks != start
                             or event.source_event_id > starting_off)):
                    identities.add((channel, event.continuity_id))
            evidence = [member for identity in sorted(identities)
                        for member in _evidence_between(segment_index, identity, start, end)]
            events = [member for identity in sorted(identities)
                      for member in _evidence_between(event_index, identity, start, end)]
            if len(identities) > 1:
                evidence.sort(key=lambda member: member.segment_id)
                events.sort(key=lambda member: member.source_event_id)
            # A same-sample partial onset/change is still an ordered operator
            # transition. Insert its zero-time control before the final slice.
            for event in reversed(events):
                if (getattr(event, 'register', None) == 0x28 and event.state.key_mask
                        and (event.rising_mask or event.falling_mask)):
                    matching = next((i for i, control in enumerate(slices)
                                     if control.start == event.vgmticks), None)
                    if matching is not None and slices[matching].state.key_mask != event.state.key_mask:
                        slices.insert(matching, Control(event.vgmticks, event.vgmticks,
                                                       event.state, (), (event.source_event_id,)))
            gates.append(Gate('ABCHIJ'[channel],channel,group[0].continuity_id,start,end,
                              tuple(slices),tuple(s.segment_id for s in evidence),
                              tuple(e.source_event_id for e in events)))
        if gates:result['ABCHIJ'[channel]]=tuple(gates)
    return result


def dump_gates(tracks,path):
    with Path(path).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(('unit_id','part','source_start','source_end','continuity_id',
                         'source_segment_ids','source_event_ids','control_trajectory'))
        for part,gates in tracks.items():
            for index,gate in enumerate(gates):
                trajectory=[dict(start=c.start,end=c.end,segment_ids=c.segment_ids,
                                 event_ids=c.event_ids,fnum=c.state.fnum,block=c.state.block,
                                 algorithm=c.state.algorithm,feedback=c.state.feedback,
                                 key_mask=c.state.key_mask,
                                 operator_tl=[o.tl for o in c.state.operators])
                            for c in gate.controls]
                writer.writerow((f'{part}:{index}',part,gate.start,gate.end,gate.continuity_id,
                                 json.dumps(gate.source_segment_ids),
                                 json.dumps(gate.source_event_ids),json.dumps(trajectory)))


def audit_fm_key_edges(analysis, tracks):
    """Require every ordered source key transition to survive gate projection.

    Positive intervals alone cannot prove this: a pulse or a temporary partial
    mask can begin and end at the same source sample.  EOF may truncate a held
    gate, but observed edges must have corresponding musical gate boundaries.
    """
    gates = [gate for channel_gates in tracks.values() for gate in channel_gates]
    by_event = {event_id: gate for gate in gates for event_id in gate.source_event_ids}
    onset_gates = set()
    for event in analysis.events:
        if event.chip_instance != 0 or event.register != 0x28:
            continue
        evidence = f'ch{event.ch} sample {event.vgmticks} source event {event.source_event_id}'
        gate = by_event.get(event.source_event_id)
        if event.rising_mask or event.falling_mask:
            if gate is None:
                raise ValueError(f'FM zero-duration/unmatched key transition: {evidence}')
            previous_mask = event.state.key_mask ^ event.rising_mask ^ event.falling_mask
            if not previous_mask and event.rising_mask:
                if gate.start != event.vgmticks:
                    raise ValueError(f'FM key-on boundary is not represented: {evidence}')
                onset_gates.add(id(gate))
            elif not event.state.key_mask and event.falling_mask:
                if gate.end != event.vgmticks:
                    raise ValueError(f'FM key-off boundary is not represented: {evidence}')
            elif event.state.key_mask:
                if not any(control.start == event.vgmticks
                           and control.state.key_mask == event.state.key_mask
                           for control in gate.controls):
                    raise ValueError(f'FM operator key control is not represented: {evidence}')
    missing = [gate for gate in gates if id(gate) not in onset_gates]
    if missing:
        raise ValueError('FM gate lacks an observed source key-on')
