"""Recursively convert VGM files and compile MGS, retaining per-file failures."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import shutil
import sys
import struct
import math

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_io import read_vgm_bytes
from check_opll_key_edges import compare_files

KEYON_FIELDS = ('reference_keyon', 'actual_keyon', 'missing_keyon', 'extra_keyon')


def check_keyons(source, mgs, folder, node, module, timeout):
    """Export existing MGS once and compare counts, without regenerating MML."""
    actual = folder / (source.stem + '.roundtrip.vgm')
    actual.unlink(missing_ok=True)
    raw = read_vgm_bytes(source)
    samples = struct.unpack_from('<I', raw, 0x18)[0]
    if not samples:
        raise ValueError('Source VGM has no declared duration; key-on comparison skipped')
    # Allow driver timing/initialization overhead; libkss stops at song end.
    duration = math.ceil(samples / 44100 * 1250 + 2000)
    command = [node, str(ROOT / 'scripts/mgs_to_vgm.mjs'), str(mgs), str(actual), str(duration)]
    if module:
        command.append(str(module.resolve()))
    proc = subprocess.run(command, capture_output=True, timeout=timeout)
    text = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
    (folder / 'keyon.log').write_text(text, encoding='utf-8')
    if proc.returncode or not actual.is_file() or not actual.stat().st_size:
        raise ValueError(text or 'MGS export produced no VGM')
    exported = read_vgm_bytes(actual)
    exported_samples = struct.unpack_from('<I', exported, 0x18)[0]
    if exported_samples / 44.1 >= duration - 20:
        raise ValueError('MGS export reached its duration limit; comparison is incomplete')
    return compare_files(source, actual, folder / 'keyon', segment_dumps=False)


def run_batch(source, output, module=None, node='node', timeout=300, mgsc=None, alloc=None,
              keyon=True, libkss_module=None, normalize_lengths=False, enhance_macros=True, legacy_loops=False):
    source, output = source.resolve(), output.resolve()
    if source == output or output in source.parents or source in output.parents:
        raise ValueError('Input and output trees must be separate')
    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in ('.vgm', '.vgz'))
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
    keyon_setup_error = ''
    if keyon:
        check = [node, str(ROOT / 'scripts/mgs_to_vgm.mjs'), '--check', '-', '-']
        if libkss_module:
            check.append(str(libkss_module.resolve()))
        try:
            setup = subprocess.run(check, capture_output=True, timeout=timeout)
            if setup.returncode:
                keyon_setup_error = (setup.stdout + setup.stderr).decode('utf-8', errors='replace')
                keyon_setup_error = keyon_setup_error or 'libkss setup failed'
        except (OSError, subprocess.TimeoutExpired) as error:
            keyon_setup_error = str(error)
        (output / 'keyon_setup.log').write_text(keyon_setup_error or 'libkss available\n', encoding='utf-8')
        if keyon_setup_error:
            print('KEYON comparison unavailable: ' + keyon_setup_error, file=sys.stderr)
    rows = []
    for path in files:
        relative = path.relative_to(source)
        folder = output / relative.parent / relative.name
        folder.mkdir(parents=True, exist_ok=True)
        mml, mgs = folder / (path.stem+'.mml'), folder / (path.stem+'.mgs')
        # Never let an earlier successful artifact look like this run's success.
        for artifact in (mml, mgs, folder / (path.stem + '.roundtrip.vgm')):
            artifact.unlink(missing_ok=True)
        row = dict(input=str(relative), status='conversion_failed', mgs='', log='')
        row.update(dict.fromkeys(KEYON_FIELDS, ''))
        row.update(keyon_status='not_compiled' if keyon else 'disabled', keyon_error='')
        stages = [('convert', [sys.executable, str(ROOT/'vgm2mml.py'), str(path), '--outdir', str(folder)]),
                  ('compile', [native, str(mml), str(mgs)] if native else [node, str(ROOT/'scripts/compile_mgs.mjs'), str(mml), str(mgs)] +
                   ([str(module.resolve())] if module else []))]
        if alloc is not None:
            stages[0][1].extend(['--alloc', alloc])
        if normalize_lengths:
            stages[0][1].append('--normalize-lengths')
        if not enhance_macros:
            stages[0][1].append('--legacy-macros')
        if legacy_loops:
            stages[0][1].append('--legacy-loops')
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
            if keyon:
                if keyon_setup_error:
                    row.update(keyon_status='unavailable', keyon_error=keyon_setup_error)
                else:
                    try:
                        row.update(check_keyons(path, mgs, folder, node, libkss_module, timeout),
                                   keyon_status='compared')
                    except (OSError, ValueError, struct.error, subprocess.TimeoutExpired) as error:
                        row.update(keyon_status='error', keyon_error=str(error))
                        (folder / 'keyon.log').write_text(str(error), encoding='utf-8')
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
    parser.add_argument('--alloc', help='Allocation overrides forwarded to every conversion')
    parser.add_argument('--normalize-lengths', action='store_true',
                        help='Enable optional musical duration normalization for every conversion')
    parser.add_argument('--enhance-macros', action='store_true', default=True,
                        help='Enable enhanced macros (now the default)')
    parser.add_argument('--legacy-macros', dest='enhance_macros', action='store_false',
                        help='Use the previous macro compressor')
    parser.add_argument('--legacy-loops', action='store_true',
                        help='Use the previous OPLL loop projection')
    parser.add_argument('--skip-keyon-counts', action='store_true', help='Disable MGS playback and OPLL key-on comparison')
    parser.add_argument('--libkss-module', type=Path, help='Explicit libkss-js entry point for MGS export')
    args = parser.parse_args()
    try:
        results = run_batch(args.input_dir, args.outdir, args.mgsc_module, args.node, args.timeout, args.mgsc, args.alloc,
                            keyon=not args.skip_keyon_counts, libkss_module=args.libkss_module,
                            normalize_lengths=args.normalize_lengths, enhance_macros=args.enhance_macros, legacy_loops=args.legacy_loops)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error)+'\n')
    sys.exit(0 if all(r['status'] == 'success' and r['keyon_status'] in ('compared', 'disabled') for r in results) else 1)
