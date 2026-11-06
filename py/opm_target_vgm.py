"""Native YM2151 (OPM) sources -> MSX cartridge variant VGMs.

Variant compositions (the export records the rest unavailable):

- ``makoto``: the OPM FM voices projected onto the OPNA Sound
  Cartridge's FM section under the verified OPM>OPNA law below,
  stamped at the cartridge's 8.00 MHz. The OPM ch8 noise lane is
  substituted by the OPNA SSG noise channel.
- ``sfg01``: near-passthrough re-emission of the OPM stream for
  the pseudo-OPM cartridge at its standard 3,579,545 Hz stamp;
  KC/KF are re-derived by absolute Hz when the source clock
  differs. ``opm4mhz`` is the same re-emission at the 4,000,000 Hz
  stamp (the cartridge's switch position; also the X68000/X1 OPM
  clock).
- ``layered``: the original OPM stream (3,579,545 Hz) layered
  with the makoto OPNA projection, the OPN2 layered composition
  precedent applied to this route.
- ``sfg01/dac_y8950``: an OPM source has no DAC-class lane for
  the Y8950 to carry, so the variant does not apply (the export
  records the reason; convert raises for dac='y8950').

The OPM>OPNA law is the candidate law of the opm_opna_study
(MEASUREMENTS.md section 8 and the data/*.csv tables, measured
2026-11-06 against ymfm renders of both chips):

- Identity: ALG/FB, DT1->DT, MUL, TL (the 0.7527 dB step is the
  same on both chips, render-proven), KS, D1L, AM enable, pan.
- Pitch: KC/KF -> (block, FNUM) by absolute-Hz minimisation with
  Hz = fnum * clock / (144 * 2**(21 - block)); the target clock
  is a parameter, 8,000,000 Hz for the MSX cartridge pair.
- EG rates: the parametric map derived from
  eg_rate_map_reverse.csv. The projection writes OPNA register
  0x29 = 0x80, selecting prescaler 6, the context in which the
  map is the identity for every measured clock pair; the ps3/ps2
  branches are embedded for completeness (ps2's RR branch depends
  on the source clock, the one pair-dependence in the table).
- LFO: per-channel PMS/AMS selection. PM depth in cents is
  OPM_FULL[pms] * PMD / 127 against the OPNA model series, chosen
  by the log-ratio rule of the study's make_pm_selection.py;
  depths above the OPNA ceiling of 79.3 cents saturate at PMS 7
  and are recorded as losses with the lost cents. AM depth picks
  the nearest OPNA AMS step in dB and saturates at 11.8 dB. LFO
  rates map by log-nearest OPNA rate; rates below the OPNA
  minimum (~4 Hz at 8 MHz) fall to rate 0 with a recorded loss,
  and selections over 25% off are recorded as approximations.
  The OPNA LFO waveform is a fixed triangle; other OPM waveforms
  are substituted and recorded.
- DT2 has no OPNA counterpart (+600/+781/+950 cents by step):
  dropped, recorded as opm_dt2_dropped (user ruling, 2026-11-06).
- Noise: OPM NFREQ -> SSG noise period by the measured table
  (m4_noise_match.csv); NFREQ 29-31 exceed the SSG brightness and
  clamp to period 1 with a recorded loss. The SSG volume is a
  fixed 15: the loudness mapping from the OPM noise operator's
  TL/EG is NOT yet calibrated, and the summary marks
  noise_loudness as calibration-pending wherever the lane sounds.
- CSM key-ons are chip-internal and cannot be projected; the
  fact is recorded, the timer writes themselves are not carried.

Channels: OPM 8 -> OPNA FM 6 is a mapping-stage policy (user
ruling, 2026-11-06: not part of the voice law). The policy is the
allocation behaviour of mucom88_vgm2mml's py/opm_opna.py with
py/opm_channel_allocation.py, ported here: channels that ever key
map in order onto the six slots; with more than six keyed
channels the conversion refuses unless forced, and under force
an ordered whole-gate dynamic allocation runs, restoring the
incoming channel's complete observed voice at each gate (a
restore with unobserved fields refuses, as in mucom88). Only the
allocation behaviour is ported: mucom88's per-field law is not
used (its pitch encoder is render-proven one octave low), and
where mucom88 neutralises the LFO and noise under force, this
projection follows the verified law above instead. Every
allocation omission is recorded in the summary.
"""
import csv
import json
import math
from collections import Counter
from pathlib import Path

from psg_scc_opm import opm_pitch
from native_imports.opm import KC_NOTES, register_channel
from native_imports.source import analyze_source
from opn2_target_vgm import (OPM4MHZ_CLOCK, OPNA_CLOCK, TARGET_CLOCK,
                             write_vgm)


