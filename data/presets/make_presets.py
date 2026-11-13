#!/usr/bin/env python3
"""Consolidate the established OPLL set into one header with a
per-target preset table per chip family.

Single source of truth: opll_presets.json (the established
set by emef2247), kept beside this script. Every derived table is generated from it through the
audited conversion laws:

- OPL: field identity (the canonical 2OP frame is OPL-native);
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


SILENT4 = (1, 127, 0, 31, 0, 0, 0, 15, 0, 0)


def slot4(op, tl, is_mod=False, perc_rr=None, ksl_comp=False):
    ar, d1r, d2r, rr = eg(op)
    if perc_rr is not None and not op['egt']:
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
    perc_rr, when given, replaces RR for percussive (egt=0)
    operators: a YM2413 percussive key-off is a fixed fast damp
    (~170 dB/s regardless of rr; measured 2026-11-13 on IKAOPLL),
    so the target RR is the register whose key-off rate matches
    the damp, not rr+1.  YM2151: RR 8 (~219 dB/s).  YM2608: RR 8
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
            ('OPM', 2, 2, 'YM2151: LFO bridge depths PMD 86 / AMD 16 are '
                          'chip-global constants of the projection.')):
        lines.append('')
        lines.append(f'/* {chip} version: {{ FB, ALG, PMS, AMS, '
                     '{ {MUL,TL,KS,AR,D1R,D2R,D1L,RR,DT,AM} x4 (M1,C1,M2,C2) } }')
        lines.append(f' * {note} */')
        lines.append(f'static const unsigned char OPLL_PRESET_{chip}[15][4 + 4 * 10] = {{')
        for i, v in enumerate(mel):
            lines.append(f'    {fmt_op4(four_op(v, pms, ams, 8 if chip in ("OPM", "OPNA") else None, chip in ("OPM", "OPNA")))}, // {NAMES[i]}')
        lines.append('};')
    lines.append('')
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


if __name__ == '__main__':
    main()
