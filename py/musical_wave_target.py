"""Project source musical curves to cartridge oscillators, never source traces."""
from collections import Counter
import math

from psg_scc_opm import carrier_tl, opm_pitch, square_voice, waveform_voice

AY_CLOCK = 1789773


def curve_value(curve, sample, default=None):
    value = default
    for at, candidate in curve:
        if at > sample:
            break
        value = candidate
    return value


def times(unit):
    return sorted({unit.start_sample, *(at for curve in (unit.pitch_curve, unit.volume_curve,
        unit.voice_curve) for at, _ in curve if unit.start_sample <= at < unit.end_sample)})


def record(unit, sample, command, reason, order=0):
    return dict(sample=sample, order=order, command=command, unit_id=unit.unit_id,
        device_id=unit.device_id, source_indices=unit.source_indices, reason=reason)


def _amplitude(unit, device, value):
    if value is None:
        return 0.
    if device.chip == 'huc6280':
        # Native tuple = register level, effective L/R attenuation. The latter
        # already includes channel and global balances; do not multiply twice.
        if isinstance(value, (tuple, list)) and len(value) >= 3:
            return (10 ** (-1.5 * value[1] / 20) + 10 ** (-1.5 * value[2] / 20)) / 2
        return 10 ** (-1.5 * (31-value) / 20)
    if device.chip == 'dcsg':
        return 0. if value >= 15 else 10 ** (-2 * value / 20)
    if device.chip == 'scc' or device.chip == 'nesapu':
        return max(0., min(1., value / 15))
    return 0. if value <= 0 else 10 ** (-3.19 * (15-(value & 15)) / 20)


def _spectrum(device, voice, losses):
    p = dict(voice.parameters) if voice else {}
    if p.get('waveform_hex'):
        return waveform_voice(p['waveform_hex'])
    waveform = p.get('waveform_u5')
    if waveform:
        known = p.get('waveform_known', ())
        if known and not all(known):
            losses['waveform_unknown_cells_approximated'] += 1
        values = [round((x-15.5)*8) for x in waveform]
    elif p.get('waveform_u6'):
        source = p['waveform_u6']
        # FDS has 64 wave cells; preserve one full cycle while reducing to 32.
        values = [round(((source[2*i]+source[2*i+1])/2-31.5)*4) for i in range(32)]
        losses['fds_64_to_32_wave_cells'] += 1
    elif device.chip == 'nesapu' and voice and voice.section == 'triangle':
        values = [round(((15-i if i<16 else i-16)-7.5)*16) for i in range(32)]
    elif device.chip == 'nesapu' and 'duty' in p:
        high = (4,8,16,24)[p['duty'] or 0]
        values = [124 if i<high else -124 for i in range(32)]
    else:
        return square_voice()
    return waveform_voice(bytes(max(-128,min(127,x)) & 255 for x in values).hex())


