"""Native chip parameter codecs, independent of source files and MML syntax.

Every observed field is retained, including reserved packed bits. Reconstruction
encodes the typed parameter values; no original FM command bytes are replayed.
"""
from native_music import NativeControl


RECIPES = {
    'huc_select': (('channel_select',7,0),),
    'huc_balance': (('right_level',15,0),('left_level',240,4)),
    'huc_period_low': (('period_low',255,0),),
    'huc_period_high': (('period_high',15,0),),
    'huc_control': (('level',31,0),('dda_enabled',64,6),('enabled',128,7)),
    'huc_wave_data': (('sample_u5',31,0),),
    'huc_sample_data': (('sample_u5',31,0),),
    'huc_noise': (('rate',31,0),('enabled',128,7)),
    'huc_lfo_frequency': (('frequency',255,0),),
    'huc_lfo_control': (('mode',3,0),('reset',128,7)),
    'opm_test': (('test_flags',255,0),),
    'opm_timer_a_high': (('timer_a_high',255,0),),
    'opm_timer_a_low': (('timer_a_low',3,0),),
    'opm_timer_b': (('timer_b',255,0),),
    'opm_timer_control': (('timer_flags',255,0),),
    'opm_lfo_rate': (('rate',255,0),),
    'opm_key': (('channel_code',7,0),('key_mask',120,3)),
    'opm_channel': (('algorithm',7,0),('feedback',56,3),('left',64,6),('right',128,7)),
    'opm_pitch_note': (('note_code',15,0),('octave',112,4)),
    'opm_pitch_fraction': (('fraction',252,2),),
    'opm_sensitivity': (('ams',3,0),('pms',112,4)),
    'opm_operator_multiple': (('multiple',15,0),('detune',112,4)),
    'fm_operator_level': (('total_level',127,0),),
    'fm_operator_attack': (('attack',31,0),('key_scale',192,6)),
    'fm_operator_decay1': (('decay1',31,0),('am_enabled',128,7)),
    'opm_operator_decay2': (('decay2',31,0),('detune2',192,6)),
    'fm_operator_release': (('release',15,0),('sustain_level',240,4)),
    'opm_noise': (('rate',31,0),('enabled',128,7)),
    'opm_modulation_depth': (('depth',127,0),('phase_modulation',128,7)),
    'opm_lfo_wave': (('waveform',3,0),('ct',192,6)),
    'opna_key': (('channel_code',7,0),('key_mask',240,4)),
    'opna_operator_multiple': (('multiple',15,0),('detune',112,4)),
    'opna_operator_decay2': (('decay2',31,0),),
    'opna_operator_ssg': (('ssg_shape',7,0),('ssg_enabled',8,3)),
    'opna_frequency_high': (('fnum_high',7,0),('block',56,3)),
    'opna_channel': (('algorithm',7,0),('feedback',56,3)),
    'opna_pan_modulation': (('pms',7,0),('ams',48,4),('right',64,6),('left',128,7)),
    'opna_lfo': (('rate',7,0),('enabled',8,3)),
    'opna_timer_a_high': (('timer_a_high',255,0),),
    'opna_timer_a_low': (('timer_a_low',3,0),),
    'opna_timer_b': (('timer_b',255,0),),
    'opna_mode': (('timer_flags',63,0),('channel3_special',64,6),('csm',128,7)),
    'opna_channel_enable': (('lower_flags',127,0),('six_channel_enabled',128,7)),
    'opna_prescaler_select': (('ignored_write_data',255,0),),
    'opna_rhythm_key': (('instrument_mask',63,0),('dump',128,7)),
    'opna_rhythm_total_level': (('attenuation',63,0),),
    'opna_rhythm_instrument': (('attenuation',31,0),('right',64,6),('left',128,7)),
    'opna_frequency_low': (('fnum_low',255,0),),
    'ssg_period_low': (('period_low',255,0),),
    'ssg_period_high': (('period_high',15,0),),
    'ssg_noise': (('period',31,0),),
    'ssg_amplitude': (('level',15,0),('envelope_enabled',16,4)),
    'ssg_shape': (('shape',15,0),),
    'ssg_mixer': (('tone_disable_mask',7,0),('noise_disable_mask',56,3),('io_flags',192,6)),
    'ssg_envelope_low': (('envelope_low',255,0),),
    'ssg_envelope_high': (('envelope_high',255,0),),
    'opll_pitch_low': (('fnum_low',255,0),),
    'opll_pitch_high': (('fnum_high',1,0),('block',14,1),('key_on',16,4),('sustain',32,5)),
    'opll_instrument_level': (('attenuation',15,0),('instrument',240,4)),
    'opll_patch': (('patch_byte',255,0),),
    'opll_rhythm': (('instrument_mask',31,0),('mode',32,5)),
    'scc_wave': (('sample_byte',255,0),),
    'scc_period_low': (('period_low',255,0),),
    'scc_period_high': (('period_high',15,0),),
    'scc_level': (('level',15,0),),
    'scc_enable': (('mask',31,0),),
}


