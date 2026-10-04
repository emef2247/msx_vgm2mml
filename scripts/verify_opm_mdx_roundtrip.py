"""VGM -> OPM Segments -> MDX MML -> external MDX/VGM -> OPM Segments."""
import argparse
import csv
import json
from pathlib import Path
import struct
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opm import build_segments
from opm_roundtrip import controls, compare
from vgm_io import read_vgm_bytes
from vgm_reader import _OpmTrace, parse_vgm
from opm_to_mdx_mml import convert


def source_files(path):
    if not path.is_dir():
        return [path]
    # Expected replay evidence must not become a new source fixture.
    return sorted(p for p in path.rglob('*')
                  if p.is_file() and p.suffix.lower() in ('.vgm', '.vgz')
                  and not {'reference', 'mdx_roundtrip'}.intersection(p.relative_to(path).parts))


def source_facts(path):
    raw = read_vgm_bytes(path)
    if len(raw) < 0x40 or raw[:4] != b'Vgm ':
        raise ValueError('Not a complete VGM header')
    # Reuse the native reader's version-aware clock/variant interpretation.
    trace = _OpmTrace(raw, struct.unpack_from('<I', raw, 8)[0])
    return dict(clock_hz=trace.clock_hz, chip_type=trace.chip_type, dual_chip=trace.dual_chip)


def generate(generator, mml, folder, stem, *, max_ticks=None):
    mdx, vgm = folder / (stem + '.mdx'), folder / (stem + '.vgm')
    command = [str(generator), str(mml), str(mdx), str(vgm)]
    if max_ticks is not None:
        command.extend(['--max-ticks', str(max_ticks)])
    log = folder / (stem + '.compile.log')
    try:
        run = subprocess.run(command, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=180)
    except subprocess.TimeoutExpired as error:
        def decoded(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        log.write_text(decoded(error.stdout) + decoded(error.stderr)
                       + '\nExternal compiler/player exceeded 180 seconds\n', encoding='utf-8')
        raise
    log.write_text(run.stdout + run.stderr, encoding='utf-8')
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    metadata = {}
    parse_vgm(str(vgm), str(folder / (stem + '_segments')), opm_metadata=metadata, dump_opm_segments=True)
    if metadata['clock_hz'] != 4000000:
        raise ValueError('Returned VGM does not declare the required 4 MHz OPM clock')
    return build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks'])


def save_results(folder, rows):
    (folder / 'results.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (folder / 'results.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='OPM VGM or directory to scan recursively')
    parser.add_argument('--outdir', type=Path, default=ROOT / 'outputs/opm/mdx_roundtrip')
    suffix = '.exe' if sys.platform == 'win32' else ''
    parser.add_argument('--generator', type=Path, default=ROOT / 'scripts/mdx_fixture_generator/target/release' / ('mdx-fixture-generator' + suffix))
    args = parser.parse_args()
    generator = args.generator.resolve()
    if not generator.is_file():
        parser.error('Build the external MDX fixture generator or pass --generator')
    args.outdir.mkdir(parents=True, exist_ok=True)
    baseline_dir = args.outdir / '_compiler_initialization'
    baseline_dir.mkdir(exist_ok=True)
    baseline_mml = baseline_dir / 'initialization.mml'
    baseline_mml.write_text('#title "Compiler initialization"\nA @t255 r%1\n', encoding='utf-8')
    initialization = controls(generate(generator, baseline_mml, baseline_dir, 'initialization'))
    if any(sample != 0 or reg == 8 for sample, reg, data in initialization):
        raise ValueError('Compiler baseline contains timed controls or Key writes')
    sources = source_files(args.input)
    if not sources:
        parser.error('No input VGM found')
    rows = []
    for source in sources:
        relative = source.relative_to(args.input) if args.input.is_dir() else Path(source.name)
        folder = args.outdir / relative.with_suffix('')
        folder.mkdir(parents=True, exist_ok=True)
        row = {'input': str(relative), 'status': 'conversion_failed'}
        try:
            row.update(source_facts(source))
            if row['clock_hz'] != 4000000 or row['chip_type'] != 'YM2151' or row['dual_chip']:
                row['status'] = 'unsupported_target'
                raise ValueError('MDX control replay requires one 4 MHz YM2151; source clock/state is not retuned')
            mml, source_analysis, projection = convert(source, folder, dump_passes=True)
            returned = generate(generator, mml, folder, 'returned', max_ticks=max(2, projection.end_mdx_tick + 1))
            result = compare(projection, source_analysis.segments, returned, initialization=initialization)
            row.update(result)
            row.update(projection.timing_report())
            row['status'] = 'success' if result['passed'] else 'comparison_failed'
        except subprocess.TimeoutExpired:
            row['status'] = 'compile_timeout'
            row['error'] = 'External compiler exceeded 180 seconds'
        except (ValueError, RuntimeError, OSError) as error:
            row['error'] = str(error)
        for label, path in [('mml', folder / (source.stem + '.mdx.mml')),
                            ('mdx', folder / 'returned.mdx'), ('vgm', folder / 'returned.vgm'),
                            ('compile_log', folder / 'returned.compile.log')]:
            if path.is_file():
                row[label] = str(path.resolve())
        (folder / 'comparison.json').write_text(json.dumps(row, indent=2) + '\n', encoding='utf-8')
        if row.get('error'):
            (folder / 'conversion.log').write_text(row['error'] + '\n', encoding='utf-8')
        rows.append(row)
        print(str(relative) + ': ' + row['status'], flush=True)
        save_results(args.outdir, rows)
    return int(any(row['status'] != 'success' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
