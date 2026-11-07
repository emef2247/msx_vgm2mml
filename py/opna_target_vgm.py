"""Native YM2608 (OPNA) Segments -> MSX cartridge variant VGMs.

Two compositions, mirroring the OPN2 route in opn2_target_vgm.py:

- ``makoto``: the OPNA Sound Cartridge alone. The source OPNA
  content is re-emitted at the cartridge's fixed 8.00 MHz stamp:
  FM, SSG, rhythm and ADPCM-B pass at register level, with the
  clock-derived quantities (FM F-numbers, SSG tone/noise/envelope
  periods, ADPCM-B delta-N, timer periods) rescaled from the
  source clock so the music keeps its pitch and tempo. Type-0x81
  ADPCM-B data blocks are carried verbatim as the stream prefix.
- ``sfg01`` (and ``opm4mhz`` at the 4 MHz OPM clock): the FM
  section is projected to the pseudo-OPM cartridge (YM2151) with
  the OPNA>OPM law V1, while the SSG, rhythm and ADPCM-B lanes
  stay on the OPNA cartridge. With ``layered``, the FM section
  additionally sounds on the OPNA itself (the register-level
  passthrough), as in the OPN2 layered composition.

The FM law body is ported from x68k_vgm2mml py/opna_opm.py
(claude/opna-voice lineage, revision
adb5ec3a075cf947791f5feedacc3c7bd207dc3e; the register mapping,
EG prescaler law and LFO laws are derived from the project's
ymfm-based audit) with the same target adaptations as the OPN2 port in
opn2_target_vgm.py: the OPM clock is a parameter (3.579545 MHz
cartridge clock by default) and the channel map is the identity
0..5 -> 0..5, because no OPM channel is reserved on this target.
The force output gate's mute test is inlined from x68k
py/opna_force.py (fm_mute_reasons).

There is no dac_y8950 composition for OPNA sources: the Y8950
variant of the OPN2 route relocates the YM2612 DAC lane, and an
OPNA source's sample lane (ADPCM-B) is native to the makoto
cartridge already; no Y8950 relocation law for it exists here,
so convert() refuses dac='y8950' and the export records the
variant unavailable instead of emitting a duplicate file.

Losses are counted, never silent. CSM, CH3 special mode and
unknown register effects refuse the FM projection unless
--force is given (the makoto passthrough carries them as-is:
the cartridge chip generates them itself).
"""
import csv
import json
import struct
from collections import Counter
from pathlib import Path

from psg_scc_opm import opm_pitch
from native_imports.opna import register_role
from native_imports.source import analyze_source
from native_imports.vgm_io import read_vgm_bytes
from opn2_target_vgm import (OPM4MHZ_CLOCK, OPNA_CLOCK, TARGET_CLOCK,
                             write_vgm)


# LFO rate mapping for the OPNA: same derivation as the OPN2
# table in opn2_target_vgm.py, but the OPNA FM sample clock is
# 7,987,200/144 = 55.5 kHz, so the nearest-OPM bytes differ.
# Each entry is the OPM byte nearest in Hz to the source rate
# (4.01/5.63/6.10/6.47/6.99/9.85/54.1/86.4 Hz). Source rate 7
# exceeds the OPM maximum and saturates at 0xff.
# Derivation script: opna_opm_voice study, lfo_rate_map.py.
#
# The OPM byte for a given Hz depends on the OPM clock actually
# stamped, so there are two tables. The 4 MHz table below served
# every target until 2026-11-06, but the sfg01 family stamps the
# OPM at 3,579,545 Hz, which made every bridged rate x0.8949 of
# intended; the 3,579,545 Hz table corrects that (opm4mhz keeps
# the 4 MHz table). Rederivation: opna_opm_voice study,
# LFO_BRIDGE_CORRECTION.md and lfo_bridge_rates.csv (2026-11-06).
_LFO_RATE_TO_OPM_4MHZ = (0xc1, 0xc8, 0xca, 0xcb, 0xcd, 0xd5, 0xfc, 0xff)
_LFO_RATE_TO_OPM = (0xc3, 0xca, 0xcd, 0xce, 0xd0, 0xd7, 0xff, 0xff)


def _lfo_rate_table(opm_clock):
    """Rate table for the OPM clock the target VGM actually stamps."""
    return (_LFO_RATE_TO_OPM_4MHZ if opm_clock == OPM4MHZ_CLOCK
            else _LFO_RATE_TO_OPM)


