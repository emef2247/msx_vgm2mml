"""Cartridge VGM variants from a source-native musical performance.

Only the source ingestion stage reads VGM/State/Segments. This module can
render an authored or deserialized NativePerformance without any source file.
"""
from collections import Counter
import csv
import json
from pathlib import Path
import struct

from musical_wave_target import project_waves, project_psg_opll

PROFILES = ('sfg01','makoto','sfg01_makoto','sfg01_msxaudio')
CLOCKS = {0x54:(0x30,3579545),0x56:(0x48,8000000),0x57:(0x48,8000000),
          0x51:(0x10,3579545),0xa0:(0x74,1789773),0x5c:(0x58,3579545)}


def _write(performance, rows, prefix, path):
    from native_imports.vgm_timing import command_times
    rows=sorted(rows,key=lambda row:(row['sample'],row.get('order',0)))
    header=bytearray(256);header[:4]=b'Vgm '
    body=bytearray(prefix);cursor=0;loop_address=None
    loop=performance.song_loop_sample
    if loop is not None and not 0<=loop<performance.end_sample:raise ValueError('Invalid musical song loop')
    def wait(count):
        while count:
            size=min(65535,count);body.extend(b'\x61'+struct.pack('<H',size));count-=size
    def advance(sample):
        nonlocal cursor,loop_address
        if sample<cursor or sample>performance.end_sample:raise ValueError('Target operation outside musical timeline')
        if loop is not None and loop_address is None and cursor<=loop<=sample:
            wait(loop-cursor);cursor=loop;loop_address=256+len(body)
            # A repeat starts with the ending chip state, not the intro's
            # cached state. Keep each register's first assignment in the loop.
            cache.clear()
        wait(sample-cursor);cursor=sample
    cache={}
    for index,row in enumerate(rows):
        advance(row['sample'])
        row['write_id']=index;row['target_address']=256+len(body)
        command=row['command']
        if command[0] not in CLOCKS:raise ValueError('Unmapped source chip escaped into cartridge output')
        offset,clock=CLOCKS[command[0]];struct.pack_into('<I',header,offset,clock)
        reg=command[1]
        state_only=(command[0]==0x54 and 0x20<=reg<=0xff or command[0] in (0x56,0x57) and (0x30<=reg<0x90 or 0xb0<=reg<=0xb6))
        key=(command[0],reg)
        row['emitted']=not (state_only and cache.get(key)==command[2])
        if row['emitted']:
            body.extend(command);cache[key]=command[2]
    advance(performance.end_sample);body.append(0x66)
    for offset,value in ((8,0x171),(0x18,performance.end_sample),(0x34,256-0x34)):
        struct.pack_into('<I',header,offset,value)
    if any(row['command'][0]==0xa0 for row in rows):header[0x78]=0x10
    if loop_address is not None:
        struct.pack_into('<I',header,0x1c,loop_address-0x1c)
        struct.pack_into('<I',header,0x20,performance.end_sample-loop)
    raw=header+body
    gd3=bytes.fromhex(dict(performance.metadata).get('gd3_hex',''))
    if gd3:
        if gd3[:4]!=b'Gd3 ' or len(gd3)<12 or int.from_bytes(gd3[8:12],'little')+12!=len(gd3):raise ValueError('Invalid retained GD3')
        struct.pack_into('<I',raw,0x14,len(raw)-0x14);raw.extend(gd3)
    struct.pack_into('<I',raw,4,len(raw)-4)
    framing=tuple(command_times(raw))
    if not framing or framing[-1].command!=0x66 or framing[-1].vgmticks!=performance.end_sample:
        raise ValueError('Cartridge VGM timing differs from musical performance')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return rows


