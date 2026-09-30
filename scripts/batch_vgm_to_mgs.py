"""Recursively convert VGM files and compile MGS, retaining per-file failures."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_batch(source, output, module=None, node='node', timeout=300, mgsc=None):
    source, output = source.resolve(), output.resolve()
    if source == output or output in source.parents or source in output.parents:
        raise ValueError('Input and output trees must be separate')
    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() == '.vgm')
    if not files:
        raise ValueError('No VGM files found')
    native = shutil.which(str(mgsc)) if mgsc else (None if module else shutil.which('mgsc'))
    if mgsc and not native:
        raise RuntimeError(f'Native MGSC executable not found: {mgsc}')
    if native:
        print(f'Compiler: {native}', flush=True)
    else:
        check = [node, str(ROOT/'scripts/compile_mgs.mjs'), '--check', '-'] + ([str(module.resolve())] if module else [])
        try:
            setup = subprocess.run(check, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f'MGSC setup failed before conversion: {error}') from error
        if setup.returncode:
            raise RuntimeError('MGSC setup failed before conversion:\n' +
                               (setup.stdout+setup.stderr).decode('utf-8', errors='replace'))
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in files:
        relative = path.relative_to(source)
        folder = output / relative.parent / relative.name
        folder.mkdir(parents=True, exist_ok=True)
        mml, mgs = folder / (path.stem+'.mml'), folder / (path.stem+'.mgs')
        # Never let an earlier successful artifact look like this run's success.
        for artifact in (mml, mgs):
            artifact.unlink(missing_ok=True)
        row = dict(input=str(relative), status='conversion_failed', mgs='', log='')
        stages = [('convert', [sys.executable, str(ROOT/'vgm2mml.py'), str(path), '--outdir', str(folder)]),
                  ('compile', [native, str(mml), str(mgs)] if native else [node, str(ROOT/'scripts/compile_mgs.mjs'), str(mml), str(mgs)] +
                   ([str(module.resolve())] if module else []))]
        for stage, command in stages:
            log = folder / (stage+'.log')
            row['log'] = str(log.relative_to(output))
            try:
                proc = subprocess.run(command, capture_output=True, timeout=timeout)
                text = (proc.stdout+proc.stderr).decode('utf-8', errors='replace')
                log.write_text(text, encoding='utf-8')
                if proc.returncode or (stage == 'compile' and (not mgs.exists() or mgs.stat().st_size == 0)):
                    row['status'] = ('conversion_failed' if stage == 'convert' else
                                     'compiler_setup_error' if not native and proc.returncode == 2 else
                                     'buffer_error' if 'buffer full' in text.lower() else 'compile_failed')
                    if stage == 'compile':
                        print(text or 'MGSC produced no MGS output', file=sys.stderr)
                        mgs.unlink(missing_ok=True)
                    break
            except (OSError, subprocess.TimeoutExpired) as error:
                log.write_text(str(error), encoding='utf-8')
                row['status'] = stage+'_error'
                break
        else:
            row.update(status='success', mgs=str(mgs.relative_to(output)))
        rows.append(row)
        with (output/'results.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader(); writer.writerows(rows)
        print(relative, row['status'], flush=True)
    (output/'results.json').write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--mgsc', help='Native MGSC executable (default: PATH)')
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    try:
        results = run_batch(args.input_dir, args.outdir, args.mgsc_module, args.node, args.timeout, args.mgsc)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error)+'\n')
    sys.exit(0 if all(r['status'] == 'success' for r in results) else 1)
