"""Source-native musical units and complete chip controls on the original clock.

The native register interpretation remains separate from output precision. PCM
commands are retained as an explicitly opaque lane in this first implementation.
"""
from collections import defaultdict
from bisect import bisect_left, bisect_right
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

from native_imports import analyze_source
from native_music import (NativeDevice, NativeControl, NativeVoice, NativeUnit,
                          NativePercussion, NativePacket, NativePerformance)
from native_registers import decode_control


COMMAND_CHIPS = {0x54:'opm',0xa4:'opm',0x56:'opna',0x57:'opna',0xa6:'opna',0xa7:'opna',
    0x50:'dcsg',0x30:'dcsg',0x4f:'dcsg',0x3f:'dcsg',0xb7:'msm6258',0xb8:'msm6295',
    0xc0:'segapcm',0xd4:'c140',0xa0:'psg',0xd2:'scc',0x51:'opll',0xa1:'opll'}
BLOCK_CHIPS = {4:'msm6258',0x44:'msm6258',0x7f:'pcm',0x80:'segapcm',0x81:'opna',0x8b:'msm6295',0x8d:'c140'}
STREAM_CHIPS = {0:'dcsg',1:'opll',3:'opm',4:'segapcm',7:'opna',0x12:'psg',
                0x17:'msm6258',0x18:'msm6295',0x19:'scc',0x1c:'c140'}
HEADER_OFFSETS = {'opm':0x30,'opna':0x48,'dcsg':0x0c,'msm6258':0x90,'msm6295':0x98,
                  'segapcm':0x38,'c140':0xa8,'psg':0x74,'scc':0x9c,'opll':0x10}
CARRIERS = (8,8,8,8,12,14,14,15)  # Source register-bank order M1,M2,C1,C2.


def _clock(header, raw, chip):
    if chip+'_clock_raw' in header:return header[chip+'_clock_raw']
    offset=HEADER_OFFSETS[chip]
    return int.from_bytes(raw[offset:offset+4],'little') if offset+4<=header['data_start'] else 0


def _chip_instance(command, raw, pos):
    if command in (0xa4,0xa6,0xa7,0xa1,0x30,0x3f):return 1
    if command in (0xb7,0xb8,0xa0):return raw[pos+1]>>7
    if command==0xc0:return int.from_bytes(raw[pos+1:pos+3],'little')>>15
    if command==0xd4:return raw[pos+1]>>7
    if command==0xd2:return raw[pos+1]>>7
    return 0


def _add_curve(curve, sample, value):
    if not curve or curve[-1][1]!=value:
        curve.append((sample,value))


