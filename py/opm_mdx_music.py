"""Musical MDX target units from immutable OPM Segments.

An attack owns its complete pitch/level/control trajectory up to key-off.
Only actual continuations are tied. Source note trajectories nominate loops;
the shared MGSDRV loop planner validates rendered commands before folding.
"""
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from opm_mdx import mdx_tick, projected_samples
from opm_mdx_structure import note_spelling, voice_key
from mdx_compaction import compact
from source_loop_plan import SourceLoopPlan

# Register-bank order M1,M2,C1,C2 (not Key register bit order).
CARRIERS = (8, 8, 8, 8, 12, 14, 14, 15)


def source_plan(keys):
    """Reuse the shared exact planner between provably unrepeatable leaves.

    A symbol occurring once cannot belong to an adjacent repeated body: that
    body would contain it at least twice. Such leaves are exact separators,
    not width/depth caps. Region catalogs are restored to global source indices.
    """
    from hierarchical_loops import Node
    from loop_structure import LoopStructure, Repeat, candidates
    keys=tuple(keys)
    counts=Counter(keys)
    cuts=[i for i,key in enumerate(keys) if counts[key]==1]
    if not cuts:
        # The shared solver already shortcuts complete repetitions of a body
        # of distinct symbols. The same lower bound applies to a periodic
        # region with a partial prefix: retain that prefix, then one repeat.
        # Equal-cost ordering prefers leaves before repeats in the shared DP.
        period=next((i for i in range(1,len(keys)) if keys[i]==keys[0]),0)
        if (period and len(keys)//period>=2 and len(set(keys[:period]))==period
                and all(key==keys[i%period] for i,key in enumerate(keys))):
            prefix=len(keys)%period
            tree=tuple(Node(i,i+1) for i in range(prefix))+(Node(prefix,len(keys),
                tuple(Node(i,i+1) for i in range(prefix,prefix+period)),len(keys)//period),)
            structure=LoopStructure(keys,candidates(keys),tree)
            return SourceLoopPlan(tree,keys,structure)
        return SourceLoopPlan.build(keys,strategy='structural')
    tree=[];catalog=[() for _ in keys];start=0
    def shifted(node,offset):
        return Node(node.start+offset,node.end+offset,
                    tuple(shifted(child,offset) for child in node.children),node.repeats)
    for stop in cuts+[len(keys)]:
        if start<stop:
            region=source_plan(keys[start:stop])
            tree.extend(shifted(node,start) for node in region.tree)
            for index,rows in enumerate(region.structure.catalog):
                catalog[start+index]=tuple(Repeat(row.start+start,row.width,row.max_repeats) for row in rows)
        if stop<len(keys): tree.append(Node(stop,stop+1))
        start=stop+1
    structure=LoopStructure(keys,tuple(catalog),tuple(tree))
    return SourceLoopPlan(structure.tree,keys,structure)


def infer_clock(segments, end_vgmticks):
    """Choose a score clock only when every observed boundary remains intact.

    The six-sample bound is the existing @t255 projection resolution. It is
    not a fit percentage: one violating boundary rejects a coarser clock.
    Tempo is inferred, never claimed to be the original composer's marking.
    Equivalent clocks are retained in the report; conventional note lengths
    and proximity to quarter=120 only choose notation among safe candidates.
    """
    times = sorted({0, end_vgmticks} | {s.vgmticks for s in segments})
    attacks = {}
    for s in segments:
        if s.rising_mask:
            attacks.setdefault(s.ch, []).append(s.vgmticks)
    intervals = [b-a for ts in attacks.values() for a,b in zip(ts,ts[1:]) if b>a]
    candidates = []
    for multiplier in range(1, 256):
        ticks = [mdx_tick(t, multiplier) for t in times]
        errors = [projected_samples(k, multiplier)-t for k,t in zip(ticks,times)]
        if max(map(abs, errors), default=0) > 6:
            continue
        if multiplier > 1 and any(a < b and ka == kb for a,b,ka,kb in zip(times,times[1:],ticks,ticks[1:])):
            continue
        # Counting conventional values ranks only representationally equivalent
        # safe clocks; it cannot allow a timing or Key-edge discrepancy.
        lengths = [mdx_tick(d, multiplier) for d in intervals]
        conventional = sum(n in (12,24,36,48,72,96,144,192) for n in lengths)
        bpm = 78125/(16*multiplier)
        candidates.append(dict(multiplier=multiplier, tempo_byte=256-multiplier,
                               inferred_bpm=bpm, conventional_intervals=conventional,
                               max_abs_error_samples=max(map(abs, errors),default=0)))
    if not candidates:
        raise ValueError('No MDX clock represents the observed boundaries')
    chosen = max(candidates,key=lambda c:(c['conventional_intervals'],
                 -abs(c['inferred_bpm']-120), c['multiplier']))
    return dict(chosen=chosen, candidates=candidates,
                basis='all native control times and common song end; notation tie-break only')


def duration_spelling(duration):
    for dots in range(3):
        numerator = 192*((1 << (dots+1))-1)
        denominator = duration*(1 << dots)
        if numerator % denominator == 0:
            value = numerator//denominator
            if value in (1,2,4,8,16,32,64,128,192):
                return str(value)+'.'*dots
    return '%'+str(duration)


def timed(name, duration, *, held=False):
    """MDX limits require ties for long notes, not independent retriggers."""
    limit = 65535 if name == 'r' else 256
    pieces = []
    while duration:
        n = min(duration, limit)
        duration -= n
        pieces.append(name+duration_spelling(n))
        if name != 'r' and (duration or held):
            pieces.append('&')
    return ' '.join(pieces)


def tone_and_level(state):
    key = voice_key(state)
    if key is None:
        return None
    ops, alg, fb, mask = key
    carrier = CARRIERS[alg]
    attenuation = min(row[5] for i,row in enumerate(ops) if carrier & (1<<i))
    base = tuple(tuple(value-attenuation if field==5 and carrier & (1<<i) else value
                       for field,value in enumerate(row)) for i,row in enumerate(ops))
    return (base, alg, fb, mask), attenuation


def level_for_tone(state, tone):
    ops,alg,_,_ = tone
    carrier = CARRIERS[alg]
    observed = tuple(op.tl for op in state.operators)
    deltas = {observed[i]-ops[i][5] for i in range(4) if carrier & (1<<i)}
    if len(deltas)!=1:
        return None
    delta = deltas.pop()
    expected = tuple(min(127,row[5]+delta) if carrier & (1<<i) else row[5]
                     for i,row in enumerate(ops))
    raw_matches=all(value==expected[(reg-0x60)//8] for reg,value in state.channel_registers
                    if 0x60<=reg<0x80)
    return delta if 0<=delta<=127 and expected==observed and raw_matches else None


@dataclass(frozen=True)
class MusicUnit:
    track: str
    start_tick: int
    end_tick: int
    source_start_vgmticks: int
    source_end_vgmticks: int
    kind: str
    command: str
    source_event_ids: tuple
    source_segment_ids: tuple
    trajectory: tuple
    voice_id: int | None = None
    target_note: str = ''
    fallback_reason: str = ''
    unlooped_command: str = ''

    @property
    def key(self):
        trajectory = self.trajectory
        if self.kind == 'note':
            onset = next((i for i, (_,reg,data,_) in enumerate(trajectory)
                          if reg == 8 and data >> 3), 0)
            # Released zero-time setup has no sounding interval. It remains
            # in the dump/membership, but does not define performed equality.
            trajectory = trajectory[onset:]
        return self.kind, self.end_tick-self.start_tick, trajectory


@dataclass
class MusicalMdx:
    units: dict
    voices: tuple
    plans: dict
    reports: dict
    text: str
    plain_text: str
    uncompacted_text: str
    compaction: tuple
    inner_reports: tuple = ()

    def summary(self):
        flat = [u for units in self.units.values() for u in units]
        depth=maximum=0
        for line in self.text.splitlines():
            if not (len(line)>1 and line[0] in 'ABCDEFGH' and line[1]==' '): continue
            for ch in line:
                if ch=='[': depth+=1; maximum=max(maximum,depth)
                elif ch==']': depth-=1
        return dict(notation='structured', musical_note_units=sum(u.kind=='note' for u in flat),
                    note_units=sum(u.kind=='note' for u in flat),
                    raw_units=sum(bool(u.fallback_reason) for u in flat), voices=len(self.voices),
                    fallback_reasons=dict(Counter(u.fallback_reason for u in flat if u.fallback_reason)),
                    emitted_loop_commands=sum(line.count('[') for line in self.text.splitlines()
                        if len(line)>1 and line[0] in 'ABCDEFGH' and line[1]==' '),
                    max_loop_depth=maximum,
                    applied_loops=sum(r['status']=='applied' for rows in self.reports.values() for r in rows),
                    applied_inner_loops=sum(r['status']=='applied' for r in self.inner_reports),
                    plain_mml_chars=len(self.plain_text), structured_mml_chars=len(self.text))

    def dump(self, prefix, *, segments_csv=None):
        prefix=Path(prefix)
        prefix.parent.mkdir(parents=True,exist_ok=True)
        Path(str(prefix)+'.plain.mml').write_text(self.plain_text,encoding='utf-8')
        Path(str(prefix)+'.uncompacted.mml').write_text(self.uncompacted_text,encoding='utf-8')
        with Path(str(prefix)+'.compaction.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=('track','token_index','action','before','after','reason','bytes_saved'))
            writer.writeheader();writer.writerows(self.compaction)
        with Path(str(prefix)+'.inner_loops.csv').open('w',newline='',encoding='utf-8') as stream:
            fields=list(self.inner_reports[0]) if self.inner_reports else ['track','note_unit','status']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(self.inner_reports)
        rows,annotation=[],{}
        for track,units in self.units.items():
            for index,u in enumerate(units):
                row=asdict(u)
                row.pop('trajectory')
                row['unit_id']=f'{track}:{index}'
                row['loop_path']=[dict(r) for r in self.reports[track] if r['unit_start']<=index<r['unit_end']]
                row['trajectory']=json.dumps([(offset,reg,data,asdict(state)) for offset,reg,data,state in u.trajectory],separators=(',',':'))
                for field in ('source_event_ids','source_segment_ids','loop_path'):
                    row[field]=json.dumps(row[field],separators=(',',':'))
                rows.append(row)
                for sid in u.source_segment_ids: annotation.setdefault(sid,[]).append(row['unit_id'])
            self.plans[track].dump(str(prefix)+f'.{track}.loops.csv',
                                  [u.source_segment_ids for u in units],self.reports[track])
        with Path(str(prefix)+'.units.csv').open('w',newline='',encoding='utf-8') as stream:
            fields=list(rows[0]) if rows else ['unit_id']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        with Path(str(prefix)+'.voices.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream);writer.writerow(('voice_id','algorithm','feedback','key_mask','operator_rows'))
            for i,(ops,alg,fb,mask) in enumerate(self.voices): writer.writerow((i,alg,fb,mask,json.dumps(ops)))
        if segments_csv:
            path=Path(segments_csv)
            # Keep the integrated view without loading the entire native CSV
            # a second time; large catalogs can contain hundreds of thousands
            # of self-contained state rows.
            with TemporaryDirectory(dir=path.parent,prefix='mdx-annotation-') as temporary:
                target=Path(temporary)/path.name
                with path.open(newline='',encoding='utf-8') as source,target.open('w',newline='',encoding='utf-8') as output:
                    reader=csv.DictReader(source);fields=list(reader.fieldnames)
                    if 'mdx_music_unit_ids' not in fields: fields.append('mdx_music_unit_ids')
                    writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
                    for row in reader:
                        row['mdx_music_unit_ids']=json.dumps(annotation.get(int(row['segment_id']),[]))
                        writer.writerow(row)
                target.replace(path)


def build_music(projection, segments, *, title='OPM music', loops=True):
    by_event = {}
    for s in segments:
        if s.source_event_id is not None:
            by_event.setdefault(s.source_event_id,{})[s.ch]=s
    tracks={'A':[]}
    for w in projection.writes: tracks.setdefault(w.mdx_track,[]).append(w)
    voices,unit_tracks={},{}
    inner_reports=[]
    inner_cache={}
    for track,writes in sorted(tracks.items()):
        ch=ord(track)-65
        units=[];cursor=0;source_cursor=0;i=0
        def state(write):
            return by_event[write.source_event_id].get(ch)
        def make(members,start,end,kind,command,voice=None,pitch='',reason='',
                 source_start=None,source_end=None,unlooped=None):
            if source_start is None:
                source_start=members[0].source_vgmticks if members else source_cursor
            if source_end is None:
                source_end=members[-1].source_vgmticks if members else projection.source_end_vgmticks
            trajectory=tuple((w.mdx_tick-start,w.register,w.data,state(w).state)
                             for w in members if state(w) is not None)
            return MusicUnit(track,start,end,source_start,source_end,kind,command,
                tuple(w.source_event_id for w in members),
                tuple(sid for w in members for sid in w.source_segment_ids),trajectory,voice,pitch,reason,
                command if unlooped is None else unlooped)
        while i<len(writes):
            first=writes[i]
            if first.mdx_tick>cursor:
                units.append(make([],cursor,first.mdx_tick,'rest',timed('r',first.mdx_tick-cursor),
                                  source_end=first.source_vgmticks))
                cursor=first.mdx_tick
                source_cursor=first.source_vgmticks
            s=state(first)
            reason=''
            onset=i
            while (onset<len(writes) and writes[onset].mdx_tick==cursor
                   and writes[onset].register!=8):
                onset+=1
            if (onset<len(writes) and writes[onset].mdx_tick==cursor
                    and state(writes[onset]) is not None and state(writes[onset]).rising_mask):
                first=writes[onset];s=state(first)
            else:
                onset=i
            if first.register==8 and s is not None and s.rising_mask:
                off=onset+1
                while off<len(writes) and writes[off].register!=8: off+=1
                tone=tone_and_level(s.state)
                spelling=note_spelling(s.state)
                terminal=state(writes[off]) if off<len(writes) else None
                if s.rising_mask!=s.state.key_mask or s.falling_mask or first.data & 128:
                    reason='partial_or_reserved_key_edge'
                elif terminal is None or terminal.state.key_mask or writes[off].data!=ch:
                    reason='no_complete_terminal_keyoff'
                elif writes[off].mdx_tick<=cursor:
                    reason='zero_duration_attack'
                elif tone is None or spelling is None:
                    reason='unknown_or_unencodable_voice_pitch'
                elif any(w.mdx_tick==cursor and (w.register in (0x20+ch,0x28+ch,0x30+ch) or w.register>=0x40)
                         for w in writes[onset+1:off]):
                    # @voice/pan/pitch are loaded by the first timed note.
                    # A post-Key update before that note would be overwritten.
                    # Preserve ordered controls rather than invent a new onset
                    # state or insert a positive duration before the update.
                    reason='same_tick_post_key_setup'
                elif s.state.noise_enabled==1:
                    reason='noise_requires_explicit_controls'
                elif any(note_spelling(state(w).state) is None for w in writes[onset:off] if state(w) is not None):
                    reason='unencodable_pitch_transition'
                elif tone[0] not in voices and len(voices)>=256:
                    reason='voice_bank_full'
                if not reason:
                    base,attenuation=tone
                    vid=voices.setdefault(base,len(voices))
                    octv,name,detune=spelling
                    pan=dict(s.state.channel_registers)[0x20+ch]>>6
                    body=[f'y{w.register},{w.data}' for w in writes[i:onset]
                          if not (w.register==0x20+ch or w.register in (0x28+ch,0x30+ch) or w.register>=0x40)]
                    body.append(f'@{vid} @v{127-attenuation} p{pan} q8 D{detune} o{octv}')
                    position=onset+1;start=cursor;current=s.state
                    slices=[];keys=[];pending=[];effects=[]
                    while start<writes[off].mdx_tick:
                        stop=position
                        next_time=writes[position].mdx_tick if position<off else writes[off].mdx_tick
                        if next_time>start:
                            o,n,d=note_spelling(current)
                            slices.append(' '.join(pending+[f'D{d} o{o}',timed(n,next_time-start,held=next_time<writes[off].mdx_tick)]))
                            keys.append((next_time-start,current,tuple(effects)))
                            pending=[];effects=[]
                            start=next_time
                        if position>=off: break
                        while stop<off and writes[stop].mdx_tick==start: stop+=1
                        group=writes[position:stop]
                        updated=next((state(w).state for w in reversed(group) if state(w) is not None),current)
                        level=level_for_tone(updated,base)
                        # A uniform carrier attenuation is a channel volume,
                        # not a new instrument. Independent operator edits stay y.
                        tl_group=any(0x60<=w.register<0x80 for w in group)
                        for w in group:
                            if w.register in (0x28+ch,0x30+ch) and start<writes[off].mdx_tick: continue
                            if tl_group and level is not None and 0x60<=w.register<0x80: continue
                            pending.append(f'y{w.register},{w.data}')
                            if w.register in (1,0x14): effects.append((w.register,w.data))
                        if tl_group and level is not None: pending.append(f'@v{127-level}')
                        current=updated;position=stop
                    # Controls exactly at the release boundary have no held
                    # duration but still define the released chip state.
                    # Retain them explicitly after the note's automatic off.
                    keys=tuple(keys)
                    if keys not in inner_cache:
                        inner_cache[keys]=source_plan(keys)
                    folded,child_report=inner_cache[keys].render(slices) if loops else (' '.join(slices),[])
                    inner_reports.extend(dict(r,track=track,note_unit=len(units)) for r in child_report)
                    release=[f'y{w.register},{w.data}' for w in writes[position:off]]
                    unlooped=' '.join(body+[' '.join(slices)]+pending+release)
                    body.append(folded)
                    body.extend(pending)
                    body.extend(release)
                    units.append(make(writes[i:off+1],cursor,writes[off].mdx_tick,'note',' '.join(body),vid,f'o{octv}{name}',
                                      unlooped=unlooped))
                    cursor=writes[off].mdx_tick;source_cursor=writes[off].source_vgmticks;i=off+1
                    continue
            # Released/setup controls and unsupported edges remain explicit.
            # Never attach an unrelated attack to the preceding control group.
            stop=i+1
            while stop<len(writes):
                following=state(writes[stop])
                if writes[stop].register==8 and following is not None and (following.rising_mask or following.falling_mask): break
                stop+=1
            # Leave same-time setup with the following real edge, so an
            # ordinary voice/note can represent it without redundant y writes.
            if stop<len(writes):
                stamp=writes[stop].mdx_tick
                while stop>i+1 and writes[stop-1].mdx_tick==stamp and writes[stop-1].register!=8:
                    stop-=1
            end=writes[stop].mdx_tick if stop<len(writes) else projection.end_mdx_tick
            source_end=writes[stop].source_vgmticks if stop<len(writes) else projection.source_end_vgmticks
            members=writes[i:stop]
            pieces=[];control_keys=[];position=0
            while position<len(members):
                after=position+1
                while after<len(members) and members[after].mdx_tick==members[position].mdx_tick:
                    after+=1
                group=members[position:after]
                following=members[after].mdx_tick if after<len(members) else end
                length=following-group[0].mdx_tick
                words=[f'y{w.register},{w.data}' for w in group]
                if length: words.append(timed('r',length))
                pieces.append(' '.join(words))
                control_keys.append((length,tuple((w.register,w.data,state(w).state if state(w) else None)
                                                  for w in group)))
                position=after
            control_keys=tuple(control_keys)
            if control_keys not in inner_cache:
                inner_cache[control_keys]=source_plan(control_keys)
            body,child_report=inner_cache[control_keys].render(pieces) if loops else (' '.join(pieces),[])
            inner_reports.extend(dict(r,track=track,note_unit=len(units)) for r in child_report)
            units.append(make(members,cursor,end,'controls',body,reason=reason,source_end=source_end,
                              unlooped=' '.join(pieces)))
            cursor=end;source_cursor=source_end;i=stop
        if cursor<projection.end_mdx_tick:
            units.append(make([],cursor,projection.end_mdx_tick,'rest',timed('r',projection.end_mdx_tick-cursor)))
        unit_tracks[track]=tuple(units)
    title=''.join(c for c in ' '.join(str(title).replace('"',"'").split()) if ord(c)>=32 and ord(c)!=127)
    header=[f'#title "{title}"','; Musical OPM notes and source-linked control trajectories.',
            f'; Tempo inferred from VGM; @t{256-projection.sample_multiplier} = {256*projection.sample_multiplier} us/tick.']
    for (ops,alg,fb,mask),vid in voices.items():
        header += [f'@{vid} = {{',*['  '+','.join(map(str,ops[i]))+',' for i in (0,2,1,3)],f'  {alg},{fb},{mask}','}']
    header.append(f'A @t{256-projection.sample_multiplier}')
    def wrapped(track,body):
        lines=[];line=track
        for word in body.split():
            if len(line)+len(word)+1>110: lines.append(line);line=track
            line+=' '+word
        if line!=track: lines.append(line)
        return lines
    plans,reports,plain,uncompacted,structured={}, {},header[:],header[:],header[:]
    decisions=[]
    for track,units in unit_tracks.items():
        commands=[u.command for u in units]
        plan=source_plan(u.key for u in units)
        text,report=plan.render(commands) if loops else (' '.join(commands),[])
        result,changes=compact(text,track,durations=loops)
        plans[track]=plan;reports[track]=report;decisions.extend(changes)
        plain+=wrapped(track,' '.join(u.unlooped_command for u in units))
        uncompacted+=wrapped(track,text);structured+=wrapped(track,result)
    return MusicalMdx(unit_tracks,tuple(voices),plans,reports,'\n'.join(structured)+'\n',
                      '\n'.join(plain)+'\n','\n'.join(uncompacted)+'\n',tuple(decisions),tuple(inner_reports))
