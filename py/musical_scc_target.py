"""Real SCC companion for layered FM, reconstructed from musical curves."""
import math
from itertools import groupby

from musical_wave_target import curve_value, record, times


def project_scc(performance):
    devices={d.device_id:d for d in performance.devices if d.chip=='scc'}
    units=[u for u in performance.units if u.device_id in devices]
    if not units:raise ValueError('No sounding SCC units for the real-SCC layered profile')
    if len(devices)!=1:raise ValueError('Real-SCC layered profiles support one SCC cartridge')
    device=next(iter(devices.values()))
    if device.instance:raise ValueError('Real-SCC layered profiles require the primary SCC instance')
    if not device.clock_hz:raise ValueError('SCC clock is unknown')
    # Nonstandard frequency/phase modes need an explicit musical target model.
    if any(c.device_id==device.device_id and c.kind=='scc_native_parameter'
           for c in performance.controls):
        raise ValueError('SCC extended test/phase controls need an explicit layered projection')
    voices={v.voice_id:v for v in performance.voices}
    plus=bool(device.clock_raw & 0x80000000)
    clock=device.clock_hz | (0x80000000 if plus else 0)
    rows=[];waves={};mask=0
    actions=[]
    for u in units:
        if not 0<=u.channel<5:raise ValueError('SCC musical channel exceeds five voices')
        points=set(times(u))
        loop=performance.song_loop_sample
        if loop is not None and u.start_sample<loop<u.end_sample:points.add(loop)
        actions.extend((at,0,u) for at in sorted(points))
        if not (u.end_sample==performance.end_sample and performance.song_loop_sample is not None
                and dict(u.parameters).get('termination','source_observation_end') in
                    ('observation_end','source_observation_end')):
            actions.append((u.end_sample,1 if u.start_sample==u.end_sample else -1,u))
    ordered=sorted(actions,key=lambda a:(a[0],a[1],a[2].unit_id))
    if not plus:
        preview={}
        for at,group in groupby(ordered,key=lambda a:a[0]):
            for _,rank,u in group:
                if rank:preview.pop(u.channel,None)
                else:
                    voice=voices.get(curve_value(u.voice_curve,at))
                    preview[u.channel]=dict(voice.parameters).get('waveform_hex') if voice else None
            if 3 in preview and 4 in preview and preview[3]!=preview[4]:
                raise ValueError('Ordinary SCC shared channel 4/5 waveforms conflict')
    loop=performance.song_loop_sample
    if loop is not None:
        row=record(units[0],loop,bytes((0xd2,3,0,0)),
            'SCC loop boundary mask initialization',-2)
        row['scc_clock_raw']=clock;rows.append(row)
    for at,rank,u in ordered:
        ch=u.channel
        def emit(port,reg,value,reason):
            row=record(u,at,bytes((0xd2,port,reg,value)),reason,rank)
            row['scc_clock_raw']=clock;rows.append(row)
        if rank:
            mask &= ~(1<<ch)
            emit(2,ch,0,'SCC musical gate end');emit(3,0,mask,'SCC enable mask')
            continue
        hz=curve_value(u.pitch_curve,at)
        level=curve_value(u.volume_curve,at)
        voice=voices.get(curve_value(u.voice_curve,at))
        wave=dict(voice.parameters).get('waveform_hex') if voice else None
        if not wave or len(bytes.fromhex(wave))!=32:
            raise ValueError('SCC musical voice requires a complete 32-byte waveform')
        if hz is None or not math.isfinite(hz) or hz<=0 or level is None:
            raise ValueError('SCC musical pitch/volume is unknown')
        # Inverse of the source interpretation, using original integer VGM time.
        period=round(device.clock_hz/(16*hz)-1)
        if not 0<=period<=4095:raise ValueError('SCC musical pitch exceeds native period range')
        if not 0<=level<=15:raise ValueError('SCC musical level exceeds native range')
        bank=ch if plus else min(ch,3)
        # Reassert on gate starts as well as changes; loop entry can inherit
        # a different ending waveform from the previous traversal.
        if waves.get(bank)!=wave or at==u.start_sample or at==performance.song_loop_sample:
            for index,value in enumerate(bytes.fromhex(wave)):
                emit(4 if plus else 0,bank*32+index,value,'SCC musical waveform')
            waves[bank]=wave
        emit(1,2*ch,period&255,'SCC musical pitch low')
        emit(1,2*ch+1,period>>8,'SCC musical pitch high')
        emit(2,ch,round(level),'SCC musical volume')
        mask |= 1<<ch;emit(3,0,mask,'SCC musical gate enable')
    return rows,{},dict(clock_hz=device.clock_hz,scc_plus=plus,
        channels=sorted({u.channel for u in units}),input_representation='NativePerformance',
        fm_companion_gain=1.0)
