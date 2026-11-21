"""OPLL (YM2413) melody units projected to cartridge FM chips.

The conversion law is a provenance port of data/presets/
make_presets.py (measured on IKAOPLL / IKAOPM / ymfm, 2026-11-13
..14); preset rows are read from the generated per-target JSONs
in data/presets/<target>/ and are never hand-edited.  Custom
patches are converted with the same law at projection time.
Carrier TL is the performance value (source VOL << 2) plus the
per-voice measured level trim from the JSON.  OPLL percussion
is not handled here: project_rhythm routes it to the native
OPLL rhythm unit or the OPNA native rhythm unit.
"""
from collections import Counter
import json
import math
from pathlib import Path

from musical_fm_target import _at
from opm_target_vgm import _opna_pitch, _opna_lfo_rate
from psg_scc_opm import opm_pitch

_PRESET_DIR = Path(__file__).resolve().parent.parent / 'data' / 'presets'
_TARGET_FILES = {'opm': ('sfg01', 'opll_to_opm.json'),
                 'opna': ('makoto', 'opll_to_opna.json')}
# Level-anchor variant: identical voices, level trims anchored to
# the owner's real YM2413 recording through the SoundCore SLOT EXG
# instead of the IKAOPLL render (see make_presets.py).
_SOUNDCORE_FILES = {'opm': ('sfg01', 'opll_to_opm_soundcore.json'),
                    'opna': ('makoto', 'opll_to_opna_soundcore.json')}
_cache = {}

MUL_MAP = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 12, 12, 15, 15]
KSL_COMP = {0: 0, 1: 7, 2: 14, 3: 19}  # TL steps, A4 reference
SILENT4 = (1, 127, 0, 31, 0, 0, 0, 15, 0, 0)
# Logical slot order is M1, C1, M2, C2.  Register address order
# differs per chip family (OPM: M1, M2, C1, C2; OPN: op1, op3,
# op2, op4 with the pair on op1 -> op2).
_OPM_SLOTS = (0, 2, 1, 3)
_OPNA_OFFSETS = (0, 8, 4, 12)
_OP_FIELDS = ('mul', 'tl', 'ks', 'ar', 'd1r', 'd2r', 'sl', 'rr', 'dt', 'am')


def _eg(op):
    ar = 0 if op['ar'] == 0 else min(31, 2 * op['ar'] + 4)
    d1r = 0 if op['dr'] == 0 else min(31, 2 * op['dr'] + 3)
    d2r = 0 if (op['egt'] or op['rr'] == 0) else min(31, 2 * op['rr'] + 3)
    rr = 0 if op['rr'] == 0 else min(15, op['rr'] + 1)
    return ar, d1r, d2r, rr


def _slot4(op, tl, is_mod=False, perc_rr=None, ksl_comp=False):
    ar, d1r, d2r, rr = _eg(op)
    if perc_rr is not None and not op['egt'] and not is_mod:
        rr = perc_rr
    if ksl_comp and is_mod:
        tl = min(127, tl + KSL_COMP[op['ksl']])
    return (MUL_MAP[op['multi']], tl, 2 if op['ksr'] else 0, ar, d1r, d2r,
            op['sl'], rr, 0, op['am'])


def _four_op(voice, pms, ams):
    """(fb, alg, pms, ams, [op x4]) in slot order M1, C1, M2, C2.

    perc_rr=8 replaces RR for the percussive (egt=0) carrier only;
    ksl_comp folds the modulator's A4-referenced KSL attenuation
    into its TL.  See make_presets.py for the measured basis.
    """
    pms = pms if (voice['mod']['vib'] or voice['car']['vib']) else 0
    ams = ams if (voice['mod']['am'] or voice['car']['am']) else 0
    return (voice['fb'], 4, pms, ams,
            [_slot4(voice['mod'], voice['mod']['tl'], True, 8, True),
             _slot4(voice['car'], 0, False, 8, True),
             SILENT4, SILENT4])


def _decode_patch(p):
    """OPLL patch bytes 0x00..0x07 -> voice dict (JSON schema)."""
    def op(b0, ksl, tl, ad, sr):
        return {'am': (b0 >> 7) & 1, 'vib': (b0 >> 6) & 1,
                'egt': (b0 >> 5) & 1, 'ksr': (b0 >> 4) & 1,
                'multi': b0 & 15, 'ksl': ksl, 'tl': tl,
                'ar': ad >> 4, 'dr': ad & 15, 'sl': sr >> 4, 'rr': sr & 15,
                'ws': 0}
    mod = op(p[0], p[2] >> 6, p[2] & 63, p[4], p[6])
    mod['ws'] = (p[3] >> 3) & 1
    car = op(p[1], p[3] >> 6, None, p[5], p[7])
    car['ws'] = (p[3] >> 4) & 1
    return {'fb': p[3] & 7, 'mod': mod, 'car': car}


