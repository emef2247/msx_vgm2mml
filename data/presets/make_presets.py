#!/usr/bin/env python3
"""Consolidate the established OPLL set into one header with a
per-target preset table per chip family.

Single source of truth: opll_presets.json (the established
set by emef2247), kept beside this script. Every derived table is generated from it through the
audited conversion laws, except the msxaudio target, whose preset
voices come from opl_derived.json, our own derivation fitted
against the conversion table observed in commercial MSX
dual-edition games (opl_commercial.json, kept as the calibration
reference; owner's policy, 2026-11-14: learn from the commercial
work, do not copy it - the derived values are an independent
realisation of the same renders). The opl3 target generated from
the derived set through 2026-11-14, but the derived set failed
its hardware audition that night (melody collapse on the real
YMF289 that the ymfm fits did not predict), and the owner
directed (2026-11-15) that opl3 be generated from the
established set by field identity - the level OPM / OPNA
already have - with per-voice OPL3 fitting as separate later
work. The commercial table remains the calibration reference,
and its rhythm template still feeds the native rhythm unit,
overlaid with the derived rhythm voices (the melody derivation
covered the melody voices only):

- OPL (from the established set; retained for the C header):
  field identity (the canonical 2OP frame is OPL-native);
  KSL values are re-framed (YM2413 frame 1<->2 swapped) so the
  physical key-scale rate is preserved; waveform flag -> WS 1.
- OPN / OPNA: the measured OPLL>OPNA law -- ALG 4 pair (M1->C1),
  other pair silenced; mod TL identity; MULTI via the pg ratio
  table ([0,1,..,10,10,12,12,15,15]); EG AR 2a+4 / D1R 2d+3 /
  D2R 2r+3 (percussive) / RR r+1, zero stays zero; KSR1 -> KS2;
  SL/FB identity; DT 0; LFO PMS 4 / AMS 2 (OPN-family steps).
  OPN and OPNA share the FM field law; the tables are emitted
  separately because the chips' clocks (and therefore sounding
  EG/LFO rates) differ and are corrected at projection time.
- OPM: the measured OPLL>OPM law -- same EG/MULTI/TL core (beta per
  TL verified equal), LFO PMS 2 / AMS 2 with the fixed bridge
  depths PMD 86 / AMD 16.

Carrier TL is a performance value (source VOL << 2); preset tables
carry 0 for the carrier and the modulator TL from the set.
Rhythm: the base table carries the OPLL entries; in addition the
OPM table below carries the five drum voices as preset codes
(measured candidates v1), with HH/TC also prepared as
hardware-noise variants.  Which variant sounds, and on which
channels, is a projection-time decision (the YM2151 noise source
lives on channel 8).  OPNA uses its internal rhythm instead.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROM = json.loads((HERE / 'opll_presets.json').read_text())
OUT = HERE / 'opll_presets_established.h'

MUL_MAP = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 12, 12, 15, 15]
NAMES = ['Violin', 'Guitar', 'Piano', 'Flute', 'Clarinet', 'Oboe', 'Trumpet',
         'Organ', 'Horn', 'Synthesizer', 'Harpsichord', 'Vibraphone',
         'SynthBass', 'AcoustBass', 'ElecGuitar']


def eg(op):
    ar = 0 if op['ar'] == 0 else min(31, 2 * op['ar'] + 4)
    d1r = 0 if op['dr'] == 0 else min(31, 2 * op['dr'] + 3)
    d2r = 0 if (op['egt'] or op['rr'] == 0) else min(31, 2 * op['rr'] + 3)
    rr = 0 if op['rr'] == 0 else min(15, op['rr'] + 1)
    return ar, d1r, d2r, rr


def ks(op):
    return 2 if op['ksr'] else 0


KSL_COMP = {0: 0, 1: 7, 2: 14, 3: 19}  # TL steps, A4 reference (see four_op)

# Per-voice output level trim for the OPM table, in carrier TL
# steps, added by projections on top of the performance carrier
# TL (source VOL << 2).  Measured 2026-11-14 on IKAOPLL /
# IKAOPM: single A4 notes at VOL 0 (OPLL) vs carrier TL 0
# (OPM), RMS over 50-350 ms, anchored to the median of the
# ws=0 voices (+23.97 dB renderer offset).  The ws=1 carrier
# voices render hot on OPM because the OPLL half-wave output
# carries less power than the sine-based projection at equal
# settings: Violin +5.2 dB, Organ +3.0, Harpsichord +3.3,
# Synthesizer +6.5 (also mod ws=1; confirmed in song balance:
# its share of the FMPAC02 mix was +4 to +6.5 dB high).
# Trumpet -0.8 dB.  Synthesizer measured +6.46 dB = 8.6 steps;
# auditions of FMPAC02 settled it at 7 (9: slightly too quiet,
# 8: still lacking pressure, 7: adopted, 2026-11-14).

# Vibraphone is excluded: its offset is
# window-dependent (-3.4 / -5.7 / -6.4 dB at 0.1 / 0.35 / 1 s),
# an EG decay-shape difference, not a level offset.
LEVEL_TRIM_TL_OPM = {'Violin': 7, 'Trumpet': -1, 'Organ': 4,
                     'Synthesizer': 7, 'Harpsichord': 4}

# OPNA (YM2608 @ 8 MHz, ymfm via opm_opna_study direct_render):
# the same 15-voice level measurement matched the OPM table
# within 0.1 dB for 13 of 15 voices (Harpsichord +3.39 vs +3.27;
# Vibraphone window-dependent as on OPM), so the same trim
# values apply.  Note direct_render writes 166666 Hz WAV.
LEVEL_TRIM_TL_OPNA = dict(LEVEL_TRIM_TL_OPM)

# OPNA fit against the OPM set, 2026-11-16 (adopted by the owner
# after audition): single-voice probes (C3/A4/C6) of the OPM table
# rendered with IKAOPM as the reference, the OPNA table rendered
# with ymfm, per-voice coordinate descent over modulator TL, FB,
# DT and PMS on harmonic distance.  Level and envelope already
# matched (offsets ~0.00 dB, envelope <= 0.7 dB), so the fit is
# timbre-only: the dominant move is PMS 4 -> 2 on the vibrato
# voices (the bridged LFO depth was too deep in this chain; the
# LFO-rate coupling is not separated).  Harmonic distance
# before -> after: SynthBass 5.73 -> 4.28, Horn 4.29 -> 3.68,
# Guitar 2.62 -> 1.99, Synthesizer 2.76 -> 2.02, Flute 2.29 ->
# 1.88.  Piano / Clarinet / Oboe / Harpsichord / AcoustBass took
# no move.  Vibraphone's carrier SL/D2R moves come from a separate
# envelope-weighted pass and stay provisional: its decay-shape
# difference is structural (see the LEVEL_TRIM note above), the
# pass only crept (envelope 9.53 -> 9.11).
OPNA_FIT = {
    'Violin': {'pms': 2},
    'Guitar': {'pms': 3, 'ops': {0: {'dt': 6}, 1: {'dt': 6}}},
    'Flute': {'pms': 2},
    'Trumpet': {'pms': 2},
    'Organ': {'ops': {0: {'dt': 5}}},
    'Horn': {'pms': 2},
    'Synthesizer': {'pms': 1},
    'Vibraphone': {'pms': 3, 'ops': {0: {'dt': 6},
                                     1: {'dt': 3, 'd2r': 9, 'sl': 4}}},
    'SynthBass': {'ops': {0: {'dt': 1}}},
    'ElecGuitar': {'pms': 2},
}


SILENT4 = (1, 127, 0, 31, 0, 0, 0, 15, 0, 0)


def slot4(op, tl, is_mod=False, perc_rr=None, ksl_comp=False):
    ar, d1r, d2r, rr = eg(op)
    if perc_rr is not None and not op['egt'] and not is_mod:
        rr = perc_rr
    if ksl_comp and is_mod:
        tl = min(127, tl + KSL_COMP[op['ksl']])
    return (MUL_MAP[op['multi']], tl, ks(op), ar, d1r, d2r,
            op['sl'], rr, 0, op['am'])


def four_op(voice, pms, ams, perc_rr=None, ksl_comp=False):
    """(fb, alg, pms, ams, [op x4]) in slot order M1, C1, M2, C2.

    PMS/AMS carry the bridged depth only when the voice actually
    uses vibrato / AM on some operator; otherwise 0 (the target
    chips gate AM per operator but PMS is channel-wide, so an
    ungated depth would add vibrato the source does not have).
    perc_rr, when given, replaces RR for the percussive (egt=0)
    CARRIER only: a YM2413 percussive carrier key-off is a fixed
    fast damp (~170 dB/s regardless of rr; measured 2026-11-13 on
    IKAOPLL), so the target RR is the register whose key-off rate
    matches the damp, not rr+1.  The modulator is excluded: an
    egt=0 modulator holds its level through key-off (sideband
    ratio unchanged over 1 s at rr 0 and 1; measured 2026-11-14
    on IKAOPLL), so it keeps the eg() law.  Carrier-only adopted
    2026-11-14: an A/B render of the FMPAC pack (both scopes)
    found no clear difference, and the measured behaviour is the
    tiebreaker.  YM2151: RR 8 (~219 dB/s).  YM2608: RR 8
    as well (grid measurement 2026-11-13: percussive voices that
    never reached -20 dB with rr+1 land at ~91 ms with RR 8;
    SynthBass lands fast at ~19 ms and stays a listening item).
    ksl_comp: YM2151/YM2608 have no per-operator KSL, but on YM2413 the
    modulator's KSL attenuates it (at A4: ksl 1/2/3 = 5.4/10.4/
    14.6 dB; measured 2026-11-13 on IKAOPLL, small-index sideband
    method).  When set, the modulator TL absorbs that attenuation
    at the A4 reference pitch (KSL_COMP steps of 0.75 dB); the
    pitch dependence (+-3 dB over A3..A5 for ksl 2) remains as a
    recorded approximation of the static table."""
    pms = pms if (voice['mod']['vib'] or voice['car']['vib']) else 0
    ams = ams if (voice['mod']['am'] or voice['car']['am']) else 0
    return (voice['fb'], 4, pms, ams,
            [slot4(voice['mod'], voice['mod']['tl'], True, perc_rr, ksl_comp),
             slot4(voice['car'], 0, False, perc_rr, ksl_comp),
             SILENT4, SILENT4])


# OPM rhythm preset codes.  Composition of the OPLL drum pairs
# follows the v1 candidates measured on IKAOPM against IKAOPLL
# references (2026-11-13): BD = bd pair; SD = hh.mod + sd.car;
# TC = tom.mod + tc.car; HH = hh.mod solo on the carrier;
# TOM = tom.mod solo on the carrier.  HH/TC also get a
# hardware-noise variant (owner decision 2026-11-13: prepare
# both; the projection chooses by channel availability, because
# the noise source occupies channel 8).  In a noise row the
# shaping operator sits on C2, whose output the noise generator
# replaces when reg 0x0F NE=1; its EG is the same law applied to
# the op that carries the FM variant's envelope (hh.mod / tc.car).
# NFRQ 29 matched both references' spectra on IKAOPM renders
# (centroids: ref HH 9397 Hz / TC 9820 Hz, NFRQ 29 -> 9402 Hz;
# one noise generator serves the whole chip, so both share it).
# The noise rows carry the same law EG as the FM variants.  Note
# the measured residual: at equal register values the noise
# path's envelope decays more slowly than an FM carrier's and
# with a different (accelerating) curve shape -- identical on
# IKAOPM and on the MAME YM2151 core, so it is chip behaviour,
# not a renderer quirk (2026-11-13).  Decay-time matching of
# the noise rows is an open calibration item; no rate
# compensation is applied until it is measured properly.
OPM_RHYTHM_NOISE_NFRQ = 29


def rhythm_opm():
    """[(name, four_op row, reg 0x0F value or 0)] for OPM drums."""
    d = ROM['drums']

    def pair(mod, car, fb):
        return four_op({'mod': mod, 'car': car, 'fb': fb}, 0, 0,
                       perc_rr=8, ksl_comp=True)

    def solo(op):
        return (0, 4, 0, 0,
                [SILENT4, slot4(op, 0, perc_rr=8, ksl_comp=True),
                 SILENT4, SILENT4])

    def noise(op):
        return (0, 4, 0, 0,
                [SILENT4, SILENT4, SILENT4,
                 slot4(op, 0, perc_rr=8, ksl_comp=True)])

    nf = 0x80 | OPM_RHYTHM_NOISE_NFRQ
    return [
        ('BD', pair(d['bd']['mod'], d['bd']['car'], d['bd']['fb']), 0),
        ('SD', pair(d['hh']['mod'], d['sd']['car'], d['hh']['fb']), 0),
        ('TOM', solo(d['tom']['mod']), 0),
        ('HH', solo(d['hh']['mod']), 0),
        ('TC', pair(d['tom']['mod'], d['tc']['car'], d['tom']['fb']), 0),
        ('HH (noise)', noise(d['hh']['mod']), nf),
        ('TC (noise)', noise(d['tc']['car']), nf),
    ]


def opl_voice(voice):
    def op(o, tl):
        ksl = {0: 0, 1: 2, 2: 1, 3: 3}[o['ksl']]  # re-frame to OPL
        return (o['am'], o['vib'], o['egt'], o['ksr'], o['multi'], ksl,
                tl, o['ar'], o['dr'], o['sl'], o['rr'], 1 if o['ws'] else 0)
    return (voice['fb'], [op(voice['mod'], voice['mod']['tl']),
                          op(voice['car'], 0xFF)])


def fmt_op4(v):
    fb, alg, pms, ams, ops = v
    flat = [fb, alg, pms, ams] + [x for op in ops for x in op]
    return '{ ' + ', '.join(str(x) for x in flat) + ' }'


def main():
    mel = [ROM['melodic'][str(i)] for i in range(1, 16)]
    lines = []
    lines.append('#ifndef OPLL_PRESETS_ESTABLISHED_H')
    lines.append('#define OPLL_PRESETS_ESTABLISHED_H')
    lines.append('')
    lines.append('/*')
    for ln in ROM['notice'].splitlines():
        lines.append(' * ' + ln if ln else ' *')
    lines.append(' *')
    lines.append(' * Contents: the base YM2413 set (register bytes), plus')
    lines.append(' * derived preset tables for OPL, OPN, OPNA and OPM,')
    lines.append(' * generated from the base set through the audited')
    lines.append(' * conversion laws (see make_presets.py). Carrier TL is')
    lines.append(' * a performance value (source VOL << 2); tables carry 0.')
    lines.append(' * OPLL_OPM_LEVEL_TRIM carries the measured per-voice')
    lines.append(' * output level correction (carrier TL steps) that')
    lines.append(' * projections add on top of the performance value.')
    lines.append(' * Rhythm voices are in the base table; the OPM rhythm')
    lines.append(' * table at the end carries the drum preset codes.')
    lines.append(' */')
    lines.append('')
    lines.append('/* Base set: YM2413 register bytes (regs 00..07), 15 melodic')
    lines.append(' * voices + 3 rhythm entries (BD, HH/SD, TOM/TC). */')
    lines.append('static const unsigned char OPLL_ESTABLISHED_BASE[18][8] = {')
    def pack(mod, car, fb, dc, dm):
        def op0(o):
            return ((o['am'] << 7) | (o['vib'] << 6) | (o['egt'] << 5)
                    | (o['ksr'] << 4) | o['multi'])
        return [op0(mod), op0(car), (mod['ksl'] << 6) | mod['tl'],
                (car['ksl'] << 6) | (dc << 4) | (dm << 3) | fb,
                (mod['ar'] << 4) | mod['dr'], (car['ar'] << 4) | car['dr'],
                (mod['sl'] << 4) | mod['rr'], (car['sl'] << 4) | car['rr']]

    base_names = ['Violin', 'Guitar', 'Piano', 'Flute', 'Clarinet',
                  'Oboe', 'Trumpet', 'Organ', 'Horn', 'Synthesizer',
                  'Harpsichord', 'Vibraphone', 'Synthsizer Bass',
                  'Acoustic Bass', 'Electric Guitar', 'R: Bass Drum',
                  'R: High-Hat(M)/Snare Drum(C)',
                  'R: Tom-tom(M)/Top Cymbal(C)']
    base_rows = []
    for i in range(1, 16):
        v = ROM['melodic'][str(i)]
        base_rows.append(pack(v['mod'], v['car'], v['fb'], v['dc'], v['dm']))
    drums = ROM['drums']
    base_rows.append(pack(drums['bd']['mod'], drums['bd']['car'],
                          drums['bd']['fb'], drums['bd']['dc'],
                          drums['bd']['dm']))
    base_rows.append(pack(drums['hh']['mod'], drums['sd']['car'],
                          drums['hh']['fb'], drums['hh']['dc'],
                          drums['hh']['dm']))
    base_rows.append(pack(drums['tom']['mod'], drums['tc']['car'],
                          drums['tom']['fb'], drums['tom']['dc'],
                          drums['tom']['dm']))
    for i, (name, vals) in enumerate(zip(base_names, base_rows)):
        lines.append('    {' + ', '.join(f'0x{v:02X}' for v in vals) +
                     f'}}, // {i + 1}: {name}')
    lines.append('};')
    lines.append('')
    lines.append('/* OPL version: { FB, { {AM,VIB,EGT,KSR,MULTI,KSL,TL,AR,DR,SL,RR,WS} x2 } }')
    lines.append(' * KSL re-framed to the OPL frame; carrier TL 0xFF = performance VOL. */')
    lines.append('static const unsigned char OPLL_PRESET_OPL[15][1 + 2 * 12] = {')
    for i, v in enumerate(mel):
        fb, ops = opl_voice(v)
        flat = [fb] + [x for op in ops for x in op]
        lines.append('    { ' + ', '.join(str(x) for x in flat) + f' }}, // {NAMES[i]}')
    lines.append('};')
    for chip, pms, ams, note in (
            ('OPN', 4, 2, 'YM2203: field law shared with OPNA; sounding EG/LFO '
                          'rates follow the 4 MHz clock, corrected at projection.'),
            ('OPNA', 4, 2, 'YM2608: law measured on this chip.'),
            ('OPM', 5, 2, 'YM2151: LFO bridge depths PMD 86 / AMD 16 are '
                          'chip-global constants of the projection. PMS 5 '
                          'measured on IKAOPM at +/-9 cents (the OPLL '
                          'vibrato depth class); PMS 2 renders ~0.')):
        lines.append('')
        lines.append(f'/* {chip} version: {{ FB, ALG, PMS, AMS, '
                     '{ {MUL,TL,KS,AR,D1R,D2R,D1L,RR,DT,AM} x4 (M1,C1,M2,C2) } }')
        lines.append(f' * {note} */')
        lines.append(f'static const unsigned char OPLL_PRESET_{chip}[15][4 + 4 * 10] = {{')
        for i, v in enumerate(mel):
            lines.append(f'    {fmt_op4(four_op(v, pms, ams, 8 if chip in ("OPM", "OPNA") else None, chip in ("OPM", "OPNA")))}, // {NAMES[i]}')
        lines.append('};')
    lines.append('')
    lines.append('')
    lines.append('/* Per-voice output level trim for OPM projections:')
    lines.append(' * carrier TL steps added to the performance carrier TL')
    lines.append(' * (source VOL << 2).  Measured 2026-11-14 on')
    lines.append(' * IKAOPLL / IKAOPM (see LEVEL_TRIM_TL_OPM in')
    lines.append(' * make_presets.py for method and per-voice values). */')
    lines.append('static const signed char OPLL_OPM_LEVEL_TRIM[15] = {')
    lines.append('    ' + ', '.join(str(LEVEL_TRIM_TL_OPM.get(n, 0)) for n in NAMES) + ' };')
    lines.append('static const signed char OPLL_OPNA_LEVEL_TRIM[15] = {')
    lines.append('    ' + ', '.join(str(LEVEL_TRIM_TL_OPNA.get(n, 0)) for n in NAMES) + ' };')
    lines.append('/* OPM rhythm: { FB, ALG, PMS, AMS, { op x4 } } preset codes')
    lines.append(' * for the five drum voices, plus HH/TC hardware-noise')
    lines.append(' * variants.  The companion table gives the reg 0x0F byte')
    lines.append(' * (NE | NFRQ) for noise rows and 0 for FM rows; a noise')
    lines.append(' * row sounds on channel 8 (its C2 slot), so the projection')
    lines.append(' * picks FM or noise per hit by channel availability. */')
    lines.append('static const unsigned char OPLL_PRESET_OPM_RHYTHM[7][4 + 4 * 10] = {')
    for name, row, _nf in rhythm_opm():
        lines.append(f'    {fmt_op4(row)}, // {name}')
    lines.append('};')
    lines.append('static const unsigned char OPLL_PRESET_OPM_RHYTHM_NOISE[7] = {')
    lines.append('    ' + ', '.join(f'0x{nf:02X}' if nf else '0'
                                     for _name, _row, nf in rhythm_opm()))
    lines.append('};')
    lines.append('')
    lines.append('#endif /* OPLL_PRESETS_ESTABLISHED_H */')
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('wrote', OUT, OUT.stat().st_size, 'bytes')
    write_target_jsons()


# Per-target preset JSONs for the vgm-variants OPLL projection
# (py/opll_fm_target.py).  Register-ready four-op rows from the
# same laws as the C header; the projector applies them and
# computes custom patches with a port of four_op().  LFO bridge:
# the OPLL vibrato rate measured through the OPM bridge is
# 5.76 Hz (LFRQ 0xCB at 3.579545 MHz, PMD 86 / AMD 16).
SYNTH_MOD_EG_OVERRIDE = {'d1r': 11, 'd2r': 4, 'sl': 6}


def _op_obj(op):
    keys = ('mul', 'tl', 'ks', 'ar', 'd1r', 'd2r', 'sl', 'rr', 'dt', 'am')
    return dict(zip(keys, op))


def _target_json(target, chip, clock, pms, ams, trims, rhythm):
    voices = []
    for i in range(1, 16):
        row = ROM['melodic'][str(i)]
        fb, alg, vp, va, ops = four_op(row, pms, ams, perc_rr=8,
                                       ksl_comp=True)
        voice = {'index': i, 'name': row['name'], 'fb': fb, 'alg': alg,
                 'pms': vp, 'ams': va,
                 'ops': [_op_obj(o) for o in ops],
                 'level_trim_tl': trims.get(row['name'], 0)}
        if row['name'] == 'Synthesizer':
            # Modulator brightness-sustain fit, 2026-11-14:
            # probe trajectory error 15.5 -> 4.1 (OPM) and
            # 12.75 -> 6.27 (OPNA) against IKAOPLL.  Adopted by
            # the owner's audition of the FMPAC02 countermeasure
            # render the same day (sound pressure restored).
            voice['mod_eg_override'] = dict(
                SYNTH_MOD_EG_OVERRIDE,
                status='adopted 2026-11-14 by owner audition (FMPAC02)')
        if target == 'makoto' and row['name'] in OPNA_FIT:
            fit = OPNA_FIT[row['name']]
            if 'pms' in fit:
                voice['pms'] = fit['pms']
            for oi, fields in fit.get('ops', {}).items():
                voice['ops'][oi].update(fields)
        voices.append(voice)
    doc = {'target': target, 'chip': chip, 'clock_hz': clock,
           'source': 'opll_presets.json via make_presets.py; do not hand-edit',
           'lfo': {'hz': 5.76, 'pms': pms, 'ams': ams},
           'voices': voices, 'rhythm': rhythm}
    if target == 'sfg01':
        doc['lfo'].update(pmd=86, amd=16, lfrq=0xCB)
    if target == 'makoto':
        doc['fit_note'] = ('Voices fitted 2026-11-16 against the OPM '
                           'table (IKAOPM reference renders, ymfm '
                           'candidates); see OPNA_FIT in '
                           'make_presets.py.')
    return doc


# OPL3 (YMF262): the same sine-projection cause as OPM - the
# OPL frame carries no waveform, so ws=1 carriers render as
# sine and come out hot by the same amounts (the ESE OPL3
# recordings of FMPAC02 show Organ about +5 dB and Synthesizer
# about +3 dB over the song's other voices, the same family).
# Initial values carried from the OPM set; the owner's audition
# may retune them per voice, as it did there (9 -> 8 -> 7).
LEVEL_TRIM_TL_OPL3 = dict(LEVEL_TRIM_TL_OPM)


def _established_opl_json(target, chip, clock):
    # OPL two-op rows straight from the established set
    # (opll_presets.json) by field identity - the same frame the
    # OPL section of the header above and the custom-patch
    # projection use: KSL re-framed ({0:0, 1:2, 2:1, 3:3}) so the
    # physical key-scale rate is preserved, modulator TL from
    # the set, carrier TL a performance value (source VOL << 2)
    # carried as 0.  Adopted for the opl3 target by the owner
    # (2026-11-15): the derived set failed its hardware audition
    # (melody collapse the ymfm fits did not predict), so opl3
    # first reaches the level the established set already has on
    # OPM / OPNA; per-voice fitting for OPL3 is separate later
    # work.  msxaudio keeps the derived table for now.
    def op(o):
        return {'am': o['am'], 'vib': o['vib'], 'egt': o['egt'],
                'ksr': o['ksr'], 'mul': o['multi'],
                'ksl': {0: 0, 1: 2, 2: 1, 3: 3}[o['ksl']],
                'tl': o['tl'] or 0,
                'ar': o['ar'], 'dr': o['dr'], 'sl': o['sl'],
                'rr': o['rr']}
    voices = []
    for i in range(1, 16):
        row = ROM['melodic'][str(i)]
        voices.append({'index': i, 'name': row['name'],
                       'fb': row['fb'],
                       'ops': [op(row['mod']), op(row['car'])],
                       'level_trim_tl':
                           LEVEL_TRIM_TL_OPL3.get(row['name'], 0)})
    return {'target': target, 'chip': chip, 'clock_hz': clock,
            'source': 'opll_presets.json via make_presets.py; '
                      'do not hand-edit',
            'law': 'field identity from the established set '
                   '(KSL re-framed); carrier TL = 4 * VOL',
            'voices': voices,
            'rhythm': {'kind': 'opl_native',
                       'note': 'OPLL percussion projects to the target '
                               'native rhythm unit with the composed '
                               'voice template (derived voices over the '
                               'commercial one; musical_opl_target / '
                               'musical_opl3_target); no FM rows.'}}


# OPL3 fitted set: the established frame plus a per-voice fit.
# First fitted 2026-11-16 against the OPM table (IKAOPM reference
# renders, AdLibEmu candidate search over the OPL frame plus
# waveform select, an axis OPM does not have), with the waveform
# select re-measured on the real chip 2026-11-20.  Re-fitted the
# same day against a real YM2413 recording of the 15-voice probe
# set (Nuked candidate renders, coordinate descent on the same
# axes plus the level trims re-anchored to the recording's
# per-voice balance): mean envelope+harmonic distance to the
# real chip 14.48 -> 10.51.  Adopted as the standard opl3 table
# by the owner 2026-11-20 after the listening comparison (the
# established-frame table it replaces is not kept).
OPL3_FIT = {
    'Violin': {'level_trim_tl': 9, 'ops': {0: {'vib': 0, 'tl': 26, 'rr': 1, 'ws': 0}, 1: {'sl': 0, 'ws': 0}}},
    'Guitar': {'ops': {0: {'ksl': 1, 'tl': 27, 'dr': 7, 'ws': 1}, 1: {'ws': 3}}},
    'Piano': {'ops': {0: {'egt': 1, 'ksl': 0, 'ws': 1}, 1: {'ws': 3}}},
    'Flute': {'fb': 6, 'level_trim_tl': 5, 'ops': {0: {'am': 1, 'ws': 4}, 1: {'ar': 7, 'ws': 2}}},
    'Clarinet': {'level_trim_tl': -2, 'ops': {0: {'vib': 1, 'tl': 29, 'ws': 2}, 1: {'rr': 9, 'ws': 3}}},
    'Oboe': {'level_trim_tl': -4, 'ops': {0: {'ws': 3}, 1: {'ar': 8, 'ws': 4}}},
    'Trumpet': {'level_trim_tl': 3, 'ops': {0: {'dr': 1, 'ws': 6}, 1: {'vib': 0, 'ws': 3}}},
    'Organ': {'level_trim_tl': 3, 'ops': {0: {'ws': 5}, 1: {'ksl': 1, 'ws': 2}}},
    'Horn': {'level_trim_tl': 7, 'ops': {0: {'vib': 0, 'tl': 26, 'ar': 4, 'ws': 6}, 1: {'ar': 8, 'ws': 0}}},
    'Synthesizer': {'level_trim_tl': 6, 'ops': {0: {'am': 1, 'vib': 0, 'tl': 13, 'sl': 9, 'ws': 2}, 1: {'ws': 3}}},
    'Harpsichord': {'ops': {0: {'sl': 0, 'ws': 2}, 1: {'am': 1, 'vib': 1, 'ws': 1}}},
    'Vibraphone': {'level_trim_tl': 4, 'ops': {0: {'ksl': 1, 'ws': 5}, 1: {'ws': 2}}},
    'SynthBass': {'level_trim_tl': 6, 'ops': {0: {'am': 1, 'rr': 2, 'ws': 3}, 1: {'dr': 6, 'rr': 3, 'ws': 6}}},
    'AcoustBass': {'level_trim_tl': 2, 'ops': {0: {'tl': 15, 'ws': 3}, 1: {'ws': 4}}},
    'ElecGuitar': {'fb': 0, 'level_trim_tl': 7, 'ops': {0: {'vib': 0, 'ws': 6}, 1: {'ws': 6}}},
}


def _fitted_opl3_json():
    import copy
    doc = _established_opl_json('opl3', 'ymf262', 14318180)
    doc['law'] = ('established frame plus the OPL3_FIT per-voice '
                  'fit (real-YM2413-recording search; see '
                  'OPL3_FIT in make_presets.py)')
    doc['fit_note'] = ('Voices fitted 2026-11-16 against the OPM '
                       'table (IKAOPM reference renders, '
                       'AdLibEmu candidates), waveform select '
                       're-measured on the real chip 2026-11-20, '
                       'then re-fitted 2026-11-20 against a real '
                       'YM2413 recording of the probe set (Nuked '
                       'candidates; mean distance 14.48 -> 10.51); '
                       'see OPL3_FIT in make_presets.py.  Adopted '
                       'as the standard opl3 table by the owner '
                       '2026-11-20.')
    for voice in doc['voices']:
        fit = OPL3_FIT[voice['name']]
        if 'fb' in fit:
            voice['fb'] = fit['fb']
        if 'level_trim_tl' in fit:
            voice['level_trim_tl'] = fit['level_trim_tl']
        for oi, fields in fit.get('ops', {}).items():
            voice['ops'][oi].update(fields)
    return doc

def _derived_opl_json(target, chip, clock):
    # OPL two-op rows from our own derived preset set
    # (opl_derived.json): fitted from the established set's
    # identity frame against renders of the commercially observed
    # reference voices (opl_commercial.json), NOT copied from
    # them - per voice 6-13 of 23 fields differ from the reference
    # values.  Y8950 and YMF262 share the two-op register frame,
    # so one source feeds both targets.  Carrier TL is a
    # performance value (source VOL << 2); the source carries 0.
    doc = json.loads((HERE / 'opl_derived.json').read_text())
    voices = [{'index': v['index'], 'name': v['name'], 'fb': v['fb'],
               'ops': v['ops']} for v in doc['voices']]
    return {'target': target, 'chip': chip, 'clock_hz': clock,
            'source': 'opl_derived.json via make_presets.py; do not hand-edit',
            'law': doc['law'],
            'voices': voices,
            'rhythm': {'kind': 'opl_native',
                       'note': 'OPLL percussion projects to the target '
                               'native rhythm unit with the commercially '
                               'observed voice template '
                               '(musical_opl_target / musical_opl3_target); '
                               'no FM rows.'}}


def write_target_jsons():
    import json as _json
    opm_rhythm = [{'name': name, 'fb': row[0], 'alg': row[1],
                   'ops': [_op_obj(o) for o in row[4]],
                   'noise_reg': nf}
                  for name, row, nf in rhythm_opm()]
    docs = {
        'msxaudio/opll_to_y8950.json': _derived_opl_json(
            'msxaudio', 'y8950', 3579545),
        'opl3/opll_to_opl3.json': _fitted_opl3_json(),
        'sfg01/opll_to_opm.json': _target_json(
            'sfg01', 'ym2151', 3579545, 5, 2, LEVEL_TRIM_TL_OPM,
            {'kind': 'fm_rows', 'rows': opm_rhythm}),
        'makoto/opll_to_opna.json': _target_json(
            'makoto', 'ym2608', 8000000, 4, 2, LEVEL_TRIM_TL_OPNA,
            {'kind': 'opna_native',
             'note': 'OPLL percussion projects to the OPNA native '
                     'rhythm unit (project_rhythm); no FM rows.'}),
    }
    for rel, doc in docs.items():
        path = HERE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        print('wrote', path, path.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