# LFO bridge depths, per sensitivity step (LFO_BRIDGE_CORRECTION.md,
# 2026-11-06). The depth series the original bridge derivation
# assumed for the OPN side, 3.4 * 2^k cents, is wrong above PMS 3:
# the render-verified OPNA PMS series is {3.4, 6.7, 10.1, 13.5,
# 20.2, 40.1, 79.3} cents, so the fixed PMD 86 was +187/+391 cents
# too deep at PMS 6/7. PMD/AMD are global OPM latches, so a bridge
# span selects the ideal value for the maximum step in use in
# that span (the span maximum governs the deepest channel; lower
# steps inherit the same latch, the documented trade-off of the
# per-activation rule). The OPNA AMS series {1.4, 5.9, 11.8} dB
# was verified correct; only AMS 1's AMD changes (16 -> 8).
_LFO_BRIDGE_PMD = {1: 85, 2: 83, 3: 61, 4: 41, 5: 31, 6: 15, 7: 15}
_LFO_BRIDGE_AMD = {1: 8, 2: 16, 3: 16}

# EG rate conversion. The OPN and OPM envelope cores share one
# design (EG clock = sample rate / 3, effective rate = 2R + the
# key-scale term, R = 0 frozen); only the sample rate differs.
# At prescaler 6 the nearest OPM rate is the source rate itself,
# but prescaler 3/2 sources run their envelopes 1.78x/2.67x
# faster and need +2/+3 rate steps to hold envelope times on
# OPM. Derived in the opna_opm_voice study (eg_rate_map.csv);
# the shift is additive in the 5-bit rate space and therefore
# independent of the key-scale term.
_EG_PRESCALE_SHIFT = {6: 0, 3: 2, 2: 3}

# Register roles that stay on the OPNA cartridge in the sfg01
# composition (and are therefore not part of the FM projection's
# unknown-write gate: the analysis files them as unmodeled
# because the FM segment model does not cover them).
NON_FM = {'ssg', 'rhythm', 'adpcm_b', 'irq_flag_control'}


def _eg_rate(rate, divisor):
    if not rate:
        return rate
    return min(31, rate + _EG_PRESCALE_SHIFT.get(divisor, 0))


def _eg_release(rr, divisor):
    # In effective-rate units the release rate is 4*RR+2 on both
    # chips (ymfm's OPN and OPM cores agree), so the prescaler
    # correction of +3.3/+5.7 effective-rate units is under one
    # RR step in both cases and rounds to +1.
    if not rr or divisor == 6:
        return rr
    return min(15, rr + 1)


def _unmapped_operator_slot(write):
    # Operator registers with channel bits 3 select no channel on
    # the hardware; drivers that upload padded voice rows write
    # them anyway.
    return (write.domain == 'uninterpreted' and write.chip_type == 'YM2608'
            and write.chip_instance == 0 and write.port in (0, 1)
            and 0x30 <= write.register <= 0x9f and write.register & 3 == 3)


def _fm_mute_reasons(segment):
    # Inlined from x68k py/opna_force.py fm_mute_reasons: under
    # --force, channels whose sound the OPM cannot reproduce are
    # output-gated rather than dropped.
    state = segment.state
    reasons = []
    if segment.ch == 2:
        if state.channel3_special_enabled:
            reasons.append('ch3_special_frequency')
        if state.csm_enabled:
            reasons.append('csm_automatic_keys')
    if any(op.ssg_eg_enabled for op in state.operators):
        reasons.append('fm_ssg_eg')
    return tuple(reasons)