class _Builder:
    def __init__(self, bundle):
        self.bundle=bundle;self.raw=bundle['raw'];self.header=bundle['header']
        self.devices={};self.controls=[];self.packets=[];self.units=[];self.voices={};self.percussion=[]
        self.decisions=[];self.latches={}

    def device(self, chip, instance=0):
        identity=f'{chip}:{instance}'
        if identity not in self.devices:
            clock=_clock(self.header,self.raw,chip)
            parameters=(('header_clock_offset',HEADER_OFFSETS[chip]),('declared',bool(clock)),)
            if chip=='dcsg':
                parameters+=(('feedback',self.header['dcsg_feedback_raw']),
                    ('shift_width',self.header['dcsg_shift_width_raw']),('flags',self.header['dcsg_flags_raw']))
            if chip=='c140':parameters+=(('chip_type',self.header['c140_type']),)
            if chip=='segapcm':parameters+=(('interface',self.header['segapcm_interface_raw']),)
            if chip=='msm6258':parameters+=(('flags',self.header['msm6258_flags']),)
            self.devices[identity]=NativeDevice(identity,chip,instance,clock&0x3fffffff,clock,parameters)
            if instance and self.header.get('extra_header_offset'):
                self.decisions.append(('extra_chip_clock_not_interpreted',identity))
        return self.devices[identity]

    def voice(self, device, section, parameters):
        parameters=tuple(parameters)
        digest=hashlib.sha256(json.dumps(parameters,sort_keys=True).encode()).hexdigest()[:16]
        identity=f'{device.device_id}:{section}:voice:{digest}'
        self.voices.setdefault(identity,NativeVoice(identity,device.device_id,section,parameters))
        return identity

    def control_ids(self, device, section, channel, start, stop):
        if not hasattr(self,'_control_index'):
            indexed=defaultdict(list)
            for c in self.controls:indexed[c.device_id,c.section,c.channel].append(c)
            self._control_index={key:([c.sample for c in rows],rows) for key,rows in indexed.items()}
        keys={(device.device_id,s,ch) for s in (section,'shared') for ch in (None,channel)}
        if device.chip=='scc' and section=='tone':
            keys.add((device.device_id,'wave',channel))
            if channel==4:keys.add((device.device_id,'wave',3))
        selected=[]
        for key in keys:
            times,rows=self._control_index.get(key,([],[]))
            selected.extend(rows[bisect_left(times,start):bisect_right(times,stop)])
        return tuple(c.control_id for c in sorted(selected,key=lambda c:(c.sample,c.order)))

    def packet(self,event,order,chip,kind,size,dependencies=()):
        self.packets.append(NativePacket(f'{chip}:packet:{order}',event.vgmticks,order,
            self.raw[event.address:event.address+size].hex(),chip,kind,tuple(dependencies),event.source_event_id))

    def commands(self):
        streams={};banks={}
        for order,event in enumerate(self.bundle['events']):
            command,pos=event.command,event.address
            if command in (0x61,0x62,0x63,0x64,0x66) or 0x70<=command<=0x7f:continue
            if command==0x67:
                kind=self.raw[pos+2];chip=BLOCK_CHIPS.get(kind)
                if chip is None:raise ValueError(f'Unsupported native source data block {kind:#x} at {pos:#x}')
                length=int.from_bytes(self.raw[pos+3:pos+7],'little');instance=length>>31
                if chip!='pcm':self.device(chip,instance)
                self.packet(event,order,chip,'data_block',7+(length&0x7fffffff))
                banks[kind&63]=self.packets[-1].packet_id
                continue
            if 0x90<=command<=0x95:
                sid=self.raw[pos+1];dependencies=[]
                if command==0x90:
                    target=self.raw[pos+2];chip=STREAM_CHIPS.get(target&127)
                    if chip is None:raise ValueError(f'Unsupported native DAC stream chip {target&127:#x}')
                    self.device(chip,target>>7);streams[sid]=dict(chip=chip,setup=f'{chip}:packet:{order}')
                stream=streams.get(sid,{})
                chip=stream.get('chip','pcm')
                if stream.get('setup'):dependencies.append(stream['setup'])
                if command==0x91:
                    bank=self.raw[pos+2]
                    stream['bank']=bank
                    if bank in banks:dependencies.append(banks[bank])
                if stream.get('bank') in banks:dependencies.append(banks[stream['bank']])
                size={0x90:5,0x91:5,0x92:6,0x93:11,0x94:2,0x95:5}[command]
                self.packet(event,order,chip,'stream_control',size,dict.fromkeys(dependencies))
                continue
            if command==0x68:
                if self.raw[pos+1]!=0x66:raise ValueError('Invalid native PCM RAM block marker')
                self.packet(event,order,'pcm','ram_copy',12,tuple(banks.values()))
                self.decisions.append(('opaque_pcm_ram_copy',order))
                continue
            chip=COMMAND_CHIPS.get(command)
            if chip is None:raise ValueError(f'Unsupported active native source command {command:#x} at {pos:#x}')
            instance=_chip_instance(command,self.raw,pos);device=self.device(chip,instance)
            if chip in ('msm6258','msm6295','segapcm','c140'):
                self.packet(event,order,chip,'native_pcm_register',4 if command in (0xc0,0xd4) else 3)
            elif chip=='opna' and command in (0x57,0xa7) and self.raw[pos+1]<0x11:
                self.packet(event,order,chip,'adpcm_b_register',3)
            else:
                self.controls.append(decode_control(device,event,self.raw,order=order,latches=self.latches))

    def fm(self,chip):
        analysis=self.bundle['analyses'].get(chip)
        if analysis is None:return
        groups=defaultdict(list)
        full_off=defaultdict(set)
        for event in analysis.events:
            if event.falling_mask and not event.state.key_mask:
                full_off[event.chip_instance,event.ch].add(event.vgmticks)
        for segment in analysis.segments:
            if segment.state.key_mask:
                groups[segment.chip_instance,segment.ch].append(segment)
        for (instance,channel),rows in sorted(groups.items()):
            device=self.device(chip,instance);gates=[]
            for row in sorted(rows,key=lambda s:(s.vgmticks,s.segment_id)):
                if (not gates or gates[-1][-1].vgmticks_end!=row.vgmticks or
                    row.vgmticks in full_off[instance,channel] and
                    gates[-1][-1].continuity_id!=row.continuity_id):gates.append([])
                gates[-1].append(row)
            for index,gate in enumerate(gates):
                start,stop=gate[0].vgmticks,gate[-1].vgmticks_end
                pitches=[];volumes=[]
                for segment in gate:
                    _add_curve(pitches,segment.vgmticks,_fm_pitch(chip,segment.state,device.clock_hz))
                    _add_curve(volumes,segment.vgmticks,_fm_level(segment.state))
                effective=next((s for s in gate if s.vgmticks==start and s.vgmticks_end>start),gate[0])
                voice=self.voice(device,'fm',_fm_voice(effective.state))
                ids=self.control_ids(device,'fm',channel,start,stop)
                parameters=(('native_segment_ids',tuple(s.segment_id for s in gate)),
                    ('source_continuity_ids',tuple(s.continuity_id for s in gate)),
                    ('volume_domain','native_carrier_attenuation'),
                    ('voice_basis','first positive onset state; ordered zero-width setup remains in controls'),
                    ('channel3_special_observed',chip=='opna' and any(s.state.channel3_special_enabled for s in gate)),
                    ('csm_observed',any(s.state.csm_enabled for s in gate)),
                    ('noise_enabled_observed',chip=='opm' and channel==7 and any(s.state.noise_enabled for s in gate)),
                    ('pitch_fraction_reset_assumption',chip=='opm' and any(s.state.kf_raw is None for s in gate)),
                    ('termination','observed_key_off' if stop in full_off[instance,channel] else 'source_observation_end'))
                self.units.append(NativeUnit(f'{device.device_id}:fm:{channel}:gate:{index}',device.device_id,
                    'fm',channel,start,stop,tuple(pitches),tuple(volumes),((start,voice),),ids,
                    tuple(s.segment_id for s in gate),'melody',parameters))

    def dcsg(self):
        analysis=self.bundle['analyses'].get('dcsg')
        if analysis is None:return
        by_channel=defaultdict(list)
        for segment in analysis.segments:by_channel[segment.chip_instance,segment.ch].append(segment)
        for (instance,channel),segments in sorted(by_channel.items()):
            device=self.device('dcsg',instance);groups=[]
            for segment in segments:
                if not segment.audible:continue
                if not groups or groups[-1][-1].end_sample!=segment.start_sample:groups.append([])
                groups[-1].append(segment)
            for index,gate in enumerate(groups):
                start,stop=gate[0].start_sample,gate[-1].end_sample
                pitches=[];volumes=[]
                for segment in gate:
                    _add_curve(pitches,segment.start_sample,segment.frequency_hz)
                    _add_curve(volumes,segment.start_sample,segment.attenuation)
                section='noise' if channel==3 else 'tone'
                voice=self.voice(device,section,(('generator',section),('noise_control',gate[0].noise_control if channel==3 else None)))
                self.units.append(NativeUnit(f'{device.device_id}:{section}:{channel}:gate:{index}',device.device_id,
                    section,channel,start,stop,tuple(pitches),tuple(volumes),((start,voice),),
                    self.control_ids(device,section,channel,start,stop),tuple(s.segment_id for s in gate),
                    'unpitched' if channel==3 else 'melody',(('boundary_origin','source_audibility'),
                    ('volume_domain','native_attenuation'),('noise_controls_retained',channel==3))))


