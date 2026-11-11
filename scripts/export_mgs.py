#!/usr/bin/env python3
"""Export VGM to MGS with 24 ms FM states and an 8 ms timing correction bound.

Conversion, compilation, diagnostics and optional key-on comparison are provided
by the existing batch runner. Its own defaults remain unchanged.

With --vgm-variants, each source additionally publishes cartridge
variant VGMs under vgm-variants/<profile>/<stem>.vgm.
Each profile consumes the same source-native musical performance.
A profile that cannot represent the source records its reason separately.
"""
import argparse
import csv
import json
from pathlib import Path

from batch_vgm_to_mgs import (KEYON_FIELDS, discover_inputs, file_digest,
                              package_manifest, publish_bundle, run_batch,
                              save_json)
from mgs_conversion_config import sample_threshold

DEFAULT_FM_STATE_MS = 24.0

VARIANT_PROFILES = ('sfg01', 'makoto', 'sfg01_makoto', 'sfg01_msxaudio', 'layered', 'scc_sfg01', 'scc_makoto', 'scc_layered')
VARIANT_PRODUCTS = tuple('vgm-variants/' + profile + '/{stem}.vgm'
                         for profile in VARIANT_PROFILES)
# Previous publications remain owned during migration and disabled reruns.
LEGACY_VARIANT_PRODUCTS = ('vgm_variants/{stem}/makoto/{stem}.vgm',
    'vgm_variants/{stem}/sfg01/dac_makoto/{stem}.vgm',
    'vgm_variants/{stem}/sfg01/dac_y8950/{stem}.vgm',
    'vgm_variants/{stem}/layered/{stem}.vgm',
    'vgm_variants/{stem}/opm4mhz/{stem}.vgm')


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Also writes musical reference tracks/<stem>.vgm and editable blueprint/<stem>.mml: '
        'structured score without executable timbre or volume controls; source instruments documented in comments.'))
    parser.add_argument('input', type=Path, help='VGM/VGZ file or directory (recursive)')
    parser.add_argument('--outdir', type=Path,
                        help='Output root preserving input-relative parents (default: beside each source VGM)')
    parser.add_argument('--mgsc', help='Native MGSC executable (default: PATH)')
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--nes-balance', action=argparse.BooleanOptionalAction, default=True,
                        help='Apply the NES mapping balance gains (NES APU sources only; '
                             'default: on, use --no-nes-balance to disable)')
    parser.add_argument('--nes-gain', action='append', default=[], metavar='KIND=FACTOR',
                        help='Override one NES mapping gain (pulse, triangle, noise, dpcm, fds)')
    parser.add_argument('--compiler', choices=('mgsc', 'mgsexc'), default='mgsc',
                        help='MML compiler: mgsexc avoids the MGSC buffer limit (default: mgsc)')
    parser.add_argument('--macro-definition-budget', type=int, default=None,
                        help='Macro definition budget in bytes for MGSC output '
                             '(default: 5500 with mgsc, none with mgsexc)')
    parser.add_argument('--node', default='node')
    parser.add_argument('--timeout', type=int, default=1200,
                        help='Timeout per conversion/compilation stage in seconds (default: 1200)')
    parser.add_argument('--alloc', help='Track allocation overrides forwarded to conversion')
    from score_normalization import add_arguments
    add_arguments(parser, include_blueprint=False)
    parser.add_argument('--fm-state-ms', type=float, default=DEFAULT_FM_STATE_MS,
                        help='OPLL internal pitch/volume state threshold in milliseconds (default: 24)')
    parser.add_argument('--normalization-ms', type=float, default=8.0,
                        help='Maximum target timing correction in milliseconds (default: 8)')
    parser.add_argument('--score-guided-loops', action='store_true',
                        help='Guide target repeats with pitch/duration/rest/attack structure (opt-in)')
    volume_curves = parser.add_mutually_exclusive_group()
    volume_curves.add_argument('--no-software-volume-curves', dest='is_software_volume_curves',
        action='store_false',default=True,
        help='Disable software volume curves (enabled by default)')
    volume_curves.add_argument('--software-volume-curves',dest='is_software_volume_curves',
        action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--force', action='store_true',
                        help='Apply only documented target omission rules')
    parser.add_argument('--vgm-variants', action='store_true',
                        help='Also publish cartridge variant VGMs under '
                             'vgm-variants/<profile>/<stem>.vgm (source-native musical projection; '
                             'other sources record a route_unavailable row, and '
                             'variants that do not apply to a source are recorded '
                             'unavailable with a reason). '
                             'Rerunning without this flag removes the variants')
    parser.add_argument('--dcsg-gain', type=float, default=0.25,
                        help='Level gain for the DCSG lanes (PSG/SSG) in OPN2 target '
                             'and variant VGMs (default 0.25, the level settled by '
                             'real-hardware listening 2026-11-08; 1.0 = no shift, '
                             'e.g. 0.036 matches the x68k PCM balance)')
    parser.add_argument('--opna-law', action='store_true',
                        help='Apply the measured OPN2>OPNA conversion law to the '
                             'OPNA FM lane of OPN2 target and variant VGMs '
                             '(carrier TL remap and decay-rate correction; '
                             'default off = register transcription)')
    parser.add_argument('--dump-passes', action='store_true',
                        help='Retain inspectable conversion passes')
    macros=parser.add_mutually_exclusive_group()
    macros.add_argument('--macro-mode',choices=('v110','current','greedy'),default='v110',
        help='Production macros: v110 (default), current, or current greedy comparison')
    macros.add_argument('--current-macros','--enhance-macros',dest='macro_mode',action='store_const',const='current',
        help='Compare the current relative/phrase-based enhanced macros')
    macros.add_argument('--greedy-macros',dest='macro_mode',action='store_const',const='greedy',
        help='Compare current shared preprocessing with greedy macro selection')
    macros.add_argument('--legacy-macros',dest='macro_mode',action='store_const',const='greedy',help=argparse.SUPPRESS)
    loops=parser.add_mutually_exclusive_group()
    loops.add_argument('--loop-mode',choices=('v110','current','envelope-first','score-guided'),default='v110',
        help='Production loops: v110 (default), current, envelope-first, or score-guided')
    loops.add_argument('--envelope-first-loops',dest='loop_mode',action='store_const',const='envelope-first',
        help='Compare the older envelope-first loop policy')
    loops.add_argument('--legacy-loops',dest='loop_mode',action='store_const',const='envelope-first',help=argparse.SUPPRESS)
    parser.add_argument('--skip-keyon-counts', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--libkss-module', type=Path,
                        help='Explicit libkss-js entry point for MGS export')
    return parser


