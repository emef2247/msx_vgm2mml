"""Native PCM content to the existing cartridge Delta-T playback conventions."""
from array import array
from collections import Counter
import hashlib
import math
import struct


def project_pcm(performance, target, *, force=False, instance=0):
    from opn2_target_vgm import (_encode_adpcm_b, OPNA_CLOCK, Y8950_CLOCK,
        ADPCM_B_DRAM_BUDGET, Y8950_RAM_BUDGET, ADPCM_B_LEVEL)
    if target not in ('opna','y8950'):
        raise ValueError('Unknown PCM cartridge')
    if instance not in (0,1):
        raise ValueError('Unknown PCM cartridge instance')
    if instance and target!='y8950':
        raise ValueError('A second PCM instance is only defined for the Y8950 Delta-T')
    assets=sorted(getattr(performance,'pcm_assets',()),key=lambda a:(a.start_sample,a.asset_id))
    if instance and assets:
        # The second unit serves the generic decoded-asset path only:
        # a single-stream source (one MSM6258 stream, one OPN2 DAC
        # timeline) is one voice and stays on the first unit whole.
        _devices={d.device_id:d for d in performance.devices}
        if all(_devices[a.device_id].chip=='msm6258' for a in assets):
            raise ValueError('MSM6258 stream projection has no second-instance form')
        if all(_devices[a.device_id].chip=='opn2' and 'dac_timeline' in dict(a.parameters) for a in assets):
            raise ValueError('OPN2 DAC timeline projection has no second-instance form')
    clock,divisor,budget=(OPNA_CLOCK,144*65536,ADPCM_B_DRAM_BUDGET) if target=='opna' else (Y8950_CLOCK,72*65536,Y8950_RAM_BUDGET)
    msm_assets=[a for a in assets if next(d for d in performance.devices if d.device_id==a.device_id).chip=='msm6258']
    if msm_assets and len(msm_assets)!=len(assets):
        raise ValueError('Mixed MSM6258 and other decoded PCM needs an explicit target mix policy')
    if assets and all(next(d for d in performance.devices if d.device_id==a.device_id).chip=='msm6258' for a in assets):
        from musical_msm6258_target import project
        return project(performance,target,force=force)
    rows=[];losses=Counter();image=bytearray();inventory={};records=[]
    # OPN2 retains the established run inventory/rate clustering. Supply
    # timings are evidence; amplitudes always come from editable PCM content.
    devices={d.device_id:d for d in performance.devices}
    opn2=[a for a in assets if devices[a.device_id].chip=='opn2']
    if (opn2 and len(opn2)==len(assets) and len({a.device_id for a in opn2})==1
        and all('dac_timeline' in dict(a.parameters) for a in opn2)):
        from opn2_target_vgm import project_dac_timeline
        timeline=[]
        for asset in opn2:
            evidence=dict(asset.parameters).get('dac_timeline')
            if evidence is None:raise ValueError('OPN2 PCM has no decoded supply timing evidence')
            for at,identity,offset,step in evidence:
                index=max(0,min(len(asset.samples)-1,round((at-asset.start_sample)*asset.rate_hz/44100)))
                byte=max(0,min(255,round(asset.samples[index]/256)+128))
                timeline.append((at,byte,identity,offset,step))
        timeline.sort(key=lambda row:(row[0],-1 if row[2] is None else row[2]))
        collapsed=[]
        for point in timeline:
            if collapsed and collapsed[-1][0]==point[0]:collapsed[-1]=point
            else:collapsed.append(point)
        projected,prefix,losses,stats,runs=project_dac_timeline(collapsed,
            source_end=performance.end_sample,dac_target=target,
            split_samples=() if performance.song_loop_sample is None else (performance.song_loop_sample,),budget_policy='replace')
        for p in projected:
            rows.append(dict(sample=p['source_vgmticks'],order=p.get('sort_rank',1),
                command=bytes((p['target_command'],p['target_register'],p['target_data'])),
                unit_id='|'.join(a.asset_id for a in opn2 if a.start_sample<=p['source_vgmticks']<=a.end_sample),
                device_id='|'.join(sorted({a.device_id for a in opn2})),
                source_indices=(p['source_event_id'],),reason=p['reason']))
        return rows,prefix,losses,dict(stats,runs=runs,encoder_path='shared_decoded_dac_timeline',ram_budget_bytes=budget,ram_used_bytes=stats['dram_bytes'])
    # All cartridges have one Delta-T voice. Mix overlapping content in this
    # target stage only; the source PCM assets and voice identities stay intact.
    groups=[]
    for asset in assets:
        if not asset.samples or asset.end_sample<=asset.start_sample:continue
        if not groups or asset.start_sample>=max(a.end_sample for a in groups[-1]):groups.append([])
        groups[-1].append(asset)
    windows=[]
    for group in groups:
        # Cut the overlap chain at every gate boundary, following the
        # bank-then-stream structure of the x68k SegaPCM route: the
        # source is first decomposed into gates, and the stream is
        # then built from segments that each hold a constant set of
        # sounding gates, mixed and encoded on their own and shared
        # when identical. A single chain-wide window could outgrow
        # the whole RAM budget and be dropped entire, taking the
        # song's PCM body with it while most of the budget sat
        # unused (AFBII02/03/04 each lost exactly one such window).
        edges=sorted({edge for a in group for edge in (a.start_sample,a.end_sample)})
        if performance.song_loop_sample is not None and edges[0]<performance.song_loop_sample<edges[-1]:
            edges=sorted(set(edges)|{performance.song_loop_sample})
        active=[];pending=sorted(group,key=lambda a:a.start_sample);index=0
        for left,right in zip(edges,edges[1:]):
            while index<len(pending) and pending[index].start_sample<=left:
                active.append(pending[index]);index+=1
            active=[a for a in active if a.end_sample>left]
            if active:
                windows.append((list(active),left,right))
    for group,start,end in windows:
        natural=min(44100,max(float(a.rate_hz) for a in group))
        delta=max(1,min(65535,round(natural*divisor/clock)));rate=clock*delta/divisor
        count=max(2,math.ceil((end-start)*rate/44100))
        if count>10000000:raise ValueError('PCM target run exceeds 10 million output samples')
        mixed=[0]*count
        for asset in group:
            lo=max(0,math.ceil((asset.start_sample-start)*rate/44100))
            hi=min(count,math.ceil((asset.end_sample-start)*rate/44100))
            for index in range(lo,hi):
                pos=max(0.,(start+index*44100/rate-asset.start_sample)*float(asset.rate_hz)/44100)
                left=min(len(asset.samples)-1,int(pos));right=min(left+1,len(asset.samples)-1)
                frac=pos-int(pos)
                mixed[index]+=round(asset.samples[left]*(1-frac)+asset.samples[right]*frac)
        if len(group)>1:losses['pcm_overlapping_assets_mixed_to_one_delta_t_voice']+=len(group)-1
        clipped=sum(abs(v)>32767 for v in mixed)
        if clipped:losses['pcm_mixed_samples_clipped']+=clipped
        wave=array('h',(max(-32768,min(32767,v)) for v in mixed))
        if len(wave)%64:wave.extend([wave[-1]]*(64-len(wave)%64))
        encoded=_encode_adpcm_b(wave)
        identity=hashlib.sha256(encoded).hexdigest()
        if identity not in inventory:
            if len(image)+len(encoded)>budget:
                losses['pcm_dram_budget_playbacks_omitted']+=1;continue
            inventory[identity]=(len(image),len(encoded));image.extend(encoded)
        address,length=inventory[identity]
        source_ids=tuple(x for a in group for x in a.source_event_ids)
        asset_ids=tuple(a.asset_id for a in group)
        def emit(at,reg,value,why,order=0):
            rows.append(dict(sample=at,order=order,command=bytes((0x57 if target=='opna' else 0xac if instance else 0x5c,reg,value&255)),
                unit_id='|'.join(asset_ids),device_id='|'.join(sorted({a.device_id for a in group})),
                source_indices=source_ids,reason=why))
        if target=='opna':
            begin=address>>5;stop=(address+length-1)>>5
            registers=((0,1),(0,0),(1,0xc2),(2,begin&255),(3,begin>>8),(4,stop&255),(5,stop>>8),
                (9,delta&255),(10,delta>>8),(11,ADPCM_B_LEVEL),(12,255),(13,255),(0,0xa0))
            reset=0
        else:
            begin=address>>2;stop=(address+length-1)>>2
            registers=((7,1),(7,0),(8,0),(9,begin&255),(10,begin>>8),(11,stop&255),(12,stop>>8),
                (16,delta&255),(17,delta>>8),(18,ADPCM_B_LEVEL),(7,0x80))
            reset=7
        for reg,value in registers:emit(start,reg,value,'PCM content trigger')
        emit(end,reset,1,'PCM content stop at source endpoint',-1)
        records.append(dict(asset_ids=asset_ids,start_sample=start,end_sample=end,
            rate_hz=rate,delta_n=delta,address=address,bytes=length,sha256=identity))
    prefix=b''
    if image:
        payload=struct.pack('<II',len(image),0)+image
        # A second chip instance is flagged by the top bit of the
        # data block size (the VGM dual-chip convention).
        prefix=bytes((0x67,0x66,0x81 if target=='opna' else 0x88))+struct.pack('<I',len(payload)|(0x80000000 if instance else 0))+payload
    return rows,prefix,losses,dict(playbacks=len(records),unique_samples=len(inventory),dram_bytes=len(image),ram_budget_bytes=budget,ram_used_bytes=len(image),runs=records,instance=instance)
