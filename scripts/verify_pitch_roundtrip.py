"""Generate MML, render with MGSC/libkss, and compare saved Segment CSVs."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from roundtrip_pitch import compare_directories, timeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vgm', type=Path)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--libkss-module', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--actual-dir', type=Path, help='Compare existing roundtrip dumps only')
    parser.add_argument('--offset-ticks', type=int, default=0,
                        help='Explicit global actual-minus-reference offset; no automatic alignment')
    parser.add_argument('--boundary-tolerance', type=int, default=1)
    args = parser.parse_args()
    if args.boundary_tolerance < 0:
        parser.error('--boundary-tolerance must be nonnegative')
    out = args.outdir.resolve()
    reference = args.reference.resolve()
    if out == reference or reference in out.parents or out in reference.parents:
        parser.error('output and reference directories must be separate')
    out.mkdir(parents=True, exist_ok=True)
    stem = args.vgm.stem
    summary = dict(stem=stem, reference=str(reference), offset_ticks=args.offset_ticks,
                   boundary_tolerance=args.boundary_tolerance, status='error')
    def run(command, log):
        with open(out / log, 'w', encoding='utf-8') as stream:
            subprocess.run(list(map(str, command)), cwd=ROOT, stdout=stream,
                           stderr=subprocess.STDOUT, check=True)
    try:
        end = max((max(states, default=0) + 1
                   for chip in ('psg', 'scc')
                   for states in timeline(reference / f'{stem}.{chip}.segments.csv', chip).values()), default=0)
        if end == 0:
            raise ValueError('reference contains no timed segments')
        actual = args.actual_dir
        if actual is None:
            if not args.mgsc_module or not args.libkss_module:
                raise ValueError('--mgsc-module and --libkss-module are required for rendering')
            summary.update(mgsc_module=str(args.mgsc_module.resolve()),
                           libkss_module=str(args.libkss_module.resolve()))
            run([sys.executable, ROOT / 'vgm2mml.py', args.vgm.resolve(),
                 '--outdir', out / 'generated', '--dump-passes'], 'generate.log')
            rendered = out / 'rendered'
            rendered.mkdir(exist_ok=True)
            vgm = rendered / f'{stem}.vgm'
            run([args.node, ROOT / 'scripts/mml_to_vgm.mjs', out / 'generated' / f'{stem}.mml',
                 vgm, int((end / 60 + 3) * 1000), args.mgsc_module.resolve(),
                 args.libkss_module.resolve()], 'compile_render.log')
            actual = out / 'actual'
            run([sys.executable, ROOT / 'vgm2mml.py', vgm, '--outdir', actual,
                 '--dump-passes'], 'reparse.log')
        diffs = compare_directories(reference, actual, stem, args.offset_ticks, args.boundary_tolerance)
        fields = ['chip', 'ch', 'tick_start', 'tick_end', 'actual_tick_start', 'kind',
                  'expected_period', 'actual_period', 'expected_csv_line', 'actual_csv_line']
        with open(out / 'pitch_diff.csv', 'w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(diffs)
        counts = {kind: sum(d['tick_end'] - d['tick_start'] for d in diffs if d['kind'] == kind)
                  for kind in ('pitch', 'activity', 'coverage', 'boundary')}
        summary.update(status='different' if diffs else 'exact', difference_ticks=counts,
                       actual=str(Path(actual).resolve()))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        summary['error'] = str(error)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'exact' else 1


if __name__ == '__main__':
    sys.exit(main())