def _variant_names(stem):
    return [pattern.format(stem=stem) for pattern in VARIANT_PRODUCTS]


def _variant_row(relative, folder, output, args):
    row = dict(input=str(relative), status='conversion_failed', mml='',
               publication_status='not_attempted', publication_error='', processing_status='',
               mgs='', vgm='', vgm_status='unavailable', vgm_detail='', blueprint='',
               blueprint_files=[], blueprint_midi_files=[], blueprint_status='not_needed',
               blueprint_detail='', log='', detail='', stage='variants', error_code='',
               legacy_status='',
               report=str((folder / 'report.txt').relative_to(output)),
               diagnostics=str((folder / 'vgm_variants.json').relative_to(output)),
               force_summary='', normalization_status='unavailable', normalization_reason='',
               normalization_ms=args.normalization_ms, fm_state_ms=args.fm_state_ms,
               keyon_status='disabled', keyon_error='', route='vgm_variants')
    row.update(dict.fromkeys(KEYON_FIELDS, ''))
    return row


def _save_variant_evidence(folder, evidence):
    folder.mkdir(parents=True, exist_ok=True)
    save_json(folder / 'vgm_variants.json', evidence)


def _remove_variants(package, folder, manifest, state, key, entry, products, names):
    """Drop owned variant products and their manifest entries as one bundle."""
    deletions = [package / name for name in names if (package / name).is_file()]
    for name in names:
        products.pop(name, None)
    entry['published'] = products
    state['entries'][key] = entry
    folder.mkdir(parents=True, exist_ok=True)
    return publish_bundle([], manifest, state, folder, deletions=deletions)