def _table(target_chip, soundcore=False):
    key = (target_chip, soundcore)
    if key not in _cache:
        files = _SOUNDCORE_FILES if soundcore else _TARGET_FILES
        folder, name = files[target_chip]
        doc = json.loads((_PRESET_DIR / folder / name).read_text())
        voices = {v['index']: v for v in doc['voices']}
        _cache[key] = (doc, voices)
    return _cache[key]


def project_opll_fm(performance, target_chip, target_clock, reserved=(), *,
                    force=False, soundcore_levels=False):
    """Project OPLL melody units to OPM/OPNA FM writes.

    Returns (rows, losses, allocation).  Only the first OPLL
    device is projected (the native lane's rule); its melody
    units are consumed here and the caller suppresses the
    native OPLL melody lane for that device.
    """
    if target_chip not in _TARGET_FILES:
        raise ValueError('OPLL FM projection targets OPM or OPNA')
    doc, voices = _table(target_chip, soundcore_levels)
    devices = {d.device_id: d for d in performance.devices}
    voice_by_id = {v.voice_id: v for v in performance.voices}
    opll_devices = [d for d in performance.devices if d.chip == 'opll']
    rows, losses = [], Counter()
    if not opll_devices:
        return rows, losses, {}
    device = opll_devices[0]
    if len(opll_devices) > 1:
        losses['second_opll_device_melody_not_fm_projected'] += 1
    units = [u for u in performance.units
             if u.device_id == device.device_id and u.section == 'fm']
    capacity = 8 if target_chip == 'opm' else 6
    allocation = {}
    for lane in sorted({(u.device_id, u.channel) for u in units}):
        free = [ch for ch in range(capacity)
                if ch not in allocation.values() and ch not in reserved]
        if free:
            allocation[lane] = lane[1] if lane[1] in free else free[0]
    if len(allocation) < len({(u.device_id, u.channel) for u in units}) and not force:
        raise ValueError('OPLL FM target capacity exceeded; force permits explicitly reported lane omission')

    def emit(unit, sample, order, register, value, reason, port=0):
        opcode = 0x54 if target_chip == 'opm' else 0x56 + port
        rows.append(dict(sample=sample, order=order,
                         command=bytes((opcode, register, value & 255)),
                         unit_id=unit.unit_id if unit else '',
                         device_id=device.device_id,
                         source_indices=unit.source_indices if unit else (),
                         reason=reason))

    resolved = {}

    def resolve(voice_id):
        if voice_id in resolved:
            return resolved[voice_id]
        voice = voice_by_id.get(voice_id)
        p = dict(voice.parameters) if voice else {}
        inst = p.get('instrument')
        lfo = doc['lfo']
        result = None
        if inst and inst in voices:
            entry = voices[inst]
            ops = [tuple(o[f] for f in _OP_FIELDS) for o in entry['ops']]
            override = entry.get('mod_eg_override')
            if override:
                m = list(ops[0])
                m[4], m[5], m[6] = (override['d1r'], override['d2r'],
                                    override['sl'])
                ops[0] = tuple(m)
            pms, ams = entry['pms'], entry['ams']
            result = (entry['fb'], entry['alg'], pms, ams, ops,
                      entry.get('level_trim_tl', 0))
        elif inst == 0:
            patch = p.get('custom_patch') or ()
            if any(b is None for b in patch):
                losses['opll_custom_patch_bytes_unobserved'] += 1
            patch = tuple(0 if b is None else b for b in patch)
            patch = patch + (0,) * (8 - len(patch))
            fb, alg, pms, ams, ops = _four_op(_decode_patch(patch),
                                              lfo['pms'], lfo['ams'])
            result = (fb, alg, pms, ams, ops, 0)
        resolved[voice_id] = result
        return result

    lfo_needed = False
    for unit in units:
        lane = (unit.device_id, unit.channel)
        if lane not in allocation:
            losses['opll_fm_units_omitted_capacity'] += 1
            continue
        pitch_values = [_at(unit.pitch_curve, unit.start_sample),
                        *(hz for at, hz in unit.pitch_curve
                          if unit.start_sample <= at < unit.end_sample)]
        if any(hz is None or not math.isfinite(hz) or hz <= 0
               for hz in pitch_values):
            losses['opll_unknown_pitch_units_muted'] += 1
            continue
        ch = allocation[lane]
        port, local = (0, ch) if target_chip == 'opm' else divmod(ch, 3)

        def emit_voice(sample, order, row, level):
            fb, alg, pms, ams, ops, trim = row
            if target_chip == 'opm':
                emit(unit, sample, order, 0x20 + ch,
                     0xC0 | (fb << 3) | alg, 'OPLL voice algorithm/feedback')
                emit(unit, sample, order, 0x38 + ch, (pms << 4) | ams,
                     'OPLL voice modulation sensitivity')
            else:
                emit(unit, sample, order, 0xB0 + local,
                     (fb << 3) | alg, 'OPLL voice algorithm/feedback', port)
                emit(unit, sample, order, 0xB4 + local,
                     0xC0 | (ams << 4) | pms,
                     'OPLL voice pan/modulation', port)
            for logical, op in enumerate(ops):
                mul, tl, ks, ar, d1r, d2r, sl, rr, dt, am = op
                if logical == 1:
                    tl = max(0, min(127, (level << 2) + trim))
                if target_chip == 'opm':
                    off = _OPM_SLOTS[logical] * 8 + ch
                    for base, value in ((0x40, (dt << 4) | mul), (0x60, tl),
                                        (0x80, (ks << 6) | ar),
                                        (0xA0, (am << 7) | d1r), (0xC0, d2r),
                                        (0xE0, (sl << 4) | rr)):
                        emit(unit, sample, order, base + off, value,
                             'OPLL voice operator', port)
                else:
                    off = _OPNA_OFFSETS[logical] + local
                    for base, value in ((0x30, (dt << 4) | mul), (0x40, tl),
                                        (0x50, (ks << 6) | ar),
                                        (0x60, (am << 7) | d1r), (0x70, d2r),
                                        (0x80, (sl << 4) | rr), (0x90, 0)):
                        emit(unit, sample, order, base + off, value,
                             'OPLL voice operator', port)

        def emit_carrier_tl(sample, order, row, level):
            trim = row[5]
            tl = max(0, min(127, (level << 2) + trim))
            if target_chip == 'opm':
                emit(unit, sample, order, 0x60 + _OPM_SLOTS[1] * 8 + ch, tl,
                     'OPLL carrier level')
            else:
                emit(unit, sample, order, 0x40 + _OPNA_OFFSETS[1] + local, tl,
                     'OPLL carrier level', port)

        def emit_pitch(sample, order, hz):
            if target_chip == 'opm':
                kc, kf, _actual = opm_pitch(hz, target_clock, clamp=True)
                emit(unit, sample, order, 0x28 + ch, kc, 'OPLL Hz to KC')
                emit(unit, sample, order, 0x30 + ch, kf, 'OPLL Hz to KF')
            else:
                block, fnum, _actual = _opna_pitch(hz, target_clock)
                emit(unit, sample, order, 0xA4 + local,
                     (block << 3) | (fnum >> 8), 'OPLL Hz atomic FNUM high',
                     port)
                emit(unit, sample, order, 0xA0 + local, fnum & 255,
                     'OPLL Hz atomic FNUM commit', port)

        def key(sample, order, on):
            if target_chip == 'opm':
                emit(unit, sample, order, 8, ((15 if on else 0) << 3) | ch,
                     'OPLL gate on' if on else 'OPLL gate end')
            else:
                emit(unit, sample, order, 0x28,
                     ((15 if on else 0) << 4) | (ch % 3) | ((ch // 3) << 2),
                     'OPLL gate on' if on else 'OPLL gate end')

        times = sorted({unit.start_sample,
                        *(at for curve in (unit.pitch_curve, unit.volume_curve,
                                           unit.voice_curve)
                          for at, _ in curve
                          if unit.start_sample <= at < unit.end_sample)})
        previous = (object(), object(), object())
        for sample in times:
            voice_id = _at(unit.voice_curve, sample)
            row = resolve(voice_id)
            if row is None:
                losses['opll_fm_missing_voice'] += 1
                continue
            level = _at(unit.volume_curve, sample, 15)
            level = 15 if level is None else max(0, min(15, int(level)))
            hz = _at(unit.pitch_curve, sample)
            state = (voice_id, row[2], row[3])
            if state != previous[0]:
                emit_voice(sample, -0.5, row, level)
                if row[2] or row[3]:
                    lfo_needed = True
            elif level != previous[1]:
                emit_carrier_tl(sample, -0.5, row, level)
            if hz != previous[2]:
                emit_pitch(sample, -0.5, hz)
            previous = (state, level, hz)
        key(unit.start_sample, 0, True)
        held_loop = (performance.song_loop_sample is not None
                     and unit.end_sample == performance.end_sample
                     and dict(unit.parameters).get('termination')
                     == 'source_observation_end')
        if not held_loop:
            key(unit.end_sample,
                -1 if unit.end_sample > unit.start_sample else 1, False)
    if lfo_needed:
        lfo = doc['lfo']
        if target_chip == 'opm':
            for reg, value in ((0x18, lfo['lfrq']), (0x19, lfo['pmd']),
                               (0x19, 0x80 | lfo['amd']), (0x1B, 0x02)):
                rows.append(dict(sample=0, order=-3,
                                 command=bytes((0x54, reg, value)),
                                 unit_id='', device_id=device.device_id,
                                 source_indices=(),
                                 reason='OPLL LFO bridge setup'))
        else:
            losses['opll_opna_lfo_depth_approximation'] += 1
            rate = _opna_lfo_rate(lfo["hz"], target_clock)[0]
            for reg, value in ((0x22, 0x08 | rate),
                               (0x24, 86), (0x25, 16)):
                rows.append(dict(sample=0, order=-3,
                                 command=bytes((0x56, reg, value)),
                                 unit_id='', device_id=device.device_id,
                                 source_indices=(),
                                 reason='OPLL LFO bridge setup'))
    return rows, losses, allocation
