#!/usr/bin/env python3
"""Export VGM to MGS with 24 ms FM states and an 8 ms timing correction bound.

Conversion, compilation, diagnostics and optional key-on comparison are provided
by the existing batch runner. Its own defaults remain unchanged.
"""
import argparse
from pathlib import Path

from batch_vgm_to_mgs import run_batch


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='VGM/VGZ file or directory (recursive)')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--mgsc', help='Native MGSC executable (default: PATH)')
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--timeout', type=int, default=1200,
                        help='Timeout per conversion/compilation stage in seconds (default: 1200)')
    parser.add_argument('--alloc', help='Track allocation overrides forwarded to conversion')
    parser.add_argument('--normalize-lengths', action='store_true',
                        help='Compatibility flag; normalization is already requested by the export thresholds')
    parser.add_argument('--fm-state-ms', type=float, default=24.0,
                        help='OPLL internal pitch/volume state threshold in milliseconds (default: 24)')
    parser.add_argument('--normalization-ms', type=float, default=8.0,
                        help='Maximum target timing correction in milliseconds (default: 8)')
    parser.add_argument('--enhance-rhythm', '--enhance-drums', dest='enhance_drums', action='store_true',
                        help='Add inferred PSG/SCC percussion on OPLL rhythm')
    parts = parser.add_mutually_exclusive_group()
    parts.add_argument('--psg-melody-only', '--psg-melody_only', dest='psg_part',
                       action='store_const', const='melody', default='all')
    parts.add_argument('--psg-rhythm-only', '--psg-rhythm_only', dest='psg_part',
                       action='store_const', const='rhythm')
    parser.add_argument('--force', action='store_true',
                        help='Apply only documented target omission rules')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Retain inspectable conversion passes')
    parser.add_argument('--enhance-macros', action='store_true', default=True,
                        help='Enable enhanced macros (default)')
    parser.add_argument('--legacy-macros', dest='enhance_macros', action='store_false',
                        help='Use the previous macro compressor')
    parser.add_argument('--legacy-loops', action='store_true',
                        help='Use the previous OPLL loop projection')
    parser.add_argument('--skip-keyon-counts', action='store_true',
                        help='Disable MGS playback and OPLL key-on comparison')
    parser.add_argument('--libkss-module', type=Path,
                        help='Explicit libkss-js entry point for MGS export')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rows = run_batch(args.input, args.outdir, module=args.mgsc_module,
                         node=args.node, timeout=args.timeout, mgsc=args.mgsc,
                         alloc=args.alloc, keyon=not args.skip_keyon_counts,
                         libkss_module=args.libkss_module,
                         normalize_lengths=args.normalize_lengths,
                         enhance_macros=args.enhance_macros, legacy_loops=args.legacy_loops,
                         force=args.force, fm_state_ms=args.fm_state_ms,
                         normalization_ms=args.normalization_ms, dump_passes=args.dump_passes,
                         enhance_drums=args.enhance_drums, psg_part=args.psg_part)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    return 0 if all(row['status'] == 'success' and row['keyon_status'] in ('compared', 'disabled', 'selection_only')
                    for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
