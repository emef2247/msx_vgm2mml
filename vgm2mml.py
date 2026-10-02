#!/usr/bin/env python3
"""
vgm2mml.py - Top-level CLI: VGM binary → MGSDRV MML

Usage:
    python vgm2mml.py <vgm_file> [--outdir <dir>] [--dump-passes] [--debug]
                      [--scc-input trace|log] [--psg-input trace|log]

Default output (no --debug):
    A single merged <stem>.mml file containing PSG, SCC, and OPLL parts.

With --debug:
    The merged <stem>.mml file plus all chip-specific MML variants and the
    raw log/trace CSV files.

Example:
    python vgm2mml.py inputs/02_StartingPoint/02_StartingPoint.vgm \\
        --outdir outputs_py --dump-passes
"""
import sys
import os
import argparse

# Allow importing py/ siblings from the repository root
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, 'py'))

from vgm_reader import parse_vgm
from scc_mml import process_scc_csv
from psg_mml import process_psg_csv
from opll_mml import process_opll_csv
from mml_sync import annotate_sync_points
from mml_macros import compress_macros
from gd3 import title_from_gd3
from mml_alloc import parse_alloc, override_alloc
from mml_envelopes import EnvelopeBank
from psg_scc_target import TUNING_HEADER


def _has_chip_data(csv_path: str) -> bool:
    """Return True if *csv_path* contains at least one non-header data row."""
    try:
        with open(csv_path, 'r', newline='') as fh:
            for line in fh:
                line = line.rstrip('\r\n')
                if line and not line.startswith('#') and line.strip():
                    return True
    except OSError:
        pass
    return False


def _extract_from_alloc(mml_path: str) -> str:
    """Read *mml_path* and return the content starting from the first ``#alloc`` line.

    Lines before the first ``#alloc`` (i.e., the chip-level header:
    ``;[name=...]``, ``#opll_mode``, ``#tempo``, ``#title``) are stripped.
    The returned string starts with the first ``#alloc`` line.
    """
    try:
        with open(mml_path, 'r', newline='') as fh:
            lines = fh.readlines()
    except OSError:
        return ''

    for i, line in enumerate(lines):
        if line.startswith('#alloc'):
            return ''.join(lines[i:])
    # No #alloc found – return full content as fallback
    return ''.join(lines)


def _build_merged_mml(stem: str, song_dir: str,
                      has_psg: bool, has_scc: bool, has_opll: bool,
                      raw_ticks: bool = False, sync_min_gap: int = 1000,
                      target: bool = True, name: str | None = None,
                      title: str | None = None) -> str:
    """Build the merged MML text from per-chip compress outputs.

    The merged file has a single global header followed by PSG, SCC, and OPLL
    parts (in that order) when the corresponding chip is present.  Each part
    begins with a separator comment and includes the chip MML content starting
    from the ``#alloc`` line (chip-level header is stripped).
    """
    lines = []
    lines.append(f';[name={stem if name is None else name} lpf=1]')
    lines.append('#opll_mode 1')
    if target and (has_psg or has_scc):
        lines.append(TUNING_HEADER)
    lines.append('#tempo 75' if raw_ticks else '#tempo 225')
    lines.append(f'#title {{ "{stem if title is None else title}"}}')
    lines.append('')

    parts = [
        ('psg',  'psg',
         "\n;-----------------------  psg part -------------------------------"),
        ('scc',  'scc',
         "\n;-----------------------  scc part -------------------------------"),
        ('opll', 'opll',
         "\n;-----------------------  OPLL part -------------------------------"),
    ]
    flags = {'psg': has_psg, 'scc': has_scc, 'opll': has_opll}

    header_text = '\n'.join(lines) + '\n'
    body_parts = [header_text]

    suffix = 'pass3.compress.MGS_pct.mml' if raw_ticks else 'pass3.compress.MGS.mml'

    for chip_key, chip_ext, separator in parts:
        if not flags[chip_key]:
            continue
        mml_path = os.path.join(song_dir,
                                f'{stem}.{chip_ext}.{suffix}')
        target_path = os.path.join(song_dir, f'{stem}.{chip_ext}.target.mml')
        if target and chip_key in ('psg', 'scc', 'opll') and os.path.exists(target_path):
            mml_path = target_path
        body_parts.append(separator + '\n')
        body_parts.append(_extract_from_alloc(mml_path))

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    formatted = annotate_sync_points(result, min_gap=sync_min_gap, drop_silent=target)
    return compress_macros(formatted) if target else formatted