def _fm_pitch(chip,state,clock):
    if not clock:return None
    if chip=='opm':
        if state.kc_raw is None:return None
        kc=state.kc_raw&127
        q=(kc-(kc>>2))*64+((state.kf_raw or 0)>>2)
        return 440*clock/3579545*2**((q/64-56)/12)
    if state.fnum is None or state.block is None:return None
    return state.fnum*clock*(6/state.fm_prescale_divisor)/(144*2**(20-state.block))


def _fm_level(state):
    if state.algorithm is None:return None
    mask=CARRIERS[state.algorithm]
    values=[op.tl for i,op in enumerate(state.operators) if mask&(1<<i) and op.tl is not None]
    return min(values) if values else None


def _fm_voice(state):
    data=asdict(state);mask=CARRIERS[state.algorithm] if state.algorithm is not None else 0
    attenuation=_fm_level(state)
    operators=[]
    for i,operator in enumerate(data['operators']):
        operator=dict(operator)
        if mask&(1<<i) and operator['tl'] is not None and attenuation is not None:
            operator['tl']-=attenuation
        operators.append(tuple(sorted(operator.items())))
    return (('algorithm',state.algorithm),('feedback',state.feedback),('operators',tuple(operators)),
            ('ams',getattr(state,'ams',None)),('pms',getattr(state,'pms',None)))


