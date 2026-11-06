#!/usr/bin/env python3
"""Export VGM like export_mgs.py, with OPN2 sources routed to target VGMs.

This is export_mgs.py plus one route. ``--target`` names the
route: ``msx-music-scc`` is the standard export_mgs behaviour
(MGS on MSX-MUSIC + SCC). OPN2 (YM2612) sources have no such
route; they publish an MSX cartridge target VGM instead, with
``--target`` selecting the composition: ``makoto`` (default
for OPN2 sources) is the OPNA Sound Cartridge alone, ``sfg01``
is the OPM cartridge plus the OPNA cartridge for SSG +
ADPCM-B. ``--dac`` picks the DAC lane's Delta-T destination
and ``--layered`` additionally layers the FM part onto both
FM sections. Products, diagnostics, staged sources, results
and the ownership manifest follow the export_mgs layout:
tracks/ holds the products, everything else lives under
_diagnostics/<stem>/.
"""
import csv
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'py'))

import export_mgs
from batch_vgm_to_mgs import (KEYON_FIELDS, discover_inputs, file_digest,
                              package_manifest, publish_bundle, run_batch,
                              save_json, save_package_results)
from mgs_conversion_config import sample_threshold
from native_imports import inspect_source
from opn2_target_vgm import convert as convert_target_vgm

TARGET_PRODUCTS = ('{stem}.target.vgm', '{stem}.layer.target.vgm')
SD_PRODUCTS = ('{stem}/makoto/{stem}.vgm', '{stem}/sfg01/dac_makoto/{stem}.vgm',
               '{stem}/sfg01/dac_y8950/{stem}.vgm', '{stem}/layered/{stem}.vgm',
               '{stem}/opm4mhz/{stem}.vgm')


def _sd_names(stem):
    return [pattern.format(stem=stem) for pattern in SD_PRODUCTS]


def build_parser():
    parser = export_mgs.build_parser()
    parser.description = __doc__
    parser.epilog = (
        'Also writes musical reference tracks/<stem>.vgm and editable blueprint/<stem>.mml for '
        'the msx-music-scc route. OPN2 (YM2612) sources instead publish '
        'tracks/<stem>.target.vgm (and tracks/<stem>.layer.target.vgm with --layered); '
        'their conversion evidence stays in _diagnostics/<stem>/.')
    parser.add_argument('--target', choices=('msx-music-scc', 'makoto', 'sfg01'),
                        default=None,
                        help='Conversion route: msx-music-scc = MGS on MSX-MUSIC + SCC '
                             '(default for non-OPN2 sources); makoto / sfg01 = MSX cartridge '
                             'target VGM (default for OPN2 sources: makoto)')
    parser.add_argument('--dac', choices=('opna', 'y8950'), default='opna',
                        help='DAC lane destination on the target VGM route: opna = OPNA '
                             'ADPCM-B (default), y8950 = MSX-AUDIO (Y8950) Delta-T unit '
                             '(with --layered the DAC lane always goes to the OPNA)')
    parser.add_argument('--layered', action='store_true',
                        help='On the target VGM route, also publish '
                             '<stem>.layer.target.vgm: the FM part layered onto both FM '
                             'sections (OPM and OPNA) at once')
    parser.add_argument('--sd-layout', action='store_true',
                        help='On the target VGM route, additionally publish every '
                             'cartridge variant in an SD-card tree: '
                             '<stem>/makoto/<stem>.vgm, <stem>/sfg01/dac_makoto/<stem>.vgm, '
                             '<stem>/sfg01/dac_y8950/<stem>.vgm, '
                             '<stem>/layered/<stem>.vgm and '
                             '<stem>/opm4mhz/<stem>.vgm (sfg01 composition with '
                             'the OPM clock at 4 MHz)')
    return parser