def _recipe(kind, value):
    fields = RECIPES.get(kind)
    if fields is None:
        return (('native_value',value),)
    known=0;result=[]
    for name,mask,shift in fields:
        known |= mask;result.append((name,(value&mask)>>shift))
    result.append(('reserved',value&~known&255))
    return tuple(result)


def _value(control):
    p=dict(control.parameters);fields=RECIPES.get(control.kind)
    if fields is None:
        value=p['native_value']
    else:
        value=p.get('reserved',0);known=0
        for name,mask,shift in fields:
            field=p[name]
            if not isinstance(field,int) or not 0<=field<=mask>>shift:
                raise ValueError(f'Invalid {control.kind}/{name}')
            known |= mask;value |= field<<shift
        if p.get('reserved',0)&known:
            raise ValueError('Reserved native bits overlap typed fields')
    if not isinstance(value,int) or not 0<=value<=255:
        raise ValueError('Native register value outside byte range')
    return value


def decode_control(device, event, raw, *, order=None, latches=None):
    """Decode one supported non-PCM command into an original-time control."""
    command,pos=event.command,event.address
    chip=device.chip;port=0;channel=None;section='shared';kind=None
    if chip=='huc6280':
        latches={} if latches is None else latches
        register=raw[pos+1]&127;data=raw[pos+2]
        if register==0:latches[device.device_id,'select']=data&7
        selected=latches.get((device.device_id,'select'),0)
        if register==4:latches[device.device_id,selected,'control']=data
        if register==7:latches[device.device_id,selected,'noise']=data
        control=latches.get((device.device_id,selected,'control'),0)
        noise=latches.get((device.device_id,selected,'noise'),0)
        if 2<=register<=7:
            channel=selected
            section='noise' if selected>=4 and noise&128 else 'pcm_dda' if control&64 else 'wave'
        kind={0:'huc_select',1:'huc_balance',2:'huc_period_low',3:'huc_period_high',
            4:'huc_control',5:'huc_balance',6:'huc_sample_data' if control&64 else 'huc_wave_data',
            7:'huc_noise',8:'huc_lfo_frequency',9:'huc_lfo_control'}.get(register,'huc_unknown_register')
    elif chip=='dcsg':
        data=raw[pos+1]
        if command in (0x4f,0x3f):
            kind='dcsg_stereo';parameters=(('stereo_mask',data),)
        elif data&128:
            register=(data>>4)&7
            if latches is not None:latches[device.device_id]=register
            channel=register//2;section='noise' if channel==3 else 'tone'
            kind='dcsg_latch';parameters=(('register',register),('low_nibble',data&15))
        else:
            register=(latches or {}).get(device.device_id)
            channel=register//2 if register is not None else None
            section='noise' if channel==3 else 'tone'
            kind='dcsg_data';parameters=(('register',register),('data_bits',data&63),('reserved',data&64))
        return NativeControl(f'{device.device_id}:control:{order if order is not None else event.source_event_id}',
            device.device_id,section,channel,event.vgmticks,event.source_event_id if order is None else order,
            kind,parameters,event.source_event_id)
    if chip=='scc':
        port=raw[pos+1]&127;register=raw[pos+2];data=raw[pos+3]
        if port in (0,4):kind='scc_wave';section='wave';channel=register//32
        elif port==1:
            kind='scc_period_high' if register&1 else 'scc_period_low';channel=register//2;section='tone'
        elif port==2:kind='scc_level';channel=register;section='tone'
        elif port==3:kind='scc_enable';section='tone'
        else:kind='scc_native_parameter'
    elif chip!='huc6280':
        register,data=raw[pos+1:pos+3]
        if chip=='opm':
            from native_imports.opm import register_channel
            channel=register_channel(register,data)
            section='fm' if channel is not None else 'shared'
            if register==8:kind='opm_key'
            elif 0x20<=register<=0x27:kind='opm_channel'
            elif 0x28<=register<=0x2f:kind='opm_pitch_note'
            elif 0x30<=register<=0x37:kind='opm_pitch_fraction'
            elif 0x38<=register<=0x3f:kind='opm_sensitivity'
            elif register>=0x40:
                kind=('opm_operator_multiple','fm_operator_level','fm_operator_attack',
                      'fm_operator_decay1','opm_operator_decay2','fm_operator_release')[(register-0x40)//32]
            else:kind={1:'opm_test',0x0f:'opm_noise',0x10:'opm_timer_a_high',0x11:'opm_timer_a_low',
                0x12:'opm_timer_b',0x14:'opm_timer_control',0x18:'opm_lfo_rate',
                0x19:'opm_modulation_depth',0x1b:'opm_lfo_wave'}.get(register,'opm_shared_parameter')
        elif chip=='opna':
            from native_imports.opna import register_channel
            port=int(command in (0x57,0xa7));channel=register_channel(register,data,port)
            section='fm' if channel is not None else 'shared'
            if not port and register<=15:
                section='ssg';channel=register//2 if register<=5 else register-8 if 8<=register<=10 else None
                kind=('ssg_period_high' if register&1 else 'ssg_period_low') if register<=5 else {
                    6:'ssg_noise',7:'ssg_mixer',8:'ssg_amplitude',9:'ssg_amplitude',10:'ssg_amplitude',
                    11:'ssg_envelope_low',12:'ssg_envelope_high',13:'ssg_shape'}.get(register,'ssg_io')
            elif not port and 0x10<=register<=0x1f:
                section='rhythm';kind=('opna_rhythm_key' if register==0x10 else
                    'opna_rhythm_total_level' if register==0x11 else
                    'opna_rhythm_instrument' if 0x18<=register<=0x1d else 'opna_rhythm_parameter')
            elif register==0x28 and not port:kind='opna_key'
            elif 0x30<=register<=0x9f:
                kind=('opna_operator_multiple','fm_operator_level','fm_operator_attack','fm_operator_decay1',
                      'opna_operator_decay2','fm_operator_release','opna_operator_ssg')[(register-0x30)//16]
            elif 0xa0<=register<=0xae:kind='opna_frequency_high' if register&4 else 'opna_frequency_low'
            elif 0xb0<=register<=0xb2:kind='opna_channel'
            elif 0xb4<=register<=0xb6:kind='opna_pan_modulation'
            else:kind={0x22:'opna_lfo',0x24:'opna_timer_a_high',0x25:'opna_timer_a_low',
                0x26:'opna_timer_b',0x27:'opna_mode',0x29:'opna_channel_enable',
                0x2d:'opna_prescaler_select',0x2e:'opna_prescaler_select',0x2f:'opna_prescaler_select'}.get(register,'opna_shared_parameter')
        elif chip=='psg':
            register&=127;section='tone';channel=register//2 if register<=5 else register-8 if 8<=register<=10 else None
            kind=('ssg_period_high' if register&1 else 'ssg_period_low') if register<=5 else {
                6:'ssg_noise',7:'ssg_mixer',8:'ssg_amplitude',9:'ssg_amplitude',10:'ssg_amplitude',
                11:'ssg_envelope_low',12:'ssg_envelope_high',13:'ssg_shape'}.get(register,'ssg_io')
        elif chip=='opll':
            section='fm'
            if 0x10<=register<=0x18:kind='opll_pitch_low';channel=register-0x10
            elif 0x20<=register<=0x28:kind='opll_pitch_high';channel=register-0x20
            elif 0x30<=register<=0x38:kind='opll_instrument_level';channel=register-0x30
            elif register<=7:kind='opll_patch';section='shared'
            elif register==14:kind='opll_rhythm';section='rhythm'
            else:kind='opll_shared_parameter';section='shared'
        else:
            raise ValueError(f'No native parameter decoder for {chip}')
    parameters=(('register',register),('port',port))+_recipe(kind,data)
    return NativeControl(f'{device.device_id}:control:{order if order is not None else event.source_event_id}',
        device.device_id,section,channel,event.vgmticks,event.source_event_id if order is None else order,
        kind,parameters,event.source_event_id)


def encode_control(control, device):
    """Encode typed native control values without consulting original VGM bytes."""
    p=dict(control.parameters);chip=device.chip
    if chip=='dcsg':
        if control.kind=='dcsg_stereo':return bytes((0x3f if device.instance else 0x4f,p['stereo_mask']))
        if control.kind=='dcsg_latch':value=128|(p['register']<<4)|p['low_nibble']
        elif control.kind=='dcsg_data':value=p['data_bits']|p['reserved']
        else:raise ValueError('Unknown DCSG control')
        return bytes((0x30 if device.instance else 0x50,value))
    register=p['register'];value=_value(control)
    if chip=='opm':return bytes((0xa4 if device.instance else 0x54,register,value))
    if chip=='opna':return bytes(((0xa6 if device.instance else 0x56)+p['port'],register,value))
    if chip=='opll':return bytes((0xa1 if device.instance else 0x51,register,value))
    if chip=='psg':return bytes((0xa0,register|(device.instance<<7),value))
    if chip=='scc':return bytes((0xd2,p['port']|(device.instance<<7),register,value))
    if chip=='huc6280':return bytes((0xb9,register|(device.instance<<7),value))
    raise ValueError(f'No native register codec for {chip}')
