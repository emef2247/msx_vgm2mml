#!/usr/bin/env python3
"""Export VGM to MGS with 24 ms FM states and an 8 ms timing correction bound.

Conversion, compilation, diagnostics and optional key-on comparison are provided
by the existing batch runner. Its own defaults remain unchanged.
"""
import argparse
import sys
from pathlib import Path

from batch_vgm_to_mgs import run_batch
from mgs_conversion_config import add_curve_arguments, curve_option_values


def boolean_value(value):
    normalized=str(value).strip().casefold()
    if normalized in ('yes','y','1','true'):return True
    if normalized in ('no','n','0','false'):return False
    raise argparse.ArgumentTypeError('Use yes/y/1/true or no/n/0/false')


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Also writes musical reference tracks/<stem>.vgm and editable blueprint/<stem>.mml: '
        'structured score without executable timbre or volume controls; source instruments documented in comments.'))
    parser.add_argument('input', type=Path, help='VGM/VGZ file or directory (recursive)')
    parser.add_argument('--outdir', type=Path,
                        help='Output root preserving input-relative parents (default: beside each source VGM)')
    parser.add_argument('--mgsc', help='Native MGSC executable (default: PATH)')
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--timeout', type=int, default=1200,
                        help='Timeout per conversion/compilation stage in seconds (default: 1200)')
    parser.add_argument('--alloc', help='Track allocation overrides forwarded to conversion')
    parser.add_argument('--normalize-lengths', action='store_true',
                        help='Compatibility flag; normalization is already requested by the export thresholds')
    from score_normalization import add_arguments
    add_arguments(parser)
    parser.add_argument('--fm-state-ms', type=float, default=24.0,
                        help='OPLL internal pitch/volume state threshold in milliseconds (default: 24)')
    parser.add_argument('--normalization-ms', type=float, default=8.0,
                        help='Maximum target timing correction in milliseconds (default: 8)')
    add_curve_arguments(parser)
    parser.add_argument('--enhance-rhythm', '--enhance-drums', dest='enhance_drums', action='store_true',
                        help='Add inferred PSG/SCC percussion on OPLL rhythm')
    volume_curves = parser.add_mutually_exclusive_group()
    volume_curves.add_argument('--no-software-volume-curves', dest='is_software_volume_curves',
        nargs='?',const=False,default=True,type=lambda value:not boolean_value(value),metavar='BOOL',
        help='Disable software volume curves (enabled by default); optional yes/no, 1/0 or true/false')
    volume_curves.add_argument('--software-volume-curves',dest='is_software_volume_curves',
        nargs='?',const=True,type=boolean_value,help=argparse.SUPPRESS)
    parts = parser.add_mutually_exclusive_group()
    parts.add_argument('--psg-melody-only', '--psg-melody_only', dest='psg_part',
                       action='store_const', const='melody', default='all')
    parts.add_argument('--psg-rhythm-only', '--psg-rhythm_only', dest='psg_part',
                       action='store_const', const='rhythm')
    parser.add_argument('--force', action='store_true',
                        help='Apply only documented target omission rules')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Retain inspectable conversion passes')
    macros=parser.add_mutually_exclusive_group()
    macros.add_argument('--legacy-macros',dest='is_legacy_macros',nargs='?',const=True,
        default=False,type=boolean_value,metavar='BOOL',
        help='Use the previous macro compressor (enhanced macros by default); optional boolean')
    macros.add_argument('--enhance-macros',dest='is_legacy_macros',nargs='?',const=False,
        type=lambda value:not boolean_value(value),help=argparse.SUPPRESS)
    parser.add_argument('--legacy-loops', action='store_true',
                        help='Use the previous OPLL loop projection')
    parser.add_argument('--skip-keyon-counts', action='store_true',
                        help='Disable MGS playback and OPLL key-on comparison')
    parser.add_argument('--libkss-module', type=Path,
                        help='Explicit libkss-js entry point for MGS export')
    return parser


def main(argv=None):
    parser = build_parser()
    # Optional booleans must not swallow a positional input after a bare flag.
    argv=list(sys.argv[1:] if argv is None else argv)
    boolean_flags={'--legacy-macros','--enhance-macros','--no-software-volume-curves','--software-volume-curves'}
    known_values={'yes','y','1','true','no','n','0','false'}
    normalized=[];options_ended=False
    for index,word in enumerate(argv):
        if word=='--':options_ended=True
        if (not options_ended and word in boolean_flags and
                (index+1==len(argv) or argv[index+1].strip().casefold() not in known_values)):
            word+='=true'
        normalized.append(word)
    argv=normalized
    args = parser.parse_args(argv)
    try:
        rows = run_batch(args.input, args.outdir, module=args.mgsc_module,
                         node=args.node, timeout=args.timeout, mgsc=args.mgsc,
                         alloc=args.alloc, keyon=not args.skip_keyon_counts,
                         libkss_module=args.libkss_module,
                         normalize_lengths=args.normalize_lengths,
                         score_normalize=args.score_normalize,score_tempo=args.score_tempo,
                         enhance_macros=not args.is_legacy_macros, legacy_loops=args.legacy_loops,
                         force=args.force, fm_state_ms=args.fm_state_ms,
                         normalization_ms=args.normalization_ms, dump_passes=args.dump_passes,
                         enhance_drums=args.enhance_drums, psg_part=args.psg_part,
                         software_volume_curves=args.is_software_volume_curves,
                         **curve_option_values(args))
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    return 0 if all(row['status'] == 'success' and row.get('vgm_status') not in ('failed', 'blocked')
                    and row['keyon_status'] in ('compared', 'disabled', 'selection_only', 'projected_source')
                    for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
