"""Decoded MSM6258 musical PCM -> bounded cartridge ADPCM-B image.

Source samples and timing remain intact. Byte-budget representative selection
is a force-only target approximation, shared with the existing OPN2 policy.
"""
from array import array
from collections import Counter
import hashlib
import math
import struct


def project(performance,target,*,force=False):
    from opn2_target_vgm import (_encode_adpcm_b,OPNA_CLOCK,Y8950_CLOCK,
        ADPCM_B_DRAM_BUDGET,Y8950_RAM_BUDGET,ADPCM_B_LEVEL)
    from pcm_target_budget import fit_bank
    clock,divisor,budget=((OPNA_CLOCK,144*65536,ADPCM_B_DRAM_BUDGET) if target=='opna'
        else (Y8950_CLOCK,72*65536,Y8950_RAM_BUDGET))
    if budget<32:raise ValueError('PCM DRAM budget must hold one aligned ADPCM-B block')
    devices={d.device_id:d for d in performance.devices}
    assets=sorted((a for a in performance.pcm_assets if devices[a.device_id].chip=='msm6258'),
        key=lambda a:(a.start_sample,a.asset_id))
    rows=[];losses=Counter();candidates=[];inventory={};playbacks=[];previous=0;frames=0
    for asset in assets:
        if asset.start_sample<previous:raise ValueError('Overlapping MSM6258 assets need an explicit source mix model')
        previous=asset.end_sample
        if asset.end_sample<=asset.start_sample:continue
        if not asset.samples:raise ValueError('MSM6258 musical PCM has no decoded samples')
        if (asset.end_sample-asset.start_sample)*asset.rate_hz/44100>len(asset.samples)+1:
            raise ValueError('MSM6258 decoded samples do not cover their declared interval')
        params=dict(asset.parameters);pan=params.get('pan')
        if pan not in (0,1,2,3):raise ValueError('MSM6258 PCM pan is unknown')
        if pan==3:
            losses['msm6258_muted_source_assets_not_encoded']+=1;continue
        pan_bits=3^pan
        if target=='y8950' and pan_bits!=3:losses['msm6258_stereo_folded_to_mono']+=1
        delta=max(1,min(65535,round(min(44100,asset.rate_hz)*divisor/clock)))
        rate=clock*delta/divisor
        # Bound the encoded candidate *after* 64-frame padding. Independent
        # target predictors make each candidate relocatable/reusable.
        maximum=max(64,(min(65536,budget)//32)*64)
        span=max(1,math.floor(maximum*44100/rate))
        cuts={asset.start_sample,asset.end_sample}
        cuts.update(range(asset.start_sample+span,asset.end_sample,span))
        loop=performance.song_loop_sample
        if loop is not None and asset.start_sample<loop<asset.end_sample:cuts.add(loop)
        for start,stop in zip(sorted(cuts),sorted(cuts)[1:]):
            count=max(1,math.ceil((stop-start)*rate/44100-1e-9));frames+=count
            if frames>10000000:raise ValueError('MSM6258 target PCM exceeds explicit 10-million-frame budget')
            wave=array('h')
            origin=(start-asset.start_sample)*asset.rate_hz/44100
            for index in range(count):
                pos=origin+index*asset.rate_hz/rate;left=int(pos);frac=pos-left
                a=asset.samples[left] if left<len(asset.samples) else 0
                b=asset.samples[left+1] if left+1<len(asset.samples) else 0
                wave.append(max(-32768,min(32767,round(a*(1-frac)+b*frac))))
            amplitudes=tuple(wave)
            if len(wave)%64:wave.extend([0]*(64-len(wave)%64))
            encoded=_encode_adpcm_b(wave)
            if len(encoded)>budget:raise ValueError('Aligned MSM6258 candidate exceeds cartridge DRAM')
            digest=hashlib.sha256(encoded).hexdigest();sid=inventory.get(digest)
            if sid is None:
                sid=len(candidates);inventory[digest]=sid
                candidates.append(dict(sample_id=sid,encoded=encoded,amplitudes=amplitudes,
                    rate_hz=rate,valid_samples=count,encoded_samples=len(wave),sha256=digest))
            playbacks.append(dict(asset=asset,start=start,end=stop,original_sample_id=sid,
                sample_id=sid,delta_n=delta,rate_hz=rate,valid_samples=count,pan_bits=pan_bits,
                source_sample_position=origin))
    for asset in assets:
        for reason in dict(asset.parameters).get('policy_reasons') or ():
            losses['msm6258_stream_'+reason]+=1
    stream_delivery=any(dict(a.parameters).get('policy_reasons') for a in assets)
    usage=Counter(p['sample_id'] for p in playbacks)
    total=sum(len(c['encoded']) for c in candidates)
    orig_candidates=candidates;blocks=None
    if total>budget and stream_delivery:
        # Stream delivery: pack the chunk candidates into sequential DRAM
        # images of at most `budget` bytes each. Every chunk keeps its own
        # audio (no representative replacement); images after the first are
        # uploaded by a data-block row at the first playback that needs one,
        # so a stream longer than one cartridge image still plays in order.
        bcandidates=[];addresses={};image=bytearray();placement={}
        blocks=[];first_sample=None;bidx=0
        for p in playbacks:
            sid=p['sample_id']
            if (loop is not None and image and first_sample is not None
                and first_sample<loop<=p['start']):
                # The first chunk at or after the song loop must open a fresh
                # image: its upload row sits inside the looped region, so a
                # repeat reloads the image those chunks address.
                blocks.append((bytes(image),first_sample))
                image=bytearray();placement={};first_sample=None;bidx+=1
            if sid in placement:
                p['block_sid'],p['block_index']=placement[sid];continue
            encoded=candidates[sid]['encoded']
            if image and len(image)+len(encoded)>budget:
                blocks.append((bytes(image),first_sample))
                image=bytearray();placement={};first_sample=None;bidx+=1
            new_sid=len(bcandidates);bcandidates.append(candidates[sid])
            placement[sid]=(new_sid,bidx);addresses[new_sid]=len(image);image.extend(encoded)
            p['block_sid'],p['block_index']=new_sid,bidx
            if first_sample is None:first_sample=p['start']
        if image:blocks.append((bytes(image),first_sample))
        candidates=bcandidates;selected=list(range(len(bcandidates)));mapping={}
        budget_report=dict(delivery='chunked_stream',blocks=len(blocks),
            block_bytes=[len(b) for b,_ in blocks],selection_method='sequential_stream_blocks')
        losses['msm6258_stream_block_uploads']+=len(blocks)-1
        image=bytearray(blocks[0][0])
    else:
        if total>budget and not force:raise ValueError(f'MSM6258 PCM exceeds cartridge DRAM ({budget} bytes); use --force for explicit representative reuse')
        mapping,selected,budget_report=fit_bank(candidates,usage,budget)
        image=bytearray();addresses={}
        for sid in selected:
            addresses[sid]=len(image);image.extend(candidates[sid]['encoded'])
    records=[]
    for p in playbacks:
        sid=p['block_sid'] if 'block_sid' in p else mapping[p['sample_id']];sample=candidates[sid]
        replaced=sample is not orig_candidates[p['original_sample_id']]
        required=(p['delta_n']*sample['valid_samples']/p['valid_samples'] if replaced else p['delta_n'])
        delta=max(1,min(65535,round(required)));rate=clock*delta/divisor
        if not 1<=round(required)<=65535:losses['msm6258_replacement_rate_clamped_playbacks']+=1
        if replaced:losses['msm6258_budget_reused_playbacks']+=1
        start,stop=p['start'],p['end'];asset=p['asset'];address=addresses[sid];length=len(sample['encoded'])
        def emit(at,reg,value,why,order=0):
            rows.append(dict(sample=at,order=order,command=bytes((0x57 if target=='opna' else 0x5c,reg,value&255)),
                unit_id=asset.asset_id,device_id=asset.device_id,source_indices=asset.source_event_ids,reason=why))
        if target=='opna':
            begin=address>>5;end=(address+length-1)>>5;reset=0
            registers=((0,1),(0,0),(1,p['pan_bits']<<6|2),(2,begin&255),(3,begin>>8),(4,end&255),(5,end>>8),
                (9,delta&255),(10,delta>>8),(11,ADPCM_B_LEVEL),(12,255),(13,255),(0,0xa0))
        else:
            begin=address>>2;end=(address+length-1)>>2;reset=7
            registers=((7,1),(7,0),(8,0),(9,begin&255),(10,begin>>8),(11,end&255),(12,end>>8),
                (16,delta&255),(17,delta>>8),(18,ADPCM_B_LEVEL),(7,0x80))
        for reg,value in registers:emit(start,reg,value,'MSM6258 musical PCM trigger')
        emit(stop,reset,1,'MSM6258 PCM stop at original endpoint',-1)
        records.append(dict(asset_id=asset.asset_id,original_sample_id=p['original_sample_id'],sample_id=sid,
            block=p.get('block_index',0),
            budget_replaced=replaced,start_sample=start,end_sample=stop,address=address,bytes=length,
            required_delta_n=required,delta_n=delta,rate_hz=rate,pan_bits=p['pan_bits'],
            source_sample_position=p['source_sample_position'],valid_samples=sample['valid_samples'],
            encoded_samples=sample['encoded_samples'],natural_exhaustion_sample=start+sample['encoded_samples']*44100/rate,
            valid_end_error_samples=sample['valid_samples']*44100/rate-(stop-start)))
    prefix=b''
    if image:
        payload=struct.pack('<II',len(image),0)+image
        prefix=bytes((0x67,0x66,0x81 if target=='opna' else 0x88))+struct.pack('<I',len(payload))+payload
    if blocks is not None:
        for bimg,bfirst in blocks[1:]:
            payload=struct.pack('<II',len(bimg),0)+bimg
            rows.append(dict(sample=bfirst,order=-2,
                command=bytes((0x67,0x66,0x81 if target=='opna' else 0x88))+struct.pack('<I',len(payload))+payload,
                unit_id='',device_id=assets[0].device_id,source_indices=(),
                reason='MSM6258 PCM stream block upload'))
    return rows,prefix,losses,dict(encoder_path='decoded_msm6258_budget_bank',playbacks=len(playbacks),
        unique_samples=len(selected),
        dram_bytes=sum(len(b) for b,_ in blocks) if blocks is not None else len(image),
        ram_used_bytes=max((len(b) for b,_ in blocks),default=0) if blocks is not None else len(image),
        ram_budget_bytes=budget,delivery='chunked_stream' if blocks is not None else 'single_bank',
        blocks=len(blocks) if blocks is not None else 1,
        bank_budget=budget_report,runs=records,source_evidence_unchanged=True,
        limitations=['Independent target ADPCM-B predictor at each packaging cut',
                     'Linear resampling; target padding is zero PCM',
                     'Representative replacement is lossy capacity policy, not perceptual equivalence'])