def _legacy_performances(source,root,stem,performances,opll_segments,raw):
    observed={e.command for e in source['events']}
    if (not performances and observed&{0xa0,0xd2}) or (opll_segments is None and 0x51 in observed):
        from vgm_reader import parse_vgm
        from psg import build_segments as build_psg
        from scc import build_segments as build_scc
        from psg_scc_performance import analyze
        from opll import _build_segments
        folder=root/'native_legacy';folder.mkdir(exist_ok=True)
        path=folder/(stem+'.source.vgm');path.write_bytes(raw)
        traces=parse_vgm(str(path),str(folder),include_vgmticks=True)
        if not performances:
            performances=(analyze(build_psg(traces[2],folder,stem,dump_passes=True),'psg'),
                analyze(build_scc(traces[3],folder,dump_passes=True,stem=stem).segments,'scc'))
        if opll_segments is None:opll_segments,_=_build_segments(traces[5])
    return tuple(performances),opll_segments


def _legacy_units(builder,performances):
    for performance in performances:
        chip=performance.chip
        if not performance.gates:continue
        device=builder.device(chip)
        original=dict(performance.source_segments)
        grouped=defaultdict(list)
        for gate in performance.gates:grouped[gate.channel].append(gate)
        for channel,gates in grouped.items():
            for index,gate in enumerate(gates):
                rows=[original[channel][i] for i in gate.segment_indices]
                start=rows[0].vgmticks;stop=rows[-1].vgmticks_end
                if start is None or stop is None:
                    builder.decisions.append(('unknown_legacy_source_boundary',chip,channel,index));continue
                pitches=[];volumes=[];voices=[]
                for row in rows:
                    at=row.vgmticks
                    if at is None:continue
                    period=row.tone_period
                    frequency=(device.clock_hz/(16*(period+(chip=='scc'))) if period+(chip=='scc')>0 else None)
                    _add_curve(pitches,at,frequency);_add_curve(volumes,at,row.volume)
                    parameters=(('waveform_hex',row.waveform_hex),) if chip=='scc' else (
                        ('mode',row.mode),('hardware_envelope',bool(row.envelope_enabled)),
                        ('envelope_shape',row.envelope_shape if row.envelope_enabled else None))
                    voice=builder.voice(device,'tone',parameters);_add_curve(voices,at,voice)
                builder.units.append(NativeUnit(f'{device.device_id}:tone:{channel}:unit:{index}',device.device_id,
                    'tone',channel,start,stop,tuple(pitches),tuple(volumes),tuple(voices),
                    builder.control_ids(device,'tone',channel,start,stop),tuple(gate.segment_indices),
                    'unpitched' if chip=='psg' and rows[0].mode==2 else 'melody',
                    (('source_gate_ids',(gate.gate_id,)),('boundary_origin','inferred_source_audibility_gate'))))