def _run_mgs(args, macro_budget, source, outdir):
    """One run_batch call with export_mgs.py's exact forwarding."""
    return run_batch(source, outdir, module=args.mgsc_module,
                     node=args.node, timeout=args.timeout, mgsc=args.mgsc,
                     compiler=args.compiler,
                     alloc=args.alloc, keyon=not args.skip_keyon_counts,
                     libkss_module=args.libkss_module,
                     normalize_lengths=False,
                     score_normalize=args.score_normalize, score_tempo=args.score_tempo,
                     blueprint_score_normalize=True,
                     enhance_macros=args.macro_mode != 'greedy',
                     legacy_loops=args.loop_mode == 'envelope-first',
                     macro_mode=args.macro_mode,
                     loop_mode='score-guided' if args.score_guided_loops else args.loop_mode,
                     force=args.force, fm_state_ms=args.fm_state_ms,
                     normalization_ms=args.normalization_ms, dump_passes=args.dump_passes,
                     enhance_drums=False, psg_part='all',
                     software_volume_curves=args.is_software_volume_curves,
                     score_guided_loops=args.score_guided_loops,
                     macro_definition_budget=macro_budget,
                     nes_balance=args.nes_balance, nes_gain=args.nes_gain,
                     psg_state_ms=None, scc_state_ms=None,
                     curve_volume_error=None, curve_mean_error=None)


def _exit_code(rows):
    return 0 if all(row['status'] == 'success' and row.get('vgm_status') not in ('failed', 'blocked')
                    and row['keyon_status'] in ('compared', 'disabled', 'selection_only', 'projected_source')
                    for row in rows) else 1


def _check_target_ownership(path, package, state):
    """Mirror publication_targets' ownership checks for target products."""
    previous = state['entries'].get(path.name, {})
    owned = previous.get('published', {})
    if not isinstance(owned, dict):
        raise ValueError(f"Invalid listening manifest: {package / 'listening_manifest.json'}")
    for pattern in TARGET_PRODUCTS:
        target = package / 'tracks' / pattern.format(stem=path.stem)
        if target.exists():
            recorded = owned.get(target.relative_to(package).as_posix())
            if not target.is_file() or recorded != file_digest(target):
                raise ValueError(f'Final target is unowned or modified: {target}')
    for name in _sd_names(path.stem):
        target = package / name
        if target.exists():
            recorded = owned.get(name)
            if not target.is_file() or recorded != file_digest(target):
                raise ValueError(f'Final target is unowned or modified: {target}')
    staged = package / '_source_inputs' / path.name
    if staged.exists():
        recorded = previous.get('staged_sha256')
        if not staged.is_file() or recorded != file_digest(staged):
            raise ValueError(f'Staged source is unowned or modified: {staged}')


def _blank_row(path, relative, folder, output, args):
    row = dict(input=str(relative), status='conversion_failed', mml='',
               publication_status='not_attempted', publication_error='', processing_status='',
               mgs='', vgm='', vgm_status='unavailable', vgm_detail='', blueprint='',
               blueprint_files=[], blueprint_midi_files=[], blueprint_status='not_needed',
               blueprint_detail='', log='', detail='', stage='convert', error_code='',
               legacy_status='',
               report=str((folder / 'report.txt').relative_to(output)),
               diagnostics=str((folder / 'report.json').relative_to(output)), force_summary='',
               normalization_status='unavailable', normalization_reason='',
               normalization_ms=args.normalization_ms, fm_state_ms=args.fm_state_ms,
               keyon_status='disabled', keyon_error='')
    row.update(dict.fromkeys(KEYON_FIELDS, ''))
    return row


