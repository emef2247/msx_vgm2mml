#!/usr/bin/env python3
"""Export VGM to MGS with 24 ms FM states and an 8 ms timing correction bound.

Conversion, compilation, diagnostics and optional key-on comparison are provided
by the existing batch runner. Its own defaults remain unchanged.

With --vgm-variants, each source additionally publishes cartridge
variant VGMs under vgm_variants/<stem>/ (see _update_vgm_variants).
OPN2 (YM2612), OPNA (YM2608), DCSG (SN76489) and OPM (YM2151)
sources have variant routes; a variant that does not apply to a
source is recorded unavailable with its reason instead of being
emitted.
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

VARIANT_PRODUCTS = ('vgm_variants/{stem}/makoto/{stem}.vgm',
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
                             'vgm_variants/<stem>/ (OPN2, OPNA, DCSG and OPM sources; '
                             'other sources record a route_unavailable row, and '
                             'variants that do not apply to a source are recorded '
                             'unavailable with a reason). '
                             'Rerunning without this flag removes the variants')
    parser.add_argument('--dcsg-gain', type=float, default=1.0,
                        help='Level gain for the DCSG lanes (PSG/SSG) in OPN2 target '
                             'and variant VGMs (default 1.0 = no shift; e.g. 0.036 '
                             'matches the x68k PCM balance)')
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


def _run_variant_pass(convert, path, stem, outdir, target, layered, products,
                      sources, unavailable, summaries, key, force):
    """Run one converter pass, filing its products or its failure reason."""
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / (stem + '.target.vgm')).unlink(missing_ok=True)
    (outdir / (stem + '.layer.target.vgm')).unlink(missing_ok=True)
    try:
        summaries[key] = convert(path, outdir, force=force, layered=layered,
                                 target=target, dac='opna')
    except Exception as error:
        for name in products:
            unavailable[name] = f'{type(error).__name__}: {error}'
        return
    for name, filename in products.items():
        sources[name] = outdir / filename


def _opna_variant_sources(path, stem, stage_root, names, force):
    """Variant products for an OPNA-only source (see opna_target_vgm)."""
    from opna_target_vgm import convert as convert_opna
    sources, unavailable, summaries = {}, {}, {}
    _run_variant_pass(convert_opna, path, stem, stage_root, 'makoto', False,
                      {names[0]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'makoto', force)
    _run_variant_pass(convert_opna, path, stem, stage_root / 'sfg01_opna',
                      'sfg01', False, {names[1]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'sfg01_opna', force)
    unavailable[names[2]] = (
        'the OPNA ADPCM-B lane is native to the makoto cartridge and has '
        'no Y8950 relocation in this route; sfg01/dac_y8950 is not '
        'emitted for OPNA sources')
    _run_variant_pass(convert_opna, path, stem, stage_root / 'layered',
                      'makoto', True, {names[3]: stem + '.layer.target.vgm'},
                      sources, unavailable, summaries, 'layered', force)
    _run_variant_pass(convert_opna, path, stem, stage_root / 'opm4mhz',
                      'opm4mhz', False, {names[4]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'opm4mhz', force)
    return sources, unavailable, summaries


def _dcsg_variant_sources(path, stem, stage_root, names, force):
    """Variant products for a DCSG-only source (see dcsg_target_vgm)."""
    from dcsg_target_vgm import convert as convert_dcsg
    sources, unavailable, summaries = {}, {}, {}
    unavailable[names[0]] = (
        'DCSG sources have no makoto composition in this stage: the '
        'OPNA-side DCSG route belongs to the mucom88-side stage (S3)')
    _run_variant_pass(convert_dcsg, path, stem, stage_root / 'sfg01_dcsg',
                      'sfg01', False, {names[1]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'sfg01_dcsg', force)
    unavailable[names[2]] = (
        'a DCSG source has no DAC-class lane for the Y8950 to carry; '
        'sfg01/dac_y8950 is not emitted for DCSG sources')
    _run_variant_pass(convert_dcsg, path, stem, stage_root / 'layered',
                      'sfg01', True, {names[3]: stem + '.layer.target.vgm'},
                      sources, unavailable, summaries, 'layered', force)
    unavailable[names[4]] = (
        'the DCSG sfg01 composition has no OPM lane whose clock the '
        'variant would switch; the layered composition runs at the '
        'cartridge clock, so opm4mhz does not apply to DCSG sources')
    return sources, unavailable, summaries


def _opm_variant_sources(path, stem, stage_root, names, force):
    """Variant products for an OPM-only source (see opm_target_vgm)."""
    from opm_target_vgm import convert as convert_opm
    sources, unavailable, summaries = {}, {}, {}
    _run_variant_pass(convert_opm, path, stem, stage_root, 'makoto', False,
                      {names[0]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'makoto', force)
    _run_variant_pass(convert_opm, path, stem, stage_root / 'sfg01_opm',
                      'sfg01', False, {names[1]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'sfg01_opm', force)
    unavailable[names[2]] = (
        'an OPM source has no DAC-class lane for the Y8950 to carry; '
        'sfg01/dac_y8950 is not emitted for OPM sources')
    _run_variant_pass(convert_opm, path, stem, stage_root / 'layered',
                      'makoto', True, {names[3]: stem + '.layer.target.vgm'},
                      sources, unavailable, summaries, 'layered', force)
    _run_variant_pass(convert_opm, path, stem, stage_root / 'opm4mhz',
                      'opm4mhz', False, {names[4]: stem + '.target.vgm'},
                      sources, unavailable, summaries, 'opm4mhz', force)
    return sources, unavailable, summaries


def _update_routed_variants(path, relative, package, output, args, row,
                            evidence, folder, manifest, state, previous_state,
                            entry, products, owned_names, names, chips):
    """Variant pass for the non-OPN2 routes (OPNA, DCSG, OPM, NES APU/FDS).

    Each route publishes the variants that apply to the source;
    the rest are recorded in the evidence with their reason. A
    route with no applicable variant at all records the same
    route_unavailable row the first stage used for every
    non-OPN2 source.
    """
    stem = path.stem
    stage_root = folder / 'vgm_variants'
    sources, unavailable, summaries = {}, {}, {}
    detail = None
    chip_set = set(chips)
    if chip_set == {'opna'}:
        evidence['source_route'] = 'opna'
        sources, unavailable, summaries = _opna_variant_sources(
            path, stem, stage_root, names, args.force)
    elif chip_set == {'dcsg'}:
        evidence['source_route'] = 'dcsg'
        sources, unavailable, summaries = _dcsg_variant_sources(
            path, stem, stage_root, names, args.force)
    elif chip_set == {'opm'}:
        evidence['source_route'] = 'opm'
        sources, unavailable, summaries = _opm_variant_sources(
            path, stem, stage_root, names, args.force)
    elif chip_set and chip_set <= {'opna', 'dcsg'}:
        detail = ('VGM variants are not available for sources mixing OPNA '
                  'and DCSG yet; each variant route covers a single source '
                  'chip in this stage')
    else:
        from native_imports.vgm_io import read_vgm_bytes
        from nesapu_projection import has_nesapu
        if has_nesapu(read_vgm_bytes(str(path))):
            evidence['source_route'] = 'nesapu'
            detail = ('VGM variants are not available for NES APU/FDS '
                      'sources yet: the x68k NES>OPM chain core (psg_scc_opm '
                      'SCC voice-bank fitting, PSG noise ownership and '
                      'musical note units) has diverged from this '
                      "repository's snapshot, so a faithful port is a "
                      'separate stage; no substitute mapping is emitted')
        else:
            detail = ('VGM variants are not available for this source yet; '
                      'OPN2 (YM2612), OPNA (YM2608), DCSG (SN76489) and '
                      'OPM (YM2151) sources produce variant VGMs')
    evidence['summaries'] = summaries
    evidence['unavailable'] = unavailable
    if not sources:
        if owned_names:
            try:
                evidence['publication'] = _remove_variants(
                    package, folder, manifest, state, path.name, entry,
                    products, owned_names)
            except OSError as error:
                raise ValueError(f'Variant removal failed: {error}') from error
        if detail is None:
            detail = ('VGM variants are not available for this source: '
                      + '; '.join(unavailable[name] for name in names
                                  if name in unavailable))
        row.update(error_code='route_unavailable', legacy_status='conversion_error',
                   processing_status='conversion_failed', detail=detail)
        evidence['status'] = 'route_unavailable'
        _save_variant_evidence(folder, evidence)
        print(f"{relative}: vgm variants unavailable (route_unavailable)", flush=True)
        return [row]
    publications = []
    for name, staged_file in sources.items():
        products[name] = file_digest(staged_file)
        publications.append((staged_file, package / name))
    deletions = [package / name for name in owned_names if name not in sources]
    if entry is None:
        entry = dict(input=path.name)
    entry['published'] = products
    state['entries'][path.name] = entry
    try:
        publication = publish_bundle(publications, manifest, state, folder,
                                     deletions=deletions)
    except OSError as error:
        publication = dict(status='failed', error=str(error),
                           context=getattr(error, 'publication_context', {}),
                           processing_status='success')
        row.update(status='publication_failed', stage='publish',
                   error_code='publication_error', publication_status='failed',
                   publication_error=str(error), processing_status='success',
                   detail=f'Variant publication failed after conversion: {error}')
        try:
            save_json(manifest, previous_state)
        except OSError as manifest_error:
            publication['manifest_error'] = str(manifest_error)
        evidence.update(status='publication_failed', publication=publication)
        _save_variant_evidence(folder, evidence)
        print(f"{relative}: vgm variants publication failed: {error}", flush=True)
        return [row]
    published = [name for name in names if name in sources]
    row.update(status='success', stage='complete', processing_status='success',
               publication_status='success', vgm_status='success',
               vgm=str((package / published[0]).relative_to(output)),
               detail=(f'{len(unavailable)} variant(s) unavailable for this '
                       'source; reasons in the variant evidence'
                       if unavailable else ''))
    evidence.update(status='success', published=published, publication=publication)
    _save_variant_evidence(folder, evidence)
    print(f"{relative}: vgm variants published", flush=True)
    return [row]


def _update_song_variants(path, relative, package, output, args):
    """Publish, refresh or remove one song's variant VGMs.

    Variant products are owned through the package listening manifest
    like every other product: an existing variant file whose digest is
    not the recorded one (or that is not recorded at all) refuses the
    run, and dropping --vgm-variants removes the products again.
    """
    stem = path.stem
    names = _variant_names(stem)
    manifest = package / 'listening_manifest.json'
    state = package_manifest(package)
    previous_state = json.loads(json.dumps(state))
    entry = state['entries'].get(path.name)
    products = dict(entry.get('published', {})) if entry else {}
    owned_names = [name for name in names if name in products]
    for name in names:
        target = package / name
        if target.exists() and (not target.is_file()
                                or file_digest(target) != products.get(name)):
            raise ValueError(f'Final target is unowned or modified: {target}')
    folder = package / '_diagnostics' / stem
    if not args.vgm_variants:
        if entry is None or not owned_names:
            return []
        try:
            _remove_variants(package, folder, manifest, state, path.name, entry,
                             products, owned_names)
        except OSError as error:
            raise ValueError(f'Variant removal failed: {error}') from error
        return []
    row = _variant_row(relative, folder, output, args)
    evidence = dict(route='vgm_variants', force=args.force, status='unavailable',
                    published=[], summaries={},
                    publication=dict(status='not_needed', operations=[]))
    from native_imports import inspect_source
    chips = inspect_source(path)['active_chips']
    if 'opn2' not in chips:
        return _update_routed_variants(path, relative, package, output, args,
                                       row, evidence, folder, manifest, state,
                                       previous_state, entry, products,
                                       owned_names, names, chips)
    # The same conversion passes export_opn2_vgm.py --sd-layout runs:
    # the makoto pass runs layered because the layered composition is
    # canonical and supplies both the makoto and the layered variant.
    from opn2_target_vgm import convert as convert_target_vgm
    stage_root = folder / 'vgm_variants'
    passes = [dict(key='makoto', target='makoto', dac='opna', layered=True,
                   outdir=stage_root),
              dict(key='sfg01_opna', target='sfg01', dac='opna', layered=False,
                   outdir=stage_root / 'sfg01_opna'),
              dict(key='sfg01_y8950', target='sfg01', dac='y8950', layered=False,
                   outdir=stage_root / 'sfg01_y8950'),
              dict(key='opm4mhz', target='opm4mhz', dac='opna', layered=False,
                   outdir=stage_root / 'opm4mhz')]
    summaries = {}
    try:
        for spec in passes:
            spec['outdir'].mkdir(parents=True, exist_ok=True)
            (spec['outdir'] / (stem + '.target.vgm')).unlink(missing_ok=True)
            (spec['outdir'] / (stem + '.layer.target.vgm')).unlink(missing_ok=True)
            summaries[spec['key']] = convert_target_vgm(
                path, spec['outdir'], force=args.force, layered=spec['layered'],
                target=spec['target'], dac=spec['dac'],
                dcsg_gain=args.dcsg_gain, opna_law=args.opna_law)
    except Exception as error:
        row.update(error_code=type(error).__name__, legacy_status='conversion_error',
                   processing_status='conversion_failed',
                   detail=f'VGM variant conversion failed: {error}')
        evidence['status'] = 'conversion_failed'
        _save_variant_evidence(folder, evidence)
        print(f"{relative}: vgm variants failed: {error}", flush=True)
        return [row]
    evidence['summaries'] = summaries
    sources = dict(zip(names, (stage_root / (stem + '.target.vgm'),
                               stage_root / 'sfg01_opna' / (stem + '.target.vgm'),
                               stage_root / 'sfg01_y8950' / (stem + '.target.vgm'),
                               stage_root / (stem + '.layer.target.vgm'),
                               stage_root / 'opm4mhz' / (stem + '.target.vgm'))))
    publications = []
    for name, staged_file in sources.items():
        products[name] = file_digest(staged_file)
        publications.append((staged_file, package / name))
    deletions = [package / name for name in owned_names if name not in sources]
    if entry is None:
        entry = dict(input=path.name)
    entry['published'] = products
    state['entries'][path.name] = entry
    try:
        publication = publish_bundle(publications, manifest, state, folder,
                                     deletions=deletions)
    except OSError as error:
        publication = dict(status='failed', error=str(error),
                           context=getattr(error, 'publication_context', {}),
                           processing_status='success')
        row.update(status='publication_failed', stage='publish',
                   error_code='publication_error', publication_status='failed',
                   publication_error=str(error), processing_status='success',
                   detail=f'Variant publication failed after conversion: {error}')
        try:
            save_json(manifest, previous_state)
        except OSError as manifest_error:
            publication['manifest_error'] = str(manifest_error)
        evidence.update(status='publication_failed', publication=publication)
        _save_variant_evidence(folder, evidence)
        print(f"{relative}: vgm variants publication failed: {error}", flush=True)
        return [row]
    row.update(status='success', stage='complete', processing_status='success',
               publication_status='success', vgm_status='success',
               vgm=str((package / names[0]).relative_to(output)))
    evidence.update(status='success', published=names, publication=publication)
    _save_variant_evidence(folder, evidence)
    print(f"{relative}: vgm variants published", flush=True)
    return [row]


def _update_vgm_variants(args):
    """Variant pass over every input, after the normal MGS export.

    Runs whether or not --vgm-variants was given: with the flag the
    variants are (re)published, without it previously published
    variants are removed again. The batch exit status stays with the
    MGS rows; variant outcomes are recorded as extra result rows.
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
        rows.extend(_update_song_variants(path, relative, output / relative.parent,
                                          output, args))
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
                         curve_volume_error=None, curve_mean_error=None)
        variant_rows = _update_vgm_variants(args)
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    if variant_rows:
        _write_combined_results(args, rows + variant_rows)
    return 0 if all(row['status'] == 'success' and row.get('vgm_status') not in ('failed', 'blocked')
                    and row['keyon_status'] in ('compared', 'disabled', 'selection_only', 'projected_source')
                    for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
