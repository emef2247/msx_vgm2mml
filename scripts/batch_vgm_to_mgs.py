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
import os
import hashlib
import tempfile
import errno

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from mgs_conversion_config import MgsOptions, add_curve_arguments, curve_option_values
from vgm_io import read_vgm_bytes
from vgm_timing import command_times
from check_opll_key_edges import compare_files

KEYON_FIELDS = ('reference_keyon', 'actual_keyon', 'missing_keyon', 'extra_keyon')


def timeout_log(error, stage):
    parts = []
    for value in (error.stdout, error.stderr):
        if value:
            parts.append(value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value)
    parts.append(f'{stage} timed out after {error.timeout} seconds.\n{error}\n')
    return '\n'.join(parts)


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
    proc = subprocess.run(command, capture_output=True, timeout=timeout, cwd=folder)
    text = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
    (folder / 'keyon.log').write_text(text, encoding='utf-8')
    if proc.returncode or not actual.is_file() or not actual.stat().st_size:
        raise ValueError(text or 'MGS export produced no VGM')
    exported = read_vgm_bytes(actual)
    exported_samples = struct.unpack_from('<I', exported, 0x18)[0]
    if exported_samples / 44.1 >= duration - 20:
        raise ValueError('MGS export reached its duration limit; comparison is incomplete')
    if any(item.command == 0xb9 for item in command_times(raw)):
        return dict(keyon_status='projected_source', keyon_error=(
            'MGS playback VGM exported; HuC6280 source is projected to other chips. '
            'OPLL key-on counts and source register equality are not applicable.'))
    return compare_files(source, actual, folder / 'keyon', segment_dumps=False)


