"""Create note-based MDX alongside existing additive target diagnostic output."""
import argparse
import csv
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'py'), str(ROOT)]
from additive_mdx_notes import render, verify
from scripts.verify_opm_mdx_roundtrip import generate
from opm_roundtrip import controls


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path, help='Existing .opm_writes.csv or output directory')
    p.add_argument('--generator', type=Path, required=True)
    args = p.parse_args()
    if not args.generator.is_file():
        p.error("Generator does not exist; specify the built mdx-fixture-generator executable")
    files = sorted(args.input.rglob('*.opm_writes.csv')) if args.input.is_dir() else [args.input]
    if not files:
        p.error('No additive write plans found')
    failed = 0
    for path in files:
        stem = path.name.removesuffix('.opm_writes.csv')
        try:
            settings = json.loads(path.with_name(stem+'.opm_target.json').read_text())
            with path.open(newline='', encoding='utf-8') as f:
                writes = [SimpleNamespace(**{k:int(row[k]) for k in ('target_ch','mdx_tick','register','data')}) for row in csv.DictReader(f)]
            end = settings['end_mdx_tick']
            text, mapping = render(writes, end, stem+' - additive MDX notes')
            mml = path.with_name(stem+'.notes.mdx.mml')
            mml.write_text(text, encoding='utf-8')
            with path.with_name(stem+'.notes.mapping.csv').open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(mapping[0]) if mapping else ['track','start_tick','end_tick','voice','volume','pan','kc','kf'])
                writer.writeheader(); writer.writerows(mapping)
            actual = generate(args.generator.resolve(), mml, path.parent, stem+'.notes', max_ticks=end+1)
            report = verify(writes, end, controls(actual))
            from opm_mdx import projected_samples
            report["end_time_matches"] = actual.source_end_vgmticks == projected_samples(end)
            report["passed"] = report["passed"] and report["end_time_matches"]
            path.with_name(stem+'.notes.verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            print(f"{stem}: {'verified' if report['passed'] else 'mismatch'}")
            failed += not report['passed']
        except (ValueError, RuntimeError, OSError, KeyError, subprocess.TimeoutExpired) as error:
            failed += 1; print(f'{stem}: failed {error}')
    return int(bool(failed))

if __name__ == '__main__':
    raise SystemExit(main())
