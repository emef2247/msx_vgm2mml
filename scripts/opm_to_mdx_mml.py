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


def convert(source, outdir, *, dump_passes=False):
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
    mml.write_text(render(projection, title=source.stem), encoding='utf-8', newline='\n')
    if dump_passes:
        dump_projection(projection, outdir / (source.stem + '.mdx.controls.csv'))
        report = projection.timing_report()
        report['source_state_writes'] = len({e.source_event_id for e in analysis.events})
        report['source_nonchanging_writes_not_in_segments'] = report['source_state_writes'] - len(projection.writes)
        (outdir / (source.stem + '.mdx.timing.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return mml, analysis, projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--outdir', type=Path, default=ROOT / 'outputs/opm/mdx')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Keep raw/state/Segment CSVs, target controls and timing report')
    args = parser.parse_args()
    mml, _, projection = convert(args.input, args.outdir, dump_passes=args.dump_passes)
    print('MDX MML:', mml)
    if args.dump_passes:
        print(json.dumps(projection.timing_report()))


if __name__ == '__main__':
    main()