def _finish_song(path, relative, folder, package, output, adjacent, row, options,
                 summary, publication):
    report = dict(result=dict(row), input_path=str(path), output_root=str(output),
                  adjacent_output=adjacent, options=options, commands=[],
                  logs={'publication': str(folder / 'publication.json')},
                  force=None, summaries={'opn2_target': summary}, publication=publication)
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = [f"{relative}: {row['status']}", f"Stage: {row['stage']}",
             f"Error code: {row['error_code']}", f"Detail: {row['detail']}",
             'Options: ' + json.dumps(options, sort_keys=True),
             'Normalization: ' + row['normalization_status'] + ' ' + row['normalization_reason']]
    lines.extend(name + ' log: ' + value for name, value in report['logs'].items())
    (folder / 'report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    save_package_results(package, output, [row])
    print(f"{relative}: {row['status']}" + (f": {row['detail']}" if row['detail'] else ''),
          flush=True)
    return row


def _export_target(path, relative, output, adjacent, args):
    """Publish one OPN2 source as a cartridge target VGM, export_mgs style."""
    package = output / relative.parent
    folder = package / '_diagnostics' / path.stem
    folder.mkdir(parents=True, exist_ok=True)
    manifest = package / 'listening_manifest.json'
    state = package_manifest(package)
    previous = state['entries'].get(path.name, {})
    staged = package / '_source_inputs' / path.name
    plain_target = package / 'tracks' / (path.stem + '.target.vgm')
    layer_target = package / 'tracks' / (path.stem + '.layer.target.vgm')
    _check_target_ownership(path, package, state)
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, staged)
    current_source_hash = file_digest(path)
    entry = dict(previous, input=path.name, source_path=str(path),
                 staged_input=staged.relative_to(package).as_posix(),
                 staged_sha256=file_digest(staged),
                 diagnostics=folder.relative_to(package).as_posix())
    if not previous.get('published'):
        entry['source_sha256'] = current_source_hash
    if entry['staged_sha256'] != current_source_hash:
        raise ValueError(f'Source changed during staging: {path}')
    state['entries'][path.name] = entry
    save_json(manifest, state)
    previous_state = json.loads(json.dumps(state))
    # Never let an earlier staged product look like this run's success.
    (folder / (path.stem + '.target.vgm')).unlink(missing_ok=True)
    (folder / (path.stem + '.layer.target.vgm')).unlink(missing_ok=True)
    selected = args.target or 'makoto'
    options = dict(route='target_vgm', target=selected, dac=args.dac,
                   layered=args.layered, force=args.force, sd_layout=args.sd_layout)
    row = _blank_row(path, relative, folder, output, args)
    summary, publication = {}, dict(status='not_needed', operations=[])
    # Conversion passes: the selected route runs in the diagnostics
    # folder; --sd-layout adds the passes the selected route does not
    # already cover, each with its own evidence folder. A makoto pass
    # always runs layered in SD mode because it also supplies the
    # layered variant (the layered composition is canonical).
    passes = [dict(key='main', target=selected, dac=args.dac,
                   layered=args.layered or (args.sd_layout and selected == 'makoto'),
                   outdir=folder)]
    if args.sd_layout:
        variants = folder / 'sd_variants'
        if selected != 'makoto':
            passes.append(dict(key='makoto', target='makoto', dac='opna',
                               layered=True, outdir=variants / 'makoto'))
        if (selected, args.dac) != ('sfg01', 'opna'):
            passes.append(dict(key='sfg01_opna', target='sfg01', dac='opna',
                               layered=False, outdir=variants / 'sfg01_opna'))
        if (selected, args.dac) != ('sfg01', 'y8950'):
            passes.append(dict(key='sfg01_y8950', target='sfg01', dac='y8950',
                               layered=False, outdir=variants / 'sfg01_y8950'))
        # opm4mhz is never the selected route (--target has no such
        # choice), so it always needs its own pass: the sfg01
        # composition with the OPM clock at 4 MHz, DAC on the OPNA.
        passes.append(dict(key='opm4mhz', target='opm4mhz', dac='opna',
                           layered=False, outdir=variants / 'opm4mhz'))
    staged_by_key = {}
    failure = None
    for spec in passes:
        spec['outdir'].mkdir(parents=True, exist_ok=True)
        (spec['outdir'] / (path.stem + '.target.vgm')).unlink(missing_ok=True)
        (spec['outdir'] / (path.stem + '.layer.target.vgm')).unlink(missing_ok=True)
        try:
            result = convert_target_vgm(path, spec['outdir'], force=args.force,
                                        layered=spec['layered'], target=spec['target'],
                                        dac=spec['dac'])
        except Exception as error:
            failure = (spec, error)
            break
        staged_by_key[spec['key']] = (spec['outdir'], result)
        if spec['key'] == 'main':
            summary = result
    if failure is not None:
        spec, error = failure
        where = 'conversion' if spec['key'] == 'main' else f"SD variant {spec['key']}"
        row.update(error_code=type(error).__name__, legacy_status='conversion_error',
                   detail=f'{where}: {error}')
    else:
        row.update(status='success', stage='complete')
        products = dict(previous.get('published', {}))
        publications, deletions = [], []

        def publish(staged_file, target_path):
            name = target_path.relative_to(package).as_posix()
            if target_path.exists() and file_digest(target_path) != products.get(name):
                raise ValueError(f'Final target changed during conversion: {target_path}')
            products[name] = file_digest(staged_file)
            publications.append((staged_file, target_path))
            return name

        publish(staged_by_key['main'][0] / (path.stem + '.target.vgm'), plain_target)
        row['vgm'] = str(plain_target.relative_to(output))
        row['vgm_status'] = 'success'
        layer_name = layer_target.relative_to(package).as_posix()
        staged_layer = folder / (path.stem + '.layer.target.vgm')
        if args.layered and staged_layer.is_file():
            publish(staged_layer, layer_target)
        elif layer_target.exists():
            deletions.append(layer_target)
            products.pop(layer_name, None)
        if args.sd_layout:
            def variant_file(key, layer=False):
                outdir = staged_by_key[key][0]
                return outdir / (path.stem + ('.layer.target.vgm' if layer
                                              else '.target.vgm'))

            if selected == 'makoto':
                makoto_file = variant_file('main')
                layered_file = variant_file('main', layer=True)
            else:
                makoto_file = variant_file('makoto')
                layered_file = variant_file('makoto', layer=True)
            opna_file = (variant_file('main') if (selected, args.dac) == ('sfg01', 'opna')
                         else variant_file('sfg01_opna'))
            y8950_file = (variant_file('main') if (selected, args.dac) == ('sfg01', 'y8950')
                          else variant_file('sfg01_y8950'))
            opm4mhz_file = variant_file('opm4mhz')
            sources = dict(zip(_sd_names(path.stem),
                               (makoto_file, opna_file, y8950_file, layered_file,
                                opm4mhz_file)))
            for name, staged_file in sources.items():
                publish(staged_file, package / name)
        else:
            for name in _sd_names(path.stem):
                if name in products:
                    deletions.append(package / name)
                    products.pop(name, None)
        entry.update(published=products, publication_status=row['status'],
                     source_sha256=current_source_hash)
    row['processing_status'] = row['status']
    entry.update(stem=path.stem, status=entry.get('publication_status', row['status']),
                 latest_attempt_status=row['status'],
                 latest_attempt=dict(row, source_sha256=current_source_hash))
    state['entries'][path.name] = entry
    if row['status'] == 'success':
        try:
            publication = publish_bundle(publications, manifest, state, folder,
                                         deletions=deletions)
            row['publication_status'] = 'success'
        except OSError as error:
            publication = dict(status='failed', error=str(error),
                               context=getattr(error, 'publication_context', {}),
                               processing_status=row['status'])
            row.update(status='publication_failed', stage='publish',
                       error_code='publication_error', publication_status='failed',
                       publication_error=str(error),
                       detail=f'Output publication failed after success: {error}',
                       vgm='', vgm_status='publication_failed')
            state = previous_state
            prior = state['entries'][path.name]
            prior.setdefault('status', 'unpublished')
            prior.update(latest_attempt_status=row['status'],
                         latest_attempt=dict(row, source_sha256=current_source_hash))
            try:
                save_json(manifest, state)
            except OSError as manifest_error:
                publication['manifest_error'] = str(manifest_error)
    else:
        save_json(manifest, state)
    (folder / 'publication.json').write_text(json.dumps(publication, indent=2) + '\n',
                                             encoding='utf-8')
    return _finish_song(path, relative, folder, package, output, adjacent, row, options,
                        summary, publication)


