"""FM target writes derived solely from editable native musical records.

Curves/voices own pitch, levels and synthesis; observed controls supply operator
key transitions and shared chip facilities. No source file or Segment is read.
"""
from collections import Counter
import math

from native_registers import _value
from psg_scc_opm import opm_pitch
from opm_target_vgm import (_opna_pitch, _opm_lfo_hz, _opna_lfo_rate,
    _opna_pms, _opna_ams, _OPM_PMS_FULL_CENTS, _OPM_AMS_FULL_DB)

CARRIERS = (8, 8, 8, 8, 12, 14, 14, 15)
FM_CHIPS = ('opm', 'opna', 'opn2')


def _at(curve, sample, default=None):
    for at, value in curve:
        if at > sample:
            break
        default = value
    return default


def project_fm(performance, target_chip, target_clock, *, force=False):
    """Return inspectable writes, counted losses, and static FM lane allocation.

    A lane is reserved for its whole duration, including envelope release. When
    force is true, excess lanes are omitted with an explicit loss per unit.
    """
    if target_chip not in FM_CHIPS or target_clock <= 0:
        raise ValueError('FM projection requires an OPM/OPNA/OPN2 target and positive clock')
    devices = {d.device_id: d for d in performance.devices}
    voices = {v.voice_id: v for v in performance.voices}
    units = [u for u in performance.units if u.section == 'fm' and devices[u.device_id].chip in FM_CHIPS]
    capacity = 8 if target_chip == 'opm' else 6
    allocation = {}
    for lane in sorted({(u.device_id, u.channel) for u in units}):
        free = [ch for ch in range(capacity) if ch not in allocation.values()]
        if free:
            allocation[lane] = lane[1] if lane[1] in free else free[0]
    rows, losses = [], Counter()
    if len(allocation) < len({(u.device_id, u.channel) for u in units}) and not force:
        raise ValueError('FM target capacity exceeded; force permits explicitly reported lane omission')
    controls = sorted(performance.controls, key=lambda c: (c.sample, c.order))
    active_devices = {u.device_id for u in units if (u.device_id, u.channel) in allocation}
    shared_owner = min(active_devices) if active_devices else None

    def emit(unit, sample, order, register, value, reason, port=0, control=None):
        opcode = 0x54 if target_chip == 'opm' else (0x56 if target_chip == 'opna' else 0x52) + port
        rows.append(dict(sample=sample, order=order, command=bytes((opcode, register, value & 255)),
            unit_id=unit.unit_id if unit else '', device_id=unit.device_id if unit else control.device_id,
            source_indices=unit.source_indices if unit else control.source_indices, reason=reason))

    def key(unit, sample, order, mask, reason):
        channel = allocation[unit.device_id, unit.channel]
        value = mask << (3 if target_chip == 'opm' else 4)
        value |= channel if target_chip == 'opm' else (channel % 3) | ((channel // 3) << 2)
        emit(unit, sample, order, 8 if target_chip == 'opm' else 0x28, value, reason)

    for unit in units:
        lane = unit.device_id, unit.channel
        if lane not in allocation:
            losses['fm_units_omitted_capacity'] += 1
            continue
        device = devices[unit.device_id]
        if dict(unit.parameters).get('onset_controls_after_key'):
            losses['fm_same_sample_onset_control_order_collapsed']+=len(dict(unit.parameters)['onset_controls_after_key'])
        pitch_values = [_at(unit.pitch_curve, unit.start_sample),
            *(hz for at, hz in unit.pitch_curve if unit.start_sample <= at < unit.end_sample)]
        if any(hz is None or not math.isfinite(hz) or hz <= 0 for hz in pitch_values):
            losses['fm_unknown_pitch_units_muted'] += 1
            continue
        ch = allocation[lane]
        port, local = (0, ch) if target_chip == 'opm' else divmod(ch, 3)
        uc = [c for c in controls if c.device_id == unit.device_id and c.channel == unit.channel
              and c.section == 'fm']
        all_keys = [c for c in uc if c.kind in ('opm_key', 'opna_key', 'opn2_key')]
        source_start=dict(unit.parameters).get('source_gate_start_order')
        source_end=dict(unit.parameters).get('source_gate_end_order')
        keys=[c for c in all_keys if (c.sample!=unit.start_sample or source_start is None or c.order>=source_start)
            and (c.sample!=unit.end_sample or source_end is None or c.order<=source_end)]
        initial = [c for c in all_keys if c.sample<unit.start_sample or c.sample==unit.start_sample and (source_start is None or c.order<=source_start)]
        initial_mask = dict(initial[-1].parameters).get('key_mask', 0) if initial else 0
        # Moved/decoded gates restore observed operator subsets even when their
        # original key edge is later than the authored musical onset.
        if not initial_mask:
            observed = [dict(c.parameters).get('key_mask', 0) for c in keys
                if dict(c.parameters).get('key_mask') and
                (c.control_id in unit.control_ids or unit.start_sample <= c.sample < unit.end_sample)]
            if not observed:
                observed = [dict(c.parameters).get('key_mask', 0) for c in initial
                            if dict(c.parameters).get('key_mask')]
            initial_mask = observed[0] if observed else 15
        boundary = [c for c in uc if c.sample == unit.start_sample]
        start_order = source_start if source_start is not None else min((c.order for c in boundary), default=0)
        times = sorted({unit.start_sample, *(at for curve in (unit.pitch_curve, unit.volume_curve, unit.voice_curve)
            for at, _ in curve if unit.start_sample <= at < unit.end_sample)})
        if device.chip == 'opm' and target_chip != 'opm':
            times = sorted(set(times) | {c.sample for c in controls if c.device_id == unit.device_id and
                c.kind == 'opm_modulation_depth' and unit.start_sample <= c.sample < unit.end_sample})
        previous_voice = previous_pitch = previous_level = object()
        for sample in times:
            same = [c.order for c in uc if c.sample == sample]
            order = min(same, default=start_order) - .5
            voice_id = _at(unit.voice_curve, sample)
            voice = voices.get(voice_id)
            vp = dict(voice.parameters) if voice else {}
            level = _at(unit.volume_curve, sample, 0)
            pms, ams = vp.get('pms') or 0, vp.get('ams') or 0
            if device.chip == 'opm' and target_chip != 'opm':
                pmd = amd = 0
                for c in controls:
                    if c.sample > sample:
                        break
                    if c.device_id == unit.device_id and c.kind == 'opm_modulation_depth':
                        cp = dict(c.parameters)
                        if cp.get('phase_modulation'):
                            pmd = cp.get('depth', 0)
                        else:
                            amd = cp.get('depth', 0)
                pms = _opna_pms(_OPM_PMS_FULL_CENTS[pms] * pmd / 127)
                ams = _opna_ams(_OPM_AMS_FULL_DB[ams] * amd / 127)
            voice_state = voice_id, pms, ams
            changed = voice_state != previous_voice
            if not voice:
                losses['fm_missing_voice'] += 1
            algorithm = vp.get('algorithm') or 0
            if changed:
                source_divisor = 64 if device.chip == 'opm' else 144
                target_divisor = 64 if target_chip == 'opm' else 144
                if device.clock_hz and abs(device.clock_hz/source_divisor/(target_clock/target_divisor)-1) > 1e-6:
                    losses['fm_envelope_clock_difference'] += 1
                left, right = vp.get('left'), vp.get('right')
                left = 1 if left is None else left
                right = 1 if right is None else right
                fb = vp.get('feedback') or 0
                if target_chip == 'opm':
                    emit(unit, sample, order, 0x20+ch, left*64+right*128+fb*8+algorithm, 'native voice algorithm/pan')
                    emit(unit, sample, order, 0x38+ch, pms*16+ams, 'native voice modulation sensitivity')
                else:
                    emit(unit, sample, order, 0xb0+local, fb*8+algorithm, 'native voice algorithm', port)
                    emit(unit, sample, order, 0xb4+local, left*128+right*64+ams*16+pms, 'native voice pan/modulation', port)
                if device.chip != target_chip and (pms or ams):
                    losses['fm_cross_chip_modulation_depth_approximation'] += 1
            if changed or level != previous_level:
                for bank, operator in enumerate(vp.get('operators', ())):
                    op = dict(operator)
                    def get(name, alternate=None, default=0):
                        value = op.get(name, op.get(alternate, default))
                        return default if value is None else value
                    tl = get('tl') + ((level or 0) if CARRIERS[algorithm] & (1 << bank) else 0)
                    if tl < 0 or tl > 127:
                        losses['fm_total_level_clamped'] += 1
                    tl = max(0, min(127, round(tl)))
                    if target_chip == 'opm':
                        offset = bank*8+ch
                        registers = [(0x60, tl)]
                        if changed:
                            registers += [(0x40, get('dt1', 'dt')*16+get('mul')),
                                (0x80, get('ks')*64+get('ar')),
                                (0xa0, get('am_enabled')*128+get('d1r')),
                                (0xc0, get('dt2')*64+get('d2r')),
                                (0xe0, get('d1l', 'sl')*16+get('rr'))]
                            if get('ssg_eg_enabled'):
                                losses['fm_ssg_eg_unavailable_on_opm'] += 1
                    else:
                        offset = bank*4+local
                        registers = [(0x40, tl)]
                        if changed:
                            registers += [(0x30, get('dt', 'dt1')*16+get('mul')),
                                (0x50, get('ks')*64+get('ar')),
                                (0x60, get('am_enabled')*128+get('d1r')),
                                (0x70, get('d2r')), (0x80, get('sl', 'd1l')*16+get('rr')),
                                (0x90, get('ssg_eg_enabled')*8+get('ssg_eg_shape'))]
                            if get('dt2'):
                                losses['fm_opm_dt2_unavailable_on_opn'] += 1
                    for base, value in registers:
                        emit(unit, sample, order, base+offset, value, 'native voice and carrier attenuation', port)
            hz = _at(unit.pitch_curve, sample)
            if hz != previous_pitch:
                if hz is None or not math.isfinite(hz) or hz <= 0:
                    losses['fm_unknown_or_invalid_pitch'] += 1
                elif target_chip == 'opm':
                    try:
                        kc, kf, actual = opm_pitch(hz, target_clock)
                    except ValueError:
                        if not force:
                            raise
                        kc, kf, actual = opm_pitch(hz, target_clock, clamp=True)
                        losses['fm_pitch_clamped'] += 1
                    emit(unit, sample, order, 0x28+ch, kc, 'native Hz to target KC')
                    emit(unit, sample, order, 0x30+ch, kf, 'native Hz to target KF')
                else:
                    block, fnum, actual = _opna_pitch(hz, target_clock)
                    if hz > 2047 * target_clock / (144 * 2**14):
                        if not force:
                            raise ValueError('Frequency outside OPN FNUM/BLOCK range')
                        losses['fm_pitch_clamped'] += 1
                    # High then low are one atomic commit. Never deduplicate the
                    # low write alone: the high latch may have changed.
                    emit(unit, sample, order, 0xa4+local, block*8+(fnum >> 8), 'native Hz atomic FNUM high', port)
                    emit(unit, sample, order, 0xa0+local, fnum & 255, 'native Hz atomic FNUM commit', port)
            previous_voice, previous_level, previous_pitch = voice_state, level, hz
        onset_keys = [c for c in keys if c.sample == unit.start_sample and dict(c.parameters).get('key_mask')]
        if onset_keys:
            for c in onset_keys:
                key(unit, c.sample, c.order, dict(c.parameters)['key_mask'], 'native operator key mask at unit onset')
        else:
            key(unit, unit.start_sample, start_order, initial_mask, 'native unit gate onset')
        for c in keys:
            if unit.start_sample < c.sample < unit.end_sample:
                mask = dict(c.parameters).get('key_mask', 0)
                # Full gate boundaries belong to the unit. A retained old
                # key-off must not shorten an edited gate; zero-duration
                # off/on retriggers remain ordered operator evidence.
                if not mask and not any(k.sample == c.sample and k.order > c.order and
                                        dict(k.parameters).get('key_mask') for k in keys):
                    losses['fm_observed_key_off_superseded_by_unit_gate'] += 1
                    continue
                key(unit, c.sample, c.order, mask, 'native internal operator key transition')
        ends = [c.order for c in keys if c.sample == unit.end_sample and not dict(c.parameters).get('key_mask')]
        held_loop = (performance.song_loop_sample is not None and unit.end_sample == performance.end_sample
                     and dict(unit.parameters).get('termination') == 'source_observation_end')
        if not held_loop:
            end_order=source_end if source_end is not None else min(ends, default=-1)
            if unit.end_sample==unit.start_sample:
                end_order=max(end_order,max((c.order for c in onset_keys),default=start_order)+1)
            key(unit, unit.end_sample, end_order, 0, 'native unit gate end; release envelope retained')
        up = dict(unit.parameters)
        for name in ('channel3_special_observed', 'csm_observed', 'noise_enabled_observed'):
            if up.get(name) and (device.chip != target_chip or ch != unit.channel):
                losses['fm_'+name+'_not_exactly_projected'] += 1

    # Only shared controls are replayable evidence; active voice/pitch/TL writes
    # are intentionally subordinate to the editable unit representation.
    special_high = {}
    for control in controls:
        device = devices[control.device_id]
        if device.chip not in FM_CHIPS or control.device_id not in active_devices:
            continue
        p = dict(control.parameters)
        if control.section == 'fm' and control.kind not in ('opm_key', 'opna_key', 'opn2_key'):
            register = p.get('register', -1)
            if control.kind=='opm_noise':
                if target_chip=='opm' and allocation.get((control.device_id,7))==7:
                    emit(None,control.sample,control.order,0x0f,_value(control),'native OPM noise on allocated channel 8',control=control)
                elif (control.device_id,7) in allocation:
                    losses['fm_native_noise_register_not_projected']+=1
                continue
            if 0xa8 <= register <= 0xae and device.chip in ('opna', 'opn2'):
                lane = control.device_id, control.channel
                if target_chip in ('opna', 'opn2') and allocation.get(lane) == 2:
                    slot = register & 3
                    if register & 4:
                        special_high[control.device_id, slot] = _value(control)
                    elif (control.device_id, slot) in special_high:
                        high = special_high[control.device_id, slot]
                        hz = (((high & 7) << 8) | _value(control)) * device.clock_hz / (144 * 2**(21-((high >> 3) & 7)))
                        block, fnum, _ = _opna_pitch(hz, target_clock)
                        emit(None, control.sample, control.order, 0xac+slot, block*8+(fnum >> 8), 'native channel3 special atomic high', control=control)
                        emit(None, control.sample, control.order, 0xa8+slot, fnum & 255, 'native channel3 special atomic commit', control=control)
                    else:
                        losses['fm_channel3_special_unknown_high'] += 1
                else:
                    losses['fm_channel3_special_frequency_unsupported'] += 1
                continue
            covering = any(u.device_id == control.device_id and u.channel == control.channel and
                           u.start_sample <= control.sample < u.end_sample for u in units)
            if not covering and control.sample > 0:
                losses['fm_postgate_or_setup_controls_not_projected'] += 1
            continue
        if control.section != 'shared':
            continue
        if control.device_id != shared_owner:
            losses['fm_shared_controls_conflicting_device_omitted'] += 1
            continue
        if 'register' not in p:
            losses['fm_shared_control_missing_register'] += 1
            continue
        reg, port = p['register'], p.get('port', 0)
        opn_family = device.chip in ('opna', 'opn2') and target_chip in ('opna', 'opn2')
        if device.chip == target_chip or opn_family:
            if control.kind in ('opna_lfo', 'opm_lfo_rate') and device.clock_hz != target_clock:
                losses['fm_shared_lfo_clock_difference'] += 1
            if control.kind == 'opna_prescaler_select':
                losses['fm_native_prescaler_not_replayed'] += 1
                continue
            if reg in (0x24, 0x25, 0x26, 0x27, 0x10, 0x11, 0x12, 0x14) and device.clock_hz != target_clock:
                losses['fm_timer_clock_difference'] += 1
            if control.kind == 'opna_channel_enable' and target_chip != 'opna':
                continue
            if control.kind == 'opn2_dac_enable':
                losses['fm_dac_enable_handled_by_pcm_projection'] += 1
                continue
            emit(None, control.sample, control.order, reg, _value(control), 'native shared FM control', port, control)
        elif control.kind == 'opna_lfo' and target_chip == 'opm':
            from opm_target_vgm import _OPNA_LFO_HZ
            enabled = p.get('enabled', 0)
            hz = _OPNA_LFO_HZ[p.get('rate', 0)] * device.clock_hz / 8000000
            rate = min(range(256), key=lambda r: abs(math.log2(_opm_lfo_hz(r, target_clock) / hz)))
            emit(None, control.sample, control.order, 0x18, rate, 'cross chip LFO rate approximation', control=control)
            emit(None, control.sample, control.order, 0x1b, 2, 'OPN triangle LFO', control=control)
            losses['fm_lfo_cross_chip_approximation'] += 1
        elif control.kind == 'opm_lfo_rate' and target_chip in ('opna', 'opn2'):
            hz = _opm_lfo_hz(p.get('rate', 0), device.clock_hz)
            rate, _, _ = _opna_lfo_rate(hz, target_clock)
            emit(None, control.sample, control.order, 0x22, rate | 8, 'cross chip LFO rate approximation', control=control)
            losses['fm_lfo_cross_chip_approximation'] += 1
        elif control.kind == 'opm_modulation_depth' and target_chip in ('opna', 'opn2'):
            losses['fm_lfo_cross_chip_approximation'] += 1
        elif control.kind == 'opm_lfo_wave' and target_chip in ('opna', 'opn2'):
            if p.get('waveform') != 2:
                losses['fm_opm_lfo_waveform_approximated'] += 1
        else:
            losses['fm_shared_'+control.kind+'_unsupported_on_'+target_chip] += 1
    if target_chip == 'opm' and shared_owner and devices[shared_owner].chip in ('opna', 'opn2'):
        from opn2_target_vgm import _LFO_BRIDGE_PMD, _LFO_BRIDGE_AMD
        lfo_controls = [c for c in controls if c.device_id == shared_owner and c.kind == 'opna_lfo']
        event_times = {c.sample for c in lfo_controls}
        selected_units = [u for u in units if u.device_id == shared_owner and
            (u.device_id, u.channel) in allocation]
        event_times.update(at for u in selected_units for at in
            (u.start_sample, u.end_sample, *(at for at, _ in u.voice_curve)))
        previous_depths = None
        for sample in sorted(event_times):
            enabled = False
            source_control = None
            for c in lfo_controls:
                if c.sample > sample:
                    break
                enabled = bool(dict(c.parameters).get('enabled'))
                source_control = c
            if source_control is None:
                continue
            sensitivities = []
            # Key-off starts an envelope release, not silence. The last voice
            # on a statically reserved lane still owns its LFO sensitivity.
            lane_owners = {}
            for u in sorted(selected_units, key=lambda u: (u.start_sample, u.unit_id)):
                if u.start_sample <= sample:
                    lane_owners[u.channel] = u
            for u in lane_owners.values():
                v = voices.get(_at(u.voice_curve, min(sample, max(u.start_sample, u.end_sample-1))))
                vp = dict(v.parameters) if v else {}
                sensitivities.append((vp.get('pms') or 0, vp.get('ams') or 0))
            pms = max((p for p, _ in sensitivities), default=0)
            ams = max((a for _, a in sensitivities), default=0)
            depths = (_LFO_BRIDGE_PMD.get(pms, 0), _LFO_BRIDGE_AMD.get(ams, 0)) if enabled else (0, 0)
            if depths != previous_depths:
                at_controls = [c.order for c in lfo_controls if c.sample == sample]
                order = max(at_controls)+.1 if at_controls else -.25
                emit(None, sample, order, 0x19, 0x80 | depths[0], 'measured OPN phase depth for active maximum PMS', control=source_control)
                emit(None, sample, order, 0x19, depths[1], 'measured OPN amplitude depth for active maximum AMS', control=source_control)
                previous_depths = depths
                losses['fm_lfo_bridge_depth_selections'] += 1
    rows.sort(key=lambda row: (row['sample'], row['order']))
    return rows, losses, allocation