# OPNA LFO rates at the 8 MHz cartridge clock (Hz), render-derived
# in the study (lfo_rate_map_reverse.csv); other target clocks
# scale linearly. Rate 0 (~4 Hz) is also the floor: OPM rates
# below it have no OPNA counterpart.
_OPNA_LFO_HZ = (4.018, 5.636, 6.112, 6.477, 6.999, 9.861, 54.148, 86.535)

# OPM PMS steps reach these depths in cents at PMD 127 (render
# measured, M4); the OPNA PMS model series is what the selection
# targets (ymfm shift table, render-confirmed).
_OPM_PMS_FULL_CENTS = (0., 5.1, 10.3, 20.9, 41.6, 82.9, 335.7, 694.8)
_OPNA_PMS_MODEL_CENTS = (0., 3.4, 6.7, 10.1, 13.5, 20.2, 40.1, 79.3)
# OPM AMS steps reach these depths in dB at AMD 127 (law table;
# renders measured 23.5/47.2/96.3); OPNA AMS steps in dB.
_OPM_AMS_FULL_DB = (0., 23.9, 47.8, 95.6)
_OPNA_AMS_MODEL_DB = (0., 1.4, 5.9, 11.8)

# Measured NFREQ -> SSG noise period (m4_noise_match.csv).
_SSG_NOISE_PERIOD = (9, 8, 10, 8, 8, 8, 8, 7, 6, 6, 6, 6, 5, 5, 5, 5,
                     4, 4, 4, 3, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1)

# The projection's own OPNA prescaler context: register 0x29 is
# written 0x80, whose prescaler select is /6.
_PRESCALER = 6


def _eg_map(rate, *, kind, prescaler, source_clock):
    """CSV-derived EG rate map (eg_rate_map_reverse.csv).

    kind is 'rate5' (AR/D1R/D2R) or 'rr'. Prescaler 6 is the
    identity for every measured clock pair. Prescaler 3 is
    pair-independent; prescaler 2's RR branch depends on the
    source clock (3579545 Hz sources saturate one step lower).
    Unrecorded prescalers fall back to the identity, the
    prescaler-6 behaviour.
    """
    if rate == 0 or prescaler == 6:
        return rate
    if prescaler == 3:
        if kind == 'rr':
            return 0 if rate <= 1 else rate - 1
        return rate if rate < 2 else 1 if rate <= 3 else rate - 2
    if prescaler == 2:
        if kind == 'rr':
            if source_clock == TARGET_CLOCK:
                return 0 if rate <= 2 else rate - 2
            return max(0, rate - 1)
        return rate if rate < 2 else 1 if rate <= 4 else rate - 3
    return rate


def _opm_frequency(kc_raw, kf6, clock_hz):
    """Nominal OPM frequency of a KC/KF pair (the opm_pitch inverse)."""
    semitone = KC_NOTES.get(kc_raw & 15)
    if semitone is None:
        return None
    q = (((kc_raw >> 4) & 7) * 12 + (semitone - 1)) * 64 + (kf6 or 0)
    return 440 * clock_hz / TARGET_CLOCK * 2 ** ((q / 64 - 56) / 12)


def _opna_pitch(hz, target_clock):
    """(block, fnum, actual) minimising |actual - hz| in Hz.

    Hz = fnum * clock / (144 * 2**(21 - block)); Hz minimisation
    and cent minimisation agreed on all 8192 study cases. Blocks
    scan high to low and only strict improvements replace the
    incumbent, the mucom88 allocation source's scan order (its
    encoder's 2**20 scaling is deliberately not shared: it is
    render-proven one octave low).
    """
    best = None
    for block in range(7, -1, -1):
        exact = hz * 144 * 2 ** (21 - block) / target_clock
        for fnum in {int(exact), int(exact) + 1}:
            fnum = max(0, min(2047, fnum))
            actual = fnum * target_clock / (144 * 2 ** (21 - block))
            if best is None or abs(actual - hz) < best[2]:
                best = (block, fnum, abs(actual - hz), actual)
    return best[0], best[1], best[3]


def _opm_lfo_hz(rate_byte, clock_hz):
    return (clock_hz / 64) * (((0x10 | (rate_byte & 0xf)) << (rate_byte >> 4))
                              / 2 ** 30)


def _opna_lfo_rate(hz, target_clock):
    """Log-nearest OPNA LFO rate index and its Hz at target_clock.

    Validated against lfo_rate_map_reverse.csv: the analytic Hz
    model plus this selection reproduces all 512 tabulated
    choices for the 8 MHz target at both source clocks.
    """
    rates = [base * target_clock / OPNA_CLOCK for base in _OPNA_LFO_HZ]
    index = min(range(8), key=lambda i: abs(math.log2(rates[i] / hz)))
    return index, rates[index], rates[0]