def _opll(builder):
    for device in list(builder.devices.values()):
        if device.chip!='opll':continue
        registers=[0]*64;known=set();active={};index=defaultdict(int);rhythm_active={};percussion=[]
        controls=[c for c in builder.controls if c.device_id==device.device_id]
        def pitch(ch):
            if 0x10+ch not in known or 0x20+ch not in known:return None
            high=registers[0x20+ch];fnum=registers[0x10+ch]|((high&1)<<8);block=(high>>1)&7
            return device.clock_hz/72*fnum*2**block/2**19 if device.clock_hz else None
        def voice(ch):
            inst=registers[0x30+ch]>>4 if 0x30+ch in known else None
            return builder.voice(device,'fm',(('instrument',inst),('custom_patch',tuple(
                registers[i] if i in known else None for i in range(8)) if inst in (0,None) else ())))
        def finish(ch,at):
            row=active.pop(ch,None)
            if row is None:return
            start=row['start'];uid=f'{device.device_id}:fm:{ch}:gate:{index[ch]}';index[ch]+=1
            builder.units.append(NativeUnit(uid,device.device_id,'fm',ch,start,at,
                tuple(row['pitch']),tuple(row['volume']),tuple(row['voice']),
                builder.control_ids(device,'fm',ch,start,at),(), 'melody',
                (('boundary_origin','observed_key_or_rhythm_resource'),('volume_domain','native_attenuation'))))
        for c in controls:
            p=dict(c.parameters);register=p['register']
            from native_registers import encode_control
            value=encode_control(c,device)[2]
            if register>=64:continue
            old_rhythm=registers[14]
            registers[register]=value
            known.add(register)
            new_rhythm=registers[14]
            for ch in range(9):
                enabled=bool(registers[0x20+ch]&16) and not (ch>=6 and new_rhythm&32)
                if not enabled:finish(ch,c.sample);continue
                if ch not in active:
                    active[ch]=dict(start=c.sample,pitch=[],volume=[],voice=[])
                row=active[ch];_add_curve(row['pitch'],c.sample,pitch(ch))
                _add_curve(row['volume'],c.sample,registers[0x30+ch]&15 if 0x30+ch in known else None)
                _add_curve(row['voice'],c.sample,voice(ch))
            if register==14:
                old=old_rhythm&31 if old_rhythm&32 else 0;new=new_rhythm&31 if new_rhythm&32 else 0
                for i,(bit,family) in enumerate(((16,'BD'),(8,'SD'),(4,'TOM'),(2,'CYM'),(1,'HH'))):
                    if old&bit and not new&bit:
                        row=rhythm_active.pop(i,None)
                        if row is not None:
                            percussion[row]['stop']=c.sample;percussion[row]['controls'].append(c.control_id)
                    if new&bit and not old&bit:
                        row=dict(instrument=i,family=family,start=c.sample,stop=None,volume=[],controls=[])
                        percussion.append(row);rhythm_active[i]=len(percussion)-1
            levels=(registers[0x36]&15 if 0x36 in known else None,
                    registers[0x37]&15 if 0x37 in known else None,
                    registers[0x38]>>4 if 0x38 in known else None,
                    registers[0x38]&15 if 0x38 in known else None,
                    registers[0x37]>>4 if 0x37 in known else None)
            for i,identity in rhythm_active.items():
                row=percussion[identity];_add_curve(row['volume'],c.sample,levels[i]);row['controls'].append(c.control_id)
        for ch in list(active):finish(ch,builder.bundle['source_end_sample'])
        for i,row in enumerate(percussion):
            builder.percussion.append(NativePercussion(f'{device.device_id}:rhythm:{i}',device.device_id,
                str(row['instrument']),row['family'],row['start'],row['stop'],tuple(row['volume']),(),
                tuple(row['controls']),True,(('volume_domain','native_attenuation'),)))


