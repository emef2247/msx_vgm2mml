#!/usr/bin/env python3
"""Export VGM to MGS with 24 ms FM states and an 8 ms timing correction bound.

Conversion, compilation, diagnostics and optional key-on comparison are provided
by the existing batch runner. Its own defaults remain unchanged.
"""
import argparse
from pathlib import Path

from batch_vgm_to_mgs import run_batch
from mgs_conversion_config import sample_threshold

DEFAULT_FM_STATE_MS = 24.0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Also writes musical reference tracks/<stem>.vgm and editable blueprint/<stem>.mml: '
        'structured score without executable timbre or volume controls; source instruments documented in comments.'))
    parser.add_argument('input', type=Path, help='VGM/VGZ file or directory (recursive)')
    parser.add_argument('--outdir', type=Path,
                        help='Output root preserving input-relative parents (default: beside each source VGM)')
    parser.add_argument('--mgsc', help='Native MGSC executable (default: PATH)')
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--compiler', choices=('mgsc', 'mgsexc'), default='mgsc',
                        help='MML compiler: mgsexc avoids the MGSC buffer limit (default: mgsc)')
    parser.add_argument('--node', default='node')
    parser.add_argument('--timeout', type=int, default=1200,
                        help='Timeout per conversion/compilation stage in seconds (default: 1200)')
    parser.add_argument('--alloc', help='Track allocation overrides forwarded to conversion')
    from score_normalization import add_arguments
    add_arguments(parser, include_blueprint=False)
    parser.add_argument('--fm-state-ms', type=float, default=DEFAULT_FM_STATE_MS,
                        help='OPLL internal pitch/volume state threshold in milliseconds (default: 24)')
    parser.add_argument('--normalization-ms', type=float, default=8.0,
                        help='Maximum target timing correction in milliseconds (default: 8)')
    parser.add_argument('--score-guided-loops', action='store_true',
                        help='Guide target repeats with pitch/duration/rest/attack structure (opt-in)')
    volume_curves = parser.add_mutually_exclusive_group()
    volume_curves.add_argument('--no-software-volume-curves', dest='is_software_volume_curves',
        action='store_false',default=True,
        help='Disable software volume curves (enabled by default)')
    volume_curves.add_argument('--software-volume-curves',dest='is_software_volume_curves',
        action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--force', action='store_true',
                        help='Apply only documented target omission rules')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Retain inspectable conversion passes')
    macros=parser.add_mutually_exclusive_group()
    macros.add_argument('--macro-mode',choices=('v110','current','greedy'),default='v110',
        help='Production macros: v110 (default), current, or current greedy comparison')
    macros.add_argument('--current-macros','--enhance-macros',dest='macro_mode',action='store_const',const='current',
        help='Compare the current relative/phrase-based enhanced macros')
    macros.add_argument('--greedy-macros',dest='macro_mode',action='store_const',const='greedy',
        help='Compare current shared preprocessing with greedy macro selection')
    macros.add_argument('--legacy-macros',dest='macro_mode',action='store_const',const='greedy',help=argparse.SUPPRESS)
    loops=parser.add_mutually_exclusive_group()
    loops.add_argument('--loop-mode',choices=('v110','current','envelope-first','score-guided'),default='v110',
        help='Production loops: v110 (default), current, envelope-first, or score-guided')
    loops.add_argument('--envelope-first-loops',dest='loop_mode',action='store_const',const='envelope-first',
        help='Compare the older envelope-first loop policy')
    loops.add_argument('--legacy-loops',dest='loop_mode',action='store_const',const='envelope-first',help=argparse.SUPPRESS)
    parser.add_argument('--skip-keyon-counts', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--libkss-module', type=Path,
                        help='Explicit libkss-js entry point for MGS export')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.score_guided_loops and args.loop_mode=='envelope-first':
        parser.error('--score-guided-loops cannot be combined with --envelope-first-loops')
    try:
        sample_threshold(args.fm_state_ms, '--fm-state-ms')
        rows = run_batch(args.input, args.outdir, module=args.mgsc_module,
                         node=args.node, timeout=args.timeout, mgsc=args.mgsc,
                         compiler=args.compiler,
                         alloc=args.alloc, keyon=not args.skip_keyon_counts,
                         libkss_module=args.libkss_module,
                         normalize_lengths=False,
                         score_normalize=args.score_normalize,score_tempo=args.score_tempo,
                         blueprint_score_normalize=True,
                         enhance_macros=args.macro_mode!='greedy', legacy_loops=args.loop_mode=='envelope-first',
                         macro_mode=args.macro_mode, loop_mode='score-guided' if args.score_guided_loops else args.loop_mode,
                         force=args.force, fm_state_ms=args.fm_state_ms,
                         normalization_ms=args.normalization_ms, dump_passes=args.dump_passes,
                         enhance_drums=False, psg_part='all',
                         software_volume_curves=args.is_software_volume_curves,
                         score_guided_loops=args.score_guided_loops,
                         psg_state_ms=None, scc_state_ms=None,
                         curve_volume_error=None, curve_mean_error=None)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    return 0 if all(row['status'] == 'success' and row.get('vgm_status') not in ('failed', 'blocked')
                    and row['keyon_status'] in ('compared', 'disabled', 'selection_only', 'projected_source')
                    for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