def _opna_pms(source_cents):
    """PMS step nearest in log ratio (the study's selection rule)."""
    return min(range(8), key=lambda t: abs(math.log2(
        (_OPNA_PMS_MODEL_CENTS[t] + 0.05) / (source_cents + 0.05))))


def _opna_ams(source_db):
    return min(range(4), key=lambda t: abs(_OPNA_AMS_MODEL_DB[t] - source_db))


class _DynamicChannels:
    """Ordered six-slot whole-gate allocation (mucom88 port).

    Behaviour ported from mucom88_vgm2mml's
    py/opm_channel_allocation.py: a key-on acquires a free slot
    (never-used slots first, then slots whose owner is key-off),
    reusing a slot may truncate the previous owner's release
    (recorded), a gate that finds no slot is omitted until its
    full Key-Off (recorded), and loop ownership must be stable
    across the song loop. Records and omissions keep mucom88's
    shapes so the summary diagnostics read the same.
    """

    def __init__(self, *, force, omissions, end, loop_start=None):
        self.force, self.omissions, self.end = force, omissions, end
        self.loop_start = loop_start
        self.channel_map = {}
        self.owners = [None] * 6
        self.keys = {ch: 0 for ch in range(8)}
        self.dropped = {}
        self.rows = []
        self.gate_ids = {}
        self.next_gate = 0
        self.entry = None
        self.peak = 0

    def snapshot(self):
        return dict(owners=list(self.owners), key_masks=dict(self.keys),
                    dropped_channels=sorted(self.dropped))

    def record(self, s, action, target=None, previous=None):
        row = dict(action=action, source_event_id=s.source_event_id,
                   original_event_id=s.original_event_id,
                   loop_iteration=s.loop_iteration,
                   source_vgmticks=s.vgmticks, source_channel=s.ch,
                   source_gate_id=self.gate_ids.get(s.ch),
                   target_channel=target,
                   previous_source_channel=previous,
                   source_key_mask=s.state.key_mask)
        self.rows.append(row)
        return row

    def before(self, group, *, same_sample_release=False):
        s = group[0]
        if self.loop_start is not None and self.entry is None \
                and s.vgmticks >= self.loop_start:
            self.entry = self.snapshot()
        if s.chip_instance or s.chip_type != 'YM2151':
            return False
        for member in group:
            if member.ch in self.dropped:
                self.dropped[member.ch]['source_event_ids'].append(
                    member.source_event_id)
        if s.register != 8:
            return False
        ch, old, mask = s.ch, self.keys[s.ch], s.state.key_mask
        restore = False
        if not old and mask:
            gate = self.next_gate
            self.next_gate += 1
            self.gate_ids[ch] = gate
            if ch in self.channel_map:
                target = self.channel_map[ch]
            else:
                free = [i for i, owner in enumerate(self.owners)
                        if owner is None or not self.keys[owner]]
                target = next((i for i in free if self.owners[i] is None),
                              next(iter(free), None))
            if target is None:
                if not self.force:
                    raise ValueError('OPM exceeds 6 simultaneous keyed FM '
                                     'voices; use --force to omit excess gates')
                reason = ('opm_same_sample_order_capacity' if same_sample_release
                          else 'opm_simultaneous_fm_capacity')
                row = dict(source_chip='OPM', part='ABCDEFGH'[ch],
                           source_channel=ch, action='omit_fm_gate',
                           reason=reason, source_gate_ids=[gate],
                           source_event_ids=[s.source_event_id],
                           source_start_vgmticks=s.vgmticks,
                           source_end_vgmticks=self.end,
                           actual=sum(bool(v) for v in self.keys.values()) + 1,
                           limit=6, unit='keyed FM voices',
                           same_sample_release_pending=same_sample_release)
                self.omissions.append(row)
                self.dropped[ch] = row
                self.record(s, 'omit_gate_start')
            else:
                previous = self.owners[target]
                if previous is not None and previous != ch:
                    if not self.force:
                        raise ValueError('Dynamic FM slot reuse may truncate '
                                         'release; use --force for explicit '
                                         'approximation')
                    self.omissions.append(dict(
                        source_chip='OPM', part='ABCDEFGH'[previous],
                        source_channel=previous, target_channel=target,
                        new_source_channel=ch,
                        action='truncate_possible_release',
                        reason='opm_dynamic_slot_reuse',
                        source_event_ids=[s.source_event_id],
                        source_start_vgmticks=s.vgmticks,
                        source_end_vgmticks=s.vgmticks,
                        detail='Key-Off is not proven silence; previous '
                               'release may be truncated by new owner'))
                    del self.channel_map[previous]
                self.owners[target] = ch
                self.channel_map[ch] = target
                self.record(s, 'acquire' if previous is None else 'reuse',
                            target, previous)
                restore = True
        self.keys[ch] = mask
        self.peak = max(self.peak, sum(bool(v) for v in self.keys.values()))
        if old and not mask:
            if ch in self.dropped:
                self.dropped[ch]['source_end_vgmticks'] = s.vgmticks
                self.record(s, 'omit_gate_end')
                del self.dropped[ch]
            else:
                self.record(s, 'key_off_release', self.channel_map.get(ch))
        return restore

    def finish(self):
        for row in self.dropped.values():
            row['source_end_vgmticks'] = self.end
        tail = self.snapshot()
        entry = self.entry if self.entry is not None else tail
        stable = self.loop_start is None or entry == tail
        if not stable and not self.force:
            raise ValueError('Dynamic FM ownership is not stable across '
                             'song loop; use --force or --no-song-loop')
        if not stable:
            self.omissions.append(dict(
                source_chip='OPM', part='FM', action='omit_song_loop',
                reason='opm_dynamic_loop_ownership_not_stable',
                source_start_vgmticks=self.loop_start,
                source_end_vgmticks=self.end,
                detail='Finite shared FM/PCM traversal retained; no '
                       'ownership reset or invented held attack'))
        return dict(rows=self.rows,
                    peak_ordered_source_keyed_voices=self.peak,
                    slot_count=6,
                    policy='ordered whole gates; retain six admitted '
                           'voices, omit new gate until full Key-Off',
                    same_sample_policy='preserve source order; transient '
                                       'conflicts explicitly diagnosed',
                    release_policy='retain released owner controls until '
                                   'reuse; reuse may truncate release',
                    loop=dict(start=self.loop_start, stable=stable,
                              entry=entry, tail=tail))