def _opna_aux(builder):
    for device in list(builder.devices.values()):
        if device.chip!='opna':continue
        registers={};prescale=6;active={};indices=defaultdict(int);rhythm=[];latest={}
        controls=[c for c in builder.controls if c.device_id==device.device_id]
        def finish(channel,at):
            row=active.pop(channel,None)
            if row is None:return
            uid=f'{device.device_id}:ssg:{channel}:gate:{indices[channel]}';indices[channel]+=1
            builder.units.append(NativeUnit(uid,device.device_id,'ssg',channel,row['start'],at,
                tuple(row['pitch']),tuple(row['volume']),tuple(row['voice']),
                builder.control_ids(device,'ssg',channel,row['start'],at),(),'melody',
                (('boundary_origin','source_audibility'),('volume_domain','native_ssg_amplitude_register'))))
        for c in controls:
            p=dict(c.parameters);register=p['register'];port=p['port']
            from native_registers import encode_control
            value=encode_control(c,device)[2]
            if port:continue
            registers[register]=value
            if register in (0x2d,0x2e,0x2f):
                prescale=6 if register==0x2d else 3 if register==0x2e and prescale==6 else prescale if register==0x2e else 2
            for channel in range(3):
                mixer=registers.get(7);amplitude=registers.get(8+channel,0)
                enabled=mixer is not None and (not mixer&(1<<channel) or not mixer&(8<<channel)) and amplitude&31
                if not enabled:finish(channel,c.sample);continue
                if channel not in active:active[channel]=dict(start=c.sample,pitch=[],volume=[],voice=[])
                row=active[channel]
                low=registers.get(2*channel);high=registers.get(2*channel+1)
                period=None if low is None or high is None else low|((high&15)<<8)
                hz=device.clock_hz/{6:4,3:2,2:1}[prescale]/(16*max(1,period)) if period is not None else None
                _add_curve(row['pitch'],c.sample,hz);_add_curve(row['volume'],c.sample,amplitude&31)
                identity=builder.voice(device,'ssg',(('tone_enabled',not bool(mixer&(1<<channel))),
                    ('noise_enabled',not bool(mixer&(8<<channel))),('hardware_envelope',bool(amplitude&16)),
                    ('envelope_shape',registers.get(13) if amplitude&16 else None)))
                _add_curve(row['voice'],c.sample,identity)
            if register==0x10:
                for i,family in enumerate(('BD','SD','CYM','HH','TOM','RIM')):
                    if not value&(1<<i):continue
                    if value&128:
                        if i in latest:
                            stopped=rhythm[latest.pop(i)];stopped['stop']=c.sample;stopped['controls'].append(c.control_id)
                    else:
                        rhythm.append(dict(instrument=i,family=family,start=c.sample,stop=None,volume=[],controls=[]))
                        latest[i]=len(rhythm)-1
            for i,index in latest.items():
                row=rhythm[index]
                if register in (0x11,0x18+i,0x10):
                    _add_curve(row['volume'],c.sample,registers[0x18+i]&31 if 0x18+i in registers else None)
                    row['controls'].append(c.control_id)
        for channel in list(active):finish(channel,builder.bundle['source_end_sample'])
        for i,row in enumerate(rhythm):
            builder.percussion.append(NativePercussion(f'{device.device_id}:rhythm:{i}',device.device_id,
                str(row['instrument']),row['family'],row['start'],row['stop'],tuple(row['volume']),(),
                tuple(row['controls']),True,(('volume_domain','native_rhythm_attenuation'),
                    ('global_total_level_retained_in_controls',True))))


