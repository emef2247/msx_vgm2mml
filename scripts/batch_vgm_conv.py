"""Generate external vgm-conv comparisons beside the additive listening outputs."""
import argparse
import csv
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--vgm-conv', default='vgm-conv', help='Executable or bin/cmd.js path')
    parser.add_argument('--node', default='node', help='Node executable when using a .js entry point')
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    if not args.input.exists():
        parser.error('Input does not exist')
    executable = shutil.which(args.vgm_conv) or args.vgm_conv
    command = [executable]
    if str(executable).lower().endswith('.js'):
        command = [args.node, executable]
    files = sorted(p for p in args.input.rglob('*') if p.suffix.lower() in ('.vgm', '.vgz')) if args.input.is_dir() else [args.input]
    if not files:
        parser.error('No VGM inputs found')
    rows = []
    for source in files:
        relative = source.relative_to(args.input) if args.input.is_dir() else Path(source.name)
        out = args.outdir / relative.with_suffix('') if args.input.is_dir() else args.outdir
        out.mkdir(parents=True, exist_ok=True)
        destination = out / (source.stem + '.vgm-conv.vgm')
        row = dict(input=str(source), status='failed', output=str(destination), detail='')
        try:
            # Write a temporary result so a failed invocation cannot publish partial VGM.
            with tempfile.TemporaryDirectory(prefix='vgm-conv-') as temp:
                result = Path(temp) / 'comparison.vgm'
                run = subprocess.run(command + ['-f', 'ay8910', '-t', 'ym2151', str(source.resolve()), '-o', str(result)], capture_output=True, timeout=args.timeout)
                log = run.stdout.decode('utf-8', errors='replace') + run.stderr.decode('utf-8', errors='replace')
                (out / (source.stem + '.vgm-conv.log')).write_text(log, encoding='utf-8')
                if run.returncode or not result.is_file():
                    raise RuntimeError(f'vgm-conv exit={run.returncode}; see conversion log')
                shutil.copyfile(result, destination)
            row['status'] = 'converted'
        except subprocess.TimeoutExpired:
            row.update(status='timeout', detail=f'Exceeded {args.timeout:g} seconds')
        except (OSError, RuntimeError) as error:
            row['detail'] = str(error)
        rows.append(row)
        print(f"{relative}: {row['status']} {row['detail']}")
    with (args.outdir / 'vgm-conv-results.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return int(any(row['status'] != 'converted' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