def error_detail(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if any(word in line.lower() for word in ('error', 'failed', 'buffer full', 'exception')):
            return line
    return lines[-1] if lines else ''


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_vgm_product(report, folder, stem):
    """Accept only the current musical-layer writer's verified product."""
    value = report.get('direct_vgm', {}) if isinstance(report, dict) else {}
    if not isinstance(value, dict):
        return None, 'blocked', 'Invalid direct VGM report'
    status, detail = value.get('status', 'unavailable'), value.get('detail', '')
    if status != 'success':
        return None, status, detail
    try:
        path = Path(value['vgm'])
        if (path.resolve() != (folder / 'tracks' / (stem + '.vgm')).resolve()
                or path.is_symlink() or not path.is_file() or not path.stat().st_size
                or file_digest(path) != value.get('vgm_sha256')):
            raise ValueError('Invalid direct VGM product')
    except (KeyError, OSError, TypeError, ValueError):
        return None, 'blocked', 'Direct VGM report has a missing or invalid product'
    return path, status, detail


def blueprint_product(report, folder, stem):
    """Compatibility accessor for the first validated blueprint page."""
    paths = blueprint_products(report, folder, stem)
    return paths[0] if paths else None


def blueprint_name(name, stem, extension='mml'):
    import re
    return bool(re.fullmatch(re.escape(stem) + r'(?:\.part\d{2,})?\.'+re.escape(extension), name))


def blueprint_artifact_name(name, stem):
    return blueprint_name(name,stem) or blueprint_name(name,stem,'midi')


def blueprint_products(report, folder, stem):
    """Validate the complete template set before publishing any of its voices."""
    value = report.get('blueprint', {}) if isinstance(report, dict) else {}
    if not isinstance(value, dict) or value.get('status') != 'success':
        return ()
    records = value['files'] if 'files' in value else [value]
    if not isinstance(records, list) or not records:
        return ()
    count = value.get('file_count', len(records))
    if type(count) is not int or count < 1 or count != len(records):
        return ()
    paths = []
    try:
        for record in records:
            if not isinstance(record, dict):
                return ()
            path = Path(record['path'])
            expected = folder / 'blueprint' / path.name
            if (not blueprint_name(path.name, stem) or path.resolve() != expected.resolve()
                    or not path.resolve().is_relative_to(folder.resolve())
                    or not path.is_file() or file_digest(path) != record.get('sha256')):
                return ()
            paths.append(path)
        if not paths or paths[0].name != stem+'.mml' or len({p.name.casefold() for p in paths}) != len(paths):
            return ()
    except (KeyError, OSError, TypeError, ValueError):
        return ()
    return tuple(paths)


def prepare_blueprints(report, folder, stem, package, products):
    """Plan an all-or-nothing optional template update, preserving hand edits."""
    value = report.get('blueprint', {}) if isinstance(report, dict) else {}
    if not isinstance(value, dict):
        return [], [], dict(products), 'blocked', 'Invalid blueprint report', []
    status, detail = value.get('status', 'unavailable'), value.get('detail', '')
    generated = blueprint_products(report, folder, stem)
    if status != 'success':
        return [], [], dict(products), status, detail, []
    if not generated:
        return [], [], dict(products), 'blocked', 'Blueprint report has missing or invalid pages', []
    # Older MML-only reports remain readable. New writers publish paired MIDI
    # records, and a malformed MIDI set must not publish a partial score bundle.
    if 'midi_files' in value:
        records=value['midi_files']
        midi=[]
        try:
            if not isinstance(records,list) or len(records)!=len(generated):raise ValueError()
            for record,score in zip(records,generated):
                path=Path(record['path'])
                if (path.resolve()!=score.with_suffix('.midi').resolve() or path.is_symlink()
                        or not path.is_file() or file_digest(path)!=record.get('sha256')):
                    raise ValueError()
                midi.append(path)
        except (OSError,ValueError,KeyError,TypeError):
            return [], [], dict(products), 'blocked', 'Blueprint report has missing or invalid MIDI pages', []
        generated=(*generated,*midi)
    old_names = {name for name in products if Path(name).parent.as_posix() == 'blueprint'
                 and blueprint_artifact_name(Path(name).name, stem)}
    new_names = {('blueprint/'+path.name) for path in generated}
    for name in old_names | new_names:
        target = package/name
        if not target.resolve().is_relative_to(package.resolve()) or target.is_symlink():
            return [], [], dict(products), 'blocked', 'Blueprint target escapes its package', []
        if target.exists() and (not target.is_file() or file_digest(target) != products.get(name)):
            return [], [], dict(products), 'blocked', 'Edited/unowned blueprint preserved', []
    updated = dict(products)
    deletions = [package/name for name in sorted(old_names-new_names) if (package/name).is_file()]
    for name in old_names-new_names:
        updated.pop(name, None)
    publications = [(path, package/'blueprint'/path.name) for path in generated]
    for source, target in publications:
        updated[target.relative_to(package).as_posix()] = file_digest(source)
    return publications, deletions, updated, status, detail, [target for _, target in publications]


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def replace_product(source, target, *, allow_copy=True):
    """Replace an owned product; tolerate DrvFS rename/share failures.

    The caller retains backups for this non-atomic fallback. A missing staged
    file or parent is a real error, not a reason to fabricate a publication.
    The manifest itself always retains atomic replacement.
    """
    try:
        os.replace(source,target)
        return 'replace'
    except OSError as error:
        if (not allow_copy or error.errno not in (errno.ENOENT,errno.EACCES,errno.EPERM,errno.EBUSY)
                or not source.is_file() or not target.parent.is_dir() or target.is_symlink()):
            raise
        shutil.copyfile(source,target)
        if file_digest(source)!=file_digest(target):
            raise OSError(errno.EIO,'Published copy verification failed',str(target))
        return 'verified_copy'


def publish_bundle(publications, manifest, state, workspace, *, deletions=()):
    """Prepare every product and manifest before replacing the owned bundle."""
    temporary=Path(tempfile.mkdtemp(prefix='publish_',dir=workspace))
    preserve_recovery=False
    try:
        prepared = []
        for index, (source, target) in enumerate(publications):
            target.parent.mkdir(parents=True, exist_ok=True)
            prepared_path = temporary / ('new_' + str(index))
            shutil.copyfile(source, prepared_path)
            prepared.append((prepared_path, target))
        manifest_data = temporary / 'manifest'
        manifest_data.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        prepared.append((manifest_data, manifest))
        backups = {}
        for index, target in enumerate([target for _, target in prepared] + list(deletions)):
            if target.exists():
                backup = temporary / ('old_' + str(index))
                shutil.copyfile(target, backup)
                backups[target] = backup
        replaced = [];methods=[];operation_source=None
        try:
            for target in deletions:
                operation_source=None
                replaced.append(target)
                target.unlink()
            for source, target in prepared:
                operation_source=source
                replaced.append(target)
                method=replace_product(source,target,allow_copy=target!=manifest)
                methods.append(dict(target=str(target),method=method))
        except OSError as error:
            error.publication_context=dict(source=str(operation_source) if operation_source else None,target=str(target),
                staged_source_exists=operation_source.is_file() if operation_source else False,target_parent_exists=target.parent.is_dir(),
                errno=error.errno,winerror=getattr(error,'winerror',None))
            rollback_errors=[]
            for target in reversed(replaced):
                try:
                    if target in backups:
                        replace_product(backups[target],target,allow_copy=target!=manifest)
                    else:
                        target.unlink(missing_ok=True)
                except OSError as rollback_error:
                    rollback_errors.append(dict(target=str(target),error=str(rollback_error)))
            error.publication_context['rollback_errors']=rollback_errors
            if rollback_errors:
                preserve_recovery=True
                error.publication_context.update(recovery_required=True,recovery_directory=str(temporary))
                recovery=dict(error=str(error),targets=[dict(target=str(target),backup=str(backup))
                    for target,backup in backups.items() if backup.is_file()],
                    rollback_errors=rollback_errors,manifest=str(manifest))
                try:
                    (temporary/'recovery.json').write_text(json.dumps(recovery,indent=2)+'\n',encoding='utf-8')
                except OSError as metadata_error:
                    error.publication_context['recovery_metadata_error']=str(metadata_error)
            raise
        return dict(status='success',operations=methods)
    finally:
        if not preserve_recovery:
            if temporary.resolve().parent!=Path(workspace).resolve():
                raise ValueError('Publication staging directory escaped its workspace')
            shutil.rmtree(temporary)


def package_manifest(package):
    path = package / 'listening_manifest.json'
    if not path.exists():
        return dict(schema_version=1, entries={})
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema_version') != 1 or not isinstance(value['entries'], dict):
            raise ValueError('Unsupported manifest schema')
        return value
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f'Invalid listening manifest: {path}') from error