def _update_song_variants(path, relative, package, output, args):
    """Project one native musical performance and atomically refresh its products."""
    stem = path.stem
    names = _variant_names(stem)
    known_names = names + [pattern.format(stem=stem) for pattern in LEGACY_VARIANT_PRODUCTS]
    manifest = package / 'listening_manifest.json'
    state = package_manifest(package)
    entry = state['entries'].get(path.name, dict(input=path.name, source_path=str(path.resolve())))
    products = dict(entry.get('published', {}))
    owned_names = [name for name in known_names if name in products]
    for name in known_names:
        target = package / name
        if target.exists() and (not target.is_file() or file_digest(target) != products.get(name)):
            raise ValueError(f'Final target is unowned or modified: {target}')
        if not target.resolve().is_relative_to(output):
            raise ValueError(f'Output route escapes output tree: {target}')
        for parent in target.parents:
            if parent == output:
                break
            if parent.exists() and not parent.is_dir():
                raise ValueError(f'Colliding output directory: {parent}')
    folder = package / '_diagnostics' / stem
    if not args.vgm_variants:
        if owned_names:
            _remove_variants(package, folder, manifest, state, path.name, entry,
                             products, owned_names)
        return []
    row = _variant_row(relative, folder, output, args)
    evidence = dict(route='vgm_variants', force=args.force, status='unavailable',
                    published=[], summaries={}, publication=dict(status='not_needed'))
    stage_root = folder / 'vgm_variants'
    folder.mkdir(parents=True, exist_ok=True)
    sources = {}
    try:
        from native_source_music import build_native_performance
        from musical_variants import export_variants
        performance = build_native_performance(path, stage_root / 'native', stem)
        summaries = export_variants(performance, stage_root, stem, force=args.force,
                                   dcsg_gain=args.dcsg_gain, opna_law=args.opna_law)
        evidence['summaries'] = summaries
        for profile, name in zip(VARIANT_PROFILES, names):
            result = summaries[profile]
            if result['status'] == 'success':
                sources[name] = Path(result['path'])
                # Validate every staged product before mutating ownership.
                file_digest(sources[name])
        failed = any(result['status'] == 'failed' for result in summaries.values())
        detail = '; '.join(profile + ': ' + result.get('reason', result['status'])
                           for profile, result in summaries.items() if result['status'] != 'success')
    except Exception as error:
        sources = {}
        failed = True
        detail = f'{type(error).__name__}: {error}'
        evidence['error'] = detail
    publications = [(staged, package / name) for name, staged in sources.items()]
    for name in owned_names:
        products.pop(name, None)
    for name, staged in sources.items():
        products[name] = file_digest(staged)
    entry['published'] = products
    state['entries'][path.name] = entry
    try:
        publication = publish_bundle(publications, manifest, state, folder,
            deletions=[package / name for name in owned_names
                       if name not in sources and (package / name).is_file()])
    except OSError as error:
        publication = dict(status='failed', error=str(error),
                           context=getattr(error, 'publication_context', {}))
        row.update(status='publication_failed', stage='publish', error_code='publication_error',
                   publication_status='failed', publication_error=str(error),
                   processing_status='conversion_failed' if failed else 'success', detail=str(error))
        evidence.update(status='publication_failed', publication=publication)
    else:
        status = 'success' if sources and not failed else 'conversion_failed'
        row.update(status=status, processing_status=status, publication_status='success',
                   stage='complete' if status == 'success' else 'variants', detail=detail,
                   vgm_status='success' if sources else 'unavailable',
                   vgm=str((package / next(iter(sources))).relative_to(output)) if sources else '',
                   error_code='' if status == 'success' else 'projection_failed' if failed else 'route_unavailable')
        evidence.update(status=status, published=list(sources), publication=publication)
    _save_variant_evidence(folder, evidence)
    print(f"{relative}: vgm variants {evidence['status']}", flush=True)
    return [row]


def _update_one_variant(path, relative, package, output, args, rows):
    """Variant update for one song, appended to rows.

    Runs whether or not --vgm-variants was given: with the flag the
    variants are (re)published, without it previously published
    variants are removed again.
    """
    if args.vgm_variants:
        print(f'{relative}: vgm variants starting', flush=True)
    try:
        rows.extend(_update_song_variants(path, relative, package, output, args))
    except (OSError, ValueError) as error:
        row = _variant_row(relative, package / '_diagnostics' / path.stem, output, args)
        row.update(status='publication_failed', publication_status='failed', stage='publish',
                   publication_error=str(error), error_code='publication_error', detail=str(error))
        rows.append(row)
        print(f'{relative}: vgm variants publication_failed: {error}', flush=True)


