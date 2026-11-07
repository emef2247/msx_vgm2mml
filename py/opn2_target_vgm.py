"""Native YM2612 (OPN2) FM Segments -> projected YM2151 (OPM) target VGM.

The target is the dual-cartridge MSX playback route: the FM part of a
Mega Drive VGM plays on the pseudo-OPM cartridge (YM2151 at
3.579545 MHz), the two SN76489 (DCSG) chips play on the MSX PSG
(AY8910 family) and the OPNA Sound Cartridge's SSG section, and
the DAC plays on the OPNA ADPCM-B channel after a YM delta
re-encode (S4).

The FM projection body is ported from x68k_vgm2mml py/opn2_opm.py (the
register-layout mapping derived from the project's ymfm-based audit)
with three target adaptations:

- TARGET_CLOCK is the MSX OPM clock 3.579545 MHz, not the X68000's
  4 MHz, so KC/KF are committed through the same pitch helper at the
  cartridge clock.
- The channel map is the identity 0..5 -> 0..5: no OPM channel is
  reserved on this target, because the PCM lanes live on the OPNA
  chip rather than on OPM channels.
- The DAC is bridged to the OPNA ADPCM-B channel (S4), not to a
  PCM stream on the OPM side: samples are YM delta-encoded into
  the cartridge DRAM image and triggered per run.

Losses are counted, never silent. CSM, CH3 special mode and unknown
register effects refuse the projection unless --force is given.
"""
import csv
import hashlib
import json
import math
import struct
from array import array
from collections import Counter
from fractions import Fraction
from pathlib import Path

from psg_scc_opm import opm_pitch
from native_imports.opn2 import Opn2UnmodeledWrite  # noqa: F401  (re-exported type)
from native_imports.source import analyze_source
from native_imports.vgm_io import read_vgm_bytes


TARGET_CLOCK = 3579545
OPM4MHZ_CLOCK = 4000000

# S3 target devices for the DCSG lanes. The MSX PSG is stamped with
# the repo family's AY clock (3579545 / 2, rounded) and the YM2149
# type byte musical_vgm uses. The YM2608 header clock is the
# cartridge's fixed 8 MHz; its SSG section is clocked at master / 2
# (the PC-98 OPNA convention), so SSG periods are computed against
# an effective 4 MHz.
AY_CLOCK = 1789773
OPNA_CLOCK = 8000000
SSG_CLOCK = 4000000

# SN76489 attenuation steps are exactly 2 dB; AY-family volume steps
# are ~3.19 dB (the uniform x1.444 DAC ladder). This table maps each
# source attenuation to the AY volume nearest in dB (worst error
# ~1.6 dB); attenuation 15 is the SN mute and maps to volume 0.
_DCSG_VOLUME_BASE = (15, 14, 14, 13, 12, 12, 11, 11, 10, 9, 9, 8, 7, 7, 6, 0)

# A lane gain (convert's dcsg_gain, CLI --dcsg-gain) can shift the
# DCSG lanes' level against the FM lanes: the shift is applied to
# the source level before the nearest-step pick, so quiet source
# levels fall off the bottom of the AY ladder to mute instead of
# being re-normalized upward. The default is 1.0 (no shift, the
# dB-faithful table below): the PSG volume is adjustable at the
# cartridge on the MSX route, so no fixed cut is baked in (user
# decision, 2026-11-07). A gain stays available for targets whose
# FM/PSG ratio is fixed in hardware, such as Misato (OPN3-L);
# x68k_vgm2mml's listening-calibrated PCM value is 0.036.
_AY_STEP_DB = 3.19


def _dcsg_volume_for(attenuation, gain):
    if attenuation >= 15:
        return 0
    level_db = -2.0 * attenuation + 20.0 * math.log10(gain)
    volume = 15 - round(-level_db / _AY_STEP_DB)
    return volume if volume > 0 else 0


def _dcsg_volume_table(gain):
    if gain == 1.0:
        return _DCSG_VOLUME_BASE
    return tuple(_dcsg_volume_for(a, gain) for a in range(16))


_DCSG_VOLUME = _DCSG_VOLUME_BASE

_DCSG_DEVICES = {0: ('ay', 0xA0, AY_CLOCK), 1: ('ssg', 0x56, SSG_CLOCK)}

# LFO rate mapping, derived from the chip models in ymfm (and
# corroborated by Nuked-OPN2's die-derived divider counts): the OPN
# LFO advances its 7-bit value when the counter's low byte reaches
# {109, 78, 72, 68, 63, 45, 9, 6}[rate] at the FM sample clock
# (OPN2 7,670,454/144 = 53.3 kHz), while the OPM rate byte is a 4.4
# float step giving Hz = (clock / 64) * ((0x10 | (b & 0xf)) <<
# (b >> 4)) / 2**30. Each entry is the OPM byte nearest in Hz to
# the source rate (3.85/5.40/5.86/6.21/6.71/9.46/51.9/83.0 Hz at
# the OPN2 clock). Source rate 7 exceeds the OPM maximum and
# saturates at 0xff. Derivation script: opna_opm_voice study,
# lfo_rate_map.py.
#
# The OPM byte for a given Hz depends on the OPM clock actually
# stamped, so there are two tables. The 4 MHz table below served
# every target until 2026-11-06, but the sfg01 family stamps the
# OPM at 3,579,545 Hz, which made every bridged rate x0.8949 of
# intended; the 3,579,545 Hz table corrects that (opm4mhz keeps
# the 4 MHz table). Rederivation: opna_opm_voice study,
# LFO_BRIDGE_CORRECTION.md and lfo_bridge_rates.csv (2026-11-06).
_LFO_RATE_TO_OPM_4MHZ = (0xc0, 0xc7, 0xc9, 0xca, 0xcc, 0xd4, 0xfb, 0xff)
_LFO_RATE_TO_OPM = (0xc2, 0xc9, 0xcb, 0xcd, 0xcf, 0xd6, 0xfe, 0xff)


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


def _unmapped_operator_slot(write):
    # Operator registers with channel bits 3 select no channel on the
    # hardware; drivers that upload padded voice rows write them anyway.
    return (write.domain == 'uninterpreted' and write.chip_instance == 0
            and write.port in (0, 1)
            and 0x30 <= write.register <= 0x9f and write.register & 3 == 3)


def _unassigned_register(write):
    # The YM2612 register map has holes the analysis leaves
    # uninterpreted: nothing is implemented at 0x00-0x20 (the chip has
    # no SSG section), in the gaps beside the common registers (0x23,
    # 0x29, 0x2c-0x2f), or past the FM block end at 0xb6. Writes there
    # select no functional register and are inert on the hardware;
    # drivers emit them as workspace or padded sweeps anyway. The
    # 0x21 test register is deliberately not exempted: it can affect
    # the chip.
    if not (write.domain == 'uninterpreted' and write.chip_instance == 0
            and write.port in (0, 1)):
        return False
    reg = write.register
    return (reg <= 0x20 or reg == 0x23 or reg == 0x29
            or 0x2c <= reg <= 0x2f or reg >= 0xb7)


