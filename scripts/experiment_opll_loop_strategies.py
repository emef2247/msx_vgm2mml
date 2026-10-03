"""Compare actual OPLL loop projections; other chip/envelope paths stay identical."""
import argparse
import csv
from functools import partial
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
import opll_target
from mml_sync import analyze_mml, _leaves


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--strategies', nargs='+', choices=('current', 'immediate', 'retained', 'structural'),
                        default=['current', 'structural'])
    args = parser.parse_args()
    original, argv = opll_target.render, sys.argv[:]
    reports, streams = [], []
    try:
        strategies = ['current'] + [s for s in dict.fromkeys(args.strategies) if s != 'current']
        for strategy in strategies:
            opll_target.render = (original if strategy == 'current' else
                                  partial(original, source_loops=True, source_strategy=strategy))
            output = args.outdir / strategy
            sys.argv = ['vgm2mml.py', str(args.input), '--outdir', str(output), '--dump-passes']
            runpy.run_path(str(ROOT / 'vgm2mml.py'), run_name='__main__')
            mml = output / (args.input.stem + '.mml')
            text = mml.read_text(encoding='cp932')
            streams.append({ch: tuple((n.text, n.start, n.end) for n in _leaves(nodes))
                            for ch, nodes in analyze_mml(text)[0].items()})
            loops = [row for path in output.glob('*.opll.*.source_loops.projection.csv')
                     for row in csv.DictReader(path.open(encoding='utf-8'))]
            row = dict(strategy=strategy, mml_characters=len(text), mml_bytes=mml.stat().st_size,
                       code_characters=len(''.join(line.split(';', 1)[0].strip() for line in text.splitlines())),
                       projected_loop_occurrences=len(loops) if strategy != 'current' else None,
                       applied_loop_occurrences=sum(r['status'] == 'applied' for r in loops) if strategy != 'current' else None,
                       maximum_applied_depth=max((int(r['depth']) + 1 for r in loops if r['status'] == 'applied'), default=0) if strategy != 'current' else None,
                       final_expanded_timed_commands_equal=streams[-1] == streams[0])
            if args.mgsc_module:
                result = subprocess.run([args.node, str(ROOT/'scripts/compile_mgs.mjs'),
                                         str(mml), str(mml.with_suffix('.mgs')),
                                         str(args.mgsc_module.resolve())], capture_output=True, text=True,
                                         encoding='utf-8', errors='replace', timeout=60)
                log = result.stdout + result.stderr
                (output/'compile.log').write_text(log, encoding='utf-8')
                row['compile_success'] = result.returncode == 0
                row['buffer_error'] = 'buffer full' in log.lower()
                row['compile_status'] = ('success' if result.returncode == 0 else
                                         'buffer_error' if row['buffer_error'] else 'compile_failed')
            reports.append(row)
    finally:
        opll_target.render, sys.argv = original, argv
    eligible = [r for r in reports if r.get('compile_success') and r['final_expanded_timed_commands_equal']]
    summary = dict(input=str(args.input), normalization=False,
                   scope='Only OPLL melodic loop strategy changes; PSG/SCC/envelopes/rhythm/macros use the same pipeline',
                   evaluation='Minimize MML characters among successfully compiled, equivalent outputs; buffer_error is a failure',
                   structural_limits='All exact adjacent repeats over the full unit sequence; no phrase/depth/repeat cap',
                   legacy_experiment_limits=dict(max_phrase_units=128, max_depth=3),
                   shortest_compilable=min(eligible, key=lambda r:r['mml_characters'])['strategy'] if eligible else None,
                   runs=reports)
    (args.outdir/'comparison.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if any(not r['final_expanded_timed_commands_equal'] or r.get('compile_success') is False for r in reports):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
