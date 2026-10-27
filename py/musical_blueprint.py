"""Editable scores: remove dynamics only at the blueprint target boundary."""
from collections import defaultdict
from dataclasses import replace
import csv
import hashlib
import json
import math
import re
from pathlib import Path
import tempfile

from native_music import NativeControl, NativeDevice, NativePerformance, NativePercussion, NativeUnit, NativeVoice
from native_blueprint import NativeBlueprintError as BlueprintError
from native_blueprint import encoded_length as _length, render_native_blueprints


def _origins(plan):
    projection = dict(plan.metadata).get('source_projection') or {}
    return {(row['target_chip'], row['target_channel']):
            (projection['source'], row['source_channel'])
            for row in projection.get('allocation', ())}


def _frequency(chip, value, clocks):
    if value is None:
        return None
    if chip == 'opll':
        fnum, block, _ = value
        return 49716*fnum*2**block/2**19 if fnum else None
    period = value[0]
    if not period and chip != 'scc':
        return None
    return clocks.get(chip, 1789773)/(16*max(1, period+(chip == 'scc')))


def _legacy_performance(plan):
    """Adapt accepted legacy decisions, without mutating their original curves."""
    origins, clocks = _origins(plan), dict(plan.chip_clocks)
    controls = plan.ordered_controls()
    by_channel = defaultdict(list)
    for c in controls:
        if c.channel is not None:
            by_channel[c.chip, c.channel].append(c)
    devices, voices, units, decisions = {}, {}, [], []
    for original in plan.units:
        if original.rest or original.end_sample <= original.start_sample or original.articulation == 'inferred_percussion':
            continue
        lane = original.chip, original.channel
        chip, channel = origins.get(lane, lane)
        device_id = chip+':0'
        devices.setdefault(device_id, NativeDevice(device_id, chip, 0, clocks.get(original.chip, 1789773)))
        section = {'opll': 'fm', 'psg': 'tone', 'scc': 'wave'}.get(original.chip, 'tone')
        rows = by_channel[lane]
        current = {'pitch': None, 'instrument': (None,), 'volume': (None,)}
        for c in rows:
            if c.sample < original.start_sample and c.kind in current:
                current[c.kind] = c.value
        events = [c for c in rows if original.start_sample <= c.sample < original.end_sample
                  and c.unit_id in (None, original.unit_id)]
        points = defaultdict(list)
        for c in events:
            points[c.sample].append(c)
        def voice(at):
            if original.chip == 'opll':
                instrument = current['instrument'][0]
                parameters = (('instrument', instrument),)
                if instrument == 0:
                    patch = [None]*8
                    for c in controls:
                        if c.sample > at:
                            break
                        if c.chip == 'opll' and c.kind == 'patch_write':
                            patch[c.value[0]] = c.value[1]
                    parameters += (('patch', tuple(patch)),)
            elif original.chip == 'scc':
                data = dict(original.parameters)
                parameters = (('waveform_id', data.get('waveform_id')),
                              ('waveform_hex', data.get('waveform_hex')))
            else:
                data = dict(original.parameters)
                parameters = (('mode', data.get('mode', 1)),)
            identity = device_id+':voice:'+hashlib.sha256(repr(parameters).encode()).hexdigest()[:12]
            voices.setdefault(identity, NativeVoice(identity, device_id, section, parameters))
            return identity
        active, start, pitch_curve, volume_curve, selected_voice, piece = True, original.start_sample, [], [], None, 0
        def close(stop):
            if stop <= start:
                decisions.append(dict(unit_id=original.unit_id, reason='zero_duration_gate'))
                return
            role = 'noise' if original.chip == 'psg' and dict(original.parameters).get('mode') == 2 else 'melody'
            units.append(NativeUnit(original.unit_id+(f':attack{piece}' if piece else ''), device_id,
                section, channel, start, stop, tuple(pitch_curve), tuple(volume_curve),
                ((start, selected_voice or voice(start)),), source_indices=original.source_indices,
                role=role, parameters=(('legacy_unit_ids', (original.unit_id,)),
                                       ('source_gate_ids', original.gate_ids))))
        for at in sorted({original.start_sample, *points}):
            group = points[at]
            incoming, off_seen = active, False
            for c in group:
                if c.kind in current:
                    current[c.kind] = c.value
                elif c.kind == 'gate':
                    off_seen |= c.value == (0,)
                    active = bool(c.value[0])
            if incoming and (not active or off_seen and at > start):
                close(at)
            if active and (not incoming or off_seen and at > start):
                piece += 1
                start, pitch_curve, volume_curve, selected_voice = at, [], [], voice(at)
            if active:
                if selected_voice is None:
                    selected_voice = voice(at)
                frequency = _frequency(original.chip, current['pitch'], clocks)
                if not pitch_curve or pitch_curve[-1][1] != frequency:
                    pitch_curve.append((at, frequency))
                if not volume_curve or volume_curve[-1][1] != current['volume'][0]:
                    volume_curve.append((at, current['volume'][0]))
        if active:
            close(original.end_sample)
    # Target score partitions sharing one source gate may differ only in dynamics.
    # Only join adjacent partitions with shared gate evidence and no observed edge.
    merged = []
    observed_edges = {(c.chip, c.channel, c.sample) for c in controls
                      if c.kind == 'gate' and c.value == (0,) and c.origin.startswith('observed_')}
    for unit in sorted(units, key=lambda u: (u.device_id, u.section, u.channel, u.start_sample)):
        if merged:
            previous = merged[-1]
            a, b = dict(previous.parameters), dict(unit.parameters)
            shared_gate = set(a.get('source_gate_ids', ())) & set(b.get('source_gate_ids', ()))
            source_edge = any(at == unit.start_sample and origins.get((chip, ch), (chip, ch)) ==
                              (devices[unit.device_id].chip, unit.channel)
                              for chip, ch, at in observed_edges)
            if (previous.device_id, previous.section, previous.channel, previous.end_sample) == (
                    unit.device_id, unit.section, unit.channel, unit.start_sample) and shared_gate and not source_edge:
                merged[-1] = replace(previous, end_sample=unit.end_sample,
                    pitch_curve=previous.pitch_curve+unit.pitch_curve,
                    volume_curve=previous.volume_curve+unit.volume_curve,
                    voice_curve=previous.voice_curve+unit.voice_curve,
                    source_indices=previous.source_indices+unit.source_indices,
                    parameters=(('legacy_unit_ids', a.get('legacy_unit_ids', ())+b.get('legacy_unit_ids', ())),
                                ('source_gate_ids', tuple(dict.fromkeys(a['source_gate_ids']+b['source_gate_ids'])))))
                continue
        merged.append(unit)
    percussion = []
    source_mask, held, overlay = 0, {}, {}
    for c in controls:
        if c.chip != 'opll':
            continue
        if c.kind == 'rhythm_register' and c.value[0] == 14:
            devices.setdefault('opll:0', NativeDevice('opll:0', 'opll', 0, clocks.get('opll', 3579545)))
            new = c.value[1] & 31 if c.value[1] & 32 else 0
            for bit, family in ((16, 'BD'), (8, 'SD'), (4, 'TOM'), (2, 'CYM'), (1, 'HH')):
                if new & bit and not source_mask & bit:
                    identity = f'opll:rhythm:{family}:{len(percussion)}'
                    held[bit] = len(percussion)
                    percussion.append(NativePercussion(identity, 'opll:0', family, family, c.sample,
                        parameters=(('origin', 'observed_opll_rhythm'),)))
                elif source_mask & bit and not new & bit and bit in held:
                    index = held.pop(bit)
                    percussion[index] = replace(percussion[index], stop_sample=c.sample)
            source_mask = new
        elif c.kind == 'percussion':
            devices.setdefault('opll:0', NativeDevice('opll:0', 'opll', 0, clocks.get('opll', 3579545)))
            instrument, volume, enabled = c.value
            family = ('BD', 'SD', 'TOM', 'CYM', 'HH')[instrument]
            identity = c.unit_id or f'opll:inferred:{family}:{c.source_sample}'
            if enabled:
                overlay[identity] = len(percussion)
                percussion.append(NativePercussion(identity, 'opll:0', family, family, c.sample,
                    observed=False, parameters=(('origin', 'inferred_percussion'),)))
            elif identity in overlay:
                index = overlay.pop(identity)
                percussion[index] = replace(percussion[index], stop_sample=c.sample)
    normalization = dict(plan.metadata).get('normalization') or {}
    tempo = (normalization.get('timing') or {}).get('tempo', 225) if normalization.get('applied') else 225
    return NativePerformance(tuple(devices.values()), tuple(merged), (), tuple(voices.values()), tuple(percussion), (),
        plan.end_sample, dict(plan.metadata).get('source_sha256', ''), '',
        metadata=(('blueprint_tempo', tempo),), decisions=tuple(decisions))