def project(analysis, *, clock_raw, pitch_policy='clamp', channel_map=None, force=False,
            dac_external=False, opm_clock=TARGET_CLOCK):
    """Return target write rows plus explicit losses, retaining source identities."""
    clock_hz = clock_raw & 0x3fffffff
    if not 0 < clock_hz < 0x40000000:
        raise ValueError('OPN2 FM projection requires one positive-clock YM2612')
    if pitch_policy not in ('clamp', 'error'):
        raise ValueError('OPM pitch policy must be clamp or error')
    channel_map = ({ch: ch for ch in range(6)}
                   if channel_map is None else dict(channel_map))
    if (any(type(ch) is not int or not 0 <= ch < 6 for ch in channel_map)
            or any(type(ch) is not int or not 0 <= ch < 8 for ch in channel_map.values())
            or len(set(channel_map.values())) != len(channel_map)):
        raise ValueError('OPN2 FM channel mapping must use distinct OPM channels')
    if analysis.csm_observed and not force:
        raise ValueError('OPN2 CSM timer-generated key events cannot project to ordinary OPM FM')
    # DAC data written while the DAC is disabled makes no sound; only
    # writes inside an enabled span are sample playback.
    enabled_spans = [(s.vgmticks, s.vgmticks_end) for s in analysis.segments
                     if s.ch == 5 and s.state.dac_enabled == 1]
    dac_live = sum(1 for w in analysis.unmodeled_writes if w.domain == 'dac_data'
                   and any(start <= w.vgmticks < end for start, end in enabled_spans))
    dac_inert = sum(1 for w in analysis.unmodeled_writes if w.domain == 'dac_data') - dac_live
    if dac_live and not force and not dac_external:
        raise ValueError('YM2612 DAC sample playback requires the DAC stage '
                         'or --force to omit the DAC channel')
    slots = [w for w in analysis.unmodeled_writes if _unmapped_operator_slot(w)]
    # Key writes whose channel field names no channel (3 or 7) decode
    # to nothing on the hardware; drivers emit them from table sweeps.
    invalid_keys = [w for w in analysis.unmodeled_writes
                    if w.domain == 'invalid_key_channel']
    # Writes past the end of the register map select no register and
    # are inert on the hardware, like the slot and key cases above.
    dead = [w for w in analysis.unmodeled_writes if _unassigned_register(w)]
    unknown = [w for w in analysis.unmodeled_writes
               if w.domain != 'dac_data' and not _unmapped_operator_slot(w)
               and w.domain != 'invalid_key_channel'
               and not _unassigned_register(w)]
    if unknown and not force:
        raise ValueError('OPN2 FM projection encountered an unknown register effect')
    losses = Counter()
    if dac_inert:
        losses['dac_data_writes_while_disabled_ignored'] = dac_inert
    if slots:
        losses['unmapped_operator_slot_writes_ignored'] = len(slots)
    if invalid_keys:
        losses['invalid_key_channel_writes_ignored'] = len(invalid_keys)
    if dead:
        losses['unassigned_register_writes_ignored'] = len(dead)
    if dac_external and dac_live:
        losses['dac_data_writes_projected_to_pcm'] = dac_live
    elif force and dac_live:
        losses['dac_data_writes_omitted'] = dac_live
    if force and unknown:
        losses['forced_unmodeled_register_writes'] = len(unknown)
    rows, cache, groups = [], {}, {}
    for s in analysis.segments:
        if s.chip_instance or s.clock_raw != clock_raw:
            raise ValueError('OPN2 FM projection requires one unflagged YM2612 clock')
        if s.state.channel3_special_enabled and not force:
            raise ValueError('OPN2 CH3 special operator frequencies are not supported by OPM projection')
        if s.state.channel3_special_enabled:
            losses['ch3_special_frequencies_not_projected'] += 1
        if s.ch == 5 and s.state.dac_enabled == 1 and s.state.key_mask:
            losses['dac_enabled_ch6_fm_output_gated'] += 1
        if s.source_event_id is not None:
            groups.setdefault(s.source_event_id, []).append(s)

    def emit(s, register, data, reason, *, frequency=None, actual=None):
        # Preserve every Key request and repeated operator edge ordering.
        if register != 8 and cache.get(register) == data:
            return
        cache[register] = data
        rows.append(dict(write_id=len(rows), state_origin='projected_opm', source_chip='opn2_fm',
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

    # Hardware LFO bridge: same law as the OPNA route. The source
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
        if s.ch == 5 and state.dac_enabled == 1:
            pan = 0  # The DAC owns channel 6 output while enabled.
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
        # Hardware pitch: the OPN phase counter is 20 bits and the block
        # scales FNUM by 2**(block-1), so Hz = fnum * clock / (144 *
        # 2**(21-block)) at prescale 6 (YM3438 manual formula; ymfm's
        # Nuked-verified phase generator agrees). The 2**(20-block)
        # form used here before played every note one octave high.
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
        emit(s, 0x28 + ch, kc, f'committed native FNUM/BLOCK to {clock_label} KC', frequency=frequency, actual=actual)
        emit(s, 0x30 + ch, kf, 'committed native FNUM/BLOCK to KF', frequency=frequency, actual=actual)

    for _, segments in sorted(groups.items()):
        s = segments[0]
        state, reg, ch = s.state, s.register, target_channel(s)
        if ch is None and not (s.port == 0 and reg in (0x22, 0x24, 0x25, 0x26, 0x27, 0x2b)):
            continue
        if 0x30 <= reg <= 0x8f:
            bank = (reg >> 2) & 3
            op = state.operators[bank]
            data = {0x30: lambda: op.dt << 4 | op.mul,
                    0x40: lambda: op.tl,
                    0x50: lambda: op.ks << 6 | op.ar,
                    0x60: lambda: op.am_enabled << 7 | op.d1r,
                    0x70: lambda: op.d2r, 0x80: lambda: op.sl << 4 | op.rr}[reg & 0xf0]()
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
            emit(s, 8, state.key_mask << 3 | ch, 'operator key mask')
        elif s.port == 0 and reg == 0x2b:
            for item in segments:
                if target_channel(item) is not None:
                    emit(item, 0x20 + target_channel(item), channel_control(item),
                         'DAC enable as channel-6 output gate; FM state retained')
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
        # High FNUM writes affect source latches; forced CH3 modes stay output-gated.
    return rows, dict(losses)


def project_dcsg(analysis, *, loop_start=None, loop_event_id=None,
                 dcsg_gain=1.0):
    """Project native DCSG Segments to AY (instance 0) + SSG (instance 1) rows.

    Split, designed for this pair: each DCSG chip keeps its three
    tones on one target device (chip 0 -> MSX PSG, chip 1 -> OPNA
    SSG) and its noise takes that device's noise generator, whose
    period is independent of the other device's. An AY-family device
    has only three channels, so the noise shares channel C with
    tone 2: the mixer enables noise on C only while the noise
    segment is audible, and C's volume belongs to the noise during
    those spans and to tone 2 otherwise. Overlap spans (tone 2 and
    noise both audible, output AND-gated on the hardware) are
    measured into the losses.

    Emission is per lane at its own Segment starts, with no
    cross-segment suppression, plus a full-state restore group at
    the loop point when a valid loop exists: a suppressed write is
    not safe across a header loop, because on re-entry the register
    holds the end-of-file state, not the first-pass state.
    """
    from bisect import bisect_right
    losses, rows, stats = Counter(), [], {}

    def emit(device, command, seg, register, data, reason, *, ch=None,
             frequency=None, actual=None, sample=None, event_id='seg', rank=2):
        rows.append(dict(
            write_id=len(rows), state_origin='projected_dcsg', source_chip='dcsg',
            target_device=device, target_command=command,
            source_event_id=seg.source_event_id if seg and event_id == 'seg' else event_id,
            source_segment_id=seg.segment_id if seg else None,
            original_event_id=None, loop_iteration=0,
            source_vgmticks=seg.start_sample if seg and sample is None else sample,
            source_ch=seg.ch if seg else None,
            source_period=seg.period if seg else None,
            source_attenuation=seg.attenuation if seg else None,
            source_noise_control=seg.noise_control if seg else None,
            target_register=register, target_data=data, reason=reason,
            source_frequency_hz=frequency, target_frequency_hz=actual,
            target_ch=ch, source_row=None, inferred_key=False, synthetic_phase=None,
            sort_rank=rank))

    def tone_period(device, clock, seg, *, quiet=False):
        # Diagnostics count only audible segments: an inaudible
        # segment's unknown or clamped period changes nothing heard,
        # and the noise lane is sliced by tone-2 activity even in
        # songs that never use noise at all.
        if seg.frequency_hz is None:
            if not quiet and seg.audible:
                losses[f'dcsg_tone_period_unknown_{device}'] += 1
            return None
        tp = round(clock / (16 * seg.frequency_hz))
        if not 1 <= tp <= 4095:
            if not quiet and seg.audible:
                losses[f'dcsg_tone_period_clamped_{device}'] += 1
            tp = min(4095, max(1, tp))
        return tp, clock / (16 * tp)

    def noise_period(device, clock, seg, *, quiet=False):
        """Return (NP, target shift Hz, note) or None when inaudible."""
        if seg.noise_shift_hz is None:
            if not seg.audible:
                return None
            if seg.noise_control is None:
                # The source never establishes the noise control, but
                # the lane sounds: every player zero-initialises the
                # chip, so the observed behaviour is the power-on
                # control (rate 0, uncoupled). Emit that rate as an
                # explicit assumption rather than leaving the target
                # period at its own power-on value, a much faster buzz.
                if not quiet:
                    losses[f'dcsg_noise_rate_power_on_default_assumed_{device}'] += 1
                assumed = analysis.config.clock_hz / (64 * analysis.config.clock_divider)
                np_ = min(31, max(1, round(clock / (16 * assumed))))
                return np_, clock / (16 * np_), 'power-on control assumed'
            # The control couples the LFSR to tone 2, whose period is
            # 0 or not established (Alien Soldier parks tone 2 at
            # period 0 and rides only the noise attenuation): the
            # shift rate is undefined in the source analysis, and no
            # AY-family period comes close to the coupled rate
            # anyway. The slowest target rate keeps the attenuation
            # articulation, which is what the lane audibly does.
            if not quiet:
                losses[f'dcsg_noise_coupled_rate_undefined_{device}'] += 1
            return 31, clock / (16 * 31), 'coupled rate undefined; slowest assumed'
        np_ = round(clock / (16 * seg.noise_shift_hz))
        if not 1 <= np_ <= 31:
            if not quiet and seg.audible:
                losses[f'dcsg_noise_period_clamped_{device}'] += 1
            np_ = min(31, max(1, np_))
        return np_, clock / (16 * np_), ''

    volume_table = _dcsg_volume_table(dcsg_gain)

    def volume_of(seg):
        return volume_table[seg.attenuation] if seg.attenuation is not None else 0

    for issue in analysis.issues:
        losses[f"dcsg_issue_{issue['code']}"] += 1
    if analysis.config.t6w28:
        losses['dcsg_t6w28_cross_chip_routing_not_projected'] += 1
    if analysis.config.stereo:
        for seg in analysis.segments:
            if seg.audible and seg.stereo_left != seg.stereo_right:
                losses['dcsg_stereo_position_not_projected'] += 1

    by_instance = {}
    for seg in analysis.segments:
        by_instance.setdefault(seg.chip_instance, {}).setdefault(seg.ch, []).append(seg)
    for instance, lanes in sorted(by_instance.items()):
        if instance not in _DCSG_DEVICES:
            losses['dcsg_undeclared_instance_not_projected'] += sum(
                len(v) for v in lanes.values())
            continue
        device, command, clock = _DCSG_DEVICES[instance]
        device_stats = dict(tone_segments=0, noise_segments=0,
                            noise_tone_overlap_samples=0, writes=0)
        stats[device] = device_stats
        before = len(rows)
        lane_starts = {ch: [s.start_sample for s in lanes.get(ch, [])]
                       for ch in (0, 1, 2, 3)}

        def covering(ch, sample):
            lane = lanes.get(ch, [])
            index = bisect_right(lane_starts[ch], sample) - 1 if lane else -1
            return lane[index] if index >= 0 else None

        # Tone lanes: period on every segment start; volumes for
        # channels A/B here, channel C in the shared walk below.
        for ch in (0, 1, 2):
            for seg in lanes.get(ch, ()):
                device_stats['tone_segments'] += 1
                if seg.attenuation is None:
                    losses[f'dcsg_tone_attenuation_unknown_{device}'] += 1
                result = tone_period(device, clock, seg)
                if result is not None:
                    tp, actual = result
                    emit(device, command, seg, ch * 2, tp & 0xff, 'dcsg tone period (fine)',
                         ch=ch, frequency=seg.frequency_hz, actual=actual)
                    emit(device, command, seg, ch * 2 + 1, tp >> 8, 'dcsg tone period (coarse)',
                         ch=ch, frequency=seg.frequency_hz, actual=actual)
                if ch != 2:
                    emit(device, command, seg, 8 + ch, volume_of(seg), 'dcsg tone volume',
                         ch=ch, frequency=seg.frequency_hz)
        # Shared walk over tone-2 and noise boundaries: noise period,
        # mixer, and the arbitrated channel-C volume.
        tone2, noise = lanes.get(2, []), lanes.get(3, [])
        boundaries = sorted({0} | {s.start_sample for s in tone2}
                            | {s.start_sample for s in noise})
        for index, sample in enumerate(boundaries):
            tseg = covering(2, sample)
            nseg = covering(3, sample)
            lead = None
            for candidate in (tseg, nseg):
                if candidate is not None and candidate.start_sample == sample:
                    lead = candidate
                    break
            lead = lead or nseg or tseg
            noise_audible = bool(nseg and nseg.audible)
            if noise_audible and tseg is not None and tseg.audible:
                following = (boundaries[index + 1] if index + 1 < len(boundaries)
                             else analysis.end_sample)
                device_stats['noise_tone_overlap_samples'] += following - sample
            if nseg is not None and nseg.start_sample == sample:
                device_stats['noise_segments'] += 1
                result = noise_period(device, clock, nseg)
                if result is not None:
                    np_, actual, note = result
                    emit(device, command, nseg, 6, np_,
                         'dcsg noise period' + (f' ({note})' if note else ''),
                         frequency=nseg.noise_shift_hz, actual=actual, sample=sample)
            mixer = 0x18 if noise_audible else 0x38
            emit(device, command, lead, 7, mixer,
                 'dcsg mixer; noise on channel C only while audible',
                 sample=sample)
            emit(device, command, lead, 10,
                 volume_of(nseg) if noise_audible else volume_of(tseg) if tseg else 0,
                 'dcsg channel C volume (noise while audible, else tone 2)',
                 ch=2, sample=sample)
        # Loop-entry restore: re-emit the full desired state at the
        # loop point so a second traversal starts from the same
        # register state as the first.
        if loop_start is not None:
            tseg = covering(2, loop_start)
            nseg = covering(3, loop_start)
            noise_audible = bool(nseg and nseg.audible)
            for ch in (0, 1, 2):
                lane = lanes.get(ch, [])
                seg = covering(ch, loop_start)
                if seg is None:
                    continue
                result = tone_period(device, clock, seg, quiet=True)
                if result is not None:
                    tp, actual = result
                    for register, data in ((ch * 2, tp & 0xff), (ch * 2 + 1, tp >> 8)):
                        emit(device, command, seg, register, data,
                             'dcsg loop entry state restore', ch=ch,
                             frequency=seg.frequency_hz, actual=actual,
                             sample=loop_start, event_id=loop_event_id, rank=0)
                if ch != 2:
                    emit(device, command, seg, 8 + ch, volume_of(seg),
                         'dcsg loop entry state restore', ch=ch,
                         sample=loop_start, event_id=loop_event_id, rank=0)
            if nseg is not None:
                result = noise_period(device, clock, nseg, quiet=True)
                if result is not None:
                    np_, actual, _note = result
                    emit(device, command, nseg, 6, np_,
                         'dcsg loop entry state restore',
                         frequency=nseg.noise_shift_hz, actual=actual,
                         sample=loop_start, event_id=loop_event_id, rank=0)
            emit(device, command, nseg or tseg, 7, 0x18 if noise_audible else 0x38,
                 'dcsg loop entry state restore',
                 sample=loop_start, event_id=loop_event_id, rank=0)
            emit(device, command, nseg or tseg, 10,
                 volume_of(nseg) if noise_audible else volume_of(tseg) if tseg else 0,
                 'dcsg loop entry state restore', ch=2,
                 sample=loop_start, event_id=loop_event_id, rank=0)
        device_stats['writes'] = len(rows) - before
    return rows, dict(losses), stats


# --- S4: DAC -> OPNA ADPCM-B --------------------------------------
# The OPNA Sound Cartridge carries up to 256 KB of DRAM for the
# YM2608 ADPCM-B channel. Encoded samples are preloaded with one
# VGM data block (type 0x81: total size, destination, content -
# the layout real OPNA rips use, 221 blocks across the Grounseed
# pack) and each run is triggered with port-1 writes (command
# 0x57): control 2 = 0xC2 (L+R output, x8 DRAM - the value real
# rips write), start/end addresses count in 32-byte units, the
# playback rate is clock * delta-N / (144 * 65536) at the power-on
# prescaler, and the level is fixed at 0xFF because the source
# waveform itself carries the dynamics (a listening calibration
# point, like the mucom88 NES DPCM level before it).
ADPCM_B_DRAM_BUDGET = 262144
ADPCM_B_LEVEL = 0xFF
# The --dac y8950 variant plays the same encoded samples through
# the MSX-AUDIO (Y8950) Delta-T unit instead: the same codec, but
# the playback rate is clock * delta-N / (72 * 65536) at the
# 3.579545 MHz cartridge clock, start/stop addresses count in
# 4-byte units in RAM 256K mode (R08 mode bits 0), triggers are
# Y8950 writes (command 0x5C, registers 0x07-0x12), the preload
# block is type 0x88, and the sample store is the MSX-AUDIO
# cartridge's sample RAM; the budget assumes the 256 KB
# expansion (the chip's RAM 256K space), per the user's call
# (2026-11-05), so no sample is dropped for space alone.
Y8950_CLOCK = 3579545
Y8950_RAM_BUDGET = 262144
_DAC_RUN_GAP_TICKS = 441  # the x68k DAC bridge's run split
_ADPCM_B_STEP_MULTIPLIERS = (57, 57, 57, 57, 77, 102, 128, 153)


def _encode_adpcm_b(wave):
    """Greedy YM delta-ADPCM encode of signed 16-bit samples.

    The predictor/step state machine is the decoder's (step starts
    at 127 and clamps to [127, 24576]); each nibble minimises the
    decoded error against the desired sample. High nibble first.
    """
    predictor, step = 0, 127
    nibbles = []
    for desired in wave:
        best_nibble, best_value, best_error = 0, predictor, None
        for nibble in range(16):
            delta = ((2 * (nibble & 7) + 1) * step) // 8
            value = predictor - delta if nibble & 8 else predictor + delta
            value = max(-32768, min(32767, value))
            error = abs(value - desired)
            if best_error is None or error < best_error:
                best_nibble, best_value, best_error = nibble, value, error
        nibbles.append(best_nibble)
        predictor = best_value
        step = max(127, min(24576,
                            step * _ADPCM_B_STEP_MULTIPLIERS[best_nibble & 7] // 64))
    encoded = bytearray()
    for index in range(0, len(nibbles), 2):
        low = nibbles[index + 1] if index + 1 < len(nibbles) else 0
        encoded.append(nibbles[index] << 4 | low)
    return bytes(encoded)


_STREAM_ONE = 1 << 32


def _decode_dac_stream(raw, events):
    """Expand DAC stream commands into byte supplies.

    Ported from x68k_vgm2mml py/opn2_pcm.py (_decode_stream_bytes),
    with supplies carrying their bank offset and step so the
    caller can split runs where the driver seeked - the driver's
    own phrase marks. Returns (supplies, issues, stats); supplies
    are (vgmticks, byte, source_event_id, bank_offset, step) from
    autonomous stream starts (0x93/0x95, libvgm phase model) and
    manual plays (0x80-0x8F positioned by 0xE0 seeks). Rips that
    drive seeks/plays with no stream setup bind to an implicit
    context over the concatenated type-0 bank.
    """
    bank = bytearray()
    blocks = []
    streams = {}
    quick = None
    implicit = None
    supplies = []
    issues = Counter()
    stats = dict(stream_setup_commands=0, stream_starts=0,
                 stream_fast_starts=0, seek_commands=0, play_commands=0,
                 autonomous_bytes=0, manual_bytes=0, data_blocks=0,
                 data_block_bytes=0, implicit_stream=False)
    cursor = 0

    def issue(code):
        issues[code] += 1

    def bind_quick():
        nonlocal quick, implicit
        if quick is not None:
            return quick
        candidates = [s for s in streams.values() if s.get('valid')]
        if len(candidates) == 1:
            quick = candidates[0]
            return quick
        if implicit is None:
            implicit = dict(offset=None, index=0, step=1)
            stats['implicit_stream'] = True
            issue('opn2_dac_implicit_stream_context')
        quick = implicit
        return quick

    def advance(end):
        nonlocal cursor
        ready = []
        for order, (sid, stream) in enumerate(streams.items()):
            if not stream.get('running'):
                continue
            frequency = stream['frequency']
            increment = (frequency * _STREAM_ONE + 22050) // 44100
            local = cursor
            while local < end and stream['running']:
                steps = max(1, (_STREAM_ONE - stream['phase']
                                + increment - 1) // increment)
                if steps > end - local:
                    stream['phase'] += (end - local) * increment
                    break
                stream['phase'] += steps * increment - _STREAM_ONE
                tick = local + steps - 1
                bank_offset = stream['offset'] + stream['index'] * stream['step']
                if not 0 <= bank_offset < len(bank):
                    issue('opn2_dac_stream_out_of_bank')
                    stream['running'] = False
                    break
                ready.append((tick, order, stream['start_event'],
                              bank[bank_offset], bank_offset, stream['step']))
                stream['index'] += 1
                if stream['index'] == stream['count']:
                    stream['running'] = False
                local += steps
        ready.sort(key=lambda item: item[:2])
        supplies.extend((tick, byte, event_id, offset, step)
                        for tick, _, event_id, byte, offset, step in ready)
        stats['autonomous_bytes'] += len(ready)
        cursor = end

    for event_id, event in enumerate(events):
        advance(event.vgmticks)
        cmd, pos, tick = event.command, event.address, event.vgmticks
        if cmd == 0x67:
            if event.loop_iteration:
                continue
            kind = raw[pos + 2]
            size = int.from_bytes(raw[pos + 3:pos + 7], 'little') & 0x7fffffff
            if kind == 0:
                blocks.append((len(bank), size))
                bank.extend(raw[pos + 7:pos + 7 + size])
                stats['data_blocks'] += 1
                stats['data_block_bytes'] += size
            continue
        if cmd in (0x52, 0x53, 0xa2, 0xa3):
            continue
        if 0x90 <= cmd <= 0x95:
            sid = raw[pos + 1]
            if sid == 255:
                if cmd == 0x94:
                    for stream in streams.values():
                        stream['running'] = False
                continue
            if cmd == 0x90:
                target, port, reg = raw[pos + 2:pos + 5]
                stream = streams.setdefault(sid, dict(
                    bank=None, step=None, base=None, frequency=None,
                    offset=None, count=None, phase=0, index=0, running=False))
                stream.update(valid=(target & 0x7f) == 2 and reg == 0x2a,
                              instance=bool(target & 0x80))
                stats['stream_setup_commands'] += 1
                if not stream['valid']:
                    issue('opn2_dac_stream_unsupported_target')
                continue
            stream = streams.get(sid)
            if stream is None:
                issue('opn2_dac_stream_configuration_incomplete')
                continue
            if cmd == 0x91:
                bank_id, step, base = raw[pos + 2:pos + 5]
                stream.update(bank=bank_id, step=step or 1, base=base)
                if bank_id != 0:
                    issue('opn2_dac_stream_unsupported_bank')
                    stream['usable'] = False
                else:
                    stream['usable'] = True
            elif cmd == 0x92:
                stream['frequency'] = int.from_bytes(raw[pos + 2:pos + 6], 'little')
            elif cmd == 0x94:
                stream['running'] = False
            elif cmd in (0x93, 0x95):
                stream['running'] = False
                if not stream.get('valid') or not stream.get('usable', True):
                    continue
                if cmd == 0x95:
                    block_index = int.from_bytes(raw[pos + 2:pos + 4], 'little')
                    flags = raw[pos + 4]
                    stats['stream_fast_starts'] += 1
                    if flags:
                        issue('opn2_dac_stream_flags_unsupported')
                    if block_index >= len(blocks):
                        issue('opn2_dac_stream_out_of_bank')
                        continue
                    offset, _length = blocks[block_index]
                    stream.update(offset=offset + (stream['base'] or 0), index=0)
                    quick = stream
                else:
                    stats['stream_starts'] += 1
                    if any(stream[key] is None for key in ('bank', 'frequency')):
                        issue('opn2_dac_stream_configuration_incomplete')
                        continue
                    if not stream['frequency'] or stream['frequency'] > 44100:
                        issue('opn2_dac_stream_frequency_unsupported')
                        continue
                    offset = int.from_bytes(raw[pos + 2:pos + 6], 'little')
                    mode = raw[pos + 6]
                    length = int.from_bytes(raw[pos + 7:pos + 11], 'little')
                    if offset == 0xffffffff:
                        if stream['offset'] is None:
                            issue('opn2_dac_stream_configuration_incomplete')
                            continue
                        offset = stream['offset']
                    step = stream['step'] or 1
                    if mode == 1:
                        count = length
                    elif mode == 3:
                        count = max(0, (len(bank) - offset
                                        - (stream['base'] or 0)) // step)
                    else:
                        issue('opn2_dac_stream_length_mode_unsupported')
                        continue
                    start = offset + (stream['base'] or 0)
                    if count <= 0 or not 0 <= start < len(bank):
                        issue('opn2_dac_stream_out_of_bank')
                        continue
                    increment = (stream['frequency'] * _STREAM_ONE + 22050) // 44100
                    stream.update(offset=start, count=count, index=0, running=True,
                                  phase=_STREAM_ONE - increment,
                                  start_event=event_id, step=step)
            continue
        if cmd == 0xe0:
            stats['seek_commands'] += 1
            context = bind_quick()
            context['offset'] = int.from_bytes(raw[pos + 1:pos + 5], 'little')
            context['index'] = 0
            continue
        if 0x80 <= cmd <= 0x8f:
            stats['play_commands'] += 1
            context = bind_quick()
            if context.get('offset') is None:
                issue('opn2_dac_play_without_stream')
                continue
            quick = context
            bank_offset = quick['offset'] + quick['index'] * (quick['step'] or 1)
            if not 0 <= bank_offset < len(bank):
                issue('opn2_dac_stream_out_of_bank')
                continue
            supplies.append((tick, bank[bank_offset], event_id,
                             bank_offset, quick['step'] or 1))
            stats['manual_bytes'] += 1
            quick['index'] += 1
            continue
    advance(1 << 62)
    return supplies, issues, stats


def project_dac(analysis, *, source_end, raw, events, dac_target='opna'):
    """Project the YM2612 DAC byte timeline onto a Delta-T unit.

    With ``dac_target='opna'`` (default) the destination is the
    OPNA's ADPCM-B channel; with ``'y8950'`` it is the MSX-AUDIO
    Y8950's ADPCM unit. The waveform inventory, run splitting,
    encoding and deduplication are shared; only the rate law,
    sample budget, preload block type and trigger registers
    differ.

    Returns (rows, data_block, losses, stats, run_rows). The
    timeline merges register writes (0x2A inside DAC-enabled
    spans) with stream supplies (ungated - the stream mechanism
    carries its own playback intent). Runs split at tick gaps
    over _DAC_RUN_GAP_TICKS and at stream seeks, the driver's
    own phrase marks; each run's waveform is resampled to the
    run's own delta-N rate and YM delta-encoded. A run containing
    stream supplies takes its samples from the byte sequence
    itself (the tick gaps are the stream clock quantised to the
    44.1 kHz grid, and baking that jitter in would defeat
    deduplication); a register-only run uses the sample-and-hold
    tick grid. Identical waveforms are stored once. Sample starts
    align to the 32-byte address unit and the nibble count is
    padded with the held final value up to a whole unit, so the
    unit-granular end address plays exactly the stored bytes.
    Samples that exceed the DRAM budget are dropped together
    with their playbacks and counted.
    """
    from bisect import bisect_right
    if dac_target not in ('opna', 'y8950'):
        raise ValueError(f'Unknown DAC target: {dac_target!r}')
    if dac_target == 'y8950':
        rate_clock, rate_divisor = Y8950_CLOCK, 72 * 65536
        sample_budget = Y8950_RAM_BUDGET
    else:
        rate_clock, rate_divisor = OPNA_CLOCK, 144 * 65536
        sample_budget = ADPCM_B_DRAM_BUDGET
    rows, run_rows = [], []
    losses = Counter()
    spans = [(segment.vgmticks, segment.vgmticks_end)
             for segment in analysis.segments
             if segment.ch == 5 and segment.state.dac_enabled == 1]
    span_starts = [start for start, _ in spans]

    def audible(tick):
        index = bisect_right(span_starts, tick) - 1
        return index >= 0 and tick < spans[index][1]

    timeline = []
    dropped_disabled = collapsed = 0
    for write in analysis.unmodeled_writes:
        if write.domain != 'dac_data' or write.chip_instance != 0:
            continue
        if not audible(write.vgmticks):
            dropped_disabled += 1
            continue
        timeline.append((write.vgmticks, write.data,
                         write.source_event_id, None, None))
    supplies, stream_issues, stream_stats = _decode_dac_stream(raw, events)
    for code, count in stream_issues.items():
        if code != 'opn2_dac_implicit_stream_context':
            losses['dac_' + code.removeprefix('opn2_dac_')] += count
    timeline.extend(supplies)
    timeline.sort(key=lambda row: (row[0], row[2]))
    merged_timeline = []
    for row in timeline:
        if merged_timeline and merged_timeline[-1][0] == row[0]:
            merged_timeline[-1] = row
            collapsed += 1
        else:
            merged_timeline.append(row)
    timeline = merged_timeline
    stats = dict(timeline_writes=len(timeline),
                 dropped_disabled_writes=dropped_disabled,
                 collapsed_same_tick_writes=collapsed,
                 stream_supplies=len(supplies),
                 stream_implicit_context=stream_stats['implicit_stream'],
                 stream_data_block_bytes=stream_stats['data_block_bytes'],
                 runs=0, playbacks=0, unique_samples=0, dram_bytes=0)
    if not timeline:
        return rows, b'', losses, stats, run_rows
    runs = [[timeline[0]]]
    for row in timeline[1:]:
        previous = runs[-1][-1]
        offset_break = (row[3] is not None and previous[3] is not None
                        and row[3] != previous[3] + (previous[4] or 1))
        if row[0] - previous[0] <= _DAC_RUN_GAP_TICKS and not offset_break:
            runs[-1].append(row)
        else:
            runs.append([row])
    stats['runs'] = len(runs)

    sample_list = []
    waveform_ids = {}
    stream_groups = {}
    image = bytearray()
    prepared = [None] * len(runs)
    run_rows = [None] * len(runs)

    def add_sample(encoded, delta_n, rate, count):
        if len(image) + len(encoded) > sample_budget:
            return None
        sample = dict(sample_id=len(sample_list), address=len(image),
                      encoded=encoded, delta_n=delta_n,
                      rate_hz=float(rate), samples=count)
        sample_list.append(sample)
        image.extend(encoded)
        return sample

    for run_index, run in enumerate(runs):
        gaps = sorted(b[0] - a[0] for a, b in zip(run, run[1:]) if b[0] > a[0])
        hold = gaps[len(gaps) // 2] if gaps else 1
        start = run[0][0]
        stop = min(run[-1][0] + hold, source_end)
        if run_index + 1 < len(runs):
            stop = min(stop, runs[run_index + 1][0][0])
        base = dict(run_index=run_index, start_vgmticks=start, end_vgmticks=stop,
                    source_bytes=len(run), first_source_event_id=run[0][2],
                    last_source_event_id=run[-1][2], sample_id='',
                    rate_hz='', delta_n='', samples_emitted='',
                    dram_address='', termination='', stream_based='',
                    natural_rate_hz='')
        if stop - start < 2:
            losses['dac_subsample_runs_dropped'] += 1
            base['termination'] = 'subsample_dropped'
            run_rows[run_index] = base
            continue
        stream_based = any(row[3] is not None for row in run)
        base['stream_based'] = stream_based
        if stream_based:
            # Stream supplies are samples of the stream's own
            # clock; their tick gaps are that clock quantised to
            # the 44.1 kHz grid (a steady ~16.5 kHz stream shows
            # gaps of 2/3/4 ticks), so an occurrence's exact tick
            # span is jitter, not content. The chunk is therefore
            # identified by its byte sequence and stored once per
            # rate cluster (second pass below) at the cluster's
            # canonical rate, its samples the bytes themselves.
            natural = Fraction(len(run) * 44100, stop - start)
            base['natural_rate_hz'] = float(natural)
            stream_groups.setdefault(bytes(row[1] for row in run), []).append(
                dict(run_index=run_index, base=base, natural=natural, stop=stop,
                     amplitudes=[(row[1] - 128) * 256 for row in run]))
            continue
        wave = array('h', bytes(2 * (stop - start)))
        for (tick, byte, _event, *_rest), (next_tick, *_tail) in zip(
                run, run[1:] + [(stop, 0, 0, None, None)]):
            wave[tick - start:next_tick - start] = (
                array('h', [(byte - 128) * 256]) * (next_tick - tick))
        natural = Fraction(44100, hold)
        base['natural_rate_hz'] = float(natural)
        delta_n = max(1, min(65535, round(natural * rate_divisor / rate_clock)))
        rate = Fraction(rate_clock * delta_n, rate_divisor)
        count = max(2, 2 * round(Fraction(stop - start) * rate / 44100 / 2))
        if count % 64:
            count += 64 - count % 64
        ratio = Fraction(44100) / rate
        resampled = array('h')
        for index in range(count):
            position = max(Fraction(0),
                           Fraction(2 * index + 1, 2) * ratio - Fraction(1, 2))
            low = min(len(wave) - 1, position.numerator // position.denominator)
            high = min(len(wave) - 1, low + 1)
            fraction = position - position.numerator // position.denominator
            resampled.append(round(wave[low] * (1 - fraction)
                                   + wave[high] * fraction))
        key = hashlib.sha256(resampled.tobytes()).digest()
        sample = waveform_ids.get(key)
        if sample is None:
            sample = add_sample(_encode_adpcm_b(resampled), delta_n, rate, count)
            if sample is None:
                losses['dac_dram_budget_samples_dropped'] += 1
                base['termination'] = 'dram_budget_dropped'
                run_rows[run_index] = base
                continue
            waveform_ids[key] = sample
        base.update(sample_id=sample['sample_id'], rate_hz=sample['rate_hz'],
                    delta_n=sample['delta_n'], samples_emitted=sample['samples'],
                    dram_address=sample['address'],
                    termination='song_end' if stop >= source_end else 'gap')
        run_rows[run_index] = base
        prepared[run_index] = base | {'sample': sample}
    for group in stream_groups.values():
        group.sort(key=lambda descriptor: descriptor['natural'])
        clusters = [[group[0]]]
        for descriptor in group[1:]:
            if descriptor['natural'] * 100 <= clusters[-1][0]['natural'] * 103:
                clusters[-1].append(descriptor)
            else:
                clusters.append([descriptor])
        for cluster in clusters:
            median = cluster[len(cluster) // 2]['natural']
            delta_n = max(1, min(65535, round(
                median * rate_divisor / rate_clock)))
            rate = Fraction(rate_clock * delta_n, rate_divisor)
            amplitudes = cluster[0]['amplitudes']
            count = len(amplitudes)
            if count % 64:
                amplitudes = amplitudes + [amplitudes[-1]] * (64 - count % 64)
                count = len(amplitudes)
            sample = add_sample(_encode_adpcm_b(amplitudes), delta_n, rate, count)
            if sample is None:
                losses['dac_dram_budget_samples_dropped'] += 1
            for descriptor in cluster:
                base = descriptor['base']
                if sample is None:
                    base['termination'] = 'dram_budget_dropped'
                else:
                    base.update(
                        sample_id=sample['sample_id'],
                        rate_hz=sample['rate_hz'], delta_n=sample['delta_n'],
                        samples_emitted=sample['samples'],
                        dram_address=sample['address'],
                        termination='song_end' if descriptor['stop'] >= source_end
                        else 'gap')
                    prepared[descriptor['run_index']] = base | {'sample': sample}
                run_rows[descriptor['run_index']] = base
    stats.update(playbacks=sum(1 for entry in prepared if entry),
                 unique_samples=len(sample_list), dram_bytes=len(image))
    if not sample_list:
        return rows, b'', losses, stats, run_rows

    def emit(tick, event_id, register, data, reason, rank=1):
        rows.append(dict(
            write_id=len(rows), state_origin='projected_dac', source_chip='opn2',
            target_device=('y8950_adpcm' if dac_target == 'y8950'
                           else 'opna_adpcm_b'),
            target_command=0x5C if dac_target == 'y8950' else 0x57,
            source_event_id=event_id, source_segment_id=None,
            original_event_id=None, loop_iteration=0,
            source_vgmticks=tick, source_ch=6, source_period=None,
            source_attenuation=None, source_noise_control=None,
            target_register=register, target_data=data, reason=reason,
            source_frequency_hz=None, target_frequency_hz=None,
            target_ch=None, source_row=None, inferred_key=False,
            synthetic_phase=None, sort_rank=rank))

    if dac_target == 'y8950':
        emit(0, None, 0x07, 0x01, 'y8950_adpcm reset', rank=0)
        emit(0, None, 0x07, 0x00, 'y8950_adpcm reset release', rank=0)
        for entry in prepared:
            if entry is None:
                continue
            sample = entry['sample']
            start_unit = sample['address'] >> 2
            stop_unit = (sample['address'] + len(sample['encoded']) - 1) >> 2
            tick, event_id = (entry['start_vgmticks'],
                              entry['first_source_event_id'])
            for register, data, reason in (
                    (0x08, 0x00, 'y8950_adpcm memory select (RAM 256K)'),
                    (0x09, start_unit & 0xFF, 'y8950_adpcm start address low'),
                    (0x0A, start_unit >> 8, 'y8950_adpcm start address high'),
                    (0x0B, stop_unit & 0xFF, 'y8950_adpcm stop address low'),
                    (0x0C, stop_unit >> 8, 'y8950_adpcm stop address high'),
                    (0x10, sample['delta_n'] & 0xFF, 'y8950_adpcm delta-N low'),
                    (0x11, sample['delta_n'] >> 8, 'y8950_adpcm delta-N high'),
                    (0x12, ADPCM_B_LEVEL, 'y8950_adpcm level'),
                    (0x07, 0x80, 'y8950_adpcm start')):
                emit(tick, event_id, register, data, reason)
        block_type = 0x88
    else:
        emit(0, None, 0x00, 0x01, 'adpcm_b reset', rank=0)
        emit(0, None, 0x00, 0x00, 'adpcm_b reset release', rank=0)
        for entry in prepared:
            if entry is None:
                continue
            sample = entry['sample']
            start_unit = sample['address'] >> 5
            end_unit = (sample['address'] + len(sample['encoded'])) >> 5
            tick, event_id = (entry['start_vgmticks'],
                              entry['first_source_event_id'])
            for register, data, reason in (
                    (0x01, 0xC2, 'adpcm_b control 2 (L+R, DRAM x8)'),
                    (0x02, start_unit & 0xFF, 'adpcm_b start address low'),
                    (0x03, start_unit >> 8, 'adpcm_b start address high'),
                    (0x04, (end_unit - 1) & 0xFF, 'adpcm_b end address low'),
                    (0x05, (end_unit - 1) >> 8, 'adpcm_b end address high'),
                    (0x09, sample['delta_n'] & 0xFF, 'adpcm_b delta-N low'),
                    (0x0A, sample['delta_n'] >> 8, 'adpcm_b delta-N high'),
                    (0x0B, ADPCM_B_LEVEL, 'adpcm_b level'),
                    (0x0C, 0xFF, 'adpcm_b limit low'),
                    (0x0D, 0xFF, 'adpcm_b limit high'),
                    (0x00, 0xA0, 'adpcm_b start (external DRAM)')):
                emit(tick, event_id, register, data, reason)
        block_type = 0x81
    payload = struct.pack('<II', len(image), 0) + bytes(image)
    data_block = (bytes((0x67, 0x66, block_type))
                  + struct.pack('<I', len(payload)) + payload)
    return rows, data_block, losses, stats, run_rows


# OPN2>OPNA conversion law (measured 2026-11-07 with ymfm cores
# driven directly; study in ~/workspace/opn2_opna_study, PLAN.md).
# The YM2608's TL is a clean -0.753 dB/step over the whole range,
# but the YM2612's effective carrier level compresses: -22.1 dB
# at TL 32 (ideal -24.1), a floor of -34..-35 dB over TL 64-100,
# and silence from TL 104. Mapping a source TL through its
# effective level on the 2612 and back to a 2608 TL at
# 0.753 dB/step gives this table. It applies to carrier slots
# only: a best-match sweep over modulator TLs found no target
# value that reproduces a 2612 modulator's spectrum better than
# identity (the residual is the 2612 output stage's own
# distortion), so modulators keep their register values.
_OPNA_LAW_TL = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 14,
    15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 24, 25, 26, 27, 28, 29,
    29, 30, 31, 32, 32, 33, 34, 34, 35, 36, 36, 37, 37, 38, 39, 39,
    40, 40, 41, 41, 41, 42, 42, 43, 43, 43, 43, 43, 44, 44, 44, 45,
    45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45,
    45, 45, 45, 46, 46, 46, 46, 46, 46, 46, 46, 46, 46, 46, 47, 47,
    47, 48, 48, 49, 49, 51, 52, 56, 127, 127, 127, 127, 127, 127, 127, 127,
    127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127, 127,
)

# EG decay rates (D1R/D2R share one measured time ladder): the
# 2608 decays faster than the clock ratio predicts, worst
# around rates 4-11 (up to ~25%). The per-rate argmin over the
# measured ladders gives -1 step at source rates {3,4,5,7,9,10,
# 11} and identity elsewhere (the fast end is measurement
# floor). Attacks match after clock normalisation, releases
# differ by less than half of their coarse (~x2) step, so AR
# and RR stay identity. The correction is applied only to
# slots whose key scale is 0; KS > 0 pushes the effective rate
# toward the range where the chips already agree.
_OPNA_LAW_DECAY = (
    0, 1, 2, 2, 3, 4, 6, 6, 8, 8, 9, 10, 12, 13, 14, 15,
    16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
)

# Carrier operator numbers (1-4) per algorithm, and the
# register slot order: slots are laid out OP1, OP3, OP2, OP4.
_ALG_CARRIERS = (
    frozenset((4,)), frozenset((4,)), frozenset((4,)), frozenset((4,)),
    frozenset((2, 4)), frozenset((2, 3, 4)), frozenset((2, 3, 4)),
    frozenset((1, 2, 3, 4)),
)
_SLOT_OPERATOR = (1, 3, 2, 4)


def project_fm_from_analysis(analysis, *, clock_raw, force=False, law=False):
    """Project the OPN2 analysis onto the OPNA's own FM section.

    This is the FM lane of the makoto target composition and the
    added lane of the layered file. Like project() on the OPM
    route, it is driven by the analysis: source events decide
    when a write happens, the segment state decides what it
    contains. The YM2608 FM register map is the YM2612's, so
    operator parameters, feedback/algorithm, pan/LFO sensitivity
    and key on/off are rebuilt from the synchronised state, and
    the F-numbers are rescaled from the source clock to the
    OPNA's 8 MHz (block preserved unless the scaled value
    overflows 11 bits). A write whose value the target already
    holds is not re-emitted, so the source's write choreography
    (in particular the F-number high byte, a latch that is only
    ever committed by the paired low write) leaves no duplicate
    writes in the target stream.

    Channel 6 keys are gated while the source DAC owns that
    channel's output, mirroring the source chip: suppressed key
    writes are counted, and the current mask is restored when
    the DAC releases the channel. Timer controls have no lane
    here and are counted, not copied. CSM is refused without
    force, as on the OPM route.

    With ``law``, the measured OPN2>OPNA conversion law is
    applied at this mapping stage: carrier TLs are remapped
    through the YM2612's effective level curve (_OPNA_LAW_TL)
    and decay rates of key-scale-0 slots are corrected
    (_OPNA_LAW_DECAY), both read from the segment state.
    Everything else stays at the state value (the measurements
    found AR, RR, DT, FB, LFO rate and PM/AM depths identical
    after clock normalisation, and no modulator TL that
    reproduces a 2612 modulator's spectrum better than
    identity). The YM2612's output-stage distortion and the
    OPNA's ~2.2 dB lower level at TL 0 have no register
    equivalent and are not corrected.
    """
    if analysis.csm_observed and not force:
        raise ValueError('OPN2 CSM timer-generated key events '
                         'cannot project to OPNA FM')
    clock = clock_raw & 0x3fffffff
    ratio = clock / OPNA_CLOCK
    rows = []
    cache = {}
    key_emitted = [0] * 6
    corrections = 0
    law_counts = dict(tl_carrier=0, decay_rate=0)
    gated_keys = 0
    timer_writes = 0

    def emit(s, command, register, data, *, force=False):
        if not force and cache.get((command, register)) == data:
            return
        cache[(command, register)] = data
        rows.append(dict(source_vgmticks=s.vgmticks,
                         source_event_id=s.source_event_id,
                         source_register=s.register, source_data=s.data,
                         target_command=command, sort_rank=2,
                         target_register=register, target_data=data))

    def emit_pitch(s, command, low_register, high_register, fnum, block):
        nonlocal corrections
        scaled = round(fnum * ratio)
        new_block = block
        while scaled > 2047 and new_block < 7:
            new_block += 1
            scaled = (scaled + 1) >> 1
        if fnum and not scaled:
            scaled = 1
        if (scaled, new_block) != (fnum, block):
            corrections += 1
        # The pair is atomic: the high byte goes into a latch cell
        # shared by every channel (ymfm's verified model), which the
        # low write then commits. Neither byte may be deduped - the
        # high byte because another channel's pitch write can
        # overwrite the shared cell before this commit, the low byte
        # because a block-only change (same low byte) takes effect
        # only when the commit write happens.
        emit(s, command, high_register, (new_block << 3) | (scaled >> 8),
             force=True)
        emit(s, command, low_register, scaled & 0xff, force=True)

    def law_reeval(s):
        # The law's target value for a slot is a function of the
        # slot's state AND its context (the channel's current
        # algorithm for TL, the slot's key scale for decay rates).
        # A context change alone - an algorithm or key-scale write
        # with no rewrite of the affected register - therefore
        # changes the desired byte, and the state machine records
        # no event for the affected register itself. Re-evaluate
        # the law-affected bytes from every segment state so a
        # context change re-emits them at the tick it takes
        # effect; the emit cache suppresses anything unchanged.
        if s.ch is None or not 0 <= s.ch < 6:
            return
        state = s.state
        # The segment's port field is its opening event's port,
        # which for fanned-out shared events (the F-number latch
        # above all) is not the channel's own port; the target
        # port follows from the channel alone.
        command = 0x56 if s.ch < 3 else 0x57
        local = s.ch % 3
        carriers = _ALG_CARRIERS[state.algorithm or 0]
        for bank, op in enumerate(state.operators):
            slot_reg = bank * 4 + local
            if op.tl is not None:
                data = (_OPNA_LAW_TL[op.tl]
                        if _SLOT_OPERATOR[bank] in carriers else op.tl)
                if (data != op.tl
                        and cache.get((command, 0x40 + slot_reg)) != data):
                    law_counts['tl_carrier'] += 1
                emit(s, command, 0x40 + slot_reg, data)
            if op.d1r is not None:
                rate = op.d1r
                if (op.ks or 0) == 0:
                    rate = _OPNA_LAW_DECAY[rate]
                data = (op.am_enabled or 0) << 7 | rate
                if (rate != op.d1r
                        and cache.get((command, 0x60 + slot_reg)) != data):
                    law_counts['decay_rate'] += 1
                emit(s, command, 0x60 + slot_reg, data)
            if op.d2r is not None:
                rate = op.d2r
                if (op.ks or 0) == 0:
                    rate = _OPNA_LAW_DECAY[rate]
                if (rate != op.d2r
                        and cache.get((command, 0x70 + slot_reg)) != rate):
                    law_counts['decay_rate'] += 1
                emit(s, command, 0x70 + slot_reg, rate)

    groups = {}
    for s in analysis.segments:
        if s.source_event_id is not None:
            groups.setdefault(s.source_event_id, []).append(s)
    for _, segments in sorted(groups.items()):
        s = segments[0]
        state, reg = s.state, s.register
        if reg is None:
            continue
        port = s.port
        command = 0x56 if port == 0 else 0x57
        if 0x30 <= reg <= 0x9f:
            bank = (reg >> 2) & 3
            op = state.operators[bank]
            kind = reg & 0xf0
            if kind == 0x30:
                data = (op.dt or 0) << 4 | (op.mul or 0)
            elif kind == 0x40:
                data = op.tl or 0
                if (law and _SLOT_OPERATOR[bank]
                        in _ALG_CARRIERS[state.algorithm or 0]):
                    mapped = _OPNA_LAW_TL[data]
                    if mapped != data:
                        law_counts['tl_carrier'] += 1
                    data = mapped
            elif kind == 0x50:
                data = (op.ks or 0) << 6 | (op.ar or 0)
            elif kind == 0x60:
                rate = op.d1r or 0
                if law and (op.ks or 0) == 0:
                    mapped = _OPNA_LAW_DECAY[rate]
                    if mapped != rate:
                        law_counts['decay_rate'] += 1
                    rate = mapped
                data = (op.am_enabled or 0) << 7 | rate
            elif kind == 0x70:
                rate = op.d2r or 0
                if law and (op.ks or 0) == 0:
                    mapped = _OPNA_LAW_DECAY[rate]
                    if mapped != rate:
                        law_counts['decay_rate'] += 1
                    rate = mapped
                data = rate
            elif kind == 0x80:
                data = (op.sl or 0) << 4 | (op.rr or 0)
            else:
                data = op.ssg_eg_raw or 0
            emit(s, command, reg, data)
        elif 0xb0 <= reg <= 0xb2:
            emit(s, command, reg,
                 (state.feedback or 0) << 3 | (state.algorithm or 0))
        elif 0xb4 <= reg <= 0xb6:
            emit(s, command, reg,
                 (state.left_enabled or 0) << 7
                 | (state.right_enabled or 0) << 6
                 | (state.ams or 0) << 4 | (state.pms or 0))
        elif 0xa0 <= reg <= 0xa2:
            if state.fnum is not None:
                emit_pitch(s, command, reg, reg + 4,
                           state.fnum, state.block or 0)
        elif 0xa8 <= reg <= 0xaa:
            name = {0xa8: 'op3', 0xa9: 'op1', 0xaa: 'op2'}[reg]
            special = {n: (f, b) for n, f, b in state.special_frequencies}
            fnum, block = special.get(name, (None, None))
            if fnum is not None:
                emit_pitch(s, command, reg, reg + 4, fnum, block or 0)
        elif reg == 0x28 and port == 0:
            if s.ch == 5 and state.dac_enabled == 1:
                gated_keys += 1
                continue
            rows.append(dict(source_vgmticks=s.vgmticks,
                             source_event_id=s.source_event_id,
                             source_register=s.register, source_data=s.data,
                             target_command=0x56, sort_rank=2,
                             target_register=0x28, target_data=s.data))
            if 0 <= s.ch < 6:
                key_emitted[s.ch] = state.key_mask or 0
        elif port == 0 and reg == 0x2b:
            if (not state.dac_enabled and s.ch == 5
                    and (state.key_mask or 0) != key_emitted[5]):
                rows.append(dict(
                    source_vgmticks=s.vgmticks,
                    source_event_id=s.source_event_id,
                    source_register=s.register, source_data=s.data,
                    target_command=0x56, sort_rank=2,
                    target_register=0x28,
                    target_data=(state.key_mask or 0) << 4 | 6))
                key_emitted[5] = state.key_mask or 0
        elif port == 0 and reg == 0x22:
            emit(s, 0x56, 0x22, state.lfo_raw or 0)
        elif port == 0 and reg == 0x27:
            emit(s, 0x56, 0x27, state.mode_raw or 0)
        elif port == 0 and reg in (0x24, 0x25, 0x26):
            timer_writes += 1
        if law:
            for item in segments:
                law_reeval(item)
    stats = dict(fnum_corrections=corrections)
    if gated_keys:
        stats['dac_enabled_ch6_key_writes_gated'] = gated_keys
    if timer_writes:
        stats['source_timer_controls_not_projected'] = timer_writes
    if law:
        stats['law_tl_carrier_writes'] = law_counts['tl_carrier']
        stats['law_decay_rate_writes'] = law_counts['decay_rate']
    return rows, stats


def write_vgm(rows, path, *, end, loop_start=None, loop_event_id=None, prefix=b'',
              opm_clock=TARGET_CLOCK):
    """Serialize merged projection rows at exact source samples.

    Rows carry their own target command (0x54 YM2151, 0xA0 AY,
    0x56/0x57 YM2608 ports 0/1, 0x5C Y8950) and must already be in
    non-decreasing source sample order. ``prefix`` bytes (the
    ADPCM-B data block) lead the command stream; they sit before
    any loop point, so the loop offset accounts for them. The
    header is the full 256-byte form so the YM2608 (0x48) and AY
    (0x74/0x78) fields fit; each clock is stamped only when its
    command actually appears. A valid source loop is carried into
    the header without expanding the timeline.
    """
    from native_imports.vgm_timing import command_times
    commands, cursor, loop_address = bytearray(prefix), 0, None
    if not 0 <= end <= 0xffffffff or (loop_start is not None and not 0 <= loop_start < end):
        raise ValueError('Projected OPN2 duration/loop is outside the VGM field range')
    def wait(gap):
        while gap:
            count = min(gap, 65535)
            commands.extend(b'\x61' + struct.pack('<H', count))
            gap -= count
    def advance(sample, source_event_id=None, *, final=False):
        nonlocal cursor, loop_address
        if sample < cursor:
            raise ValueError('OPN2 projection writes are not in source sample order')
        at_loop = (loop_event_id is None or final or sample > (loop_start or 0)
                   or source_event_id is not None and source_event_id >= loop_event_id)
        if loop_start is not None and loop_address is None and cursor <= loop_start <= sample and at_loop:
            wait(loop_start - cursor)
            cursor = loop_start
            loop_address = 0x100 + len(commands)
        wait(sample - cursor)
        cursor = sample
    for row in rows:
        advance(row['source_vgmticks'], row['source_event_id'])
        row['target_command_address'] = 0x100 + len(commands)
        commands.extend((row.get('target_command', 0x54),
                         row['target_register'], row['target_data']))
    advance(end, final=True)
    commands.append(0x66)
    raw = bytearray(0x100) + commands
    raw[:4] = b'Vgm '
    present = {row.get('target_command', 0x54) for row in rows}
    stamps = [(4, len(raw) - 4), (8, 0x171), (0x18, end),
              (0x34, 0x100 - 0x34)]
    if 0x54 in present:
        stamps.append((0x30, opm_clock))
    if present & {0x56, 0x57}:
        stamps.append((0x48, OPNA_CLOCK))
    if 0x5C in present:
        stamps.append((0x58, Y8950_CLOCK))
    if 0xA0 in present:
        stamps.append((0x74, AY_CLOCK))
    for offset, value in stamps:
        struct.pack_into('<I', raw, offset, value)
    if 0xA0 in present:
        raw[0x78] = 0x10  # YM2149 type byte, the musical_vgm convention
    if loop_address is not None:
        struct.pack_into('<I', raw, 0x1c, loop_address - 0x1c)
        struct.pack_into('<I', raw, 0x20, end - loop_start)
    identities = {e.address: i for i, e in enumerate(command_times(raw))
                  if e.command in (0x54, 0xA0, 0x56, 0x57, 0x5C)}
    for row in rows:
        row['target_source_event_id'] = identities[row['target_command_address']]
    Path(path).write_bytes(raw)


def convert(source, outdir, *, force=False, layered=False, target='makoto',
            dac='opna', dcsg_gain=1.0, opna_law=False):
    """Analyze one OPN2 VGM and emit its target VGM.

    Native evidence (registers/states/segments CSVs and the source
    report) lands in ``outdir`` next to ``<stem>.target.vgm``, the
    per-lane projected-writes CSVs and the summary JSON. The DCSG
    lanes go to the MSX PSG + OPNA SSG and the DAC is re-encoded
    to a Delta-T unit (see ``dac`` below).

    ``target`` selects the FM composition. ``makoto`` (default)
    is the OPNA cartridge alone: the FM part is retargeted onto
    the OPNA's own FM section (project_fm_from_analysis) and no YM2151
    writes are emitted. ``sfg01`` is the dual-cartridge
    composition: the FM part is projected to the OPM cartridge
    (YM2151) and the OPNA cartridge carries SSG + ADPCM-B.
    ``opm4mhz`` is that same composition with the OPM clock at
    4 MHz (the eseopm switch position for X1/X68000 pitches);
    only the KC/KF pitch projection and the YM2151 header clock
    change.

    ``dac`` selects the DAC lane's destination: ``opna``
    (default) is the OPNA's ADPCM-B; ``y8950`` is an MSX-AUDIO
    Y8950's Delta-T unit (e.g. alongside a Misato cartridge,
    which has no ADPCM of its own).

    With ``layered``, a second file ``<stem>.layer.target.vgm``
    is emitted alongside: the target composition plus the other
    FM lane, so the FM sounds on the OPM and OPNA cartridges
    together. Only the FM lane is layered. The layered
    composition is the dual-cartridge one, so with ``layered``
    a ``dac`` of ``y8950`` is corrected to ``opna`` (the OPNA
    cartridge is present by construction); the summary then
    carries ``dac_corrected_from``.
    """
    dac_corrected = bool(layered and dac == 'y8950')
    if dac_corrected:
        dac = 'opna'
    if not dcsg_gain > 0:
        raise ValueError(f'dcsg_gain must be positive: {dcsg_gain!r}')
    opm_clock = OPM4MHZ_CLOCK if target == 'opm4mhz' else TARGET_CLOCK
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    bundle = analyze_source(source, outdir, stem)
    if 'opn2' not in bundle['active_chips']:
        raise ValueError('Input has no OPN2 (YM2612) writes')
    analysis = bundle['analyses']['opn2']
    if analysis is None:
        raise ValueError(f"OPN2 analysis failed: {bundle['errors'].get('opn2')}")
    clock_raw = bundle['header']['opn2_clock_raw']
    loop = bundle['loop']
    loop_start = loop_event_id = None
    if loop.get('status') == 'valid':
        loop_start = loop['loop_start_samples']
        loop_event_id = next((e.source_event_id for e in bundle['events']
                              if e.address == loop.get('loop_address')), None)
    rows, losses = project(analysis, clock_raw=clock_raw, force=force, dac_external=True,
                           opm_clock=opm_clock)
    losses.pop('dac_data_writes_projected_to_pcm', None)
    dcsg_rows, dcsg_stats = [], {}
    dcsg_analysis = bundle['analyses'].get('dcsg')
    if dcsg_analysis is not None:
        dcsg_rows, dcsg_losses, dcsg_stats = project_dcsg(
            dcsg_analysis, loop_start=loop_start, loop_event_id=loop_event_id,
            dcsg_gain=dcsg_gain)
        for key, value in dcsg_losses.items():
            losses[key] = losses.get(key, 0) + value
    raw = read_vgm_bytes(str(source))
    dac_rows, dac_block, dac_losses, dac_stats, dac_runs = project_dac(
        analysis, source_end=bundle['source_end_sample'],
        raw=raw, events=bundle['events'], dac_target=dac)
    for key, value in dac_losses.items():
        losses[key] = losses.get(key, 0) + value
    if target not in ('makoto', 'sfg01', 'opm4mhz'):
        raise ValueError(f'Unknown OPN2 target cartridge: {target!r}')
    opna_fm_rows, opna_fm_stats = [], {}
    if target == 'makoto' or layered:
        opna_fm_rows, opna_fm_stats = project_fm_from_analysis(
            analysis, clock_raw=clock_raw, force=force, law=opna_law)
    fm_rows = opna_fm_rows if target == 'makoto' else rows
    merged = sorted(fm_rows + dcsg_rows + dac_rows,
                    key=lambda r: (r['source_vgmticks'], r.get('sort_rank', 1)))
    target_file = outdir / f'{stem}.target.vgm'
    write_vgm(merged, target_file, end=bundle['source_end_sample'],
              loop_start=loop_start, loop_event_id=loop_event_id,
              prefix=dac_block, opm_clock=opm_clock)
    writes_csv = outdir / f'{stem}.opn2_opm.writes.csv'
    with writes_csv.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['write_id'])
        writer.writeheader()
        writer.writerows(rows)
    if opna_fm_rows:
        opna_csv = outdir / f'{stem}.opn2_opna_fm.writes.csv'
        with opna_csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(opna_fm_rows[0]))
            writer.writeheader()
            writer.writerows(opna_fm_rows)
    if dcsg_rows:
        dcsg_csv = outdir / f'{stem}.opn2_dcsg.writes.csv'
        with dcsg_csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dcsg_rows[0]))
            writer.writeheader()
            writer.writerows(dcsg_rows)
    if dac_runs:
        dac_csv = outdir / f'{stem}.opn2_dac.csv'
        with dac_csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dac_runs[0]))
            writer.writeheader()
            writer.writerows(dac_runs)
    added_rows, layer_target, layer_target_writes = [], None, 0
    if layered:
        added_rows = rows if target == 'makoto' else opna_fm_rows
        if added_rows:
            # The layered composition is canonical - OPM lane,
            # DCSG, DAC, then the OPNA FM lane - whichever target
            # was picked as primary, so the layered file is the
            # same dual-cartridge file the trial established (with
            # stable sorting, same-tick same-rank rows keep this
            # concatenation order).
            layer_merged = sorted(rows + dcsg_rows + dac_rows + opna_fm_rows,
                                  key=lambda r: (r['source_vgmticks'],
                                                 r.get('sort_rank', 1)))
            layer_target = outdir / f'{stem}.layer.target.vgm'
            write_vgm(layer_merged, layer_target,
                      end=bundle['source_end_sample'],
                      loop_start=loop_start, loop_event_id=loop_event_id,
                      prefix=dac_block, opm_clock=opm_clock)
            layer_target_writes = len(layer_merged)
    deferred = {}
    summary = dict(source=str(source), source_sha256=bundle['source_sha256'],
                   active_chips=list(bundle['active_chips']),
                   opn2_clock_hz=clock_raw & 0x3fffffff,
                   target_cartridge=target,
                   target_clock_hz=(opm_clock if target in ('sfg01', 'opm4mhz')
                                    else OPNA_CLOCK),
                   target_vgm=target_file.name,
                   target_writes=len(merged),
                   opm_writes=len(rows) if target in ('sfg01', 'opm4mhz') else 0,
                   opna_fm_writes=(len(opna_fm_rows)
                                   if target == 'makoto' else 0),
                   dcsg_writes=len(dcsg_rows), dcsg=dcsg_stats,
                   dcsg_gain=dcsg_gain,
                   opna_law=opna_law,
                   dac_target=dac,
                   dac_writes=len(dac_rows), dac=dac_stats,
                   layered=layered, layer_writes=len(added_rows),
                   layer=opna_fm_stats,
                   layer_target_vgm=(layer_target.name if layer_target else None),
                   layer_target_writes=layer_target_writes,
                   losses=losses, deferred=deferred,
                   loop=dict(status=loop.get('status'), start_sample=loop_start))
    if dac_corrected:
        summary['dac_corrected_from'] = 'y8950'
    (outdir / f'{stem}.opn2_opm.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary
