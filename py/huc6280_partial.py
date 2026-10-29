"""Explicit whole-channel HuC force view; original native evidence stays intact."""
import hashlib
import itertools
import struct

from huc6280 import analyze
from vgm_loop import read_loop_metadata
from vgm_timing import command_times


def _filtered(raw, keep):
    events=list(command_times(raw));start=events[0].address
    header=bytearray(raw[:start]);body=bytearray();mapping={};selected=0;loop_at=None
    loop=read_loop_metadata(raw)
    for index,event in enumerate(events):
        if event.address==loop['loop_address']:loop_at=start+len(body)
        stop=events[index+1].address if index+1<len(events) else event.address+1
        command=raw[event.address:stop]
        if event.command==0xb9:
            register=command[1]&127
            if register==0:selected=command[2]&7
            if 2<=register<=7 and selected not in keep:continue
            if register in (8,9):continue  # LFO voices are excluded below.
        mapping[len(mapping)]=index
        body.extend(command)
    result=header+body
    struct.pack_into('<I',result,0x14,0)
    struct.pack_into('<I',result,0x1c,loop_at-0x1c if loop_at is not None else 0)
    relative=int.from_bytes(raw[0x14:0x18],'little')
    if relative:
        at=0x14+relative
        if raw[at:at+4]!=b'Gd3 ' or at+12>len(raw):raise ValueError('Invalid source GD3 metadata')
        end=at+12+int.from_bytes(raw[at+8:at+12],'little')
        if end>len(raw):raise ValueError('Truncated source GD3 metadata')
        struct.pack_into('<I',result,0x14,len(result)-0x14);result.extend(raw[at:end])
    struct.pack_into('<I',result,4,len(result)-4)
    return bytes(result),mapping


def project_subset(raw, trace):
    from huc6280_projection import project,ProjectionError
    if trace.issues:
        raise ProjectionError('HuC6280 source issues cannot be bypassed by force: '+', '.join(trace.issues))
    allowed={0xb9,0x61,0x62,0x63,0x64,0x66,*range(0x70,0x80)}
    if any(e.command not in allowed for e in command_times(raw)):
        raise ProjectionError('HuC6280 force cannot silently omit mixed/unsupported source commands')
    active={s.channel for s in trace.segments if s.active}
    blocked=set()
    for segment in trace.segments:
        if not segment.active:continue
        if segment.state.mode=='dda' or (segment.state.mode=='wave' and not segment.state.waveform_complete):
            blocked.add(segment.channel)
        if segment.lfo_control&3:blocked.update((0,1))
    for event in trace.states:
        state=event.channels[event.selected_channel]
        if event.write.register==6 and state.enabled and not state.dda_mode:
            blocked.add(event.selected_channel)
    candidates=sorted(active-blocked)
    failures=[]
    # Six source channels bound this search to at most63 nonempty subsets.
    # Validate each candidate normally; force never bypasses a source guard.
    for count in range(len(candidates),0,-1):
        for members in itertools.combinations(candidates,count):
            filtered,mapping=_filtered(raw,set(members))
            try:result=project(filtered,analyze(filtered))
            except (ValueError,OverflowError) as error:
                failures.append(str(error));continue
            if not result.summary['source_channels']:continue
            def original(value):return mapping[value] if value is not None else None
            for row in (*result.controls,*result.writes):
                row['source_event_id']=original(row['source_event_id'])
            for row in result.gates:
                for field in ('start_source_event_id','end_source_event_id'):row[field]=original(row[field])
            omitted=sorted(active-set(members))
            result.summary.update(source_sha256=hashlib.sha256(raw).hexdigest(),
                force_partial=True,retained_source_channels=list(members),
                omitted_source_channels=omitted,
                omissions=[dict(source_channel=ch,action='omit_whole_source_channel',
                    reason='unsupported_or_conflicting_MGS_projection',
                    modes=sorted({s.state.mode for s in trace.segments if s.channel==ch and s.active})) for ch in omitted],
                native_source_unchanged=True,source_event_ids='original_input_command_ordinals')
            return result
    raise ProjectionError('HuC6280 force: no validated nonempty target subset; '+
        (failures[0] if failures else 'all active channels require unsupported DDA/LFO/wave handling'))