def _groups(analysis):
    """Source writes in order: one event list per source event id."""
    groups = {}
    for event in analysis.events:
        if event.source_event_id is not None:
            groups.setdefault(event.source_event_id, []).append(event)
    return [groups[key] for key in sorted(groups)]


def _representative(group):
    first = group[0]
    ch = register_channel(first.register, first.data)
    if ch is not None:
        for event in group:
            if event.ch == ch:
                return event
    return first


def project_opna(analysis, *, clock_raw, force=False,
                 target_clock=OPNA_CLOCK, loop_start=None):
    """Project the OPM FM stream onto OPNA FM (the makoto variant).

    Returns (rows, losses, allocation) where allocation is
    (report, omissions) under dynamic allocation, else
    (None, omissions). Rows are write_vgm rows in source order.
    """
    clock_hz = clock_raw & 0x3fffffff
    if not 0 < clock_hz < 0x40000000:
        raise ValueError('OPM>OPNA projection requires one positive-clock YM2151')
    if any(event.chip_instance for event in analysis.events):
        raise ValueError('dual-chip YM2151 (0xa4) sources are not '
                         'supported by the OPM variant route')
    if target_clock <= 0:
        raise ValueError('OPM>OPNA target clock must be positive')
    losses = Counter()
    rows, cache = [], {}

    active = sorted({event.ch for event in analysis.events
                     if event.state.key_mask})
    omissions = []
    allocator = None
    if len(active) > 6:
        if not force:
            raise ValueError(
                f'OPM source keys {len(active)} FM channels; the OPNA has '
                '6 (use --force for dynamic allocation with full voice '
                'restore)')
        allocator = _DynamicChannels(force=force, omissions=omissions,
                                     end=analysis.source_end_vgmticks,
                                     loop_start=loop_start)
        channel_map = allocator.channel_map
    else:
        channel_map = {ch: index for index, ch in enumerate(active)}
    releases = {}
    for event in analysis.events:
        if event.register == 8 and event.falling_mask:
            releases.setdefault(event.vgmticks, set()).add(event.ch)

    selections = {}       # source ch -> (pms_step, ams_step) last selected
    pm_saturated = {}     # source ch -> bool, for transition counting
    am_saturated = {}
    noise = {'enabled': False, 'nfreq': None}

    def inactive_write():
        # Fixed allocation only: a channel that never keys is not
        # in the map, and its writes are inaudible on the source
        # too. Under dynamic allocation an unmapped channel is the
        # normal pre-acquisition state instead: the voice restore
        # at gate acquisition re-emits its current state, and
        # omitted gates are recorded by the allocator itself.
        if allocator is None:
            losses['opm_inactive_channel_writes_ignored'] += 1

    def emit(s, command, register, data, reason, *, force_emit=False,
             frequency=None, actual=None):
        # Key and pitch-commit writes are never suppressed (the
        # mucom88 emit rule); everything else dedups per
        # (command, register).
        if not force_emit and register != 0x28 \
                and not 0xa0 <= register <= 0xa6 \
                and cache.get((command, register)) == data:
            return
        cache[(command, register)] = data
        rows.append(dict(
            write_id=len(rows), state_origin='projected_opna',
            source_chip='opm',
            source_event_id=s.source_event_id if s else None,
            source_segment_id=None,
            original_event_id=s.original_event_id if s else None,
            loop_iteration=s.loop_iteration if s else 0,
            source_vgmticks=s.vgmticks if s else 0,
            source_ch=s.ch if s else None,
            source_register=s.register if s else None,
            source_data=s.data if s else None,
            target_command=command, target_register=register,
            target_data=data, reason=reason,
            source_frequency_hz=frequency, target_frequency_hz=actual,
            target_ch=None, source_row=None, inferred_key=False,
            synthetic_phase=None))

    def port_local(tch):
        return (0x56, tch) if tch < 3 else (0x57, tch - 3)

    def selection(state):
        pms, ams = state.pms or 0, state.ams or 0
        pm_cents = _OPM_PMS_FULL_CENTS[pms] * (state.pmd or 0) / 127
        am_db = _OPM_AMS_FULL_DB[ams] * (state.amd or 0) / 127
        return pm_cents, am_db, _opna_pms(pm_cents), _opna_ams(am_db)

    def emit_b4(s, tch, *, force_emit=False):
        state = s.state
        pm_cents, am_db, pms_step, ams_step = selection(state)
        for key, excess_key, saturated, excess in (
                ('opm_pm_depth_saturated', 'opm_pm_depth_saturation_cents',
                 pm_saturated, pm_cents - _OPNA_PMS_MODEL_CENTS[7]),
                ('opm_am_depth_saturated', 'opm_am_depth_saturation_db',
                 am_saturated, am_db - _OPNA_AMS_MODEL_DB[3])):
            now = excess > 0
            if now and not saturated.get(s.ch):
                losses[key] += 1
                losses[excess_key] += round(excess, 1)
            saturated[s.ch] = now
        selections[s.ch] = (pms_step, ams_step)
        command, local = port_local(tch)
        emit(s, command, 0xb4 + local,
             (state.left_enabled or 0) << 7 | (state.right_enabled or 0) << 6
             | ams_step << 4 | pms_step,
             'pan to LRS; PMS/AMS selected per channel (OPM>OPNA law)',
             force_emit=force_emit)

    def pitch(s, tch, *, force_emit=False):
        state = s.state
        kc = state.kc_raw
        if kc is None or KC_NOTES.get(kc & 15) is None:
            losses['opm_pitch_state_assumed'] += 1
            kc = 0
        frequency = _opm_frequency(kc, state.kf, clock_hz)
        block, fnum, actual = _opna_pitch(frequency, target_clock)
        if fnum > 1900 and selections.get(s.ch, (0, 0))[0]:
            # The OPNA 12-bit FNUM adder wraps at this depth: the
            # chip model explodes the intended depth (study M4).
            losses['opm_pm_fnum_wrap_risk'] += 1
        command, local = port_local(tch)
        emit(s, command, 0xa4 + local, block << 3 | fnum >> 8,
             'KC/KF to BLOCK/FNUM by absolute-Hz minimisation',
             force_emit=force_emit, frequency=frequency, actual=actual)
        emit(s, command, 0xa0 + local, fnum & 0xff,
             'FNUM low commit (latches the pitch)',
             force_emit=force_emit, frequency=frequency, actual=actual)

    def emit_operator(s, tch, bank, base, *, force_emit=False):
        state = s.state
        op = state.operators[bank]
        command, local = port_local(tch)
        offset = 4 * bank + local

        def rate(value, kind):
            mapped = _eg_map(value, kind=kind, prescaler=_PRESCALER,
                             source_clock=clock_hz)
            if mapped != value:
                losses['eg_rate_prescaler_adjustments'] += 1
            return mapped

        if base == 0x40 and op.dt1 is not None and op.mul is not None:
            emit(s, command, 0x30 + offset, op.dt1 << 4 | op.mul,
                 'DT1->DT, MUL identity', force_emit=force_emit)
        elif base == 0x60 and op.tl is not None:
            emit(s, command, 0x40 + offset, op.tl, 'TL identity',
                 force_emit=force_emit)
        elif base == 0x80 and op.ks is not None and op.ar is not None:
            emit(s, command, 0x50 + offset, op.ks << 6 | rate(op.ar, 'rate5'),
                 'KS identity; AR via the EG rate map', force_emit=force_emit)
        elif base == 0xa0 and op.am_enabled is not None and op.d1r is not None:
            emit(s, command, 0x60 + offset,
                 op.am_enabled << 7 | rate(op.d1r, 'rate5'),
                 'AM enable identity; D1R via the EG rate map',
                 force_emit=force_emit)
        elif base == 0xc0 and op.d2r is not None:
            if op.dt2:
                losses['opm_dt2_dropped'] += 1
            emit(s, command, 0x70 + offset, rate(op.d2r, 'rate5'),
                 'D2R via the EG rate map; DT2 dropped (recorded loss)',
                 force_emit=force_emit)
        elif base == 0xe0 and op.d1l is not None and op.rr is not None:
            emit(s, command, 0x80 + offset, op.d1l << 4 | rate(op.rr, 'rr'),
                 'D1L identity; RR via the EG rate map', force_emit=force_emit)

    def restore_owner(s):
        state, tch = s.state, channel_map[s.ch]
        complete = all(value is not None for value in (
            state.algorithm, state.feedback, state.left_enabled,
            state.right_enabled, state.kc_raw, state.kf_raw)) and all(
            value is not None for op in state.operators for value in (
                op.dt1, op.mul, op.tl, op.ks, op.ar, op.am_enabled,
                op.d1r, op.dt2, op.d2r, op.d1l, op.rr))
        if not complete:
            raise ValueError('Dynamic FM allocation needs a complete '
                             'observed source voice')
        command, local = port_local(tch)
        emit(s, command, 0xb0 + local,
             (state.feedback or 0) << 3 | (state.algorithm or 0),
             'dynamic allocation: voice restore (ALG/FB identity)',
             force_emit=True)
        emit_b4(s, tch, force_emit=True)
        for bank in range(4):
            emit(s, command, 0x90 + 4 * bank + local, 0,
                 'dynamic allocation: SSG-EG neutral', force_emit=True)
            for base in (0x40, 0x60, 0x80, 0xa0, 0xc0, 0xe0):
                emit_operator(s, tch, bank, base, force_emit=True)
        pitch(s, tch, force_emit=True)

    def project_noise(s):
        state = s.state
        enabled = state.noise_enabled == 1
        nfreq = state.noise_rate or 0
        if enabled:
            period = _SSG_NOISE_PERIOD[nfreq]
            emit(s, 0x56, 0x06, period,
                 'OPM NFREQ to SSG noise period (measured table)')
            emit(s, 0x56, 0x07, 0x1f,
                 'SSG mixer: tones off, noise on channel C only')
            emit(s, 0x56, 0x0a, 15,
                 'SSG noise volume fixed at 15 (loudness uncalibrated)')
            if not noise['enabled'] or noise['nfreq'] != nfreq:
                if nfreq >= 29:
                    losses['opm_noise_brightness_clamped'] += 1
                if not noise['enabled']:
                    losses['opm_noise_loudness_uncalibrated'] += 1
            noise.update(enabled=True, nfreq=nfreq)
        elif noise['enabled']:
            emit(s, 0x56, 0x0a, 0, 'OPM noise disabled: SSG channel C silent')
            noise.update(enabled=False, nfreq=None)

    emit(None, 0x56, 0x29, 0x80,
         'OPNA six-channel mode; prescaler 6 (identity EG context)')
    emit(None, 0x56, 0x27, 0x00, 'OPNA normal FM mode (no CH3 special/CSM)')

    for group in _groups(analysis):
        s = _representative(group)
        reg = s.register
        restore = False
        if allocator is not None:
            restore = allocator.before(
                group, same_sample_release=bool(
                    releases.get(s.vgmticks, set()) - {s.ch}))
        if reg == 8:
            tch = channel_map.get(s.ch)
            if tch is None:
                # Never-keyed channel, or a gate the dynamic
                # allocation omitted (dropped channels hold no slot).
                continue
            if restore:
                restore_owner(s)
            command, local = port_local(tch)
            emit(s, command, 0x28,
                 (s.state.key_mask or 0) << 4
                 | (local | (4 if tch >= 3 else 0)),
                 'operator key mask to OPNA key register')
        elif reg == 0x0f:
            project_noise(s)
        elif 0x20 <= reg <= 0x27:
            tch = channel_map.get(s.ch)
            if tch is None:
                inactive_write()
                continue
            command, local = port_local(tch)
            emit(s, command, 0xb0 + local,
                 (s.state.feedback or 0) << 3 | (s.state.algorithm or 0),
                 'FB/ALG identity')
            emit_b4(s, tch)
        elif 0x28 <= reg <= 0x37:
            tch = channel_map.get(s.ch)
            if tch is None:
                inactive_write()
                continue
            pitch(s, tch)
        elif 0x38 <= reg <= 0x3f:
            tch = channel_map.get(s.ch)
            if tch is None:
                inactive_write()
                continue
            emit_b4(s, tch)
        elif 0x40 <= reg <= 0xff:
            tch = channel_map.get(s.ch)
            if tch is None:
                inactive_write()
                continue
            emit_operator(s, tch, (reg & 0x1f) >> 3, reg & 0xe0)
        elif reg == 0x18:
            hz = _opm_lfo_hz(s.data, clock_hz)
            index, rate_hz, minimum_hz = _opna_lfo_rate(hz, target_clock)
            emit(s, 0x56, 0x22, 0x08 | index,
                 'LFO rate: log-nearest OPNA rate (LFO enabled)')
            if hz < minimum_hz:
                losses['opm_lfo_below_opna_range'] += 1
            elif abs(rate_hz / hz - 1) > 0.25:
                losses['opm_lfo_rate_approximated'] += 1
        elif reg == 0x19:
            # PMD/AMD are global latches: every mapped channel's
            # selection may move. The shared write's group carries
            # one post-write snapshot per channel, each already
            # reflecting the new latch, so re-derive each channel
            # from its own group member.
            for member in group:
                if member.ch in channel_map:
                    emit_b4(member, channel_map[member.ch])
        elif reg == 0x1b:
            if (s.state.lfo_waveform if s.state.lfo_waveform is not None
                    else s.data & 3) != 2:
                losses['opm_lfo_waveform_substituted'] += 1
        elif reg in (0x10, 0x11, 0x12, 0x14):
            losses['source_timer_controls_not_projected'] += 1
        elif s.ev_type == 'uninterpreted':
            losses['opm_uninterpreted_writes_not_projected'] += 1
        # Remaining shared controls (test register, LFO reset) have
        # no OPNA-side write in this law and no sounding content.

    if analysis.csm_observed:
        losses['opm_csm_not_projected'] = 1
    report = None
    if allocator is not None:
        report = allocator.finish()
        for omission in omissions:
            losses[f"allocation_{omission['reason']}"] += 1
    return rows, dict(losses), (report, omissions)