def publication_targets(files, source_root, output, psg_part):
    """Preflight all routes and owned publications before changing any artifact."""
    mode = Path() if psg_part == 'all' else Path('psg_' + psg_part)
    diagnostics = output / '_diagnostics' / mode
    routes, seen = [], set()
    for path in files:
        relative = path.relative_to(source_root)
        if any(part.casefold() in ('_diagnostics', '_source_inputs', 'tracks', 'blueprint', 'psg_melody', 'psg_rhythm', '_huc6280_target', '_score_normalized', 'native_legacy')
               for part in relative.parts[:-1]):
            raise ValueError(f'Reserved output route in input: {relative}')
        package = output / mode / relative.parent
        final = package / 'tracks' / (path.stem + '.mml')
        key = str(final.relative_to(output)).casefold()
        if key in seen:
            raise ValueError(f'Colliding final targets for input: {relative}')
        seen.add(key)
        folder = package / '_diagnostics' / path.stem
        staged = package / '_source_inputs' / path.name
        targets = (final, final.with_suffix('.mgs'))
        reference = final.with_suffix('.vgm')
        blueprint = package / 'blueprint' / (path.stem + '.mml')
        manifest = package / 'listening_manifest.json'
        for candidate in (*targets, reference, blueprint, folder, staged, manifest, package / 'results.csv', package / 'results.json',
                          diagnostics / 'results.csv', diagnostics / 'results.json', diagnostics / 'keyon_setup.log'):
            if not candidate.resolve().is_relative_to(output):
                raise ValueError(f'Output route escapes output tree: {candidate}')
            for parent in candidate.parents:
                if parent == output:
                    break
                if parent.exists() and not parent.is_dir():
                    raise ValueError(f'Colliding output directory: {parent}')
        if folder.exists():
            for artifact in folder.rglob('*'):
                if artifact.is_symlink() and not artifact.resolve().is_relative_to(output):
                    raise ValueError(f'Diagnostic artifact escapes output tree: {artifact}')
        previous = package_manifest(package)['entries'].get(path.name, {})
        if previous.get('source_path') and Path(previous['source_path']).resolve() != path.resolve():
            raise ValueError(f'Output belongs to a different source: {path}')
        owned = previous.get('published', {})
        if not isinstance(owned, dict):
            raise ValueError(f'Invalid listening manifest: {manifest}')
        for name in owned:
            allowed_products = {target.relative_to(package).as_posix() for target in targets}
            allowed_products.add((package / 'tracks' / (path.stem + '.vgm')).relative_to(package).as_posix())
            allowed_products.add(blueprint.relative_to(package).as_posix())
            if name not in allowed_products and not (Path(name).parent.as_posix() == 'blueprint'
                    and blueprint_artifact_name(Path(name).name, path.stem)):
                raise ValueError(f'Unexpected published path in manifest: {name}')
        # A hand-edited template protects that optional product, not the main conversion.
        for target in (*targets, reference):
            if target.exists():
                recorded = owned.get(target.relative_to(package).as_posix())
                if not target.is_file() or recorded != file_digest(target):
                    raise ValueError(f'Final target is unowned or modified: {target}')
        if staged.exists():
            recorded = previous.get('staged_sha256')
            if not staged.is_file() or recorded != file_digest(staged):
                raise ValueError(f'Staged source is unowned or modified: {staged}')
        routes.append((path, relative, folder, targets, manifest))
    artifacts = {}
    directories = set()
    for path, _, folder, targets, manifest in routes:
        package = manifest.parent
        for item in (*targets, targets[0].with_suffix('.vgm'), package / 'blueprint' / (path.stem + '.mml'),
                     package / 'blueprint' / (path.stem + '.midi'),package / '_source_inputs' / path.name, manifest,
                     package / 'results.csv', package / 'results.json',
                     diagnostics / 'results.csv', diagnostics / 'results.json', diagnostics / 'keyon_setup.log'):
            key = item.relative_to(output).as_posix().casefold()
            if key in artifacts and artifacts[key] != item:
                raise ValueError(f'Colliding output paths: {item}')
            for component in (item, *item.parents):
                if component == output:
                    break
                if component.parent.is_dir():
                    for sibling in component.parent.iterdir():
                        if sibling.name.casefold() == component.name.casefold() and sibling.name != component.name:
                            raise ValueError(f'Colliding output paths: {component} and {sibling}')
            artifacts[key] = item
            for parent in item.parents:
                if parent == output:
                    break
                directories.add(parent.relative_to(output).as_posix().casefold())
        directories.add(folder.relative_to(output).as_posix().casefold())
    if set(artifacts) & directories:
        raise ValueError('Colliding output files and directories')
    return diagnostics, routes


