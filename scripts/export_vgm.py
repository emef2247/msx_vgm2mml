"""Export reconstructed PSG/SCC/OPLL performances directly to VGM, without MGSC."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from musical_conversion import build_plan, source_gd3
from musical_vgm import write_vgm
from mgs_conversion_config import sample_threshold, MgsOptions, add_curve_arguments, curve_option_values
from batch_vgm_to_mgs import discover_inputs, file_digest, package_manifest, prepare_blueprints, publish_bundle, save_json


def parser():
    result = argparse.ArgumentParser(description=__doc__, epilog=(
        'Also writes editable blueprint/<stem>.mml; edited templates are preserved independently.'))
    result.add_argument('input', type=Path, help='VGM/VGZ file or recursive input directory')
    result.add_argument('--outdir', type=Path, help='Output root (default: beside the source)')
    result.add_argument('--timeout', type=int, default=1200, help='Per-input conversion timeout, seconds (default: 1200)')
    result.add_argument('--normalization-ms', type=float, default=8,
                        help='Shared musical clock-fit tolerance in milliseconds (default: 8)')
    result.add_argument('--fm-state-ms', type=float, default=24,
                        help='OPLL internal pitch/volume threshold when normalization is accepted (default: 24)')
    add_curve_arguments(result)
    result.add_argument('--no-normalization', action='store_true', help='Use the existing unnormalized musical clock')
    curves = result.add_mutually_exclusive_group()
    curves.add_argument('--software-volume-curves', action='store_true', default=True,
                        help='Join supported exact PSG/SCC software volume curves (default: enabled)')
    curves.add_argument('--no-software-volume-curves', dest='software_volume_curves', action='store_false',
                        help='Retain the earlier score partitions and their volume controls')
    parts = result.add_mutually_exclusive_group()
    parts.add_argument('--psg-melody-only', dest='psg_part', action='store_const', const='melody', default='all')
    parts.add_argument('--psg-rhythm-only', dest='psg_part', action='store_const', const='rhythm')
    result.add_argument('--enhance-drums', '--enhance-rhythm', dest='enhance_drums', action='store_true')
    result.add_argument('--song-loop', choices=('none', 'source'), default='none',
                        help='Finite reconstructed performance, or validated declared source loop (default: none)')
    result.add_argument('--force', action='store_true', help='Apply reviewed unsupported-source omission rules')
    result.add_argument('--dump-passes', action='store_true', help='Also retain inherited analysis pass CSVs')
    result.add_argument('--_worker', type=Path, help=argparse.SUPPRESS)
    return result


def _worker(args):
    folder = args._worker
    stem = args.input.stem
    target = folder / (stem + '.reconstructed.vgm')
    target.unlink(missing_ok=True)
    stage = 'interpretation'
    try:
        options = MgsOptions(software_volume_curves=args.software_volume_curves, **curve_option_values(args))
        plan, report = build_plan(args.input, folder, stem,
            normalization_ms=args.normalization_ms, fm_state_ms=args.fm_state_ms,
            normalize_lengths=not args.no_normalization,
            software_volume_curves=args.software_volume_curves, force=args.force,
            psg_part=args.psg_part, enhance_drums=args.enhance_drums,
            song_loop=args.song_loop, dump_passes=args.dump_passes,
            score_guided_loops=options.score_guided_loops, curve_approx_options=options.curve_approx_options)
        from musical_blueprint import write_blueprint
        report['blueprint'] = write_blueprint(plan, folder, stem)
        stage = 'vgm_generation'
        writes = write_vgm(plan, target, gd3=source_gd3(args.input),
                           mapping_path=folder / f'{stem}.vgm.writes.csv')
        report.update(status='success', stage='complete', vgm_bytes=target.stat().st_size,
                      target_writes=len(writes), target_sha256=file_digest(target))
        save_json(folder / 'report.json', report)
        return 0
    except Exception as error:
        target.unlink(missing_ok=True)
        blueprint = locals().get('report', {}).get('blueprint', {})
        report = dict(status='conversion_failed' if stage == 'interpretation' else 'vgm_generation_failed',
                      stage=stage, detail=str(error), error_type=type(error).__name__,
                      mml_generated=False, compiler_invoked=False, blueprint=blueprint)
        save_json(folder / 'report.json', report)
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1


def _flags(args):
    result = ['--normalization-ms', str(args.normalization_ms), '--fm-state-ms', str(args.fm_state_ms),
              '--song-loop', args.song_loop]
    for flag in ('force', 'dump_passes', 'enhance_drums', 'no_normalization'):
        if getattr(args, flag):
            result.append('--' + flag.replace('_', '-'))
    if not args.software_volume_curves:
        result.append('--no-software-volume-curves')
    if args.psg_part != 'all':
        result.append('--psg-' + args.psg_part + '-only')
    options = MgsOptions(software_volume_curves=args.software_volume_curves, **curve_option_values(args))
    result.extend(options.curve_cli_args())
    return result


def run_export(args):
    source = args.input.resolve()
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    if args.timeout <= 0:
        raise ValueError('--timeout must be positive')
    sample_threshold(args.normalization_ms, '--normalization-ms')
    sample_threshold(args.fm_state_ms, '--fm-state-ms')
    MgsOptions(software_volume_curves=args.software_volume_curves, **curve_option_values(args))
    source_root = source.parent if source.is_file() else source
    output = args.outdir.resolve() if args.outdir else source_root
    if args.outdir and (source == output or source in output.parents or output in source.parents):
        raise ValueError('Explicit input/output trees must be separate; omit --outdir for adjacent output')
    files = discover_inputs(source, adjacent=args.outdir is None)
    if not files:
        raise ValueError('No VGM/VGZ inputs found')
    mode = '' if args.psg_part == 'all' else 'psg_' + args.psg_part
    routes, seen = [], set()
    # All ownership checks precede the first publication or input copy.
    for path in files:
        relative = path.relative_to(source_root)
        if any(part.casefold() in ('_diagnostics', '_source_inputs', 'tracks', 'blueprint', 'psg_melody', 'psg_rhythm')
               for part in relative.parts[:-1]):
            raise ValueError(f'Reserved generated output route in input: {relative}')
        package = output / mode / relative.parent
        target = package / 'tracks' / (path.stem + '.vgm')
        blueprint = package / 'blueprint' / (path.stem + '.mml')
        diagnostic = package / '_diagnostics' / path.stem
        staged = package / '_source_inputs' / path.name
        key = str(target).casefold()
        if key in seen:
            raise ValueError(f'Colliding VGM target: {target}')
        seen.add(key)
        for candidate in (target, blueprint, diagnostic, staged):
            if not candidate.resolve().is_relative_to(output):
                raise ValueError(f'Output route escapes requested directory: {candidate}')
        state = package_manifest(package)
        previous = state['entries'].get(path.name, {})
        if previous.get('source_path') and Path(previous['source_path']).resolve() != path.resolve():
            raise ValueError(f'Package belongs to a different source: {path}')
        if target.exists() and previous.get('published', {}).get(target.relative_to(package).as_posix()) != file_digest(target):
            raise ValueError(f'Final VGM is unowned or modified: {target}')
        if staged.exists() and previous.get('staged_sha256') != file_digest(staged):
            raise ValueError(f'Staged source is unowned or modified: {staged}')
        routes.append((path, relative, package, target, diagnostic, staged))
    rows = []
    for path, relative, package, target, folder, staged in routes:
        folder.mkdir(parents=True, exist_ok=True)
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, staged)
        command = [sys.executable, str(Path(__file__).resolve()), str(staged), '--_worker', str(folder), *_flags(args)]
        log = folder / 'convert.log'
        (folder / 'report.json').unlink(missing_ok=True)
        try:
            process = subprocess.run(command, capture_output=True, timeout=args.timeout, cwd=ROOT)
            log.write_bytes(process.stdout + process.stderr)
            if not (folder / 'report.json').is_file():
                report = dict(status='conversion_failed', detail=(
                    'Worker exited unsuccessfully' if process.returncode else 'Worker produced no report'))
                save_json(folder / 'report.json', report)
            else:
                report = json.loads((folder / 'report.json').read_text())
            if process.returncode and report.get('status') == 'success':
                report.update(status='conversion_failed', detail='Worker exited unsuccessfully')
        except subprocess.TimeoutExpired as error:
            log.write_bytes((error.stdout or b'') + (error.stderr or b''))
            report = dict(status='timeout', stage='interpretation', detail=f'Conversion exceeded {args.timeout} seconds')
            save_json(folder / 'report.json', report)
        except (OSError, ValueError) as error:
            report = dict(status='conversion_failed', detail=str(error))
            save_json(folder / 'report.json', report)
        state = package_manifest(package)
        entry = dict(state['entries'].get(path.name, {}))
        entry.update(source_path=str(path), staged_sha256=file_digest(staged),
                     diagnostics=folder.relative_to(package).as_posix())
        publications = []
        published = dict(entry.get('published', {}))
        if report['status'] == 'success':
            generated = folder / (path.stem + '.reconstructed.vgm')
            published[target.relative_to(package).as_posix()] = file_digest(generated)
            entry.update(source_sha256=file_digest(path), published=published,
                         publication_status='success', output='reconstructed_vgm')
            publications.append((generated, target))
        else:
            entry.update(last_status=report['status'])
        bp_publish, bp_delete, published, blueprint_status, blueprint_detail, bp_targets = prepare_blueprints(
            report, folder, path.stem, package, published)
        if bp_targets:
            publications.extend(bp_publish)
            entry.update(published=published, blueprint_source_sha256=file_digest(path))
        state['entries'][path.name] = entry
        if publications:
            publish_bundle(publications, package / 'listening_manifest.json', state, folder, deletions=bp_delete)
        else:
            save_json(package / 'listening_manifest.json', state)
        row = dict(input=relative.as_posix(), status=report['status'],
                   vgm=target.relative_to(output).as_posix() if target.exists() else '',
                   diagnostics=(folder / 'report.json').relative_to(output).as_posix(),
                   units=report.get('units', ''), controls=report.get('controls', ''),
                    blueprint=bp_targets[0].relative_to(output).as_posix() if bp_targets else '',
                    blueprint_files=[target.relative_to(output).as_posix() for target in bp_targets],
                    blueprint_status=blueprint_status, blueprint_detail=blueprint_detail,
                   vgm_bytes=report.get('vgm_bytes', ''), detail=report.get('detail', ''))
        rows.append(row)
        print(f"{relative.as_posix()}: {row['status']}" + (': ' + row['detail'] if row['detail'] else ''), flush=True)
        if blueprint_status == 'blocked':
            print('Blueprint update skipped: ' + blueprint_detail, flush=True)
        selected = [r for r in rows if (output / r['diagnostics']).parent.parent.parent == package]
        _results(package, selected)
    _results(output / mode / '_diagnostics', rows)
    print(f"{sum(row['status'] == 'success' for row in rows)}/{len(rows)} exported; results: {output / mode / '_diagnostics/results.csv'}")
    return rows


def _results(folder, rows):
    folder.mkdir(parents=True, exist_ok=True)
    save_json(folder / 'results.json', rows)
    with (folder / 'results.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    args = parser().parse_args(argv)
    if args._worker:
        return _worker(args)
    try:
        rows = run_export(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return int(any(row['status'] != 'success' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