def project_passthrough(analysis, *, clock_raw, stamp_clock):
    """Re-emit the OPM stream at stamp_clock (sfg01/opm4mhz).

    Writes pass through verbatim, except pitch: when the stamp
    clock differs from the source clock, KC writes re-derive the
    (KC, KF) pair by absolute Hz from the post-write state (the
    companion KF write is part of the correction) and KF writes
    re-derive the fraction the same way, so pitch survives the
    reclocking. Returns (rows, stats).
    """
    clock_hz = clock_raw & 0x3fffffff
    if any(event.chip_instance for event in analysis.events):
        raise ValueError('dual-chip YM2151 (0xa4) sources are not '
                         'supported by the OPM variant route')
    rows = []
    reclocked = companions = 0

    def row(s, register, data, reason):
        rows.append(dict(
            write_id=len(rows), state_origin='passthrough_opm',
            source_chip='opm', source_event_id=s.source_event_id,
            source_segment_id=None, original_event_id=s.original_event_id,
            loop_iteration=s.loop_iteration, source_vgmticks=s.vgmticks,
            source_ch=s.ch, source_register=s.register, source_data=s.data,
            target_command=0x54, target_register=register, target_data=data,
            reason=reason, source_frequency_hz=None,
            target_frequency_hz=None, target_ch=None, source_row=None,
            inferred_key=False, synthetic_phase=None))

    for group in _groups(analysis):
        s = _representative(group)
        reg, data = s.register, s.data
        if stamp_clock != clock_hz and 0x28 <= reg <= 0x37:
            state = s.state
            frequency = None
            if state.kc_raw is not None \
                    and KC_NOTES.get(state.kc_raw & 15) is not None:
                frequency = _opm_frequency(state.kc_raw, state.kf, clock_hz)
            if frequency:
                kc, kf, _actual = opm_pitch(frequency, stamp_clock, clamp=True)
                if reg >= 0x30:
                    row(s, reg, kf, 'KF re-derived by absolute Hz for the '
                                    'stamp clock')
                    reclocked += kf != data
                else:
                    row(s, reg, kc, 'KC re-derived by absolute Hz for the '
                                    'stamp clock')
                    row(s, 0x30 + (reg & 7), kf,
                        'KF companion of the re-derived KC')
                    reclocked += kc != data
                    companions += 1
                continue
        row(s, reg, data, 'OPM write re-emitted verbatim')
    stats = dict(source_clock_hz=clock_hz, stamp_clock_hz=stamp_clock,
                 pitch_writes_reclocked=reclocked,
                 pitch_kf_companion_writes=companions)
    return rows, stats