def main():
    parser = argparse.ArgumentParser(
        description='Convert a VGM file to MGSDRV MML (SCC + PSG + OPLL)')
    parser.add_argument('vgm', help='Input VGM file')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: <vgm_stem>_log/ next to vgm)')
    parser.add_argument('--name', help='Override the player metadata name (default: input stem)')
    parser.add_argument('--title', dest='title',
                        help='Override #title (default: GD3 metadata, then input stem)')
    parser.add_argument('--gd3-language', choices=['ja', 'en'], default='ja',
                        help='Preferred GD3 language, with per-field fallback (default: ja)')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Keep event log/trace CSVs and write pass0-3 and PSG/SCC Segment CSVs')
    parser.add_argument('--vgmticks', action='store_true',
                        help='Append absolute VGM sample positions to trace/Segment evidence; does not retime MML')
    parser.add_argument('--debug', action='store_true',
                        help='Write all chip-specific MML variants and raw CSV files '
                             'in addition to the merged <stem>.mml output')
    parser.add_argument('--scc-input', choices=['trace', 'log'], default='trace',
                        help='SCC intermediate format: trace (default, chronological)'
                             ' or log (per-channel grouped)')
    parser.add_argument('--psg-input', choices=['trace', 'log'], default='trace',
                        help='PSG intermediate format: trace (default, chronological)'
                             ' or log (per-channel grouped)')
    parser.add_argument('--raw-ticks', action='store_true',
                        help='Output note lengths as raw tick %% notation '
                             '(e.g. c%%N). '
                             'Default is note-value/divisor notation (e.g. c16, d8.).')
    parser.add_argument('--sync-min-gap', type=int, default=1000,
                        help='Minimum target-MML steps between sync comments '
                             '(default: 1000; 0: all shared boundaries; end always shown)')
    parser.add_argument('--alloc', type=parse_alloc,
                        help='Override selected track allocations, e.g. "9=1800, a=3780"')
    args = parser.parse_args()
    if args.sync_min_gap < 0:
        parser.error('--sync-min-gap must be nonnegative')

    for field, value in (('name', args.name), ('title', args.title)):
        if value is not None and (any(c in value for c in '\r\n') or
                                  (']' in value if field == 'name' else '"' in value)):
            parser.error(f'--{field} contains a character that would break the MML header')

    vgm_path = args.vgm
    if not os.path.isfile(vgm_path):
        print(f"Error: {vgm_path!r} not found", file=sys.stderr)
        sys.exit(1)

    # Determine base name: "02_StartingPoint"
    base_name = os.path.splitext(os.path.basename(vgm_path))[0]
    if args.title is None:
        args.title = title_from_gd3(vgm_path, base_name, args.gd3_language)

    if args.outdir:
        song_dir = args.outdir
    else:
        song_dir = os.path.join(
            os.path.dirname(os.path.abspath(vgm_path)),
        )
    
    os.makedirs(song_dir, exist_ok=True)

    # ── Step 1: Parse VGM → SCC + PSG + OPLL log/trace CSVs ──────
    (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
     opll_log_csv, opll_trace_csv, opll_voice_csv, opll_regs_csv) = parse_vgm(
         vgm_path, song_dir, dump_loop=args.debug or args.dump_passes,
         include_vgmticks=args.vgmticks)

    if args.debug:
        print(f"PSG log:       {psg_log_csv}")
        print(f"PSG trace:     {psg_trace_csv}")
        print(f"SCC log:       {scc_log_csv}")
        print(f"SCC trace:     {scc_trace_csv}")
        print(f"OPLL log:      {opll_log_csv}")
        print(f"OPLL trace:    {opll_trace_csv}")
        print(f"OPLL voice:    {opll_voice_csv}")
        print(f"OPLL regs:     {opll_regs_csv}")

    # Detect chip presence from trace CSVs
    has_psg  = _has_chip_data(psg_trace_csv)
    has_scc  = _has_chip_data(scc_trace_csv)
    has_opll = _has_chip_data(opll_trace_csv)

    # ── Step 2: SCC MML pipeline ─────────────────────────────────
    envelope_bank = EnvelopeBank(deferred=True)
    scc_csv = scc_trace_csv if args.scc_input == 'trace' else scc_log_csv

    scc_mml_path = process_scc_csv(scc_csv, song_dir, stem=base_name,
                                   dump_passes=args.dump_passes,
                                   debug=args.debug,
                                   raw_ticks=args.raw_ticks,
                                   envelope_bank=envelope_bank)
    if args.debug:
        print(f"SCC MML: {scc_mml_path}")

    # ── Step 3: PSG MML pipeline ─────────────────────────────────
    psg_csv = psg_trace_csv if args.psg_input == 'trace' else psg_log_csv

    psg_mml_path = process_psg_csv(psg_csv, song_dir, stem=base_name,
                                   dump_passes=args.dump_passes,
                                   debug=args.debug,
                                   raw_ticks=args.raw_ticks,
                                   envelope_bank=envelope_bank)
    if args.debug:
        print(f"PSG MML: {psg_mml_path}")

    envelope_bank.flush()

    # ── Step 4: OPLL MML pipeline ────────────────────────────────
    opll_mml_path = process_opll_csv(opll_trace_csv, song_dir, stem=base_name,
                                     dump_passes=args.dump_passes,
                                     debug=args.debug,
                                     voice_csv_path=opll_voice_csv,
                                     raw_ticks=args.raw_ticks)
    if args.debug:
        print(f"OPLL MML: {opll_mml_path}")

    # ── Step 5: Build merged MML ──────────────────────────────────
    merged_text = _build_merged_mml(base_name, song_dir,
                                    has_psg, has_scc, has_opll,
                                    raw_ticks=args.raw_ticks,
                                    sync_min_gap=args.sync_min_gap,
                                    name=args.name, title=args.title)
    merged_text = override_alloc(merged_text, args.alloc)
    merged_path = os.path.join(song_dir, f'{base_name}.mml')
    with open(merged_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(merged_text)
    print(f"Merged MML: {merged_path}")
    if not args.debug and not args.dump_passes:
        for chip in ('psg', 'scc', 'opll'):
            os.remove(os.path.join(song_dir, f'{base_name}.{chip}.target.mml'))

    # ── Step 6: Clean up intermediate files in non-debug mode ─────
    if not args.debug:
        # Remove log/trace CSVs written by parse_vgm (intermediate inputs)
        if not args.dump_passes:
            for csv_path in (psg_log_csv, psg_trace_csv,
                             scc_log_csv, scc_trace_csv,
                             opll_log_csv, opll_trace_csv,
                             opll_voice_csv, opll_regs_csv):
                try:
                    os.remove(csv_path)
                except OSError:
                    pass
        # Every pipeline writes these variants, including absent chips.
        # Debug mode retains them; normal output must not leak empty-chip files.
        chips_to_clean = ('psg', 'scc', 'opll')

        for chip in chips_to_clean:
            for suffix in ('pass3.compress.MGS.mml', 'pass3.compress.MGS_pct.mml'):
                chip_path = os.path.join(song_dir, f'{base_name}.{chip}.{suffix}')
                try:
                    os.remove(chip_path)
                except OSError:
                    pass


if __name__ == '__main__':
    main()