def _patterns(units,root,stem,end_sample):
    """Describe complete-unit repetition without replacing/expanding controls."""
    from loop_structure import LoopStructure
    parts=defaultdict(list);patterns=[];artifacts=[]
    for unit in units:parts[unit.device_id,unit.section,unit.channel].append(unit)
    for (device,section,channel),rows in sorted(parts.items()):
        rows.sort(key=lambda u:(u.start_sample,u.end_sample,u.unit_id))
        keys=[]
        for i,u in enumerate(rows):
            next_start=rows[i+1].start_sample if i+1<len(rows) else end_sample
            def relative(curve):return tuple((at-u.start_sample,value) for at,value in curve)
            keys.append((u.end_sample-u.start_sample,next_start-u.end_sample,relative(u.pitch_curve),
                         relative(u.volume_curve),relative(u.voice_curve),u.role))
        structure=LoopStructure.build(keys)
        prefix=root/f'{stem}.native_music.{device.replace(":","_")}.{section}.ch{channel}'
        structure.dump(prefix);artifacts.append(str(prefix))
        def visit(nodes,depth=0):
            for node in nodes:
                if not node.children:continue
                width=(node.end-node.start)//node.repeats
                patterns.append(dict(device_id=device,section=section,channel=channel,
                    start_unit=node.start,end_unit=node.end,body_units=width,repeats=node.repeats,depth=depth,
                    body_unit_ids=tuple(u.unit_id for u in rows[node.start:node.start+width]),
                    equality_basis='complete unit duration/gap/pitch/volume/voice; native shared controls remain separate',
                    executable=False))
                visit(node.children,depth+1)
        visit(structure.tree)
    return tuple(patterns),tuple(artifacts)


def build_native_performance(source,outdir,stem=None,legacy_performances=(),legacy_opll_segments=None):
    """Build source-native musical structure with reversible control evidence."""
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    stem=('source' if isinstance(source,(bytes,bytearray,memoryview)) else Path(source).stem) if stem is None else stem
    bundle=analyze_source(source,root,stem)
    builder=_Builder(bundle);builder.commands()
    for chip in ('opm','opna'):builder.fm(chip)
    builder.dcsg()
    performances,_=_legacy_performances(bundle,root,stem,legacy_performances,legacy_opll_segments,bundle['raw'])
    _legacy_units(builder,performances);_opll(builder);_opna_aux(builder)
    membership=defaultdict(list)
    for unit in builder.units:
        for identity in unit.control_ids:membership[identity].append(unit.unit_id)
    controls=tuple(replace(c,unit_ids=tuple(membership[c.control_id])) for c in builder.controls)
    raw=bundle['raw'];gd3=b''
    offset=int.from_bytes(raw[0x14:0x18],'little')
    if offset:
        address=0x14+offset
        if address+12>len(raw) or raw[address:address+4]!=b'Gd3 ':raise ValueError('Invalid native source GD3 metadata')
        length=int.from_bytes(raw[address+8:address+12],'little')+12
        if address+length>len(raw):raise ValueError('Truncated native source GD3 metadata')
        gd3=raw[address:address+length]
    loop=bundle['loop'];loop_sample=loop_order=None
    if loop.get('status')=='valid':
        loop_sample=loop['loop_start_samples']
        loop_order=next((i for i,e in enumerate(bundle['events']) if e.address==loop['loop_address']),None)
    patterns,pattern_artifacts=_patterns(builder.units,root,stem,bundle['source_end_sample'])
    metadata=(('gd3_hex',gd3.hex()),('native_analysis',bundle['report']),('pattern_artifacts',pattern_artifacts),
        ('wait_override_in_loop',loop.get('status')=='valid' and any(e.command==0x64 for e in bundle['events'])),
        ('native_source_evidence',str((root/f'{stem}.native.source.json').resolve())),
        ('opm_unwritten_fraction_assumption','Derived pitch assumes reset KF=0; native unknown state remains unknown'),
        ('pcm_policy','original native commands/data/stream dependencies; no bank conversion or waveform generation'))
    performance=NativePerformance(tuple(sorted(builder.devices.values(),key=lambda d:d.device_id)),
        tuple(builder.units),controls,tuple(builder.voices.values()),tuple(builder.percussion),tuple(builder.packets),
        bundle['source_end_sample'],bundle['source_sha256'],raw[:bundle['header']['data_start']].hex(),
        loop_sample,loop_order,metadata,tuple(builder.decisions),patterns)
    performance.dump(root,stem)
    return performance