def convert(source, outdir, *, force=False, layered=False, target='makoto',
            dac='opna', target_clock=OPNA_CLOCK):
    """Analyze one OPM VGM and emit its MSX cartridge variant VGM.

    Same contract as opn2_target_vgm.convert. ``target`` selects
    the main composition: 'makoto' (the OPNA projection),
    'sfg01' or 'opm4mhz' (passthrough re-emission at the two
    pseudo-OPM clocks). With ``layered`` the layer file carries
    the 3,579,545 Hz OPM stream plus the OPNA projection. The
    projection law's target clock is ``target_clock`` (the MSX
    cartridge's 8,000,000 Hz by default; write_vgm stamps the
    YM2608 header field from its own OPNA_CLOCK constant, the
    same value). ``dac`` must be 'opna': an OPM source has no
    DAC-class lane.
    """
    if dac != 'opna':
        raise ValueError('OPM sources have no DAC-class lane for the '
                         'Y8950 to carry')
    if target not in ('makoto', 'sfg01', 'opm4mhz'):
        raise ValueError(f'Unknown OPM target cartridge: {target!r}')
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    bundle = analyze_source(source, outdir, stem)
    if 'opm' not in bundle['active_chips']:
        raise ValueError('Input has no OPM (YM2151) writes')
    extra = [chip for chip in bundle['active_chips'] if chip != 'opm']
    if extra:
        raise ValueError('OPM variant route covers OPM-only sources in '
                         f'this stage; this source also uses {extra}')
    analysis = bundle['analyses']['opm']
    if analysis is None:
        raise ValueError(f"OPM analysis failed: {bundle['errors'].get('opm')}")
    clock_raw = bundle['header']['opm_clock_raw']
    loop = bundle['loop']
    loop_start = loop_event_id = None
    if loop.get('status') == 'valid':
        loop_start = loop['loop_start_samples']
        loop_event_id = next((event.source_event_id for event in bundle['events']
                              if event.address == loop.get('loop_address')), None)

    projection = passthrough = layer_passthrough = None
    losses, allocation, omissions = {}, None, []
    passthrough_stats = {}
    if target == 'makoto' or layered:
        projection, losses, (allocation, omissions) = project_opna(
            analysis, clock_raw=clock_raw, force=force,
            target_clock=target_clock, loop_start=loop_start)
    stamp = TARGET_CLOCK
    if target in ('sfg01', 'opm4mhz'):
        stamp = OPM4MHZ_CLOCK if target == 'opm4mhz' else TARGET_CLOCK
        passthrough, passthrough_stats = project_passthrough(
            analysis, clock_raw=clock_raw, stamp_clock=stamp)
    if layered:
        # The layered composition is defined at the cartridge's
        # standard clock, whatever the main target's stamp is.
        if target == 'sfg01':
            layer_passthrough = passthrough
        else:
            layer_passthrough, layer_stats = project_passthrough(
                analysis, clock_raw=clock_raw, stamp_clock=TARGET_CLOCK)
            if target == 'makoto':
                passthrough_stats = layer_stats

    main_rows = projection if target == 'makoto' else passthrough
    main_clock = target_clock if target == 'makoto' else stamp
    # Dump the evidence CSV before write_vgm annotates the rows
    # in place (the S2 lesson).
    writes_csv = outdir / f'{stem}.opm.writes.csv'
    with writes_csv.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(main_rows[0]))
        writer.writeheader()
        writer.writerows(main_rows)
    target_file = outdir / f'{stem}.target.vgm'
    write_vgm(main_rows, target_file, end=bundle['source_end_sample'],
              loop_start=loop_start, loop_event_id=loop_event_id,
              opm_clock=TARGET_CLOCK if target == 'makoto' else stamp)
    layer_target, layer_target_writes = None, 0
    if layered:
        layer_rows = sorted(layer_passthrough + projection,
                            key=lambda r: (r['source_vgmticks'],
                                           r.get('sort_rank', 1)))
        layer_target = outdir / f'{stem}.layer.target.vgm'
        write_vgm(layer_rows, layer_target, end=bundle['source_end_sample'],
                  loop_start=loop_start, loop_event_id=loop_event_id,
                  opm_clock=TARGET_CLOCK)
        layer_target_writes = len(layer_rows)
    summary = dict(
        source=str(source), source_sha256=bundle['source_sha256'],
        active_chips=list(bundle['active_chips']),
        opm_clock_hz=clock_raw & 0x3fffffff,
        target_cartridge=target,
        target_clock_hz=main_clock,
        target_vgm=target_file.name,
        target_writes=len(main_rows),
        opna_fm_writes=len(projection) if projection is not None else 0,
        opm_writes=len(passthrough) if passthrough is not None else (
            len(layer_passthrough) if layer_passthrough is not None else 0),
        passthrough=passthrough_stats,
        allocation=allocation,
        allocation_omissions=omissions,
        noise_loudness=('calibration-pending'
                        if losses.get('opm_noise_loudness_uncalibrated')
                        else None),
        layered=layered,
        layer_target_vgm=(layer_target.name if layer_target else None),
        layer_target_writes=layer_target_writes,
        losses=losses,
        loop=dict(status=loop.get('status'), start_sample=loop_start))
    (outdir / f'{stem}.opm_target.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary
