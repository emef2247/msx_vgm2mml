#!/usr/bin/env python3
"""
vgm2mml_grid.py - Top-level CLI: VGM binary → MGSDRV MML text (OPLL)
"""

import sys
import os
import math
import argparse
from collections import defaultdict

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, 'py'))

from vgm_reader import parse_vgm
from mml_utils import track_id_to_mgsdrv, estimate_mml_used, estimate_alloc, compress_mml_text
from opll import NUM_CH, _assign_voice_ids, _build_segments, _user_patch_mml_defs

_FREQ_NTSC: float = 59.988527908187
_FREQ_PAL: float = 50.214039335288

STEPS_PER_PATTERN = 16
DEFAULT_RHYTHM_NOTE = 36

_SCALE_NAMES = ['c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b']
_STEP_TABLE: list[tuple[int, str]] = [
    (16, '1'), (12, '2.'), (8, '2'), (6, '4.'),
    (4, '4'), (3, '8.'), (2, '8'), (1, '16'),
]
_MML_MELODY_CHANNELS = (0, 1, 2, 3, 4, 5)
_MML_RHYTHM_CHANNELS = (9, 10, 11, 12, 13)
_RHYTHM_NOTE_SYMBOLS = {9: 'b', 10: 's', 11: 'm', 12: 'c', 13: 'h'}


def fnum_block_to_ms2_note(fnum: int, block: int) -> int | None:
    if fnum == 0:
        return None
    freq = 49716.0 * fnum * (1 << block) / (1 << 19)
    if freq < 8.0:
        return None
    midi = 69.0 + 12.0 * math.log2(freq / 440.0)
    midi_int = round(midi)
    ms2_note = midi_int - 12
    if ms2_note < 0 or ms2_note > 95:
        return None
    return ms2_note


def _ms2_note_to_octave_scale(ms2_note: int) -> tuple[int, str]:
    note = int(ms2_note)
    return note // 12 + 1, _SCALE_NAMES[note % 12]


def _opll_vol_to_mml_v(opll_vol: int) -> int:
    return max(0, min(15, 15 - int(opll_vol)))


def _steps_to_mml_lengths(step_count: int) -> list[str]:
    remain = max(0, int(step_count))
    parts: list[str] = []
    for size, token in _STEP_TABLE:
        while remain >= size:
            parts.append(token)
            remain -= size
    return parts if parts else ['16']


def _emit_note_with_lengths(scale: str, lengths: list[str], tie_from_prev: bool = False) -> str:
    if not lengths:
        lengths = ['16']
    text = ''
    for i, ln in enumerate(lengths):
        if i == 0:
            prefix = '&' if tie_from_prev else ''
            text += f'{prefix}{scale}{ln}'
        else:
            text += f'&{scale}{ln}'
    return text


def _emit_rest_tokens(step_count: int) -> list[str]:
    return [f'r{ln}' for ln in _steps_to_mml_lengths(step_count)]


def _build_step_grid(
    segments: dict,
    ticks_per_step: int,
    total_steps: int,
) -> dict:
    grid: dict[tuple, tuple] = {}
    if segments:
        max_ch = max(segments.keys())
    else:
        max_ch = NUM_CH - 1
    for ch in range(max_ch + 1):
        segs = segments.get(ch, [])
        assignments: dict[int, tuple] = {}
        for seg in segs:
            start_step = seg.tick_start // ticks_per_step
            if start_step >= total_steps:
                continue
            at_token = getattr(seg, 'at_token', '')
            if getattr(seg, 'ev_type', 'note') == 'rhythm':
                if seg.keyon:
                    ms2_note = fnum_block_to_ms2_note(seg.fnum, seg.block)
                    if ms2_note is None:
                        ms2_note = DEFAULT_RHYTHM_NOTE
                    assignments[start_step] = (1, ms2_note, seg.inst, seg.vol, True, at_token, getattr(seg, 'is_legato', 0))
                    end_tick = getattr(seg, 'tick_end', None)
                    if end_tick is not None:
                        end_step_idx = end_tick // ticks_per_step
                        if 0 < end_step_idx < total_steps:
                            if assignments.get(end_step_idx, (0,))[0] != 1:
                                assignments[end_step_idx] = (0, 0, seg.inst, seg.vol, False, at_token, 0)
            elif seg.keyon:
                ms2_note = fnum_block_to_ms2_note(seg.fnum, seg.block)
                if ms2_note is not None:
                    is_legato_val = getattr(seg, 'is_legato', 0)
                    retrigger = (is_legato_val == 0)
                    assignments[start_step] = (1, ms2_note, seg.inst, seg.vol, retrigger, at_token, is_legato_val)
            else:
                if start_step not in assignments or assignments[start_step][0] == 0:
                    assignments[start_step] = (0, 0, seg.inst, seg.vol, False, at_token, 0)
        cur_state: tuple = (0, 0, 0, 0, False, '', 0)
        for step in range(total_steps):
            if step in assignments:
                cur_state = assignments[step]
            else:
                if cur_state[4]:
                    cur_state = (
                        cur_state[0],
                        cur_state[1],
                        cur_state[2],
                        cur_state[3],
                        False,
                        cur_state[5],
                        cur_state[6],
                    )
            grid[(ch, step)] = cur_state
    return grid


def _grid_ch_to_mml_line(
    grid: dict,
    ch: int,
    pat_start: int,
    pat_end: int,
    track_id: str,
    state: dict,
) -> str:
    tokens: list[str] = []
    step = pat_start
    while step < pat_end:
        keyon, ms2_note, _inst, vol_opll, retrigger, at_token, _is_legato = grid.get(
            (ch, step),
            (0, 0, 0, 15, False, '', 0),
        )
        if keyon and ms2_note is not None:
            run = 1
            while step + run < pat_end:
                n_keyon, n_note, _ni, n_vol, n_retrigger, n_at_token, _nl = grid.get(
                    (ch, step + run),
                    (0, 0, 0, 15, False, '', 0),
                )
                if not n_keyon or n_note != ms2_note or n_retrigger:
                    break
                if int(n_vol) != int(vol_opll) or n_at_token != at_token:
                    break
                run += 1

            if at_token and at_token != state['at_token']:
                tokens.append(at_token)
                state['at_token'] = at_token

            mml_v = _opll_vol_to_mml_v(vol_opll)
            if mml_v != state['mml_v']:
                tokens.append(f'v{mml_v}')
                state['mml_v'] = mml_v

            octave, scale = _ms2_note_to_octave_scale(ms2_note)
            if state['octave'] != octave:
                tokens.append(f'o{octave}')
                state['octave'] = octave

            tie_from_prev = bool(state['note_active'] and state['note'] == ms2_note and not retrigger)
            tokens.append(_emit_note_with_lengths(scale, _steps_to_mml_lengths(run), tie_from_prev=tie_from_prev))
            state['note_active'] = True
            state['note'] = ms2_note
            step += run
            continue

        run = 1
        while step + run < pat_end:
            n_keyon = grid.get((ch, step + run), (0, 0, 0, 15, False, '', 0))[0]
            if n_keyon:
                break
            run += 1
        tokens.extend(_emit_rest_tokens(run))
        state['note_active'] = False
        state['note'] = None
        step += run

    if not tokens:
        tokens = ['r1']
    return f'{track_id} {" ".join(tokens)}'


def _grid_rhythm_to_mml_line(
    grid: dict,
    pat_start: int,
    pat_end: int,
    track_id: str,
) -> str:
    step_symbols: list[str] = []
    for step in range(pat_start, pat_end):
        symbols = ''.join(
            _RHYTHM_NOTE_SYMBOLS[ch]
            for ch in _MML_RHYTHM_CHANNELS
            if grid.get((ch, step), (0, 0, 0, 15, False, '', 0))[0]
        )
        step_symbols.append(symbols if symbols else 'r')

    tokens: list[str] = []
    i = 0
    while i < len(step_symbols):
        sym = step_symbols[i]
        run = 1
        while i + run < len(step_symbols) and step_symbols[i + run] == sym:
            run += 1
        if sym == 'r':
            tokens.extend(_emit_rest_tokens(run))
        else:
            for ln in _steps_to_mml_lengths(run):
                tokens.append(f'{sym}{ln}')
        i += run

    if not tokens:
        tokens = ['r1']
    return f'{track_id} {" ".join(tokens)}'


def _grid_to_mml_text(
    grid: dict,
    n_patterns: int,
    stem: str,
    bpm: int,
    user_patches: dict,
    warnings: list[str],
) -> str:
    melody_track_ids = {ch: track_id_to_mgsdrv(ch + 9) for ch in _MML_MELODY_CHANNELS}
    rhythm_track_id = track_id_to_mgsdrv(15)
    state_by_ch = {
        ch: {'at_token': None, 'mml_v': None, 'octave': None, 'note_active': False, 'note': None}
        for ch in _MML_MELODY_CHANNELS
    }
    body_lines: list[str] = []
    per_track_lines: dict[str, list[str]] = defaultdict(list)
    for pat in range(n_patterns):
        body_lines.append(f'; === Pattern {pat} ===')
        pat_start = pat * STEPS_PER_PATTERN
        pat_end = pat_start + STEPS_PER_PATTERN
        for ch in _MML_MELODY_CHANNELS:
            track_id = melody_track_ids[ch]
            line = _grid_ch_to_mml_line(grid, ch, pat_start, pat_end, track_id, state_by_ch[ch])
            body_lines.append(line)
            per_track_lines[track_id].append(line)
        rline = _grid_rhythm_to_mml_line(grid, pat_start, pat_end, rhythm_track_id)
        body_lines.append(rline)
        per_track_lines[rhythm_track_id].append(rline)

    lines: list[str] = [
        ';[name=opll]',
        '#opll_mode 1',
        f'#tempo {int(bpm)}',
        f'#title {{ "{stem}" }}',
    ]
    for ch in _MML_MELODY_CHANNELS:
        track_id = melody_track_ids[ch]
        lines.append(f'#alloc {track_id}={estimate_alloc(estimate_mml_used(per_track_lines[track_id]))}')
    lines.append(f'#alloc {rhythm_track_id}={estimate_alloc(estimate_mml_used(per_track_lines[rhythm_track_id]))}')

    if user_patches:
        lines.append('')
        lines.extend(_user_patch_mml_defs(user_patches))
    if warnings:
        lines.extend(warnings)

    lines.append('')
    lines.extend(body_lines)
    lines.append('')
    return compress_mml_text('\n'.join(lines) + '\n')


def build_mgsdrvmml_file(
    segments: dict,
    voice_csv_path: str | None,
    stem: str,
    bpm: int = 120,
    base_ms2: str | None = None,
    video: str = 'ntsc',
    debug: bool = False,
    ticks_per_step_override: int | None = None,
) -> str:
    _voice_table, user_patches, warnings = _assign_voice_ids(segments, voice_csv_path)

    if debug and base_ms2 is not None:
        print(f"[build_mgsdrvmml_file] base_ms2={base_ms2} (ignored for MML export)")

    if video == 'pal':
        freq_hz = _FREQ_PAL
    else:
        freq_hz = _FREQ_NTSC
    ticks_per_step_16th = max(1, round(freq_hz * 15 / bpm))

    min_l = None
    for ch in range(NUM_CH):
        for seg in segments.get(ch, []):
            seg_min_l = getattr(seg, 'min_l', None)
            if seg_min_l is None:
                continue
            try:
                seg_min_l_f = float(seg_min_l)
            except (TypeError, ValueError):
                continue
            if seg_min_l_f > 0:
                min_l = seg_min_l_f if min_l is None else min(min_l, seg_min_l_f)

    ticks_per_step = ticks_per_step_16th
    if min_l is not None:
        min_l_int = int(min_l)
        ticks_per_step = max(1, min(min_l_int, ticks_per_step_16th))
        ticks_per_step = min(ticks_per_step, 0xFFFF // 256)
        if debug:
            print(
                f"[ticks_per_step] min_l={min_l} int(min_l)={min_l_int} "
                f"legacy={ticks_per_step_16th} → using ticks_per_step={ticks_per_step}"
            )

    if ticks_per_step_override is not None:
        ticks_per_step = max(2, int(ticks_per_step_override))
        if debug:
            print(f"[ticks_per_step] override={ticks_per_step_override} → using ticks_per_step={ticks_per_step}")

    mgs_bpm = max(1, round(freq_hz * 15 / ticks_per_step))
    if debug:
        print(f"[mgs_bpm] ticks_per_step={ticks_per_step} freq_hz={freq_hz:.4f} → mgs_bpm={mgs_bpm}")

    last_note_end_tick = 0
    for ch in range(NUM_CH):
        for seg in segments.get(ch, []):
            if seg.keyon:
                last_note_end_tick = max(last_note_end_tick, seg.tick_end)
    if last_note_end_tick == 0:
        for ch in range(NUM_CH):
            for seg in segments.get(ch, []):
                last_note_end_tick = max(last_note_end_tick, seg.tick_end)
    n_patterns = max(1, math.ceil(last_note_end_tick / (ticks_per_step * STEPS_PER_PATTERN)))
    total_steps = n_patterns * STEPS_PER_PATTERN
    grid = _build_step_grid(segments, ticks_per_step, total_steps)
    return _grid_to_mml_text(grid, n_patterns, stem, mgs_bpm, user_patches, warnings)


def main():
    parser = argparse.ArgumentParser(
        description='Convert VGM (OPLL/YM2413) to MGSDRV MML text using MS2 step-grid mapping'
    )
    parser.add_argument('vgm_file', nargs='?', default=None, help='Input VGM file')
    parser.add_argument(
        '--outdir', default=None,
        help='Output directory (default: outputs/<song_stem>/)'
    )
    parser.add_argument(
        '--bpm', type=int, default=120,
        help='Song tempo in BPM (default: 120)'
    )
    parser.add_argument(
        '--timer', type=int, default=0, choices=[0, 1],
        help='0 = VDP timer (default), 1 = 50 Hz timer (kept for compatibility)'
    )
    parser.add_argument(
        '--base-ms2', default=None, metavar='PATH',
        help=(
            'Path to an MS2 file to use as the base preset instrument library. '
            'The first 15 instruments map to OPLL presets 1..15.'
        ),
    )
    parser.add_argument(
        '--video', default='ntsc', choices=['ntsc', 'pal'],
        help='Video system: ntsc (default) or pal',
    )
    parser.add_argument(
        '--ticks-per-step', type=int, default=None, metavar='N',
        help=(
            'Override ticks_per_step used for MS2 step grid quantization. '
            'Minimum value: 2. Must be a positive integer >= 2.'
        ),
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Print extra information'
    )
    args = parser.parse_args()
    if args.ticks_per_step is not None and args.ticks_per_step < 2:
        parser.error('--ticks-per-step must be >= 2')

    if args.vgm_file is None:
        parser.error('vgm_file is required')

    vgm_path = args.vgm_file
    if not os.path.isfile(vgm_path):
        print(f"ERROR: VGM file not found: {vgm_path}", file=sys.stderr)
        sys.exit(1)

    if args.base_ms2 and not os.path.isfile(args.base_ms2):
        print(f"ERROR: --base-ms2 file not found: {args.base_ms2}", file=sys.stderr)
        sys.exit(1)

    base_name = os.path.splitext(os.path.basename(vgm_path))[0]

    if args.outdir:
        output_dir = args.outdir
    else:
        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(vgm_path)),
        )
    os.makedirs(output_dir, exist_ok=True)

    print(f"Parsing VGM: {vgm_path}")
    (
        psg_log_csv, scc_log_csv,
        psg_trace_csv, scc_trace_csv,
        opll_log_csv, opll_trace_csv,
        opll_voice_csv, opll_regs_csv,
    ) = parse_vgm(vgm_path, output_dir)

    print("Building OPLL segments …")
    num_ch = 18
    segments, bpm_detected = _build_segments(
        opll_trace_csv,
        include_rhythm=True,
        ticks_per_step_override=args.ticks_per_step,
        debug=args.debug,
    )
    n_segs = sum(len(v) for v in segments.values())
    print(f"  {n_segs} segments across {num_ch} channels")

    print(f"Generating MGSDRV MML (BPM={bpm_detected}, timer={args.timer}) …")
    if args.base_ms2:
        print(f"  Using base instrument library: {args.base_ms2}")
    mml_text = build_mgsdrvmml_file(
        segments=segments,
        voice_csv_path=opll_voice_csv,
        stem=base_name,
        bpm=bpm_detected,
        base_ms2=args.base_ms2,
        video=args.video,
        debug=args.debug,
        ticks_per_step_override=args.ticks_per_step,
    )

    out_name = base_name + '.opll.mml'
    out_path = os.path.join(output_dir, out_name)
    with open(out_path, 'w', newline='\n') as f:
        f.write(mml_text)

    print(f"Written: {out_path}  ({len(mml_text)} bytes)")

    if not args.debug:
        for _csv in [psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
                     opll_log_csv, opll_trace_csv, opll_voice_csv, opll_regs_csv]:
            try:
                if _csv and os.path.isfile(_csv):
                    os.remove(_csv)
            except OSError:
                pass


if __name__ == '__main__':
    main()