def project_waves(performance, target_chip, clock, reserved=(), *, force=False):
    devices = {d.device_id:d for d in performance.devices}
    voices = {v.voice_id:v for v in performance.voices}
    units = [u for u in performance.units if devices[u.device_id].chip in ('scc','huc6280','nesapu')
             and u.section not in ('pcm_dda','dpcm','noise') and u.role!='unpitched']
    lanes = sorted({(u.device_id,u.channel) for u in units})
    capacity = 8 if target_chip == 'opm' else 6
    free = [i for i in range(capacity) if i not in set(reserved)]
    allocation = dict(zip(lanes,free))
    rows, losses = [], Counter()
    spectra = {}
    for unit in units:
        target = allocation.get((unit.device_id,unit.channel))
        if target is None:
            losses['wave_channel_capacity_units_omitted'] += 1
            continue
        device=devices[unit.device_id]
        if device.chip=='huc6280' and any(isinstance(v,(tuple,list)) and len(v)>=3 and v[1]!=v[2] for _,v in unit.volume_curve):
            losses['wave_stereo_balance_folded_to_mono'] += 1
        if unit.role in ('noise','unpitched') or unit.section=='noise':
            # A finite periodic approximation is explicit, not mislabelled as
            # emulation of the source LFSR/noise transfer function.
            losses['noise_periodic_spectrum_approximation'] += 1
        if dict(unit.parameters).get('lfo_pitch_phase_unmodeled'):
            losses['huc_lfo_base_pitch_approximation'] += 1
        losses['four_harmonic_phase_free_wave_approximation'] += 1
        def emit(at,reg,val,reason,port=0):
            rows.append(record(unit,at,bytes((0x54 if target_chip=='opm' else 0x56+port,reg,val&255)),reason))
        started=False
        for at in times(unit):
            voice=voices.get(curve_value(unit.voice_curve,at))
            identity=voice.voice_id if voice else device.chip
            if identity not in spectra:spectra[identity]=_spectrum(device,voice,losses)
            spectrum=spectra[identity]
            p=dict(voice.parameters) if voice else {}
            hz=curve_value(unit.pitch_curve,at) or p.get('base_frequency_hz')
            if not hz or not math.isfinite(hz) or hz<=0:
                losses['unknown_wave_pitch_intervals_muted'] += 1
                if target_chip=='opm': emit(at,0x20+target,7,'unknown pitch mute')
                else: emit(at,0xb4+target%3,0,'unknown pitch mute',target//3)
                continue
            level=_amplitude(unit,device,curve_value(unit.volume_curve,at))
            if target_chip=='opm':
                kc,kf,_=opm_pitch(hz,clock,clamp=True)
                emit(at,0x20+target,0xc7,'additive voice stereo')
                emit(at,0x38+target,0,'disable LFO')
                emit(at,0x28+target,kc,'musical pitch')
                emit(at,0x30+target,kf,'musical pitch fraction')
                for bank,(harmonic,amplitude) in enumerate(zip(spectrum.harmonics,spectrum.amplitudes)):
                    offset=target+bank*8
                    for reg,value in ((0x40,harmonic),(0x60,carrier_tl(.125*level*amplitude)),
                                      (0x80,31),(0xa0,0),(0xc0,0),(0xe0,15)):
                        emit(at,reg+offset,value,'wave spectrum and musical volume')
                if not started:emit(at,8,0x78|target,'musical gate start')
            else:
                from opm_target_vgm import _opna_pitch
                block,fnum,*_=_opna_pitch(hz,clock)
                ch,port=target%3,target//3
                emit(at,0xb0+ch,7,'additive voice',port)
                emit(at,0xb4+ch,0xc0,'additive stereo',port)
                emit(at,0xa4+ch,(block<<3)|(fnum>>8),'musical pitch high atomic',port)
                emit(at,0xa0+ch,fnum&255,'musical pitch low commit',port)
                for bank,(harmonic,amplitude) in enumerate(zip(spectrum.harmonics,spectrum.amplitudes)):
                    offset=ch+bank*4
                    for reg,value in ((0x30,harmonic),(0x40,carrier_tl(.125*level*amplitude)),
                                      (0x50,31),(0x60,0),(0x70,0),(0x80,15),(0x90,0)):
                        emit(at,reg+offset,value,'wave spectrum and musical volume',port)
                if not started:emit(at,0x28,0xf0|ch|(4 if port else 0),'musical gate start')
            started=True
        if (unit.end_sample==performance.end_sample and performance.song_loop_sample is not None
            and dict(unit.parameters).get('termination','source_observation_end') in ('observation_end','source_observation_end')):
            continue
        if target_chip=='opm':
            emit(unit.end_sample,8,target,'musical gate end')
        else:
            emit(unit.end_sample,0x28,target%3|(4 if target>=3 else 0),'musical gate end')
        # Same-source adjacent gates: stop precedes the next gate's setup/start.
        rows[-1]['order']=-1 if unit.end_sample>unit.start_sample else 1
    if losses and not force:
        raise ValueError('Wave target requires approximation: '+', '.join(sorted(losses)))
    return rows,losses,allocation


def project_psg_opll(performance, *, dcsg_gain=.5, opna=False, force=False):
    """Render native PSG/SSG/OPLL units, plus DCSG's AY approximation."""
    from native_registers import encode_control
    devices={d.device_id:d for d in performance.devices}
    voices={v.voice_id:v for v in performance.voices}
    rows=[];losses=Counter()
    psg_units=[u for u in performance.units if devices[u.device_id].chip in ('psg','dcsg') or
               devices[u.device_id].chip=='opna' and u.section=='ssg' or
               devices[u.device_id].chip in ('huc6280','nesapu') and u.section=='noise']
    lanes=sorted({(u.device_id,u.channel) for u in psg_units},key=lambda x:(devices[x[0]].chip!='psg',x))
    lane_map={lane:(0xa0 if index<3 else 0x56,index%3) for index,lane in enumerate(lanes[:6 if opna else 3])}
    mixer={0xa0:63,0x56:63}
    noise_demands={0xa0:{},0x56:{}}
    # Merge channel controls with shared-generator controls on the same timeline.
    actions=[]
    for u in psg_units:
        if (u.device_id,u.channel) not in lane_map:
            losses['psg_channel_capacity_units_omitted']+=1;continue
        actions.extend((at,0,u) for at in times(u));actions.append((u.end_sample,-1 if u.end_sample>u.start_sample else 1,u))
    for at,rank,u in sorted(actions,key=lambda row:(row[0],row[1],row[2].unit_id)):
        device=devices[u.device_id];cmd,ch=lane_map[u.device_id,u.channel]
        def emit(reg,value,why):rows.append(record(u,at,bytes((cmd,reg,value&255)),why,rank))
        if rank:
            noise_demands[cmd].pop((u.device_id,u.channel),None)
            mixer[cmd]|=(1<<ch)|(8<<ch);emit(7,mixer[cmd],'musical silence');emit(8+ch,0,'musical gate end');continue
        voice=voices.get(curve_value(u.voice_curve,at));p=dict(voice.parameters) if voice else {}
        mode=p.get('mode', 2 if u.section=='noise' else 1)
        tone=p.get('tone_enabled',bool(mode&1));noise=p.get('noise_enabled',bool(mode&2))
        hz=curve_value(u.pitch_curve,at) or p.get('native_noise_rate_hz') or p.get('noise_rate_hz')
        effective_clock=AY_CLOCK if cmd==0xa0 else 2000000 # OPNA /4 at prescale6
        if tone and not hz:
            tone=False;losses['psg_unknown_pitch_interval_muted']+=1
        if hz and tone:
            period=max(1,min(4095,round(effective_clock/(16*hz))))
            emit(ch*2,period&255,'musical tone period low');emit(ch*2+1,period>>8,'musical tone period high')
        volume=curve_value(u.volume_curve,at,0) or 0
        if device.chip=='dcsg':
            from opn2_target_vgm import _dcsg_volume_for
            volume=_dcsg_volume_for(volume,dcsg_gain)
            losses['dcsg_ay_level_and_noise_approximation']+=1
        if device.chip in ('huc6280','nesapu'):
            amplitude=_amplitude(u,device,volume)
            volume=max(0,min(15,round(15+20*math.log10(amplitude)/3.19))) if amplitude>0 else 0
            if p.get('lfsr_mode'):losses['noise_lfsr_mode_substituted_by_ay']+=1
        if p.get('hardware_envelope'):volume=16
        mixer[cmd]=(mixer[cmd]&~((1<<ch)|(8<<ch))) | (0 if tone else 1<<ch) | (0 if noise else 8<<ch)
        emit(7,mixer[cmd],'musical tone/noise mode');emit(8+ch,volume&31,'musical volume')
        if noise and device.chip in ('dcsg','huc6280','nesapu'):
            if hz:
                exact=effective_clock/(16*hz);period=max(1,min(31,round(exact)))
                if not 1<=exact<=31:losses['noise_rate_clamped_to_ay_range']+=1
            else:
                period=16;losses['unknown_noise_rate_assumed_period16']+=1
            noise_demands[cmd][u.device_id,u.channel]=period
            if len(set(noise_demands[cmd].values()))>1:losses['shared_noise_period_conflict']+=1
            chosen=noise_demands[cmd][min(noise_demands[cmd])]
            emit(6,chosen,'AY noise rate; shared generator uses first source lane')
            losses['source_noise_spectrum_approximated_by_ay']+=1
    # Shared AY envelope/noise generator controls are separate musical effects.
    for c in performance.controls:
        device=devices[c.device_id];p=dict(c.parameters)
        owned=[dest for lane,dest in lane_map.items() if lane[0]==c.device_id]
        if owned and c.kind in ('ssg_noise','ssg_envelope_low','ssg_envelope_high','ssg_shape'):
            raw=encode_control(c,device)
            cmd=owned[0][0];value=raw[-1]
            source_clock=device.clock_hz if device.chip=='psg' else device.clock_hz/4
            target_clock=AY_CLOCK if cmd==0xa0 else 2000000
            if c.kind=='ssg_noise':
                value=max(1,min(31,round((value&31)*target_clock/source_clock)))
            # Envelope low/high must be projected as an atomic pair below.
            if c.kind.startswith('ssg_envelope_'):continue
            rows.append(dict(sample=c.sample,order=c.order,command=bytes((cmd,p['register'],value)),
                unit_id='',device_id=c.device_id,source_indices=c.source_indices,reason=c.kind))
    for device in performance.devices:
        owned=[dest for lane,dest in lane_map.items() if lane[0]==device.device_id]
        if not owned:continue
        period=0
        for c in performance.controls:
            if c.device_id!=device.device_id or c.kind not in ('ssg_envelope_low','ssg_envelope_high'):continue
            from native_registers import encode_control
            value=encode_control(c,device)[-1]
            period=(period&0xff00)|value if c.kind.endswith('low') else (period&255)|(value<<8)
            source_clock=device.clock_hz if device.chip=='psg' else device.clock_hz/4
            target_clock=AY_CLOCK if owned[0][0]==0xa0 else 2000000
            projected=max(1,min(65535,round(period*target_clock/source_clock)))
            for reg,v in ((11,projected&255),(12,projected>>8)):
                rows.append(dict(sample=c.sample,order=c.order,command=bytes((owned[0][0],reg,v)),
                    unit_id='',device_id=device.device_id,source_indices=c.source_indices,reason='shared envelope period'))
    opll_devices=[d for d in performance.devices if d.chip=='opll']
    for device in opll_devices[:1]:
        if device.clock_raw & 0x80000000:losses['vrc7_patch_rom_approximated_by_opll']+=1
        for u in (u for u in performance.units if u.device_id==device.device_id):
            if not 0<=u.channel<9:continue
            ch=u.channel;last_pitch=0
            def emit(at,reg,v,why,order=0):rows.append(record(u,at,bytes((0x51,reg,v&255)),why,order))
            for at in times(u):
                hz=curve_value(u.pitch_curve,at)
                if not hz:losses['opll_unknown_pitch']+=1;continue
                pitches=[(abs(hz-3579545/72*max(1,min(511,round(hz*72*2**(19-b)/3579545)))*2**b/2**19),b) for b in range(8)]
                b=min(pitches)[1];f=max(1,min(511,round(hz*72*2**(19-b)/3579545)));last_pitch=(b<<1)|(f>>8)
                v=voices.get(curve_value(u.voice_curve,at));p=dict(v.parameters) if v else {}
                inst=p.get('instrument') or 0
                patch=p.get('custom_patch',())
                if inst==0:
                    for reg,value in enumerate(patch):
                        if value is not None:emit(at,reg,value,'native OPLL custom patch')
                level=curve_value(u.volume_curve,at,15)
                emit(at,0x30+ch,(inst<<4)|max(0,min(15,int(level if level is not None else 15))),'native OPLL instrument and volume')
                emit(at,0x10+ch,f&255,'musical OPLL pitch low')
                sustain=next((dict(c.parameters).get('sustain',0) for c in reversed(performance.controls) if c.device_id==device.device_id and c.channel==ch and c.kind=='opll_pitch_high' and c.sample<=at),0)
                emit(at,0x20+ch,16|(32 if sustain else 0)|(b<<1)|(f>>8),'musical OPLL gate and pitch')
            emit(u.end_sample,0x20+ch,last_pitch,'musical OPLL gate end',-1 if u.end_sample>u.start_sample else 1)
        # Shared non-rhythm controls retain explicit typed semantics.
        for c in performance.controls:
            if c.device_id==device.device_id and (c.section=='shared' and c.kind!='opll_patch'):
                rows.append(dict(sample=c.sample,order=c.order,command=encode_control(c,device),
                    unit_id='',device_id=device.device_id,source_indices=c.source_indices,reason='native OPLL rhythm/shared control'))
    if len(opll_devices)>1:losses['second_opll_device_omitted']+=len(opll_devices)-1
    if losses and not force:raise ValueError('Auxiliary target loss: '+', '.join(sorted(losses)))
    return rows,losses
