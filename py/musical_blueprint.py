"""Editable, timbre-free MGSDRV score lowered from accepted musical units.

This backend does not edit native evidence or the ordinary MML backend. Volume
holds are explicit score controls; wave/patch/SW-envelope banks are not copied.
"""
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from fractions import Fraction
from itertools import groupby
import hashlib
import json
import math
import re
from pathlib import Path
import tempfile

from mml_envelopes import length_tokens
from mml_macros import compress_macros
from mml_sync import annotate_sync_points
from opll_target import MGSDRV_FNUM, NOTE_NAMES
from psg_scc_target import BASE_PERIODS, TUNING_HEADER, envelope_period_tokens
from source_loop_plan import SourceLoopPlan


class BlueprintError(ValueError):
    def __init__(self, message, **projection_detail):
        super().__init__(message)
        self.projection_detail = projection_detail


TRACKS = {'psg': '123', 'scc': '45678', 'opll': '9abcdefgh'}


def _length(pitch, steps, tie=False, minimum=1):
    # A one/two-step hold must use %1/%2: c192/c96 exceed MGSC's
    # denominator range. The normal frame renderer never reaches those holds.
    parts = []
    while steps:
        chunk = min(steps, 255)
        if 0 < steps-chunk < minimum:
            chunk -= minimum-(steps-chunk)
        if chunk < minimum:
            raise BlueprintError('Encoded duration is below the MGSC minimum', steps=steps, minimum=minimum)
        parts.append(length_tokens(pitch, chunk, True, tie=tie or bool(parts)))
        steps -= chunk
    text = ' '.join(parts)
    def spelling(match):
        amount = int(match[1])
        return str(192 // amount) if 192 % amount == 0 and 192 // amount <= 64 else match[0]
    return re.sub(r'%(\d+)', spelling, text)


def _origins(plan):
    projection = dict(plan.metadata).get('source_projection') or {}
    return {(row['target_chip'], row['target_channel']):
            (projection['source'], row['source_channel'])
            for row in projection.get('allocation', ())}


def _pitch(chip, value, target, clocks):
    if chip == 'opll':
        fnum, block, _ = value
        if not fnum:
            raise BlueprintError('An active OPLL note has no pitch')
        octave, scale = min(((o, n) for o in range(1, 9) for n in range(12)),
            key=lambda pair: abs(math.log2((MGSDRV_FNUM[pair[1]] * 2 ** (pair[0]-1)) /
                                          (fnum * 2 ** block))))
        return octave, NOTE_NAMES[scale], 0
    period = value[0]
    if chip == target:
        if period <= 0:
            raise BlueprintError('A pitched PSG/SCC note has zero period')
        octave, scale = min(((o, n) for o in range(1, 9) for n in range(12)),
            key=lambda pair: abs(math.log2((BASE_PERIODS[pair[1]] >> (pair[0]-1)) / period)))
        base = BASE_PERIODS[scale] >> (octave-1)
        detune = base - period
        if not -127 <= detune <= 127:
            raise BlueprintError('PSG/SCC pitch exceeds MGSDRV detune range')
        return octave, NOTE_NAMES[scale], detune
    # The native frequency is interpreted here, not written back into the plan.
    frequency = clocks.get(chip, 1789773) / (16 * max(1, period + (chip == 'scc')))
    if target == 'opll':
        octave, scale = min(((o, n) for o in range(1, 9) for n in range(12)),
            key=lambda pair: abs(math.log2((49716 * MGSDRV_FNUM[pair[1]] * 2 ** (pair[0]-1) /
                                          2 ** 19) / frequency)))
        return octave, NOTE_NAMES[scale], 0
    wanted = round(clocks.get('psg', 1789773) / (16 * frequency))
    return _pitch('psg', (wanted,), 'psg', clocks)


def _allocate(plan, units, rhythm):
    origins = _origins(plan)
    native = {(u.chip, u.channel) for u in units if (u.chip, u.channel) not in origins}
    occupied = defaultdict(list)
    allocations, affinity = {}, {}
    for unit in sorted(units, key=lambda u: (u.start_sample, u.chip, u.channel, u.unit_id)):
        lane = unit.chip, unit.channel
        if lane not in origins:
            target = lane
        else:
            candidates = [('opll', ch) for ch in range(6 if rhythm else 9)] + [('psg', ch) for ch in range(3)]
            if lane in affinity:
                candidates.remove(affinity[lane])
                candidates.insert(0, affinity[lane])
            target = next((item for item in candidates if item not in native and all(
                unit.end_sample <= start or unit.start_sample >= stop for start, stop in occupied[item])), None)
            if target is None:
                raise BlueprintError(f'No free OPLL/PSG lane for {origins[lane]} at {unit.start_sample}')
            affinity[lane] = target
        if target[0] not in TRACKS:
            raise BlueprintError(f'No blueprint notation for {target[0]}')
        if rhythm and target[0] == 'opll' and target[1] >= 6:
            raise BlueprintError('Nine-channel OPLL melody and rhythm require different MGSDRV modes')
        if any(unit.start_sample < stop and unit.end_sample > start for start, stop in occupied[target]):
            raise BlueprintError(f'Overlapping sounding units in blueprint lane {target}')
        occupied[target].append((unit.start_sample, unit.end_sample))
        allocations[unit.unit_id] = target
    return allocations, origins


def render_blueprint(plan):
    """Return MML and an inspectable projection report, without file mutation."""
    normalization = dict(plan.metadata).get('normalization') or {}
    tempo = (normalization.get('timing') or {}).get('tempo', 225) if normalization.get('applied') else 225
    ratio = Fraction(str(tempo)) * 48 / (44100 * 60)
    # Same compiler-frame bound used by the ordinary normalized MML backend.
    minimum = max(1, int(tempo) // 75)
    rounding = {}
    def step(sample):
        value = round(sample * ratio)
        shift = float(Fraction(value, 1) / ratio - sample)
        if abs(shift) > 0.51:
            rounding[sample] = dict(sample=sample, step=value, shift_samples=shift)
        return value
    def encode_duration(pitch, steps, tie=False, **context):
        if 0 < steps < minimum:
            raise BlueprintError('Blueprint interval is below the MGSC minimum duration',
                tempo=tempo, steps=steps, minimum_steps=minimum, **context)
        return _length(pitch, steps, tie=tie, minimum=minimum)
    controls = plan.ordered_controls()
    rhythm = any(c.kind == 'percussion' or c.kind == 'rhythm_register' and
                 c.value[0] == 14 and c.value[1] & 32 for c in controls)
    units = [u for u in plan.units if not u.rest and u.end_sample > u.start_sample
             and u.articulation != 'inferred_percussion']
    allocations, origins = _allocate(plan, units, rhythm)
    channels, globals_ = defaultdict(list), []
    for control in controls:
        if control.channel is None:
            globals_.append(control)
        else:
            channels[control.chip, control.channel].append(control)
    histories = {}
    for lane, rows in channels.items():
        kinds = defaultdict(list)
        for c in rows:
            kinds[c.kind].append(c)
        histories[lane] = {kind: ([c.sample for c in seq], seq) for kind, seq in kinds.items()}
    def before(lane, kind, sample, default):
        times, rows = histories.get(lane, {}).get(kind, ([], []))
        index = bisect_right(times, sample - 1) - 1
        return rows[index].value if index >= 0 else default
    global_history = defaultdict(list)
    for c in globals_:
        global_history[c.kind].append(c)
    def global_before(kind, sample, default):
        rows = global_history.get(kind, ())
        index = bisect_right([c.sample for c in rows], sample) - 1
        return rows[index].value if index >= 0 else default

    lanes = defaultdict(list)
    evidence, excluded = [], Counter()
    for c in controls:
        if c.kind in ('instrument', 'waveform', 'wave_write', 'patch_write'):
            excluded[c.kind] += 1
    for unit in units:
        lane = unit.chip, unit.channel
        target = allocations[unit.unit_id]
        events = [c for c in channels[lane] if unit.start_sample <= c.sample < unit.end_sample
                  and c.unit_id in (None, unit.unit_id) and c.kind in
                  ('pitch', 'volume', 'gate', 'psg_mode', 'psg_envelope_enable')]
        if unit.chip == target[0] == 'psg':
            parameters = dict(unit.parameters)
            events += [c for c in globals_ if unit.start_sample <= c.sample < unit.end_sample and
                       (c.kind == 'psg_noise' and parameters.get('mode', 1) & 2 or
                        c.kind in ('psg_envelope_period', 'psg_envelope_shape') and
                        parameters.get('hardware_envelope', False))]
        events.sort(key=lambda c: (c.sample, c.order))
        points = defaultdict(list)
        start, stop = step(unit.start_sample), step(unit.end_sample)
        if stop <= start:
            raise BlueprintError(f'Positive sounding unit collapses on the MML clock: {unit.unit_id}')
        for c in events:
            points[min(stop, step(c.sample))].append(c)
        state = {kind: before(lane, kind, unit.start_sample, default) for kind, default in
                 (('pitch', None), ('volume', (15,)), ('psg_mode', (1,)),
                  ('psg_envelope_enable', (0,)))}
        state['gate'] = (1,)
        for kind, default in (('psg_noise', (0,)), ('psg_envelope_period', (0,)),
                              ('psg_envelope_shape', (0,))):
            state[kind] = global_before(kind, unit.start_sample, default)
        commands, previous, sounding = [], {}, False
        cuts = sorted({start, stop, *points})
        for index, at in enumerate(cuts[:-1]):
            reattack, envelope_trigger = False, False
            for c in points[at]:
                if c.kind == 'gate' and c.value == (0,):
                    reattack = True
                if c.kind == 'psg_envelope_shape':
                    envelope_trigger = True
                state[c.kind] = c.value
            duration = cuts[index+1] - at
            if not duration:
                continue
            def duration_text(pitch, tie=False):
                return encode_duration(pitch, duration, tie=tie, unit_id=unit.unit_id,
                    sample_start=unit.start_sample, sample_end=unit.end_sample,
                    step_start=at, step_end=cuts[index+1], controls=[dict(
                        sample=c.sample, kind=c.kind, value=c.value, source_event_id=c.source_event_id)
                        for c in points[at]])
            if state['gate'] == (0,):
                commands.append(duration_text('r'))
                sounding = False
                continue
            if state['pitch'] is None:
                raise BlueprintError(f'No accepted pitch for {unit.unit_id}')
            octave, note, detune = _pitch(unit.chip, state['pitch'], target[0], dict(plan.chip_clocks))
            desired = {'octave': octave, 'detune': detune, 'volume': state['volume'][0]}
            for key, value in desired.items():
                if previous.get(key) != value:
                    prefix = {'octave': 'o', 'detune': '\\', 'volume': 'v'}[key]
                    commands.append(f'{prefix}{value}')
            if target[0] == 'psg':
                mode = state['psg_mode'][0] if unit.chip == 'psg' and lane not in origins else 1
                if previous.get('mode') != mode:
                    commands.append(f'/{mode}')
                previous['mode'] = mode
                noise = state['psg_noise'][0]
                if mode & 2 and previous.get('noise') != noise:
                    commands.append(f'n{noise}')
                previous['noise'] = noise
                hw = bool(state['psg_envelope_enable'][0]) and lane not in origins
                if hw:
                    period, shape = state['psg_envelope_period'][0], state['psg_envelope_shape'][0]
                    if previous.get('period') != period:
                        commands.append(envelope_period_tokens(period))
                    if (envelope_trigger or not previous.get('hw') or previous.get('shape') != shape
                            or previous.get('volume') != desired['volume']):
                        commands.append(f's{shape}')
                    previous.update(period=period, shape=shape)
                elif previous.get('hw'):
                    commands.append(f'v{desired["volume"]}')
                previous['hw'] = hw
            commands.append(duration_text(note, tie=sounding and not reattack))
            previous.update(desired)
            sounding = True
        text = ' '.join(commands)
        lanes[target].append((start, stop, text, unit.unit_id))
        source_chip, source_channel = origins.get(lane, lane)
        evidence.append(dict(unit_id=unit.unit_id, source_chip=source_chip, source_channel=source_channel,
            plan_chip=unit.chip, plan_channel=unit.channel, target_chip=target[0], target_channel=target[1],
            track=TRACKS[target[0]][target[1]], sample_start=unit.start_sample, sample_end=unit.end_sample,
            step_start=start, step_end=stop, mml=text))

    lines = ['; Editable blueprint: assign your own timbres; @0 is a placeholder.',
             '; No SCC wave, OPLL patch, or software-envelope definitions are copied.',
             '; Volume changes are explicit v commands. SCC needs your own @s0 definition.',
             f'#opll_mode {1 if rhythm else 0}', f'#tempo {tempo}', TUNING_HEADER]
    loops = []
    for lane, rows in sorted(lanes.items()):
        commands, cursor = [], 0
        for start, stop, text, _ in sorted(rows):
            if start < cursor:
                raise BlueprintError('MML clock rounding overlaps allocated sounding units')
            if start > cursor:
                commands.append(encode_duration('r', start-cursor, lane=lane, step_start=cursor, step_end=start))
            commands.append(text)
            cursor = stop
        if cursor < step(plan.end_sample):
            commands.append(encode_duration('r', step(plan.end_sample)-cursor,
                                     lane=lane, step_start=cursor, step_end=step(plan.end_sample)))
        loop_plan = SourceLoopPlan.build(commands, strategy='structural')
        body, hierarchy = loop_plan.render(commands)
        loops.extend(dict(row, chip=lane[0], channel=lane[1]) for row in hierarchy)
        track = TRACKS[lane[0]][lane[1]]
        lines.append(f'; Track {track}: {lane[0]} {lane[1]+1}; edit @0 to choose a timbre.')
        lines.append(f'{track} @0 q8 ' + body)
    rhythm_text, rhythm_evidence = _rhythm(controls, step, plan.end_sample, minimum)
    if rhythm_text:
        lines.append(rhythm_text)
    text = annotate_sync_points(compress_macros('\n'.join(lines) + '\n'))
    report = dict(status='success', tempo=tempo, sounding_units=len(units), omitted_units=0,
        allocations=evidence, loops=loops, rhythm=rhythm_evidence,
        rhythm_source_controls=[dict(sample=c.sample, kind=c.kind, value=c.value)
            for c in controls if c.kind in ('rhythm_register', 'percussion')],
        timing_rounding=list(rounding.values()), stripped_controls=dict(excluded),
        volume_policy='accepted numeric levels retained as inline v commands',
        timbre_policy='editable @0 placeholders; no source timbre/SW-envelope definitions',
        song_loop_policy='finite accepted traversal; source loop position retained in musical_plan')
    return text, report


def _rhythm_levels(registers):
    return (15-(registers.get(0x36, 0) & 15), 15-(registers.get(0x37, 0) & 15),
            15-(registers.get(0x38, 0) >> 4), 15-(registers.get(0x38, 0) & 15),
            15-(registers.get(0x37, 0) >> 4))


def _rhythm_stable_levels(controls):
    """Reject positive held level changes, not zero-width setup transients."""
    registers, mask, levels = {}, 0, {}
    bits = (16, 8, 4, 2, 1)
    for sample, group in groupby(controls, key=lambda c: c.sample):
        incoming, released, before = mask, 0, _rhythm_levels(registers)
        for c in group:
            if c.kind != 'rhythm_register':
                continue
            reg, value = c.value
            registers[reg] = value
            if reg == 14:
                new = value & 31 if value & 32 else 0
                released |= mask & ~new
                mask = new
        after = _rhythm_levels(registers)
        if any(incoming & mask & ~released & bit and before[i] != after[i] for i, bit in enumerate(bits)):
            raise BlueprintError('Held OPLL percussion volume curve is not representable by rhythm attack MML')
        levels[sample] = after
    return levels


def _rhythm(controls, step, end, minimum=1):
    """Retain rhythm attacks/levels in MGSDRV's fixed-preset score grammar."""
    registers, mask = {}, 0
    stable_levels = _rhythm_stable_levels(controls)
    hits = defaultdict(dict)
    letters, bits = 'bsmch', (16, 8, 4, 2, 1)
    for c in controls:
        if c.kind == 'rhythm_register':
            reg, value = c.value
            registers[reg] = value
            if reg != 14:
                continue
            new = value & 31 if value & 32 else 0
            for i, bit in enumerate(bits):
                if new & bit and not mask & bit:
                    key = step(c.sample)
                    if letters[i] in hits[key]:
                        raise BlueprintError('Multiple same-instrument rhythm attacks collapse on the MML clock')
                    hits[key][letters[i]] = stable_levels[c.sample][i]
            mask = new
        elif c.kind == 'percussion' and c.value[2]:
            instrument, volume, _ = c.value
            key = step(c.sample)
            if letters[instrument] in hits[key]:
                raise BlueprintError('Overlapping native/inferred rhythm attacks in blueprint')
            hits[key][letters[instrument]] = volume
    if not hits:
        return '', []
    times = sorted(hits)
    commands = [_length('r', times[0], minimum=minimum)] if times[0] else []
    evidence = []
    for i, at in enumerate(times):
        stop = times[i+1] if i+1 < len(times) else step(end)
        if stop-at < minimum:
            raise BlueprintError('Rhythm interval is below the MGSC minimum duration',
                step_start=at, step_end=stop, minimum_steps=minimum)
        if stop-at > 255:
            duration = 255
            if 0 < stop-at-duration < minimum:
                duration -= minimum-(stop-at-duration)
        else:
            duration = stop-at
        notes = ''.join(sorted(hits[at]))
        commands.extend(f'v{letter}{volume}' for letter, volume in sorted(hits[at].items()))
        commands.append(f'{notes}%{duration}')
        if stop-at > duration:
            commands.append(_length('r', stop-at-duration, minimum=minimum))
        evidence.append(dict(step=at, volumes=hits[at]))
    return 'f ' + ' '.join(commands), evidence


def write_blueprint(plan, output_root, stem):
    """Isolate blueprint capacity/notation failures and protect hand-edited files."""
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report_path = root / f'{stem}.blueprint.json'
    target = root / 'blueprint' / f'{stem}.mml'
    try:
        previous = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previous = {}
    report = dict(status='blocked', source_sha256=dict(plan.metadata).get('source_sha256'))
    # Keep the ownership digest across an unsuccessful attempt, without marking
    # the previous artifact as a successful result of this attempt.
    if previous.get('sha256'):
        report.update(sha256=previous['sha256'], previous_artifact_retained=target.is_file())
    try:
        if not target.resolve().is_relative_to(root) or target.is_symlink():
            raise BlueprintError('Blueprint output escapes its output root')
        initial_digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        if target.exists() and (not target.is_file() or initial_digest != previous.get('sha256')):
            raise BlueprintError(f'Refusing to overwrite an unowned or edited blueprint: {target}')
        text, result = render_blueprint(plan)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text.encode('utf-8'))
        try:
            current_digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            if target.is_symlink() or current_digest != initial_digest:
                raise BlueprintError('Blueprint changed during rendering; keeping the edited file')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        report.update(result, path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        report.pop('previous_artifact_retained', None)
        rows = result['allocations']
        with (root / f'{stem}.blueprint.units.csv').open('w', encoding='utf-8', newline='') as stream:
            fields = list(rows[0]) if rows else ['unit_id', 'source_chip', 'source_channel', 'target_chip', 'target_channel']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    except (ValueError, OSError) as error:
        report.update(status='blocked', detail=str(error), error_type=type(error).__name__)
        if isinstance(error, BlueprintError):
            report['projection_detail'] = error.projection_detail
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
