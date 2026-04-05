#!/usr/bin/env python3
"""
vgm2mml.py - Top-level CLI: VGM binary → MGSDRV MML

Usage:
    python vgm2mml.py <vgm_file> [--outdir <dir>] [--dump-passes]
                      [--scc-input trace|log] [--psg-input trace|log]

Example:
    python vgm2mml.py inputs/02_StartingPoint/02_StartingPoint.vgm \
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


def main():
    parser = argparse.ArgumentParser(
        description='Convert a VGM file to MGSDRV MML (SCC + PSG)')
    parser.add_argument('vgm', help='Input VGM file')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: <vgm_stem>_log/ next to vgm)')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Write pass0-3 intermediate CSV files')
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
    # With --outdir: place all outputs under <outdir>/<base_name>/ so that
    # processing multiple VGM files into the same --outdir keeps them separate.
    # Without --outdir: use <vgm_dir>/<base_name>_log/ (legacy default).
    if args.outdir:
        song_dir = os.path.join(args.outdir, base_name)
    else:
        song_dir = os.path.join(os.path.dirname(os.path.abspath(vgm_path)),
                                base_name + '_log')

    os.makedirs(song_dir, exist_ok=True)

    # ── Step 1: Parse VGM → SCC + PSG log/trace CSVs ─────────────
    psg_log_csv, scc_log_csv, psg_trace_csv, scc_trace_csv = parse_vgm(
        vgm_path, song_dir)
    print(f"PSG log:   {psg_log_csv}")
    print(f"PSG trace: {psg_trace_csv}")
    print(f"SCC log:   {scc_log_csv}")
    print(f"SCC trace: {scc_trace_csv}")

    # ── Step 2: SCC MML pipeline ─────────────────────────────────
    if args.scc_input == 'trace':
        scc_csv = scc_trace_csv
        stem_suffix = base_name + '_trace'
    else:
        scc_csv = scc_log_csv
        stem_suffix = base_name + '_log'

    # Put SCC pass files into a sub-directory named after the stem
    scc_out_dir = os.path.join(song_dir, stem_suffix)
    mml_path = process_scc_csv(scc_csv, scc_out_dir,
                                dump_passes=args.dump_passes)
    print(f"SCC MML:   {mml_path}")

    # ── Step 3: PSG MML pipeline ─────────────────────────────────
    # Default: use trace CSV (chronological order, same as SCC default).
    # Use --psg-input log for the log-based variant (debug).
    if args.psg_input == 'trace':
        psg_csv = psg_trace_csv
        psg_stem_suffix = base_name + '_psg_trace'
    else:
        psg_csv = psg_log_csv
        psg_stem_suffix = base_name + '_psg_log'

    psg_out_dir = os.path.join(song_dir, psg_stem_suffix)
    psg_mml_path = process_psg_csv(psg_csv, psg_out_dir,
                                   stem=psg_stem_suffix,
                                   dump_passes=args.dump_passes)
    print(f"PSG MML:   {psg_mml_path}")


if __name__ == '__main__':
    main()