def _export_unavailable(path, relative, output, adjacent, args, detail):
    """Record a route that does not exist yet for this source as a failure row."""
    package = output / relative.parent
    folder = package / '_diagnostics' / path.stem
    folder.mkdir(parents=True, exist_ok=True)
    options = dict(route=args.target, target=args.target, dac=args.dac,
                   layered=args.layered, force=args.force, sd_layout=args.sd_layout)
    row = _blank_row(path, relative, folder, output, args)
    row.update(error_code='route_unavailable', legacy_status='conversion_error',
               detail=detail, processing_status='conversion_failed')
    publication = dict(status='not_needed', operations=[])
    (folder / 'publication.json').write_text(json.dumps(publication, indent=2) + '\n',
                                             encoding='utf-8')
    return _finish_song(path, relative, folder, package, output, adjacent, row, options,
                        {}, publication)


def _write_combined_results(output, rows):
    diagnostics = output / '_diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (diagnostics / 'results.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (diagnostics / 'results.json').write_text(json.dumps(rows, indent=2) + '\n',
                                              encoding='utf-8')
    print(f"{sum(row['status'] == 'success' for row in rows)}/{len(rows)} exported; "
          f"results: {diagnostics / 'results.csv'}", flush=True)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.score_guided_loops and args.loop_mode == 'envelope-first':
        parser.error('--score-guided-loops cannot be combined with --envelope-first-loops')
    try:
        sample_threshold(args.fm_state_ms, '--fm-state-ms')
    except ValueError as error:
        parser.exit(2, str(error) + '\n')
    macro_budget = args.macro_definition_budget
    if macro_budget is None and args.compiler == 'mgsc':
        from macro_budget import MGSC_MACRO_DEFINITION_BUDGET
        macro_budget = MGSC_MACRO_DEFINITION_BUDGET
    source = args.input.resolve()
    source_root = source.parent if source.is_file() else source
    adjacent = args.outdir is None
    output = source_root if adjacent else args.outdir.resolve()
    if not adjacent and (source == output or output in source.parents or source in output.parents):
        parser.exit(2, 'Explicit input and output trees must be separate; '
                       'omit --outdir for adjacent output\n')
    files = discover_inputs(source, adjacent=adjacent)
    if not files:
        parser.exit(2, 'No VGM files found\n')
    opn2 = {path: 'opn2' in inspect_source(path)['active_chips'] for path in files}
    cartridge = args.target in ('makoto', 'sfg01')
    try:
        if not any(opn2.values()) and not cartridge:
            # Pure export_mgs behaviour, one batch call on the original arguments.
            return _exit_code(_run_mgs(args, macro_budget, args.input, args.outdir))
        for path in files:
            if opn2[path] and args.target != 'msx-music-scc':
                _check_target_ownership(path, output / path.relative_to(source_root).parent,
                                          package_manifest(output / path.relative_to(source_root).parent))
        rows = []
        for path in files:
            relative = path.relative_to(source_root)
            if opn2[path]:
                if args.target == 'msx-music-scc':
                    rows.append(_export_unavailable(
                        path, relative, output, adjacent, args,
                        'OPN2 sources have no msx-music-scc route; '
                        'use --target makoto or sfg01'))
                else:
                    rows.append(_export_target(path, relative, output, adjacent, args))
            elif cartridge:
                rows.append(_export_unavailable(
                    path, relative, output, adjacent, args,
                    f'--target {args.target} is not available for this source yet; '
                    'only OPN2 sources use the cartridge target VGM route'))
            else:
                rows.extend(_run_mgs(args, macro_budget, path,
                                     None if adjacent else output / relative.parent))
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    rows.sort(key=lambda row: row['input'])
    _write_combined_results(output, rows)
    return _exit_code(rows)


if __name__ == '__main__':
    raise SystemExit(main())
