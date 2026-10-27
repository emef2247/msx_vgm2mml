"""HuC native sounding units; target routing and PCM approximation stay later."""
from bisect import bisect_left,bisect_right
from collections import defaultdict
from huc6280 import analyze,attenuation_levels
from native_music import NativeUnit


def add_units(builder,root,stem):
    trace=analyze(builder.raw)
    trace.dump(root,stem)
    device=builder.device('huc6280')
    by_channel=defaultdict(list)
    for control in builder.controls:
        if control.device_id==device.device_id:
            by_channel[control.channel].append(control)
    indexed={key:([c.sample for c in rows],rows) for key,rows in by_channel.items()}
    def identities(channel,start,stop):
        result=[]
        for key in (None,channel):
            times,rows=indexed.get(key,([],[]))
            result.extend(rows[bisect_left(times,start):bisect_right(times,stop)])
        return tuple(c.control_id for c in sorted(result,key=lambda c:(c.sample,c.order)))
    rows=defaultdict(list)
    edges=defaultdict(list)
    for event in trace.states:
        if event.key_on_edge and event.selected_channel<6:
            edges[event.selected_channel].append((event.write.vgmticks,event.write.source_event_id))
    for index,segment in enumerate(trace.segments):rows[segment.channel].append((index,segment))
    for channel,segments in sorted(rows.items()):
        active=[];number=0
        def finish():
            nonlocal number
            if not active:return
            first,last=active[0][1],active[-1][1]
            mode=first.state.mode
            pitch=[];volume=[];voices=[]
            def append(curve,at,value):
                if not curve or curve[-1][1]!=value:curve.append((at,value))
            for _,segment in active:
                state=segment.state;at=segment.start_vgmticks
                hz=(trace.clock_hz/(32*(state.frequency or 4096))
                    if trace.clock_hz and mode=='wave' and not (channel<2 and segment.lfo_control&3) else None)
                append(pitch,at,hz)
                append(volume,at,(state.volume,*attenuation_levels(state.control,state.balance,segment.global_balance)))
                voice=builder.voice(device,mode,(('waveform_u5',state.waveform),
                    ('waveform_known',state.waveform_known),('waveform_id',state.waveform_id),
                    ('noise_control',state.noise_control),('lfo_frequency',segment.lfo_frequency),
                    ('lfo_control',segment.lfo_control)))
                append(voices,at,voice)
            section='pcm_dda' if mode=='dda' else mode
            builder.units.append(NativeUnit(f'huc6280:0:{channel}:gate:{number}',device.device_id,
                section,channel,first.start_vgmticks,last.end_vgmticks,tuple(pitch),tuple(volume),tuple(voices),
                identities(channel,first.start_vgmticks,last.end_vgmticks),tuple(i for i,_ in active),
                'pcm' if mode=='dda' else 'noise' if mode=='noise' else 'melody',
                (('boundary_origin','source_audibility_or_mode_transition'),
                 ('volume_domain','native_control_level_and_left_right_attenuation'),
                 ('dda_samples_retained_in_control_ids',mode=='dda'),
                 ('lfo_pitch_phase_unmodeled',any(s.lfo_control&3 for _,s in active)))))
            number+=1;active.clear()
        for index,segment in segments:
            if not segment.active:
                finish();continue
            retrigger=bool(active and any(active[-1][1].start_vgmticks < at <= segment.start_vgmticks
                and (segment.start_event_id is None or identity<=segment.start_event_id)
                for at,identity in edges[channel]))
            if active and (active[-1][1].end_vgmticks!=segment.start_vgmticks
                           or active[-1][1].state.mode!=segment.state.mode or retrigger):
                finish()
            active.append((index,segment))
        finish()
    report=builder.bundle['report']
    report['active_chips']=tuple(dict.fromkeys((*report['active_chips'],'huc6280')))
    report['analysis_available']['huc6280']=True
    report['command_counts']['huc6280']=len(trace.writes)
    report['interpretation_issues']['huc6280']=list(trace.issues)
    builder.decisions.extend(('huc6280_source_issue',issue) for issue in trace.issues)
    import json
    (root/f'{stem}.native.source.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