def project_fm(analysis, *, clock_raw, pitch_policy='clamp', channel_map=None,
               force=False, opm_clock=TARGET_CLOCK):
    """Project OPNA FM segments to OPM write rows (OPNA>OPM law V1).

    Returns (rows, losses). Rows carry no target_command: the
    shared serializer defaults them to the YM2151 command 0x54.
    """
    clock_hz = clock_raw & 0x3fffffff
    if not 0 < clock_hz < 0x40000000:
        raise ValueError('OPNA FM projection requires one positive-clock YM2608')
    if pitch_policy not in ('clamp', 'error'):
        raise ValueError('OPM pitch policy must be clamp or error')
    channel_map = ({ch: ch for ch in range(6)}
                   if channel_map is None else dict(channel_map))
    if (any(type(ch) is not int or not 0 <= ch < 6 for ch in channel_map)
            or any(type(ch) is not int or not 0 <= ch < 8 for ch in channel_map.values())
            or len(set(channel_map.values())) != len(channel_map)):
        raise ValueError('OPNA FM channel mapping must use distinct OPM channels')
    if analysis.csm_observed and not force:
        raise ValueError('OPNA CSM timer-generated key events cannot project to ordinary OPM FM')
    slots = [w for w in analysis.unmodeled_writes if _unmapped_operator_slot(w)]
    unknown = [w for w in analysis.unmodeled_writes
               if w.domain not in NON_FM and not _unmapped_operator_slot(w)]
    if unknown and not force:
        raise ValueError('OPNA FM projection encountered an unknown register effect')
    losses = Counter(w.domain for w in analysis.unmodeled_writes)
    if slots:
        losses['unmapped_operator_slot_writes_ignored'] = len(slots)
    if force and unknown:
        losses['forced_unmodeled_register_writes'] = len(unknown)
    rows, cache, groups = [], {}, {}
    for s in analysis.segments:
        if s.chip_instance or s.clock_raw != clock_raw:
            raise ValueError('OPNA FM projection requires one unflagged YM2608 clock')
        if s.state.channel3_special_enabled and not force:
            raise ValueError('OPNA CH3 special operator frequencies are not supported by OPM projection')
        if s.source_event_id is not None:
            groups.setdefault(s.source_event_id, []).append(s)

    def emit(s, register, data, reason, *, frequency=None, actual=None):
        # Preserve every Key request and repeated operator edge ordering.
        if register != 8 and cache.get(register) == data:
            return
        cache[register] = data
        rows.append(dict(write_id=len(rows), state_origin='projected_opm', source_chip='opna_fm',
            source_event_id=s.source_event_id if s else None,
            source_segment_id=s.segment_id if s else None,
            original_event_id=s.original_event_id if s else None,
            loop_iteration=s.loop_iteration if s else 0,
            source_vgmticks=s.vgmticks if s else 0,
            source_ch=s.ch if s else None, source_register=s.register if s else None,
            source_data=s.data if s else None, target_register=register, target_data=data,
            reason=reason, source_frequency_hz=frequency, target_frequency_hz=actual,
            target_ch=channel_map.get(s.ch) if s and register != 0x18 else None,
            source_row=None, inferred_key=False, synthetic_phase=None))

    emit(None, 0x18, _lfo_rate_table(opm_clock)[0], 'initial LFO frequency')

    # Hardware LFO bridge: same law as the OPN2 route. The source
    # LFO waveform is a fixed triangle and its depths live in the
    # per-channel PMS/AMS steps, while OPM scales those steps by
    # the global PMD/AMD latches, so the bridge selects the latch
    # values per activation: PMD is the ideal value for the
    # maximum PMS in use in the span and AMD the value for the
    # maximum AMS (_LFO_BRIDGE_PMD/_LFO_BRIDGE_AMD; the fixed
    # PMD 86 / AMD 16 pair used until 2026-11-06 rested on a wrong
    # depth series, see the table comment). Sensitivities arrive
    # one write at a time, so the span maximum is not known when
    # the span opens: if a later sensitivity write changes the
    # selected pair mid-span, the pair is re-emitted and the
    # reselection is recorded. A span with no PM sensitivity
    # selects PMD 0 (likewise AMD 0), since the depth tables only
    # cover steps 1..7. Every selection is counted in the losses
    # dict as lfo_bridge_pmd_<value>/lfo_bridge_amd_<value> so the
    # summary shows which values were chosen. The depths are
    # zeroed when the span ends; rate and sensitivities already
    # flow as 0x18/0x38 writes.
    lfo = {'enabled': False, 'on': False, 'sensitivities': {},
           'depths': None}

    def lfo_bridge(s):
        active = lfo['enabled'] and any(
            pms or ams for pms, ams in lfo['sensitivities'].values())
        if active:
            max_pms = max(pms for pms, ams in lfo['sensitivities'].values())
            max_ams = max(ams for pms, ams in lfo['sensitivities'].values())
            depths = (_LFO_BRIDGE_PMD.get(max_pms, 0),
                      _LFO_BRIDGE_AMD.get(max_ams, 0))
            if not lfo['on']:
                emit(s, 0x1b, 0x02, 'OPN fixed triangle as OPM LFO waveform')
                emit(s, 0x19, 0x80 | depths[0],
                     'OPM PMD: ideal for the maximum PMS in this span')
                emit(s, 0x19, depths[1],
                     'OPM AMD: ideal for the maximum AMS in this span')
                losses['lfo_depths_bridged'] += 1
                losses[f'lfo_bridge_pmd_{depths[0]}'] += 1
                losses[f'lfo_bridge_amd_{depths[1]}'] += 1
                lfo['on'] = True
                lfo['depths'] = depths
            elif depths != lfo['depths']:
                emit(s, 0x19, 0x80 | depths[0],
                     'OPM PMD reselected: span sensitivity maximum changed')
                emit(s, 0x19, depths[1],
                     'OPM AMD reselected: span sensitivity maximum changed')
                losses['lfo_bridge_depths_reselected'] += 1
                losses[f'lfo_bridge_pmd_{depths[0]}'] += 1
                losses[f'lfo_bridge_amd_{depths[1]}'] += 1
                lfo['depths'] = depths
        elif lfo['on']:
            emit(s, 0x19, 0x80, 'LFO bridge span ended: PM depth zero')
            emit(s, 0x19, 0, 'LFO bridge span ended: AM depth zero')
            lfo['on'] = False
            lfo['depths'] = None

    def target_channel(s):
        return channel_map.get(s.ch)

    def channel_control(s):
        state = s.state
        pan = (state.left_enabled or 0) << 6 | (state.right_enabled or 0) << 7
        if s.ch >= 3 and state.six_channel_enabled == 0:
            pan = 0  # Output gate, not a synthetic key/envelope restart.
        if force and _fm_mute_reasons(s):
            pan = 0  # Keep ordinary keys/controls underneath the explicit output gate.
        return pan | (state.feedback or 0) << 3 | (state.algorithm or 0)

    def pitch(s):
        state, ch = s.state, target_channel(s)
        if ch is None:
            return
        if state.fnum is None or state.block is None:
            losses['unknown_pitch_target_reset_zero_assumption'] += 1
            fnum = state.fnum_low_raw or 0
            block = 0
        else:
            fnum, block = state.fnum, state.block
        # Hardware pitch: the OPN phase counter is 20 bits and
        # the block scales FNUM by 2**(block-1), so Hz = fnum *
        # clock / (144 * 2**(21-block)) at prescale 6 (YM2608
        # manual formula; ymfm's Nuked-verified phase generator
        # agrees).
        frequency = fnum * clock_hz * (6 / state.fm_prescale_divisor) / (144 * 2 ** (21 - block))
        clock_label = ('3.579545MHz' if opm_clock == TARGET_CLOCK
                       else f'{opm_clock / 1000000:g}MHz')
        if frequency:
            try:
                kc, kf, actual = opm_pitch(frequency, opm_clock)
            except ValueError:
                if pitch_policy == 'error':
                    raise
                kc, kf, actual = opm_pitch(frequency, opm_clock, clamp=True)
                losses['pitch_range_clamped'] += 1
        else:
            kc = kf = 0
            actual = None
            losses['zero_frequency_target_minimum_pitch'] += 1
        emit(s, 0x28 + ch, kc, f'committed native FNUM/BLOCK to {clock_label} KC',
             frequency=frequency, actual=actual)
        emit(s, 0x30 + ch, kf, 'committed native FNUM/BLOCK to KF',
             frequency=frequency, actual=actual)

    for _, segments in sorted(groups.items()):
        s = segments[0]
        state, reg, ch = s.state, s.register, target_channel(s)
        if ch is None and not (s.port == 0 and reg in (0x22, 0x24, 0x25, 0x26, 0x27,
                                                       0x29, 0x2d, 0x2e, 0x2f)):
            continue
        if 0x30 <= reg <= 0x8f:
            bank = (reg >> 2) & 3
            op = state.operators[bank]
            divisor = state.fm_prescale_divisor
            plain = {0x30: lambda: op.dt << 4 | op.mul,
                     0x40: lambda: op.tl,
                     0x50: lambda: op.ks << 6 | op.ar,
                     0x60: lambda: op.am_enabled << 7 | op.d1r,
                     0x70: lambda: op.d2r,
                     0x80: lambda: op.sl << 4 | op.rr}[reg & 0xf0]()
            data = plain
            if divisor != 6:
                data = {0x50: lambda: op.ks << 6 | _eg_rate(op.ar, divisor),
                        0x60: lambda: op.am_enabled << 7 | _eg_rate(op.d1r, divisor),
                        0x70: lambda: _eg_rate(op.d2r, divisor),
                        0x80: lambda: op.sl << 4 | _eg_release(op.rr, divisor)
                        }.get(reg & 0xf0, lambda: plain)()
                if data != plain:
                    losses['eg_rate_prescaler_adjustments'] += 1
            emit(s, 0x40 + ((reg & 0xf0) - 0x30) * 2 + bank * 8 + ch,
                 data, 'operator bank mapping; DT2 reset zero')
        elif 0x90 <= reg <= 0x9f:
            if state.operators[(reg >> 2) & 3].ssg_eg_enabled:
                losses['ssg_eg_not_available_on_opm'] += 1
            if force:
                emit(s, 0x20 + ch, channel_control(s), 'forced FM SSG-EG output gate')
        elif 0xb0 <= reg <= 0xb2 or 0xb4 <= reg <= 0xb6:
            # Target-only reset assumptions for unwritten counterpart controls.
            emit(s, 0x20 + ch, channel_control(s),
                 'RL swap and FB/algorithm')
            if reg >= 0xb4:
                emit(s, 0x38 + ch, state.pms << 4 | state.ams, 'PMS/AMS mapping')
                lfo['sensitivities'][s.ch] = (state.pms or 0, state.ams or 0)
                lfo_bridge(s)
        elif 0xa0 <= reg <= 0xa2:
            pitch(s)
        elif s.port == 0 and reg == 0x28:
            if s.ch >= 3 and state.six_channel_enabled is None:
                losses['unknown_output_enable_target_enabled_assumption'] += 1
            emit(s, 8, state.key_mask << 3 | ch, 'operator key mask')
        elif s.port == 0 and reg == 0x29:
            for item in segments:
                if item.ch >= 3 and target_channel(item) is not None:
                    emit(item, 0x20 + target_channel(item), channel_control(item),
                         'OPNA six-channel output enable as RL gate; held keys preserved')
        elif s.port == 0 and reg in (0x2d, 0x2e, 0x2f):
            for item in segments:
                if item.state.fnum is not None:
                    pitch(item)
        elif s.port == 0 and reg == 0x22:
            emit(s, 0x18, _lfo_rate_table(opm_clock)[state.lfo_rate],
                 'approximate LFO frequency (derived rate table)')
            lfo['enabled'] = bool(state.lfo_enabled)
            lfo_bridge(s)
        elif s.port == 0 and reg in (0x24, 0x25, 0x26, 0x27):
            losses['source_timer_controls_not_projected'] += 1
            if force and reg == 0x27:
                for item in segments:
                    if item.ch == 2 and target_channel(item) is not None:
                        emit(item, 0x20 + target_channel(item), channel_control(item),
                             'forced CH3/CSM output gate; ordinary keys retained')
        # High FNUM writes affect source latches; the six-channel
        # and prescaler groups above re-commit what they change.
    return rows, dict(losses)



