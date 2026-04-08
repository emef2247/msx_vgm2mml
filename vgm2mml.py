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
                      has_psg: bool, has_scc: bool, has_opll: bool) -> str:
    """Build the merged MML text from per-chip compress.MGS_pct outputs.

    The merged file has a single global header followed by PSG, SCC, and OPLL
    parts (in that order) when the corresponding chip is present.  Each part
    begins with a separator comment and includes the chip MML content starting
    from the ``#alloc`` line (chip-level header is stripped).
    """
    lines = []
    lines.append(';[name=psg lpf=1]')
    lines.append('#opll_mode 1')
    lines.append('#tempo 75')
    lines.append(f'#title {{ "{stem}"}}')
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

    for chip_key, chip_ext, separator in parts:
        if not flags[chip_key]:
            continue
        mml_path = os.path.join(song_dir,
                                f'{stem}.{chip_ext}.pass3.compress.MGS_pct.mml')
        body_parts.append(separator + '\n')
        body_parts.append(_extract_from_alloc(mml_path))

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Convert a VGM file to MGSDRV MML (SCC + PSG + OPLL)')
    parser.add_argument('vgm', help='Input VGM file')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: <vgm_stem>_log/ next to vgm)')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Write pass0-3 intermediate CSV files')
    parser.add_argument('--debug', action='store_true',
                        help='Write all chip-specific MML variants and raw CSV files '
                             'in addition to the merged <stem>.mml output')
    parser.add_argument('--scc-input', choices=['trace', 'log'], default='trace',
                        help='SCC intermediate format: trace (default, chronological)'
                             ' or log (per-channel grouped)')
    parser.add_argument('--psg-input', choices=['trace', 'log'], default='trace',
                        help='PSG intermediate format: trace (default, chronological)'
                             ' or log (per-channel grouped)')
    args = parser.parse_args()

    vgm_path = args.vgm
    if not os.path.isfile(vgm_path):
        print(f"Error: {vgm_path!r} not found", file=sys.stderr)
        sys.exit(1)

    # Determine base name: "02_StartingPoint"
    base_name = os.path.splitext(os.path.basename(vgm_path))[0]

    # Determine song-level output directory.
    # All outputs (raw CSVs + MML + pass CSVs) go into a single flat directory.
    # With --outdir: <outdir>/<vgm_stem>/
    # Without --outdir: <repo_root>/outputs/<vgm_stem>/
    if args.outdir:
        song_dir = os.path.join(args.outdir, base_name)
    else:
        song_dir = os.path.join(_SCRIPT_DIR, 'outputs', base_name)

    os.makedirs(song_dir, exist_ok=True)

    # ── Step 1: Parse VGM → SCC + PSG + OPLL log/trace CSVs ──────
    (psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv,
     opll_log_csv, opll_trace_csv) = parse_vgm(vgm_path, song_dir)

    if args.debug:
        print(f"PSG log:    {psg_log_csv}")
        print(f"PSG trace:  {psg_trace_csv}")
        print(f"SCC log:    {scc_log_csv}")
        print(f"SCC trace:  {scc_trace_csv}")
        print(f"OPLL log:   {opll_log_csv}")
        print(f"OPLL trace: {opll_trace_csv}")

    # Detect chip presence from trace CSVs
    has_psg  = _has_chip_data(psg_trace_csv)
    has_scc  = _has_chip_data(scc_trace_csv)
    has_opll = _has_chip_data(opll_trace_csv)

    # ── Step 2: SCC MML pipeline ─────────────────────────────────
    scc_csv = scc_trace_csv if args.scc_input == 'trace' else scc_log_csv

    scc_mml_path = process_scc_csv(scc_csv, song_dir, stem=base_name,
                                   dump_passes=args.dump_passes,
                                   debug=args.debug)
    if args.debug:
        print(f"SCC MML: {scc_mml_path}")

    # ── Step 3: PSG MML pipeline ─────────────────────────────────
    psg_csv = psg_trace_csv if args.psg_input == 'trace' else psg_log_csv

    psg_mml_path = process_psg_csv(psg_csv, song_dir, stem=base_name,
                                   dump_passes=args.dump_passes,
                                   debug=args.debug)
    if args.debug:
        print(f"PSG MML: {psg_mml_path}")

    # ── Step 4: OPLL MML pipeline ────────────────────────────────
    opll_mml_path = process_opll_csv(opll_trace_csv, song_dir, stem=base_name,
                                     dump_passes=args.dump_passes,
                                     debug=args.debug)
    if args.debug:
        print(f"OPLL MML: {opll_mml_path}")

    # ── Step 5: Build merged MML ──────────────────────────────────
    merged_text = _build_merged_mml(base_name, song_dir,
                                    has_psg, has_scc, has_opll)
    merged_path = os.path.join(song_dir, f'{base_name}.mml')
    with open(merged_path, 'w', newline='\n') as fh:
        fh.write(merged_text)
    print(f"Merged MML: {merged_path}")

    # ── Step 6: Clean up intermediate files in non-debug mode ─────
    if not args.debug:
        # Remove log/trace CSVs written by parse_vgm (intermediate inputs)
        for csv_path in (psg_log_csv, psg_trace_csv,
                         scc_log_csv, scc_trace_csv,
                         opll_log_csv, opll_trace_csv):
            try:
                os.remove(csv_path)
            except OSError:
                pass
        # Remove per-chip compress.MGS_pct intermediate files
        for chip in ('psg', 'scc', 'opll'):
            chip_path = os.path.join(song_dir,
                                     f'{base_name}.{chip}.pass3.compress.MGS_pct.mml')
            try:
                os.remove(chip_path)
            except OSError:
                pass


if __name__ == '__main__':
    main()