def render_blueprints(plan):
    source = getattr(plan, 'source_performance', None)
    if source is not None and _origins(plan):
        # HuC currently reaches the legacy engine through a documented native
        # projection. Correct blueprint provenance without changing that bundle.
        origins = _origins(plan)
        devices = {device.device_id: device for device in source.devices}
        units, remapped_devices = [], {}
        for unit in source.units:
            device = devices[unit.device_id]
            origin = origins.get((device.chip, unit.channel))
            if origin is not None:
                chip, channel = origin
                identity = f'{chip}:{device.instance}'
                remapped_devices.setdefault(identity, NativeDevice(identity, chip, device.instance,
                    device.clock_hz, parameters=(('blueprint_source_alias', device.device_id),)))
                units.append(replace(unit, device_id=identity, channel=channel))
            else:
                units.append(unit)
        source = replace(source, devices=source.devices+tuple(remapped_devices.values()), units=tuple(units))
    return render_native_blueprints(source if source is not None else _legacy_performance(plan),
                                    score_guide=getattr(plan,'score_guide',None))


def render_blueprint(plan):
    """Compatibility view of the first score; file_count reports required splits."""
    pages = render_blueprints(plan)
    if not pages:
        raise BlueprintError('No non-PCM sounding parts for blueprint')
    return pages[0]


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_blueprint(plan, output_root, stem):
    """Publish all score pages atomically and protect any hand-edited page."""
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not stem or Path(stem).name != stem:
        return dict(status='blocked', detail='Blueprint stem must be a file name')
    report_path = root/f'{stem}.blueprint.json'
    csv_path = root/f'{stem}.blueprint.units.csv'
    if report_path.is_symlink() or report_path.exists() and not report_path.is_file():
        return dict(status='blocked', detail='Blueprint diagnostic path is not a regular owned output')
    try:
        previous = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}
    source = getattr(plan, 'source_performance', None)
    source_hash = source.source_sha256 if source is not None else dict(plan.metadata).get('source_sha256')
    report = dict(status='blocked', source_sha256=source_hash)
    previous_files = previous.get('files') or ([dict(path=previous.get('path', str(root/'blueprint'/f'{stem}.mml')),
                                                 sha256=previous['sha256'])] if previous.get('sha256') else [])
    if not isinstance(previous_files, list):
        previous_files = []
    invalid_ownership = False
    for item in previous_files:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('sha256'), str):
            invalid_ownership = True
            break
        path = Path(item['path'])
        extra = re.fullmatch(re.escape(stem)+r'\.part(\d{2,})\.mml', path.name)
        if (not path.is_absolute() or path.parent.resolve() != (root/'blueprint').resolve()
                or path.name != stem+'.mml' and not (extra and int(extra[1]) >= 2)
                or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])):
            invalid_ownership = True
            break
    if invalid_ownership:
        previous_files = []
    owned = {str(Path(item['path']).resolve()): item['sha256'] for item in previous_files}
    if previous.get('sha256'):
        report.update(sha256=previous['sha256'], files=previous_files,
                      previous_artifact_retained=any(Path(item['path']).exists() for item in previous_files))
    try:
        if invalid_ownership:
            raise BlueprintError('Invalid blueprint ownership record; keeping existing files')
        if (root/'blueprint').is_symlink():
            raise BlueprintError('Blueprint output directory is a symbolic link')
        if csv_path.is_symlink() or csv_path.exists() and not csv_path.is_file():
            raise BlueprintError('Blueprint diagnostic path is a symbolic link')
        rendered = render_blueprints(plan)
        if not rendered:
            report.update(status='not_applicable', detail='No non-PCM sounding parts for blueprint')
            report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            return report
        targets = [root/'blueprint'/(f'{stem}.mml' if i == 0 else f'{stem}.part{i+1:02d}.mml')
                   for i in range(len(rendered))]
        candidates = {Path(name) for name in owned} | set(targets)
        initial = {}
        for target in candidates:
            if not target.resolve().is_relative_to(root) or target.is_symlink():
                raise BlueprintError('Blueprint output escapes its output root')
            value = _digest(target) if target.is_file() else None
            if target.exists() and (not target.is_file() or value != owned.get(str(target.resolve()))):
                raise BlueprintError(f'Refusing to overwrite an unowned or edited blueprint: {target}')
            initial[target] = value
        files, allocations = [], []
        for i, ((text, data), target) in enumerate(zip(rendered, targets)):
            files.append(dict(path=str(target), name=target.name,
                              sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                              sounding_units=data['sounding_units'], source_parts=sorted({
                                  (r['source_chip'], r['source_instance'], r['source_section'], r['source_channel'])
                                  for r in data['allocations']})))
            allocations.extend(dict(row, file_name=target.name) for row in data['allocations'])
        report = dict(rendered[0][1], source_sha256=source_hash, path=str(targets[0]),
            sha256=files[0]['sha256'], files=files, file_count=len(files),
            sounding_units=sum(data['sounding_units'] for _, data in rendered),
            allocations=allocations, per_file_reports=[data for _, data in rendered])
        target_root = root/'blueprint'
        target_root.mkdir(parents=True, exist_ok=True)
        # Prepare the complete score/diagnostic bundle before changing owned files.
        with tempfile.TemporaryDirectory(dir=root, prefix='.blueprint_') as temporary:
            temporary = Path(temporary)
            prepared = {}
            for i, ((text, _), target) in enumerate(zip(rendered, targets)):
                stage = temporary/f'score{i}'
                stage.write_text(text, encoding='utf-8')
                prepared[target] = stage
            stage = temporary/'units.csv'
            with stage.open('w', encoding='utf-8', newline='') as stream:
                fields = list(allocations[0]) if allocations else ['unit_id','source_chip','source_channel','file_name']
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader();writer.writerows(allocations)
            prepared[csv_path] = stage
            stage = temporary/'report.json'
            stage.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            prepared[report_path] = stage
            for target, value in initial.items():
                now = _digest(target) if target.is_file() else None
                if target.is_symlink() or now != value:
                    raise BlueprintError('Blueprint changed during rendering; keeping the edited file')
            backups = {p: p.read_bytes() if p.is_file() else None for p in candidates | set(prepared)}
            try:
                for target, stage in prepared.items():
                    stage.replace(target)
                for target in candidates-set(targets):
                    target.unlink(missing_ok=True)
            except OSError:
                for target, data in backups.items():
                    if data is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(data)
                raise
        return report
    except (ValueError, OSError) as error:
        report.update(status='blocked', detail=str(error), error_type=type(error).__name__)
        if isinstance(error, BlueprintError):
            report['projection_detail'] = error.projection_detail
        if not report_path.is_symlink():
            try:
                report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            except OSError as diagnostic_error:
                report['diagnostic_error'] = str(diagnostic_error)
        return report