_FNUM_GROUPS = ((0xA0, 0xA4), (0xA8, 0xAC))


def _adpcm_blocks(raw, events):
    """Concatenate the source's type-0x81 (YM2608 ADPCM-B) blocks.

    The DRAM image does not depend on the chip clock, so the
    blocks are carried verbatim; convert() places them ahead of
    the command stream as the serializer prefix.
    """
    blocks, skipped = [], Counter()
    for event in events:
        if event.command != 0x67:
            continue
        address = event.address
        block_type = raw[address + 2]
        size = struct.unpack_from('<I', raw, address + 3)[0]
        if block_type == 0x81:
            blocks.append(bytes(raw[address:address + 7 + size]))
        else:
            skipped[f'data_block_type_0x{block_type:02x}_not_carried'] += 1
    return b''.join(blocks), dict(skipped)


def project_passthrough(events, raw, *, clock_raw):
    """Re-emit the source OPNA writes at the cartridge's 8 MHz.

    Returns (rows, fm_rows, nonfm_rows, stats): ``rows`` is every
    emitted row in source stream order; the other two split it by
    register role for the sfg01/layered compositions (SSG, rhythm,
    ADPCM-B and the IRQ flag register stay on the cartridge;
    everything else is the FM section). At a source clock of
    exactly 8 MHz every write passes verbatim. Otherwise the
    clock-derived quantities are rescaled by the source/target
    clock ratio: FM F-numbers and ADPCM-B delta-N scale with the
    clock, SSG periods, the envelope period and the timer counts
    scale against it. Paired registers commit through their
    latch: only the bytes the rescaling actually changes are
    re-emitted, at the tick of the write that changed them.
    """
    clock_hz = clock_raw & 0x3fffffff
    ratio = clock_hz / OPNA_CLOCK
    rescale = clock_hz != OPNA_CLOCK
    rows, fm_rows, nonfm_rows = [], [], []
    stats = Counter()
    latch = {}          # (port, high register) -> last high byte
    emitted_pair = {}   # pair key -> last emitted integer value
    pair_source = {}    # pair key -> last source integer value

    def emit(event, port, register, data, *, reason='register passthrough'):
        row = dict(write_id=len(rows), state_origin='passthrough_opna',
                   source_chip='opna', source_event_id=event.source_event_id,
                   original_event_id=None,
                   loop_iteration=event.loop_iteration,
                   source_vgmticks=event.vgmticks,
                   source_register=register,
                   source_data=raw[event.address + 2],
                   target_command=0x56 if port == 0 else 0x57,
                   target_register=register, target_data=data,
                   reason=reason,
                   sort_rank=1 if register_role(register, port) in NON_FM else 2)
        rows.append(row)
        (nonfm_rows if row['sort_rank'] == 1 else fm_rows).append(row)
        return row

    def pair(event, port, key, value, scale, emit_bytes, *, kind):
        """Emit the changed bytes of a rescaled latch pair."""
        pair_source[key] = value
        scaled = scale(value)
        previous = emitted_pair.get(key)
        if previous is None or scaled != previous:
            for register, data in emit_bytes(scaled, previous):
                emit(event, port, register, data,
                     reason=f'{kind} rescaled to the 8 MHz cartridge clock')
            emitted_pair[key] = scaled
            if scaled != value:
                stats[f'{kind}_corrections'] += 1

    for event in events:
        if event.command not in (0x56, 0x57):
            if event.command in (0xa6, 0xa7):
                raise ValueError('dual-chip YM2608 writes cannot be re-emitted '
                                 'by the single-cartridge variant serializer')
            continue
        port = 0 if event.command == 0x56 else 1
        register = raw[event.address + 1]
        data = raw[event.address + 2]
        if not rescale:
            emit(event, port, register, data)
            continue
        group = next(((lo, hi) for lo, hi in _FNUM_GROUPS
                      if lo <= register <= lo + 2 or hi <= register <= hi + 2),
                     None) if register >= 0xA0 else None
        if group and group[0] <= register <= group[0] + 2 and (
                port == 0 or group[0] == 0xA0):
            lo, hi = group
            high_register = hi + (register - lo)
            high = latch.get((port, high_register), 0)
            block = (high >> 3) & 7
            fnum = ((high & 7) << 8) | data
            scaled = round(fnum * ratio)
            new_block = block
            while scaled > 2047 and new_block < 7:
                new_block += 1
                scaled = (scaled + 1) >> 1
            if fnum and not scaled:
                scaled = 1
            # The F-number commits on the low write against the
            # high latch, so the corrected high byte is emitted
            # first.
            emit(event, port, high_register, (new_block << 3) | (scaled >> 8),
                 reason='F-number high byte rescaled to the 8 MHz cartridge clock')
            emit(event, port, register, scaled & 0xff,
                 reason='F-number low byte rescaled to the 8 MHz cartridge clock')
            if (scaled, new_block) != (fnum, block):
                stats['fnum_corrections'] += 1
        elif group and (port == 0 or group[0] == 0xA0):
            latch[(port, register)] = data
            emit(event, port, register, data)
        elif port == 0 and register <= 0x05:
            # SSG tone period pair (fine, coarse), 12 bits.
            base = register & ~1
            source_pair = pair_source.get(('ssg', base), 0)
            if register == base:
                source_pair = (source_pair & 0xf00) | data
            else:
                source_pair = (source_pair & 0xff) | ((data & 0x0f) << 8)
            pair(event, port, ('ssg', base), source_pair,
                 lambda v: min(0xfff, round(v / ratio)),
                 lambda v, prev: [(base, v & 0xff), (base + 1, (v >> 8) & 0x0f)]
                 if prev is None else
                 ([(base, v & 0xff)] if (v & 0xff) != (prev & 0xff) else [])
                 + ([(base + 1, (v >> 8) & 0x0f)]
                    if (v >> 8) & 0x0f != (prev >> 8) & 0x0f else []),
                 kind='ssg_tone_period')
        elif port == 0 and register == 0x06:
            pair(event, port, ('ssg_noise',), data & 0x1f,
                 lambda v: min(0x1f, round(v / ratio)) if v else 0,
                 lambda v, prev: [(0x06, v)],
                 kind='ssg_noise_period')
        elif port == 0 and register in (0x0b, 0x0c):
            source_pair = pair_source.get(('ssg_env',), 0)
            if register == 0x0b:
                source_pair = (source_pair & 0xff00) | data
            else:
                source_pair = (source_pair & 0xff) | (data << 8)
            pair(event, port, ('ssg_env',), source_pair,
                 lambda v: min(0xffff, round(v / ratio)),
                 lambda v, prev: [(0x0b, v & 0xff), (0x0c, (v >> 8) & 0xff)]
                 if prev is None else
                 ([(0x0b, v & 0xff)] if (v & 0xff) != (prev & 0xff) else [])
                 + ([(0x0c, (v >> 8) & 0xff)]
                    if (v >> 8) & 0xff != (prev >> 8) & 0xff else []),
                 kind='ssg_envelope_period')
        elif port == 0 and register in (0x24, 0x25):
            source_ta = pair_source.get(('timer_a',), 0)
            if register == 0x24:
                source_ta = (data << 2) | (source_ta & 3)
            else:
                source_ta = (source_ta & 0x3fc) | (data & 3)
            pair(event, port, ('timer_a',), source_ta,
                 lambda v: max(0, min(1023, 1024 - round((1024 - v) / ratio))),
                 lambda v, prev: [(0x24, (v >> 2) & 0xff),
                                  (0x25, (data & 0xfc) | (v & 3))]
                 if prev is None or register == 0x25 else
                 [(0x24, (v >> 2) & 0xff)] if (v >> 2) != (prev >> 2) else [],
                 kind='timer_a_period')
        elif port == 0 and register == 0x26:
            pair(event, port, ('timer_b',), data,
                 lambda v: max(0, min(255, 256 - round((256 - v) / ratio))),
                 lambda v, prev: [(0x26, v)],
                 kind='timer_b_period')
        elif port == 1 and register in (0x09, 0x0a):
            source_dn = pair_source.get(('delta_n',), 0)
            if register == 0x09:
                source_dn = (source_dn & 0xff00) | data
            else:
                source_dn = (source_dn & 0xff) | (data << 8)
            pair(event, port, ('delta_n',), source_dn,
                 lambda v: min(0xffff, round(v * ratio)) if v else 0,
                 lambda v, prev: [(0x09, v & 0xff), (0x0a, (v >> 8) & 0xff)]
                 if prev is None else
                 ([(0x09, v & 0xff)] if (v & 0xff) != (prev & 0xff) else [])
                 + ([(0x0a, (v >> 8) & 0xff)]
                    if (v >> 8) & 0xff != (prev >> 8) & 0xff else []),
                 kind='adpcm_b_delta_n')
        else:
            emit(event, port, register, data)
    stats['passthrough_writes'] = len(rows)
    stats['fm_passthrough_writes'] = len(fm_rows)
    stats['nonfm_passthrough_writes'] = len(nonfm_rows)
    return rows, fm_rows, nonfm_rows, dict(stats)


