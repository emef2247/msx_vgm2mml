"""Regenerate original public OPM fixtures using an external MDX compiler."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/public/opm/from_mdx'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    suffix = '.exe' if sys.platform == 'win32' else ''
    parser.add_argument('--generator', type=Path, default=ROOT / 'scripts/mdx_fixture_generator/target/release' / ('mdx-fixture-generator' + suffix))
    parser.add_argument('--case', action='append', help='Only regenerate this case (repeatable)')
    args = parser.parse_args()
    if not args.generator.is_file():
        parser.error('Build scripts/mdx_fixture_generator with cargo build --release --locked, or pass --generator')
    cases = sorted(p for p in FIXTURES.iterdir() if p.is_dir())
    if args.case:
        known = {p.name for p in cases}
        unknown = set(args.case) - known
        if unknown:
            parser.error('Unknown case: ' + ', '.join(sorted(unknown)))
        cases = [p for p in cases if p.name in args.case]
    failed = False
    for case in cases:
        source = case / 'reference' / (case.name + '.mml')
        mdx = case / 'reference' / (case.name + '.mdx')
        vgm = case / (case.name + '.vgm')
        try:
            run = subprocess.run([str(args.generator.resolve()), str(source), str(mdx), str(vgm)],
                                 capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            print(case.name + ': generation_timeout', file=sys.stderr)
            failed = True
            continue
        if run.returncode:
            print(case.name + ': generation_failed', file=sys.stderr)
            print(run.stdout + run.stderr, file=sys.stderr)
            failed = True
        else:
            print(case.name + ': generated')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
