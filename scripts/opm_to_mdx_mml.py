"""Convert native OPM VGM through inspectable Segments to MDX MML controls."""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opm import build_segments
from opm_mdx import project_segments, render, dump_projection
from vgm_reader import parse_vgm


def convert(source, outdir, *, dump_passes=False, track_layout='channels', notation='structured', loops=True):
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    metadata = {}
    with TemporaryDirectory(prefix='opm-mdx-') as temporary:
        analysis_dir = outdir if dump_passes else Path(temporary)
        parse_vgm(str(source), str(analysis_dir), opm_metadata=metadata,
                  dump_opm_segments=dump_passes)
        if not metadata['csv_path']:
            raise ValueError('Input declares no supported OPM stream')
        analysis = build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks'])
    projection = project_segments(analysis.segments, end_vgmticks=analysis.source_end_vgmticks)
    mml = outdir / (source.stem + '.mdx.mml')
    structure = None
    if notation == 'structured':
        if track_layout != 'channels':
            raise ValueError('Structured notation requires channel tracks; use --notation registers for conductor replay')
        from opm_mdx_structure import build_structure
        structure = build_structure(projection, analysis.segments, title=source.stem, loops=loops)
        text = structure.text
    elif notation == 'registers':
        text = render(projection, title=source.stem, track_layout=track_layout)
    else:
        raise ValueError('Unknown MDX notation')
    mml.write_text(text, encoding='utf-8', newline='\n')
    if dump_passes:
        dump_projection(projection, outdir / (source.stem + '.mdx.controls.csv'), track_layout=track_layout)
        report = projection.timing_report()
        report['track_layout'] = track_layout
        report['notation'] = notation
        if structure is not None:
            structure.dump(outdir / (source.stem + '.mdx.structure'),
                           segments_csv=outdir / (source.stem + '.opm.segments.csv'))
            report.update(structure.summary())
        report['source_state_writes'] = len({e.source_event_id for e in analysis.events})
        report['source_nonchanging_writes_not_in_segments'] = report['source_state_writes'] - len(projection.writes)
        (outdir / (source.stem + '.mdx.timing.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return mml, analysis, projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--outdir', type=Path, default=ROOT / 'outputs/opm/mdx')
    parser.add_argument('--notation', choices=('structured', 'registers'), default='structured',
                        help='Hybrid notes/voices with reversible loops (default), or raw register replay')
    parser.add_argument('--no-loops', action='store_true', help='Disable finite target loop emission')
    parser.add_argument('--track-layout', choices=('channels', 'conductor'), default='channels',
                        help='Channels A..H (default), or original one-track control replay')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Keep raw/state/Segment CSVs, target controls and timing report')
    args = parser.parse_args()
    mml, _, projection = convert(args.input, args.outdir, dump_passes=args.dump_passes, track_layout=args.track_layout,
                                 notation=args.notation, loops=not args.no_loops)
    print('MDX MML:', mml)
    if args.dump_passes:
        print(json.dumps(projection.timing_report()))


if __name__ == '__main__':
    main()