def save_package_results(package, output, rows):
    previous = package / 'results.json'
    selected = json.loads(previous.read_text(encoding='utf-8')) if previous.is_file() else []
    if not isinstance(selected, list) or any(not isinstance(item, dict) for item in selected):
        raise ValueError(f'Invalid package results: {previous}')
    path_fields = ('mml', 'mgs', 'vgm', 'blueprint', 'log', 'report', 'diagnostics')
    for row in rows:
        if (output / row['report']).parent.parent.parent != package:
            continue
        item = dict(row)
        item['input'] = Path(row['input']).name
        for field in path_fields:
            if item.get(field):
                item[field] = (output / item[field]).relative_to(package).as_posix()
        for field in ('blueprint_files','blueprint_midi_files'):
            if item.get(field):
                item[field] = [(output/name).relative_to(package).as_posix() for name in item[field]]
        selected = [prior for prior in selected if prior.get('input') != item['input']]
        selected.append(item)
    if selected:
        with (package / 'results.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in selected for key in row)))
            writer.writeheader()
            writer.writerows(selected)
        save_json(package / 'results.json', selected)


def discover_inputs(source, adjacent=False):
    def is_input(path):
        if path.suffix.lower() in ('.vgm', '.vgz'):return True
        # Some public/private collections omit the filename separator. Detect
        # actual VGM data without renaming or accepting arbitrary binary files.
        try:
            with path.open('rb') as handle:return handle.read(4) == b'Vgm '
        except OSError:return False
    if source.is_file():
        return [source] if is_input(source) else []
    if not adjacent:
        return sorted(p for p in source.rglob('*') if p.is_file()
                      and '_huc6280_target' not in [part.casefold() for part in p.relative_to(source).parts[:-1]]
                      and is_input(p))
    # Adjacent reruns must not convert their own roundtrip VGM or audition trees.
    reserved = {'_diagnostics', '_source_inputs', 'tracks', 'blueprint', 'psg_melody', 'psg_rhythm', '_huc6280_target', '_score_normalized', 'native_legacy'}
    files = []
    for parent, directories, names in os.walk(source):
        directories[:] = [name for name in directories if name.casefold() not in reserved]
        files.extend(Path(parent) / name for name in names if is_input(Path(parent) / name))
    return sorted(files)


def run_batch(source, output=None, module=None, node='node', timeout=1200, mgsc=None, alloc=None,
              keyon=True, libkss_module=None, normalize_lengths=False, enhance_macros=True, legacy_loops=False,
              force=False, fm_state_ms=None, normalization_ms=None, dump_passes=False, enhance_drums=False, psg_part='all',
              software_volume_curves=False, score_guided_loops=False,
              psg_state_ms=None, scc_state_ms=None, curve_volume_error=None, curve_mean_error=None,
              score_normalize=False, score_tempo=225, blueprint_score_normalize=False,
              macro_mode=None, loop_mode=None):
    options = MgsOptions(normalize_lengths=normalize_lengths, normalization_ms=normalization_ms,
                         fm_state_ms=fm_state_ms, force=force, dump_passes=dump_passes, enhance_drums=enhance_drums, psg_part=psg_part,
                         software_volume_curves=software_volume_curves, score_guided_loops=score_guided_loops,
                         psg_state_ms=psg_state_ms, scc_state_ms=scc_state_ms,
                         curve_volume_error=curve_volume_error, curve_mean_error=curve_mean_error,
                         score_normalize=score_normalize,score_tempo=score_tempo,
                         blueprint_score_normalize=blueprint_score_normalize)
    option_args = options.cli_args()
    effective_options = options.as_dict()
    effective_options.update(macro_mode=macro_mode or 'current', loop_mode=loop_mode or 'current')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Timeout must be finite and positive')
    source = source.resolve()
    source_root = source.parent if source.is_file() else source
    adjacent = output is None
    output = source_root if adjacent else output.resolve()
    if not adjacent and (source == output or output in source.parents or source in output.parents):
        raise ValueError('Explicit input and output trees must be separate; omit --outdir for adjacent output')
    files = discover_inputs(source, adjacent=adjacent)
    if not files:
        raise ValueError('No VGM files found')
    diagnostics, routes = publication_targets(files, source_root, output, psg_part)
    native = shutil.which(str(mgsc)) if mgsc else (None if module else shutil.which('mgsc'))
    compiler_setup_error = f'Native MGSC executable not found: {mgsc}' if mgsc and not native else ''
    if native:
        print(f'Compiler: {native}', flush=True)
    elif not compiler_setup_error:
        check = [node, str(ROOT/'scripts/compile_mgs.mjs'), '--check', '-'] + ([str(module.resolve())] if module else [])
        try:
            setup = subprocess.run(check, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            compiler_setup_error = f'MGSC setup failed: {error}'
        else:
            if setup.returncode:
                compiler_setup_error = ('MGSC setup failed:\n' +
                    (setup.stdout+setup.stderr).decode('utf-8', errors='replace'))
    diagnostics.mkdir(parents=True, exist_ok=True)
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
        (diagnostics / 'keyon_setup.log').write_text(keyon_setup_error or 'libkss available\n', encoding='utf-8')
        if keyon_setup_error:
            print('KEYON comparison unavailable: ' + keyon_setup_error, file=sys.stderr)
    rows = []
    for path, relative, folder, (final_mml, final_mgs), manifest in routes:
        folder.mkdir(parents=True, exist_ok=True)
        mml, mgs = folder / (path.stem+'.mml'), folder / (path.stem+'.mgs')
        package = final_mml.parent.parent
        state = package_manifest(package)
        previous = state['entries'].get(path.name, {})
        staged = package / '_source_inputs' / path.name
        staged.parent.mkdir(parents=True, exist_ok=True)
        if staged.exists() and file_digest(staged) != previous.get('staged_sha256'):
            raise ValueError(f'Staged source changed before conversion: {staged}')
        shutil.copyfile(path, staged)
        current_source_hash = file_digest(path)
        entry = dict(previous, input=path.name, source_path=str(path),
                     staged_input=staged.relative_to(package).as_posix(),
                     staged_sha256=file_digest(staged), diagnostics=folder.relative_to(package).as_posix())
        if not previous.get('published'):
            entry['source_sha256'] = current_source_hash
        if entry['staged_sha256'] != current_source_hash:
            raise ValueError(f'Source changed during staging: {path}')
        state['entries'][path.name] = entry
        save_json(manifest, state)
        converted = False
        # Never let an earlier successful artifact look like this run's success.
        for artifact in (mml, mgs, folder / 'tracks' / (path.stem + '.vgm'), folder / (path.stem + '.roundtrip.vgm'),
                         folder / 'report.json', folder / 'report.txt',
                         folder / 'publication.json',
                         folder / 'convert.log', folder / 'compile.log', folder / 'keyon.log',
                         folder / (path.stem + '.normalization.json'),
                         folder / (path.stem + '.fm.short_states.json'),
                         folder / (path.stem + '.fm.short_states.csv'),
                         folder / (path.stem + '.mgs.force.json'),
                         folder / (path.stem + '.mgs.force.csv'),
                         *(folder / f'{path.stem}.{chip}.curve_approx.{suffix}'
                           for chip in ('psg', 'scc') for suffix in ('json', 'decisions.csv')),
                         *(folder / (path.stem + '.' + suffix) for suffix in
                           ('conversion.json', 'mgs.source.json', 'volume_curves.target.json', 'opll.normalized.notes.csv',
                            'opll.normalized.loops.csv', 'opll.normalized.expanded.mml',
                            'opll.before.normalize.mml', 'psg.before.normalize.mml', 'scc.before.normalize.mml',
                            'psg.before.envelope_ties.mml', 'scc.before.envelope_ties.mml',
                            'psg.selection.json', 'psg.selection.candidates.csv', 'psg.selection.mask.csv',
                            'drums.json', 'drums.candidates.csv', 'drums.projection.csv',
                            'drums.before.target.mml', 'drums.after.target.mml')),
                         *(folder / (path.stem + '.' + chip + '.volume_curves.' + suffix)
                           for chip in ('psg', 'scc')
                           for suffix in ('json', 'candidates.csv', 'notes.csv', 'decisions.csv'))):
            if not artifact.resolve().is_relative_to(output):
                raise ValueError(f'Diagnostic artifact escapes output tree: {artifact}')
            artifact.unlink(missing_ok=True)
        row = dict(input=str(relative), status='conversion_failed', mml='',
                   publication_status='not_attempted',publication_error='',processing_status='',
                   mgs='', vgm='', vgm_status='unavailable', vgm_detail='', blueprint='', blueprint_files=[], blueprint_midi_files=[], blueprint_status='unavailable', blueprint_detail='', log='', detail='', stage='', error_code='', legacy_status='',
                   report=str((folder / 'report.txt').relative_to(output)),
                   diagnostics=str((folder / 'report.json').relative_to(output)), force_summary='',
                   normalization_status='unavailable', normalization_reason='',
                   normalization_ms=effective_options['normalization_ms'], fm_state_ms=effective_options['fm_state_ms'])
        commands = []
        force_data = None
        row.update(dict.fromkeys(KEYON_FIELDS, ''))
        row.update(keyon_status='not_compiled' if keyon else 'disabled', keyon_error='')
        stages = [('convert', [sys.executable, str(ROOT/'vgm2mml.py'), str(staged), '--outdir', str(folder), '--output-format', 'both']),
                  ('compile', [native, str(mml), str(mgs)] if native else [node, str(ROOT/'scripts/compile_mgs.mjs'), str(mml), str(mgs)] +
                   ([str(module.resolve())] if module else []))]
        if alloc is not None:
            stages[0][1].extend(['--alloc', alloc])
        stages[0][1].extend(option_args)
        if macro_mode is not None:stages[0][1].extend(['--macro-mode',macro_mode])
        if loop_mode is not None:stages[0][1].extend(['--loop-mode',loop_mode])
        if not enhance_macros:
            stages[0][1].append('--legacy-macros')
        if legacy_loops:
            stages[0][1].append('--legacy-loops')
        for stage, command in stages:
            row['stage'] = stage
            commands.append(dict(stage=stage, command=command))
            log = folder / (stage+'.log')
            row['log'] = str(log.relative_to(output))
            if stage == 'compile' and compiler_setup_error:
                log.write_text(compiler_setup_error, encoding='utf-8')
                row.update(status='compilation_failed', error_code='compiler_setup_error',
                           legacy_status='compiler_setup_error', detail=compiler_setup_error)
                break
            try:
                proc = subprocess.run(command, capture_output=True, timeout=timeout, cwd=folder)
                text = (proc.stdout+proc.stderr).decode('utf-8', errors='replace')
                log.write_text(text, encoding='utf-8')
                target = mml if stage == 'convert' else mgs
                missing_output = not target.is_file() or target.stat().st_size == 0
                partial_mml = False
                if stage == 'convert' and proc.returncode and not missing_output:
                    try:
                        partial = json.loads((folder / (path.stem + '.conversion.json')).read_text(encoding='utf-8'))
                        product = partial.get('outputs', {}).get('mml', {})
                        partial_mml = (partial.get('status') == 'partial_failure'
                            and product.get('status') == 'success'
                            and Path(product.get('path', '')).resolve() == mml.resolve())
                    except (OSError, ValueError, TypeError):
                        pass
                if (proc.returncode and not partial_mml) or missing_output:
                    code = ('missing_output' if not proc.returncode and missing_output else
                            'conversion_error' if stage == 'convert' else
                            'compiler_setup_error' if not native and proc.returncode == 2 else
                            'buffer_error' if 'buffer full' in text.lower() else
                            'compiler_error' if proc.returncode else 'missing_output')
                    row.update(status='conversion_failed' if stage == 'convert' else 'compilation_failed',
                               error_code=code, detail=(f'{stage} produced no nonempty {target.suffix[1:].upper()} output'
                                                       if code == 'missing_output' else error_detail(text)),
                               legacy_status=code if code in ('compiler_setup_error', 'buffer_error') else
                               'conversion_failed' if stage == 'convert' else 'compile_failed')
                    if stage == 'compile':
                        print(text or 'MGSC produced no MGS output', file=sys.stderr)
                        mgs.unlink(missing_ok=True)
                    break
                if stage == 'convert':
                    converted = True
            except subprocess.TimeoutExpired as error:
                log.write_text(timeout_log(error, stage), encoding='utf-8')
                row.update(status='conversion_failed' if stage == 'convert' else 'compilation_failed',
                           error_code='timeout', legacy_status=stage+'_timeout',
                           detail=f'{stage} timed out after {timeout} seconds')
                if stage == 'compile':
                    mgs.unlink(missing_ok=True)
                break
            except OSError as error:
                log.write_text(str(error), encoding='utf-8')
                row.update(status='conversion_failed' if stage == 'convert' else 'compilation_failed',
                           error_code='process_error', legacy_status=stage+'_error', detail=str(error))
                if stage == 'compile':
                    mgs.unlink(missing_ok=True)
                break
        else:
            row.update(status='success', stage='complete')
            if keyon:
                if keyon_setup_error:
                    row.update(keyon_status='unavailable', keyon_error=keyon_setup_error)
                else:
                    try:
                        counts = check_keyons(path, mgs, folder, node, libkss_module, timeout)
                        if counts.get('keyon_status') == 'projected_source':
                            row.update(counts)
                        else:
                            different = counts['missing_keyon'] or counts['extra_keyon']
                            row.update(counts, keyon_status='mismatch' if different else 'compared')
                        if psg_part != 'all' and row['keyon_status'] != 'projected_source':
                            row.update(keyon_status='selection_only', keyon_error=(
                                'PSG solo playback export completed; native OPLL intentionally excluded; '
                                'melodic key-on count equality is not applicable'))
                    except subprocess.TimeoutExpired as error:
                        row.update(keyon_status='timeout', keyon_error=str(error))
                        (folder / 'keyon.log').write_text(timeout_log(error, 'keyon'), encoding='utf-8')
                    except (OSError, ValueError, struct.error) as error:
                        row.update(keyon_status='error', keyon_error=str(error))
                        (folder / 'keyon.log').write_text(str(error), encoding='utf-8')
        previous_state=json.loads(json.dumps(state))
        products = dict(previous.get('published', {}))
        # Keep a previously complete listening pair when a later attempt fails.
        listening_names = {target.relative_to(package).as_posix() for target in (final_mml, final_mgs)}
        publish = row['status'] == 'success' or (converted and not listening_names.intersection(products))
        publications = []
        if publish:
            for target in (final_mml, final_mgs):
                if target.exists() and file_digest(target) != products.get(target.relative_to(package).as_posix()):
                    raise ValueError(f'Final target changed during conversion: {target}')
            row['mml'] = str(final_mml.relative_to(output))
            products[final_mml.relative_to(package).as_posix()] = file_digest(mml)
            publications.append((mml, final_mml))
            if row['status'] == 'success':
                row['mgs'] = str(final_mgs.relative_to(output))
                products[final_mgs.relative_to(package).as_posix()] = file_digest(mgs)
                publications.append((mgs, final_mgs))
            entry.update(published=products, publication_status=row['status'], source_sha256=current_source_hash)
        conversion_report = folder / (path.stem + '.conversion.json')
        try:
            current_report = json.loads(conversion_report.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            current_report = {}
        reference, vgm_status, vgm_detail = reference_vgm_product(current_report, folder, path.stem)
        row.update(vgm_status=vgm_status, vgm_detail=vgm_detail)
        if reference:
            final_vgm = final_mml.with_suffix('.vgm')
            name = final_vgm.relative_to(package).as_posix()
            if final_vgm.exists() and file_digest(final_vgm) != products.get(name):
                raise ValueError(f'Final VGM changed during conversion: {final_vgm}')
            products[name] = file_digest(reference)
            publications.append((reference, final_vgm))
            row['vgm'] = final_vgm.relative_to(output).as_posix()
            entry.update(published=products, vgm_source_sha256=current_source_hash)
        bp_publish, bp_delete, products, bp_status, bp_detail, bp_targets = prepare_blueprints(
            current_report, folder, path.stem, package, products)
        row.update(blueprint_status=bp_status, blueprint_detail=bp_detail,
                   blueprint_files=[target.relative_to(output).as_posix() for target in bp_targets if target.suffix=='.mml'],
                   blueprint_midi_files=[target.relative_to(output).as_posix() for target in bp_targets if target.suffix=='.midi'])
        if bp_targets:
            row['blueprint'] = row['blueprint_files'][0]
            publications.extend(bp_publish)
            entry.update(published=products, blueprint_source_sha256=current_source_hash)
        row['processing_status']=row['status']
        row['publication_status']='success' if publications else 'not_needed'
        entry.update(stem=path.stem, status=entry.get('publication_status', row['status']),
                     latest_attempt_status=row['status'], latest_attempt=dict(row, source_sha256=current_source_hash))
        state['entries'][path.name] = entry
        try:
            if publications:
                publication=publish_bundle(publications, manifest, state, folder, deletions=bp_delete)
                row['publication_status']='success'
            else:
                save_json(manifest, state)
                publication=dict(status='not_needed',operations=[])
                row['publication_status']='not_needed'
        except OSError as error:
            publication=dict(status='failed',error=str(error),
                context=getattr(error,'publication_context',{}),processing_status=row['status'])
            row.update(status='publication_failed',stage='publish',error_code='publication_error',
                publication_status='failed',publication_error=str(error),
                detail=f"Output publication failed after {row['processing_status']}: {error}",
                mml='',mgs='',vgm='',blueprint='',blueprint_files=[],blueprint_midi_files=[])
            if reference:row['vgm_status']='publication_failed'
            if bp_targets:row['blueprint_status']='publication_failed'
            state=previous_state
            prior=state['entries'][path.name]
            prior.setdefault('status','unpublished')
            prior.update(latest_attempt_status=row['status'],latest_attempt=dict(row,source_sha256=current_source_hash))
            try:save_json(manifest,state)
            except OSError as manifest_error:publication['manifest_error']=str(manifest_error)
        (folder/'publication.json').write_text(json.dumps(publication,indent=2)+'\n',encoding='utf-8')
        summaries = {}
        for name, suffix in (('normalization', 'normalization.json'),
                             ('fm_states', 'fm.short_states.json'), ('conversion', 'conversion.json'),
                             ('drums', 'drums.json'), ('psg_selection', 'psg.selection.json'),
                             ('psg_volume_curves', 'psg.volume_curves.json'),
                             ('scc_volume_curves', 'scc.volume_curves.json'),
                             ('volume_curve_target', 'volume_curves.target.json'),
                             ('source_projection', 'huc6280.projection.json')):
            summary_path = folder / (path.stem + '.' + suffix)
            if summary_path.is_file():
                try:
                    summaries[name] = json.loads(summary_path.read_text(encoding='utf-8'))
                except (ValueError, TypeError) as error:
                    summaries[name] = dict(report_error=str(error))
        normalization = summaries.get('normalization', {})
        row['normalization_status'] = normalization.get('status', 'unavailable')
        row['normalization_reason'] = normalization.get('reason', '')
        sidecar = folder / (path.stem + '.mgs.force.json')
        if sidecar.is_file():
            try:
                force_data = json.loads(sidecar.read_text(encoding='utf-8'))
                if force_data.get('enabled') or force_data['omission_count']:
                    row['force_summary'] = f"{force_data['omission_count']} omitted target operations"
            except (ValueError, KeyError, TypeError) as error:
                row['force_summary'] = f'Invalid force report: {error}'
        report = dict(result=dict(row), input_path=str(path), output_root=str(output), adjacent_output=adjacent,
                      options=effective_options,
                      commands=commands, logs={name: str(folder / (name + '.log'))
                                              for name in ('convert', 'compile', 'keyon')
                                              if (folder / (name + '.log')).is_file()},
                      force=force_data, summaries=summaries,publication=publication)
        report['logs']['publication']=str(folder/'publication.json')
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        lines = [f"{relative}: {row['status']}", f"Stage: {row['stage']}",
                 f"Error code: {row['error_code']}", f"Detail: {row['detail']}",
                 'Options: ' + json.dumps(effective_options, sort_keys=True),
                 'Normalization: ' + row['normalization_status'] + ' ' + row['normalization_reason']]
        lines.extend(item['stage'] + ': ' + json.dumps(item['command']) for item in commands)
        lines.extend(name + ' log: ' + value for name, value in report['logs'].items())
        (folder / 'report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        rows.append(row)
        save_package_results(package, output, rows)
        with (diagnostics/'results.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader(); writer.writerows(rows)
        (diagnostics/'results.json').write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')
        print(f"{relative}: {row['status']}" + (f": {row['detail']}" if row['detail'] else ''), flush=True)
        if row['blueprint_status'] == 'blocked':
            print('Blueprint update skipped: ' + row['blueprint_detail'], flush=True)
        if row['keyon_status'] == 'mismatch':
            print(f"Key-on mismatch: reference {row['reference_keyon']}; actual {row['actual_keyon']}; "
                  f"missing {row['missing_keyon']}; extra {row['extra_keyon']}", flush=True)
        drums = summaries.get('drums', {})
        if drums.get('enabled'):
            print(f"Rhythm enhancement: {drums['added_hits']} added hits; {drums['reason']}", flush=True)
        selection = summaries.get('psg_selection', {})
        if selection.get('enabled'):
            print(f"PSG selection: {selection['part']}; {selection['eligible_rhythm_candidates']} rhythm candidates; "
                  f"{selection['selected_audible_intervals']} audible intervals; "
                  f"{selection['hardware_phase_abstentions']} hardware-envelope abstentions", flush=True)
        source_projection = summaries.get('source_projection', {})
        if source_projection.get('force_loop_approximation'):
            print('HuC6280 loop approximation: restore first-traversal state at loop entry; '
                  'native source evidence is unchanged', flush=True)
            print('Projection details: ' + str(folder / (path.stem + '.huc6280.projection.json')), flush=True)
        if row['force_summary']:
            print('Forced MGS projection: ' + row['force_summary'], flush=True)
            print('Omission details: ' + str(force_data.get('csv_path', sidecar) if force_data else sidecar), flush=True)
    print(f"{sum(row['status'] == 'success' for row in rows)}/{len(rows)} exported; results: {diagnostics / 'results.csv'}", flush=True)
    return rows


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir', type=Path)
    parser.add_argument('--outdir', type=Path,
                        help='Output root preserving input-relative parents (default: beside each source VGM)')
    parser.add_argument('--mgsc', help='Native MGSC executable (default: PATH)')
    parser.add_argument('--mgsc-module', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--timeout', type=int, default=1200)
    parser.add_argument('--alloc', help='Allocation overrides forwarded to every conversion')
    parser.add_argument('--normalize-lengths', action='store_true',
                        help='Enable optional musical duration normalization for every conversion')
    from score_normalization import add_arguments
    add_arguments(parser)
    parser.add_argument('--normalization-ms', type=float, help='Duration correction threshold in milliseconds; enables normalization')
    parser.add_argument('--fm-state-ms', type=float, help='Internal FM state threshold in milliseconds (default: 1)')
    add_curve_arguments(parser)
    parser.add_argument('--enhance-rhythm', '--enhance-drums', dest='enhance_drums', action='store_true', help='Add inferred PSG/SCC percussion on OPLL rhythm')
    volume_curves = parser.add_mutually_exclusive_group()
    volume_curves.add_argument('--software-volume-curves', action='store_true', default=False,
                        help='Project exact fixed-pitch PSG/SCC volume curves to software envelopes (opt-in)')
    volume_curves.add_argument('--no-software-volume-curves', dest='software_volume_curves',
                               action='store_false', help='Disable PSG/SCC software volume curve projection')
    parts = parser.add_mutually_exclusive_group()
    parts.add_argument('--psg-melody-only', '--psg-melody_only', dest='psg_part',
                       action='store_const', const='melody', default='all')
    parts.add_argument('--psg-rhythm-only', '--psg-rhythm_only', dest='psg_part',
                       action='store_const', const='rhythm')
    parser.add_argument('--force', action='store_true', help='Apply only documented target omission rules')
    parser.add_argument('--dump-passes', action='store_true', help='Retain inspectable conversion passes')
    parser.add_argument('--enhance-macros', action='store_true', default=True,
                        help='Enable enhanced macros (now the default)')
    parser.add_argument('--legacy-macros', dest='enhance_macros', action='store_false',
                        help='Use the previous macro compressor')
    parser.add_argument('--legacy-loops', action='store_true',
                        help='Use the previous OPLL loop projection')
    parser.add_argument('--skip-keyon-counts', action='store_true', help='Disable MGS playback and OPLL key-on comparison')
    parser.add_argument('--libkss-module', type=Path, help='Explicit libkss-js entry point for MGS export')
    return parser


if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()
    try:
        results = run_batch(args.input_dir, args.outdir, args.mgsc_module, args.node, args.timeout, args.mgsc, args.alloc,
                            keyon=not args.skip_keyon_counts, libkss_module=args.libkss_module,
                            normalize_lengths=args.normalize_lengths, enhance_macros=args.enhance_macros, legacy_loops=args.legacy_loops,
                            score_normalize=args.score_normalize,score_tempo=args.score_tempo,
                            blueprint_score_normalize=args.blueprint_score_normalize,
                            force=args.force, fm_state_ms=args.fm_state_ms, normalization_ms=args.normalization_ms,
                            dump_passes=args.dump_passes, enhance_drums=args.enhance_drums, psg_part=args.psg_part,
                            software_volume_curves=args.software_volume_curves,
                            **curve_option_values(args))
    except (RuntimeError, ValueError) as error:
        parser.exit(2, str(error)+'\n')
    sys.exit(0 if all(r['status'] == 'success' and r.get('vgm_status') not in ('failed', 'blocked')
                     and r['keyon_status'] in ('compared', 'disabled', 'selection_only', 'projected_source') for r in results) else 1)
