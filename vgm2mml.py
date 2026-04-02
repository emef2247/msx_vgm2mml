#!/usr/bin/env python3
"""
vgm2mml.py - Top-level CLI: VGM binary → MGSDRV MML

Usage:
    python vgm2mml.py <vgm_file> [--outdir <dir>] [--dump-passes]

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


def main():
    parser = argparse.ArgumentParser(
        description='Convert a VGM file to MGSDRV MML (SCC + PSG)')
    parser.add_argument('vgm', help='Input VGM file')
    parser.add_argument('--outdir', default=None,
                        help='Output directory (default: <vgm_stem>_log/ next to vgm)')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Write pass0-3 intermediate CSV files')
    args = parser.parse_args()

    vgm_path = args.vgm
    if not os.path.isfile(vgm_path):
        print(f"Error: {vgm_path!r} not found", file=sys.stderr)
        sys.exit(1)

    # Determine base name: "02_StartingPoint"
    base_name = os.path.splitext(os.path.basename(vgm_path))[0]
    # Stem for log files: "02_StartingPoint_log"
    log_stem = base_name + '_log'

    # Determine output directory
    if args.outdir:
        out_root = args.outdir
    else:
        out_root = os.path.join(os.path.dirname(os.path.abspath(vgm_path)),
                                log_stem)

    os.makedirs(out_root, exist_ok=True)

    # ── Step 1: Parse VGM → SCC + PSG log CSVs ──────────────────
    psg_csv, scc_csv = parse_vgm(vgm_path, out_root)
    print(f"PSG log: {psg_csv}")
    print(f"SCC log: {scc_csv}")

    # ── Step 2: SCC MML pipeline ─────────────────────────────────
    # Put SCC pass files into a sub-directory named after the log stem
    scc_out_dir = os.path.join(out_root, log_stem)
    mml_path = process_scc_csv(scc_csv, scc_out_dir,
                                dump_passes=args.dump_passes)
    print(f"SCC MML: {mml_path}")


if __name__ == '__main__':
    main()