def convert(source, outdir, *, force=False, layered=False, target='makoto',
            dac='opna'):
    """Analyze one OPNA VGM and emit its cartridge variant VGM.

    Same contract as opn2_target_vgm.convert: evidence lands in
    ``outdir`` next to ``<stem>.target.vgm`` (and
    ``<stem>.layer.target.vgm`` when ``layered``), and the
    returned summary dict is JSON-serializable. ``target`` is
    'makoto' (OPNA cartridge alone), 'sfg01' (OPM FM + OPNA
    SSG/rhythm/ADPCM-B) or 'opm4mhz' (the sfg01 composition at
    the 4 MHz OPM clock). ``dac`` accepts only 'opna': an OPNA
    source's sample lane already lives on the cartridge.
    """
    if dac != 'opna':
        raise ValueError("OPNA sources have no Y8950 sample-lane relocation: "
                         "the ADPCM-B lane is native to the makoto cartridge")
    if target not in ('makoto', 'sfg01', 'opm4mhz'):
        raise ValueError(f'Unknown OPNA target cartridge: {target!r}')
    opm_clock = OPM4MHZ_CLOCK if target == 'opm4mhz' else TARGET_CLOCK
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    bundle = analyze_source(source, outdir, stem)
    if 'opna' not in bundle['active_chips']:
        raise ValueError('Input has no OPNA (YM2608) writes')
    extra = [chip for chip in bundle['active_chips'] if chip != 'opna']
    if extra:
        raise ValueError('OPNA variant route covers OPNA-only sources in this '
                         f'stage; this source also uses {extra}')
    analysis = bundle['analyses']['opna']
    if analysis is None:
        raise ValueError(f"OPNA analysis failed: {bundle['errors'].get('opna')}")
    clock_raw = bundle['header']['opna_clock_raw']
    if not clock_raw:
        raise ValueError('Input has no YM2608 clock in its header')
    if clock_raw & 0x40000000:
        raise ValueError('dual-chip YM2608 sources are not supported by the '
                         'single-cartridge variant serializer')
    loop = bundle['loop']
    loop_start = loop_event_id = None
    if loop.get('status') == 'valid':
        loop_start = loop['loop_start_samples']
        loop_event_id = next((e.source_event_id for e in bundle['events']
                              if e.address == loop.get('loop_address')), None)
    raw = read_vgm_bytes(str(source))
    pass_rows, fm_pass_rows, nonfm_rows, pass_stats = project_passthrough(
        bundle['events'], raw, clock_raw=clock_raw)
    block, block_losses = _adpcm_blocks(raw, bundle['events'])
    opm_rows, losses = [], {}
    if target in ('sfg01', 'opm4mhz') or layered:
        opm_rows, losses = project_fm(analysis, clock_raw=clock_raw,
                                      force=force, opm_clock=opm_clock)
    carried = {}
    for domain in sorted(NON_FM):
        if domain in losses:
            carried[domain] = losses.pop(domain)
    for key, value in block_losses.items():
        losses[key] = losses.get(key, 0) + value
    merged = (pass_rows if target == 'makoto' else
              sorted(opm_rows + nonfm_rows,
                     key=lambda r: (r['source_vgmticks'], r.get('sort_rank', 1))))
    # Evidence CSVs are dumped before serialization: write_vgm
    # annotates the row dicts it serializes in place, and the
    # merged stream shares dicts with the per-lane lists.
    if opm_rows:
        writes_csv = outdir / f'{stem}.opna_opm.writes.csv'
        with writes_csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(opm_rows[0]))
            writer.writeheader()
            writer.writerows(opm_rows)
    pass_csv = outdir / f'{stem}.opna_passthrough.writes.csv'
    with pass_csv.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pass_rows[0]) if pass_rows
                                else ['write_id'])
        writer.writeheader()
        writer.writerows(pass_rows)
    target_file = outdir / f'{stem}.target.vgm'
    write_vgm(merged, target_file, end=bundle['source_end_sample'],
              loop_start=loop_start, loop_event_id=loop_event_id,
              prefix=block, opm_clock=opm_clock)
    layer_target, layer_target_writes = None, 0
    if layered:
        layer_merged = sorted(opm_rows + nonfm_rows + fm_pass_rows,
                              key=lambda r: (r['source_vgmticks'],
                                             r.get('sort_rank', 1)))
        layer_target = outdir / f'{stem}.layer.target.vgm'
        write_vgm(layer_merged, layer_target, end=bundle['source_end_sample'],
                  loop_start=loop_start, loop_event_id=loop_event_id,
                  prefix=block, opm_clock=opm_clock)
        layer_target_writes = len(layer_merged)
    summary = dict(source=str(source), source_sha256=bundle['source_sha256'],
                   active_chips=list(bundle['active_chips']),
                   opna_clock_hz=clock_raw & 0x3fffffff,
                   target_cartridge=target,
                   target_clock_hz=(OPNA_CLOCK if target == 'makoto'
                                    else opm_clock),
                   target_vgm=target_file.name,
                   target_writes=len(merged),
                   opm_writes=len(opm_rows) if target in ('sfg01', 'opm4mhz') else 0,
                   opna_fm_writes=len(fm_pass_rows) if target == 'makoto' else 0,
                   passthrough=pass_stats,
                   adpcm_block_bytes=len(block),
                   carried_lanes=carried,
                   layered=layered,
                   layer_target_vgm=(layer_target.name if layer_target else None),
                   layer_target_writes=layer_target_writes,
                   losses=losses,
                   loop=dict(status=loop.get('status'), start_sample=loop_start))
    (outdir / f'{stem}.opna_target.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary
