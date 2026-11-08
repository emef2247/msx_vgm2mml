"""Native percussion attacks/stops and level curves to cartridge rhythms."""
from collections import Counter

from musical_wave_target import curve_value
from native_registers import encode_control

OPLL_BITS={'BD':16,'SD':8,'TOM':4,'CYM':2,'HH':1}
OPNA_BITS={'BD':1,'SD':2,'CYM':4,'HH':8,'TOM':16,'RIM':32}
OPLL_LEVEL={'BD':(0x36,0),'SD':(0x37,0),'HH':(0x37,4),'TOM':(0x38,4),'CYM':(0x38,0)}


def project_rhythm(performance, *, makoto=False):
    devices={d.device_id:d for d in performance.devices}
    controls={c.control_id:c for c in performance.controls}
    rows=[];losses=Counter()
    def emit(event,at,order,cmd,reg,value,reason):
        rows.append(dict(sample=at,order=order,command=bytes((cmd,reg,value)),
            unit_id=event.event_id,device_id=event.device_id,source_indices=event.control_ids,reason=reason))
    for device in performance.devices:
        events=[e for e in performance.percussion if e.device_id==device.device_id]
        if not events:continue
        if device.chip=='opna' and not makoto:
            losses['opna_rhythm_requires_makoto']+=len(events);continue
        if device.chip not in ('opna','opll'):
            losses['unsupported_native_percussion_device']+=len(events);continue
        relevant=[c for c in performance.controls if c.device_id==device.device_id]
        def order(event,at,stop=False):
            observed=[controls[i] for i in event.control_ids if i in controls and controls[i].sample==at]
            return (max if stop else min)((c.order for c in observed),default=1 if stop else 0)
        actions=[]
        for event in events:
            family=event.instrument_family
            bits=OPLL_BITS if device.chip=='opll' else OPNA_BITS
            if family not in bits:
                losses['unsupported_percussion_instrument']+=1;continue
            actions.append((event.start_sample,order(event,event.start_sample),'start',event))
            if event.stop_sample is not None:
                actions.append((event.stop_sample,order(event,event.stop_sample,True),'stop',event))
            actions.extend((at,order(event,at)-.25,'level',event) for at,_ in event.volume_curve)
        # Shared total level, rhythm pitch and pan belong to musical effects;
        # original key masks/levels never override editable percussion events.
        if device.chip=='opll':
            actions.extend((c.sample,c.order,'mode',c) for c in relevant if c.kind=='opll_rhythm')
            for c in relevant:
                p=dict(c.parameters)
                mode_at=next((dict(q.parameters).get('mode',0) for q in reversed(relevant) if q.kind=='opll_rhythm' and (q.sample,q.order)<=(c.sample,c.order)),0)
                if mode_at and c.channel is not None and c.channel>=6 and c.kind in ('opll_pitch_low','opll_pitch_high'):
                    rows.append(dict(sample=c.sample,order=c.order,command=encode_control(c,device),
                        unit_id='',device_id=device.device_id,source_indices=c.source_indices,reason='native rhythm oscillator frequency'))
        else:
            for c in relevant:
                if c.kind=='opna_rhythm_total_level':
                    rows.append(dict(sample=c.sample,order=c.order,command=encode_control(c,device),
                        unit_id='',device_id=device.device_id,source_indices=c.source_indices,reason='native rhythm global total level'))
                elif c.kind=='opna_rhythm_instrument':
                    for event in events:
                        if dict(c.parameters)['register']==0x18+list(OPNA_BITS).index(event.instrument_family) and event.start_sample<=c.sample and (event.stop_sample is None or c.sample<event.stop_sample):
                            actions.append((c.sample,c.order,'level',event))
        mask=0;mode=True;levels={0x36:0,0x37:0,0x38:0}
        for at,rank,kind,event in sorted(actions,key=lambda a:(a[0],a[1],a[2]=='start')):
            if kind=='mode':
                mode=bool(dict(event.parameters).get('mode'))
                # A source mode switch is retained; sounding percussion masks
                # come only from interpreted attack/stop events below.
                rows.append(dict(sample=at,order=rank,command=bytes((0x51,14,(32 if mode else 0)|mask)),unit_id='',device_id=device.device_id,source_indices=event.source_indices,reason='native OPLL rhythm mode'))
                continue
            family=event.instrument_family
            level=curve_value(event.volume_curve,at)
            if kind in ('level','start') and level is not None:
                level=max(0,min(15 if device.chip=='opll' else 31,int(level)))
                if device.chip=='opll':
                    reg,shift=OPLL_LEVEL[family];levels[reg]=(levels[reg]&~(15<<shift))|(level<<shift)
                    emit(event,at,rank-.1,0x51,reg,levels[reg],'native percussion level curve')
                else:
                    reg=0x18+list(OPNA_BITS).index(family)
                    pan=next((dict(c.parameters) for c in reversed(relevant) if c.kind=='opna_rhythm_instrument' and c.sample<=at and dict(c.parameters)['register']==reg),{})
                    emit(event,at,rank-.1,0x56,reg,(pan.get('left',1)<<7)|(pan.get('right',1)<<6)|level,'native percussion level/pan curve')
            if kind=='level':continue
            bit=(OPLL_BITS if device.chip=='opll' else OPNA_BITS)[family]
            if device.chip=='opll':
                if kind=='start':mask|=bit
                else:mask&=~bit
                emit(event,at,rank,0x51,14,(32 if mode else 0)|mask,'musical percussion '+kind)
            else:
                emit(event,at,rank,0x56,0x10,bit|(128 if kind=='stop' else 0),'musical percussion '+kind)
    return rows,losses
