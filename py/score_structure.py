"""Source-time score evidence shared by blueprint and target repeat proposals.

Semitone equality proposes motifs; it never replaces native pitch/detune or
authorizes a target note boundary. Dynamics and timbres stay in native music.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import cached_property
from bisect import bisect_left, bisect_right
import csv
import json
import math
from pathlib import Path

from source_loop_plan import SourceLoopPlan


def midi_pitch(frequency):
    if frequency is None or not math.isfinite(frequency) or frequency <= 0:
        return None
    return round(69+12*math.log2(frequency/440))


def pitch_points(unit):
    current = None
    for at, frequency in unit.pitch_curve:
        if at <= unit.start_sample:
            current = midi_pitch(frequency)
    points = [(unit.start_sample, current)]
    for at, frequency in unit.pitch_curve:
        value = midi_pitch(frequency)
        if unit.start_sample < at < unit.end_sample and value != points[-1][1]:
            points.append((at, value))
    return tuple(points)


@dataclass(frozen=True)
class ScoreEvent:
    event_id: str
    device_id: str
    section: str
    channel: int
    start_sample: int
    end_sample: int
    midi: int | None
    articulation: str
    unit_ids: tuple = ()
    source_indices: tuple = ()

    @property
    def key(self):
        return self.end_sample-self.start_sample, self.midi, self.articulation


@dataclass(frozen=True)
class ScoreGuide:
    events: tuple
    unit_points: tuple
    patterns: tuple
    decisions: tuple
    source_sha256: str

    @cached_property
    def point_map(self):
        return dict(self.unit_points)

    def points(self, unit):
        return self.point_map[unit.unit_id] if unit.unit_id in self.point_map else pitch_points(unit)

    def dump(self, folder, stem):
        prefix = Path(folder)/f'{stem}.score_guide'
        data = asdict(self)
        data.update(time_domain='original_source_samples', sample_rate=44100,
                    pitch_equality='nearest_semitone_candidates_only',
                    executable=False, volume_and_timbre_in_native_source=True)
        prefix.with_suffix('.score_guide.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
        with Path(str(prefix)+'.events.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(ScoreEvent.__dataclass_fields__))
            writer.writeheader()
            for event in self.events:
                writer.writerow({k: json.dumps(v) if isinstance(v, tuple) else v for k,v in asdict(event).items()})


def build(performance, *, repeats=False):
    devices = {d.device_id:d for d in performance.devices}
    grouped = defaultdict(list)
    points = []
    for unit in performance.units:
        device = devices[unit.device_id]
        if (device.chip in ('msm6258','msm6295','segapcm','c140') or 'pcm' in unit.section.lower()
                or unit.role in ('pcm','sample') or unit.end_sample <= unit.start_sample):
            continue
        values = pitch_points(unit)
        points.append((unit.unit_id, values))
        for index, ((start,midi), stop) in enumerate(zip(values, [v[0] for v in values[1:]]+[unit.end_sample])):
            grouped[unit.device_id,unit.section,unit.channel].append(ScoreEvent(
                f'{unit.unit_id}:score:{index}',unit.device_id,unit.section,unit.channel,
                start,stop,midi,'hold' if index else 'attack', (unit.unit_id,),unit.source_indices))
    events,patterns,decisions = [],[],[]
    for part, sounding in sorted(grouped.items()):
        rows=[];cursor=0;overlap=False
        for event in sorted(sounding,key=lambda e:(e.start_sample,e.end_sample,e.event_id)):
            if event.start_sample < cursor:
                overlap=True
            if event.start_sample > cursor:
                rows.append(ScoreEvent(f'{part}:rest:{cursor}',*part,cursor,event.start_sample,None,'rest'))
            rows.append(event);cursor=max(cursor,event.end_sample)
        if cursor < performance.end_sample:
            rows.append(ScoreEvent(f'{part}:rest:{cursor}',*part,cursor,performance.end_sample,None,'rest'))
        events.extend(rows)
        if repeats and not overlap:
            plan=SourceLoopPlan.build([r.key for r in rows],strategy='structural')
            _,report=plan.render([repr(r.key) for r in rows])
            patterns.extend(dict(row,source_part=part,basis='source_time_score_candidates') for row in report)
        if overlap:
            decisions.append(dict(source_part=part,action='abstain_repeat_guide',reason='overlapping_source_parts'))
    return ScoreGuide(tuple(events),tuple(points),tuple(patterns),tuple(decisions),performance.source_sha256)


def partition_key(note, previous=None):
    """Propose target score motifs without changing accepted partitioning."""
    hold = (previous is not None and not note.rest and not previous.rest
            and previous.start+previous.length == note.start
            and bool(set(getattr(previous,'gate_ids',())) & set(getattr(note,'gate_ids',()))))
    return (note.length,note.rest,None if note.rest else (note.segment.octave,note.segment.scale),
            'rest' if note.rest else 'hold' if hold else 'attack')


def pitched_trajectory_key(spans):
    """Merge pitch-equivalent internal slices without touching their source."""
    result=[]
    for offset,duration,pitch in spans:
        if duration <= 0:continue
        if result and result[-1][2]==pitch and result[-1][0]+result[-1][1]==offset:
            previous=result[-1];result[-1]=(previous[0],previous[1]+duration,pitch)
        else:
            result.append((offset,duration,pitch))
    return tuple(result)


def variant_representatives(plan, rows, chip):
    """Retain every exact curve/settings variant at each structural leaf slot."""
    from psg_scc_performance import settings
    slots={}
    def visit(nodes, offset=0):
        for node in nodes:
            if node.children:
                width=(node.end-node.start)//node.repeats
                for repeat in range(node.repeats):
                    visit(node.children,offset+repeat*width)
            else:
                slots[node.start+offset]=node.start
    visit(plan.tree)
    seen=set();selected=[]
    for index,note in enumerate(rows):
        variant=(slots[index],note.rest,() if note.rest else settings(note.segment,chip),tuple(note.runs))
        if variant not in seen:
            selected.append(note);seen.add(variant)
    return selected


class GuidedLoopPlan:
    """Score candidates cannot weaken exact command equality or old compaction."""
    def __init__(self, guide, exact):
        self.guide,self.exact,self.selected=guide,exact,guide
        self.comparison=None

    def __getattr__(self,name):
        return getattr(self.selected,name)

    def render(self,commands):
        guided,guided_report=self.guide.render(commands)
        exact,exact_report=self.exact.render(commands)
        selected=len(guided) <= len(exact)
        self.selected=self.guide if selected else self.exact
        self.comparison=dict(selected='score_guide' if selected else 'exact_fallback',
            score_characters=len(guided),exact_characters=len(exact),
            policy='shorter exactly equivalent command text; not a compiled-byte estimate')
        return (guided,guided_report) if selected else (exact,exact_report)

    def dump(self,path,members,report=()):
        self.selected.dump(path,members,report)
        self.guide.dump(str(path).replace('.csv','.score_candidate.csv'),members)
        Path(str(path).replace('.csv','.score_selection.json')).write_text(
            json.dumps(self.comparison,indent=2)+'\n',encoding='utf-8')


def map_partitions(guide, performance):
    """Inspectable many-to-many mapping; never turn guide cuts into attacks."""
    events=defaultdict(list)
    for event in guide.events:
        if event.unit_ids:
            events[event.device_id,event.channel].append(event)
    native=dict(performance.source_segments)
    indexed={}
    for key,items in events.items():
        items.sort(key=lambda e:(e.start_sample,e.end_sample))
        ends=[];last=0
        for event in items:
            last=max(last,event.end_sample);ends.append(last)
        indexed[key]=(items,[e.start_sample for e in items],ends)
    rows=[]
    for channel,notes in performance.channels:
        for index,note in enumerate(notes):
            segments=[native[channel][i] for i in note.segment_indices]
            known=bool(segments) and all(s.vgmticks is not None and s.vgmticks_end is not None for s in segments)
            start=min(s.vgmticks for s in segments) if known and segments else None
            stop=max(s.vgmticks_end for s in segments) if known and segments else None
            matches=[]
            if known:
                items,starts,ends=indexed.get((performance.chip+':0',channel),([],[],[]))
                matches=[e for e in items[bisect_right(ends,start):bisect_left(starts,stop)]
                         if start < e.end_sample]
            cuts=sorted({e.start_sample for e in matches if start < e.start_sample < stop})
            rows.append(dict(channel=channel,note_index=index,source_segment_indices=note.segment_indices,
                source_start=start,source_end=stop,score_event_ids=[e.event_id for e in matches],
                source_unit_ids=sorted({u for e in matches for u in e.unit_ids}),
                internal_guide_cuts=cuts,executable_cuts_applied=False,
                status='rest' if note.rest else 'unknown_source_time' if not known else
                    'unmapped' if not matches else 'many_to_many' if len(matches)>1 else 'mapped'))
    return rows


def guided_partition_keys(guide, performance):
    """Refine the source guide onto whole accepted notes, without new cuts."""
    events={e.event_id:e for e in guide.events}
    notes=dict(performance.channels)
    keys={}
    for row in map_partitions(guide,performance):
        channel,index=row['channel'],row['note_index'];note=notes[channel][index]
        if note.rest:
            keys[channel,index]=partition_key(note)
            continue
        matched=[events[e] for e in row['score_event_ids']]
        intervals=sorted((max(row['source_start'],e.start_sample),min(row['source_end'],e.end_sample))
                         for e in matched)
        cursor=row['source_start'];contiguous=bool(intervals)
        for start,stop in intervals:
            if start != cursor:contiguous=False
            cursor=stop
        if (not contiguous or cursor != row['source_end'] or len(row['source_unit_ids']) != 1
                or note.gate_ambiguity):
            keys[channel,index]=('exact_unmapped_partition',note.structural_key)
            continue
        signature=tuple((e.midi,'attack' if e.start_sample==row['source_start']
                         and e.articulation=='attack' else 'hold') for e in matched)
        keys[channel,index]=('source_score_candidate',note.length,signature)
    return keys