def project_variant(performance, profile, *, force=False, dcsg_gain=.5, opna_law=False):
    from musical_fm_target import project_fm
    from musical_pcm_target import project_pcm
    if profile not in PROFILES:raise ValueError('Unknown cartridge profile')
    if not 0<dcsg_gain<=1:raise ValueError('DCSG gain must be >0 and <=1')
    chip='opna' if profile=='makoto' else 'opm'
    clock=8000000 if chip=='opna' else 3579545
    auxiliary='opna' if profile in ('makoto','sfg01_makoto') else 'y8950' if profile=='sfg01_msxaudio' else None
    losses=Counter();rows=[];prefix=b''
    supported={'opm','opna','opn2','psg','opll','scc','dcsg','huc6280','nesapu'}
    for device in performance.devices:
        if device.chip not in supported:losses['unsupported_source_device_'+device.chip]+=1
    if any(k.startswith('unsupported_source_device_') for k in losses):
        raise ValueError('No cartridge projection for '+', '.join(sorted(losses)))
    # Inherent cross-chip waveform/LFO approximations are reported, not fatal.
    # Resource omissions still follow the caller's documented --force policy.
    fm,fm_losses,allocation=project_fm(performance,chip,clock,force=force)
    rows.extend(fm);losses.update(fm_losses)
    wave,wave_losses,wave_allocation=project_waves(performance,chip,clock,
        set(allocation.values()),force=True)
    if wave_losses.get('wave_channel_capacity_units_omitted') and not force:
        raise ValueError('Waveform voices exceed cartridge FM capacity (use --force for explicit omission)')
    rows.extend(wave);losses.update(wave_losses)
    aux,aux_losses=project_psg_opll(performance,dcsg_gain=dcsg_gain,
        opna=auxiliary=='opna',force=True)
    if any(aux_losses.get(k) for k in ('psg_channel_capacity_units_omitted','second_opll_device_omitted')) and not force:
        raise ValueError('Auxiliary voices exceed cartridge capacity (use --force for explicit omission)')
    rows.extend(aux);losses.update(aux_losses)
    assets=getattr(performance,'pcm_assets',())
    pcm_stats={}
    missing_pcm=[decision for decision in performance.decisions if decision and decision[0] in ('nes_pcm_missing_sample_bytes','opn2_pcm_source_issue','opn2_pcm_direct_without_observed_enable')]
    if missing_pcm:losses['source_pcm_content_incomplete_diagnostics']+=len(missing_pcm)
    if assets:
        if auxiliary is None:raise ValueError('PCM source requires sfg01_makoto or sfg01_msxaudio')
        pcm,prefix,pcm_losses,pcm_stats=project_pcm(performance,auxiliary)
        if any(count for code,count in pcm_losses.items() if 'budget' in code and ('omitted' in code or 'dropped' in code)) and not force:
            raise ValueError('PCM content exceeds cartridge DRAM (use --force for explicit omission)')
        rows.extend(pcm);losses.update(pcm_losses)
    native_pcm=[p for p in performance.pcm_packets if p.chip=='opna']
    if native_pcm:
        from opn2_target_vgm import ADPCM_B_DRAM_BUDGET
        blocks=[bytes.fromhex(p.command_hex) for p in native_pcm if bytes.fromhex(p.command_hex)[0]==0x67]
        exceeds=any(len(b)<15 or int.from_bytes(b[7:11],'little')>ADPCM_B_DRAM_BUDGET or int.from_bytes(b[11:15],'little')+len(b)-15>ADPCM_B_DRAM_BUDGET for b in blocks)
        if exceeds:
            if not force:raise ValueError('Native OPNA ADPCM exceeds the Makoto 256 KiB RAM budget; relocation required')
            losses['native_opna_adpcm_capacity_lane_omitted']+=1
            native_pcm=[]
    if native_pcm:
        if assets:raise ValueError('Native OPNA ADPCM and decoded PCM compete for one Delta-T unit')
        if auxiliary!='opna':raise ValueError('Native OPNA ADPCM requires Makoto auxiliary cartridge')
        for p in native_pcm:
            command=bytes.fromhex(p.command_hex)
            if command[0]==0x67:
                if p.sample!=0:raise ValueError('Mid-song native ADPCM memory uploads require an explicit relocation plan')
                prefix+=command
            elif command[0] in (0x56,0x57):
                rows.append(dict(sample=p.sample,order=p.order,command=command,
                    unit_id='',device_id='opna:0',source_indices=(p.source_event_id,),reason='native ADPCM preservation'))
            else:raise ValueError('Native ADPCM stream transport needs decoded content before relocation')
        losses['native_opna_adpcm_clock_not_repitched']+=1
        pcm_stats.update(ram_budget_bytes=ADPCM_B_DRAM_BUDGET,ram_used_bytes=max((int.from_bytes(b[11:15],'little')+len(b)-15 for b in blocks),default=0),encoder_path='native_opna_packet_preservation')
    from musical_rhythm_target import project_rhythm
    rhythm,rhythm_losses=project_rhythm(performance,makoto=auxiliary=='opna')
    rows.extend(rhythm);losses.update(rhythm_losses)
    # The measured OPNA TL/decay law is applied to projected carrier values,
    # after native curve/voice recombination, never to source evidence.
    if opna_law and chip=='opna':
        from opn2_target_vgm import _OPNA_LAW_TL, _OPNA_LAW_DECAY
        device_chips={d.device_id:d.chip for d in performance.devices}
        carriers=(8,8,8,8,12,14,14,15);algorithms={};ks={}
        for row in sorted(rows,key=lambda r:(r['sample'],r.get('order',0))):
            if device_chips.get(row['device_id'])!='opn2':continue
            cmd,reg,value=row['command'];port=cmd-0x56
            if cmd not in (0x56,0x57):continue
            ch=reg%4+3*port;bank=(reg%16)//4
            if 0xb0<=reg<=0xb2:algorithms[ch]=value&7
            elif 0x50<=reg<=0x5f:ks[ch,bank]=value>>6
            elif 0x40<=reg<=0x4f and carriers[algorithms.get(ch,0)]&(1<<bank):value=_OPNA_LAW_TL[value&127]
            elif 0x60<=reg<=0x7f and ks.get((ch,bank),0)==0:value=(value&0xe0)|_OPNA_LAW_DECAY[value&31]
            row['command']=bytes((cmd,reg,value))
    if any(row['command'][0] in (0x56,0x57) for row in rows):
        rows.insert(0,dict(sample=0,order=-2,command=bytes((0x56,0x29,0x80)),unit_id='',device_id='',source_indices=(),reason='enable six OPNA FM channels'))
    if not rows and not prefix:raise ValueError('No mapped musical operations in source')
    return rows,prefix,dict(losses),dict(fm_allocation={str(k):v for k,v in allocation.items()},
        waveform_allocation={str(k):v for k,v in wave_allocation.items()},pcm=pcm_stats)