def _update_vgm_variants(args):
    """Standalone variant pass over every input.

    main() no longer calls this after the batch: it passes a per-song
    hook to run_batch so each song's variants are processed right after
    that song's MGS export. This pass remains for callers that only
    want the variant stage. The batch exit status stays with the MGS
    rows; variant outcomes are recorded as extra result rows.
    """
    source = args.input.resolve()
    if not source.exists():
        return []
    source_root = source.parent if source.is_file() else source
    adjacent = args.outdir is None
    output = source_root if adjacent else args.outdir.resolve()
    rows = []
    for path in discover_inputs(source, adjacent=adjacent):
        relative = path.relative_to(source_root)
        package = output / relative.parent
        _update_one_variant(path, relative, package, output, args, rows)
    return rows


def _write_combined_results(args, rows):
    source = args.input.resolve()
    source_root = source.parent if source.is_file() else source
    output = source_root if args.outdir is None else args.outdir.resolve()
    diagnostics = output / '_diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (diagnostics / 'results.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (diagnostics / 'results.json').write_text(json.dumps(rows, indent=2) + '\n',
                                              encoding='utf-8')
    packages = {}
    for row in rows:
        if row.get('route') == 'vgm_variants':
            packages.setdefault(output / Path(row['input']).parent, []).append(row)
    for package, variants in packages.items():
        target = package / 'results.json'
        previous = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else []
        inputs = {Path(row['input']).name for row in variants}
        selected = [row for row in previous
                    if not (row.get('route') == 'vgm_variants' and row.get('input') in inputs)]
        for row in variants:
            item = dict(row, input=Path(row['input']).name)
            for field in ('vgm', 'report', 'diagnostics'):
                if item.get(field):
                    item[field] = (output / item[field]).relative_to(package).as_posix()
            selected.append(item)
        save_json(target, selected)
        with (package / 'results.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in selected for key in row)))
            writer.writeheader()
            writer.writerows(selected)



def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.score_guided_loops and args.loop_mode=='envelope-first':
        parser.error('--score-guided-loops cannot be combined with --envelope-first-loops')
    try:
        sample_threshold(args.fm_state_ms, '--fm-state-ms')
        macro_budget = args.macro_definition_budget
        if macro_budget is None and args.compiler == 'mgsc':
            from macro_budget import MGSC_MACRO_DEFINITION_BUDGET
            macro_budget = MGSC_MACRO_DEFINITION_BUDGET
        variant_rows = []

        def _song_hook(path, relative, package, output):
            _update_one_variant(path, relative, package, output, args, variant_rows)

        rows = run_batch(args.input, args.outdir, module=args.mgsc_module,
                         node=args.node, timeout=args.timeout, mgsc=args.mgsc,
                         compiler=args.compiler,
                         alloc=args.alloc, keyon=not args.skip_keyon_counts,
                         libkss_module=args.libkss_module,
                         normalize_lengths=False,
                         score_normalize=args.score_normalize,score_tempo=args.score_tempo,
                         blueprint_score_normalize=True,
                         enhance_macros=args.macro_mode!='greedy', legacy_loops=args.loop_mode=='envelope-first',
                         macro_mode=args.macro_mode, loop_mode='score-guided' if args.score_guided_loops else args.loop_mode,
                         force=args.force, fm_state_ms=args.fm_state_ms,
                         normalization_ms=args.normalization_ms, dump_passes=args.dump_passes,
                         enhance_drums=False, psg_part='all',
                         software_volume_curves=args.is_software_volume_curves,
                         score_guided_loops=args.score_guided_loops,
                         macro_definition_budget=macro_budget,
                         nes_balance=args.nes_balance, nes_gain=args.nes_gain,
                         psg_state_ms=None, scc_state_ms=None,
                         curve_volume_error=None, curve_mean_error=None,
                         song_hook=_song_hook)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    if variant_rows:
        _write_combined_results(args, rows + variant_rows)
    return 0 if all(row['status'] == 'success' and row.get('vgm_status') not in ('failed', 'blocked')
                    and row['keyon_status'] in ('compared', 'disabled', 'selection_only', 'projected_source')
                    for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