def export_variants(performance, outdir, stem, *, force=False, dcsg_gain=.5, opna_law=False):
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True);results={}
    has_pcm=bool(getattr(performance,'pcm_assets',()) or any(p.chip=='opna' for p in performance.pcm_packets))
    native_rhythm=any(e.device_id in {d.device_id for d in performance.devices if d.chip=='opna'} for e in performance.percussion)
    for profile in PROFILES:
        folder=root/profile;folder.mkdir(parents=True,exist_ok=True)
        path=folder/(stem+'.vgm');path.unlink(missing_ok=True)
        result=dict(profile=profile,stage='musical_layer_target_projection',
            input_representation='NativePerformance',source_file_consulted=False,
            sample_rate=44100,status='unavailable',source_decisions=performance.decisions)
        try:
            if profile.startswith('sfg01_') and not (has_pcm or profile=='sfg01_makoto' and native_rhythm):
                raise ValueError('No PCM/native rhythm requiring this auxiliary cartridge; use sfg01')
            rows,prefix,losses,plan=project_variant(performance,profile,force=force,
                dcsg_gain=dcsg_gain,opna_law=opna_law)
            rows=_write(performance,rows,prefix,path)
            with (folder/(stem+'.writes.csv')).open('w',newline='',encoding='utf-8') as stream:
                fields=['write_id','sample','order','device_id','unit_id','source_indices','reason','command_hex','target_address','emitted']
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
                for row in rows:
                    writer.writerow({k:(row['command'].hex() if k=='command_hex' else
                        json.dumps(row.get(k)) if k=='source_indices' else row.get(k,'')) for k in fields})
            result.update(status='success',path=str(path),writes=sum(r['emitted'] for r in rows),planned_writes=len(rows),losses=losses,plan=plan,
                song_loop_sample=performance.song_loop_sample)
        except ValueError as error:
            result.update(reason=str(error))
        except Exception as error:
            result.update(status='failed',reason=f'{type(error).__name__}: {error}')
        (folder/(stem+'.projection.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        results[profile]=result
    return results
