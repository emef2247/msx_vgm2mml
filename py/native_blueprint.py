"""Simple editable scores projected from source-native musical units.

Dynamics and synthesis controls stay in NativePerformance. This projection
retains gates, semitone pitch changes and source-timbre identities only.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction
import json
import re
import textwrap

from mml_envelopes import length_tokens
from mml_macros import compress_macros
from mml_sync import annotate_sync_points
from mml_layout import format_mml_loops
from source_loop_plan import SourceLoopPlan
from score_structure import midi_pitch as _midi, pitch_points as _pitch_points


TRACKS = {'psg': '123', 'scc': '45678', 'opll': '9abcdefgh'}
NOTES = ('c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b')
PCM_CHIPS = {'msm6258', 'msm6295', 'segapcm', 'c140'}


class NativeBlueprintError(ValueError):
    def __init__(self, message, **projection_detail):
        super().__init__(message)
        self.projection_detail = projection_detail


def encoded_length(pitch, steps, tie=False, minimum=1):
    parts = []
    while steps:
        chunk = min(steps, 255)
        if 0 < steps-chunk < minimum:
            chunk -= minimum-(steps-chunk)
        if chunk < minimum:
            raise NativeBlueprintError('Encoded duration is below the MGSC minimum',
                                       steps=steps, minimum_steps=minimum)
        parts.append(length_tokens(pitch, chunk, True, tie=tie or bool(parts)))
        steps -= chunk
    def spelling(match):
        amount = int(match[1])
        return str(192//amount) if 192 % amount == 0 and 192//amount <= 64 else match[0]
    return re.sub(r'%(\d+)', spelling, ' '.join(parts))


def _voice_at_start(unit):
    preceding = [(t, value) for t, value in unit.voice_curve if t <= unit.start_sample]
    return str(preceding[-1][1]) if preceding else f'{unit.device_id}/{unit.section}/unspecified'


def _unit_voices(unit):
    return {_voice_at_start(unit)} | {str(value) for t, value in unit.voice_curve
                                      if unit.start_sample < t < unit.end_sample}


@dataclass
class _Part:
    identity: tuple
    units: list
    voices: set
    chunk: int


def _parts(performance):
    devices = {d.device_id: d for d in performance.devices}
    grouped, excluded = defaultdict(list), []
    for unit in performance.units:
        device = devices[unit.device_id]
        reason = ('pcm' if device.chip in PCM_CHIPS or 'pcm' in unit.section.lower() or unit.role in ('pcm', 'sample')
                  else 'percussion' if unit.section.lower() in ('rhythm', 'percussion')
                  else 'zero_duration' if unit.end_sample <= unit.start_sample else None)
        if reason:
            excluded.append(dict(unit_id=unit.unit_id, reason=reason))
            continue
        grouped[unit.device_id, unit.section, unit.channel].append(unit)
    parts = []
    def key(identity):
        device_id, section, channel = identity
        d = devices[device_id]
        return (d.chip not in TRACKS, d.chip, d.instance, section, channel, device_id)
    for identity in sorted(grouped, key=key):
        lanes = []
        for unit in sorted(grouped[identity], key=lambda u: (u.start_sample, u.end_sample, u.unit_id)):
            onset = _voice_at_start(unit)
            lane = next((lane for lane in lanes if lane.units[-1].end_sample <= unit.start_sample), None)
            if lane is None:
                lane = _Part(identity, [], set(), len(lanes))
                lanes.append(lane)
            lane.units.append(unit)
            lane.voices.add(onset)
        parts.extend(lanes)
    return parts, excluded


def _pack(parts, devices):
    files = []
    for part in parts:
        device = devices[part.identity[0]]
        def candidates():
            if device.chip in TRACKS:
                preferred = part.identity[2]
                count = len(TRACKS[device.chip])
                return [(device.chip, i) for i in ([preferred] if 0 <= preferred < count else []) +
                        [i for i in range(count) if i != preferred]]
            return [('opll', i) for i in range(9)] + [('psg', i) for i in range(3)]
        selected = None
        for file in files:
            target = next((item for item in candidates() if item not in file['parts']), None)
            if target is not None:
                selected = file, target
                break
        if selected is None:
            file = dict(parts={}, voices=set())
            files.append(file)
            selected = file, candidates()[0]
        file, target = selected
        file['parts'][target] = part
        file['voices'] |= part.voices
    return files


def _device_clock(parts, performance, ratio, minimum, devices, score_guide=None):
    """Smallest monotone target clock satisfying each rendered interval."""
    constraints, samples = defaultdict(list), {0, performance.end_sample}
    def interval(start, stop):
        samples.update((start, stop))
        if stop > start:
            constraints[stop].append(start)
    for part in parts:
        cursor = 0
        for unit in part.units:
            interval(cursor, unit.start_sample)
            points = [at for at, _ in (score_guide.points(unit) if score_guide else _pitch_points(unit))]+[unit.end_sample]
            for start, stop in zip(points, points[1:]):
                interval(start, stop)
            cursor = unit.end_sample
        interval(cursor, performance.end_sample)
    rhythms = defaultdict(list)
    for event in performance.percussion:
        if devices[event.device_id].chip == 'opll':
            rhythms[event.device_id].append(event)
            if event.stop_sample is not None:
                interval(event.start_sample,event.stop_sample)
    for events in rhythms.values():
        times = sorted({event.start_sample for event in events} | {performance.end_sample})
        for start, stop in zip([0]+times, times):
            interval(start, stop)
    mapping, rows, previous = {}, [], 0
    for sample in sorted(samples):
        ideal = round(sample*ratio)
        result = max(ideal, previous, *(mapping[start]+minimum for start in constraints[sample]))
        mapping[sample], previous = result, result
        rows.append(dict(sample=sample, step=result, rounded_step=ideal,
                         shift_samples=float(Fraction(result)/ratio-sample)))
    return mapping, rows


def _clock(parts,performance,ratio,minimum,devices,score_guide=None):
    mapping={};rows=[]
    for identity in devices:
        local=[part for part in parts if part.identity[0]==identity]
        selected=replace(performance,percussion=tuple(e for e in performance.percussion if e.device_id==identity))
        if not local and not any(devices[e.device_id].chip=='opll' for e in selected.percussion):continue
        clock,rounding=_device_clock(local,selected,ratio,minimum,devices,score_guide)
        mapping.update({(identity,at):step for at,step in clock.items()})
        rows.extend(dict(row,device_id=identity) for row in rounding)
    return mapping,rows


def render_native_blueprints(performance, *, tempo=None, score_guide=None, note_values=False, sync_report=None):
    """Return all (MML, report) files; never rewrite the source performance."""
    tempo = tempo or 75
    ratio = Fraction(str(tempo))*48/(44100*60)
    minimum = max(1, int(tempo)//75)
    devices = {d.device_id: d for d in performance.devices}
    def finish(text):
        if note_values:
            from mml_note_values import decompose
            text=decompose(text)
        if sync_report:
            from score_normalization import comment_header
            text=comment_header(text,sync_report)
        from mml_notation import compact
        return compact(format_mml_loops(annotate_sync_points(compress_macros(text))))
    voices = {v.voice_id: v for v in performance.voices}
    parts, excluded = _parts(performance)
    excluded_percussion = [dict(event_id=event.event_id, source_chip=devices[event.device_id].chip,
        instrument_family=event.instrument_family, reason='no_blueprint_rhythm_mapping')
        for event in performance.percussion if devices[event.device_id].chip != 'opll']
    if not parts and not performance.percussion:
        return []
    packed = _pack(parts, devices)
    if not packed:
        packed = [dict(parts={}, voices=set())]
    clock, rounding = _clock(parts, performance, ratio, minimum, devices,score_guide)
    score_clocks={}
    if note_values and sync_report:
        from score_normalization import timing_for_devices
        for device in sync_report.get('devices',()):
            if device['status']=='applied':score_clocks[device['device_id']]=timing_for_devices(
                sync_report,{device['device_id']})
        for key in clock:
            identity,sample=key
            if identity in score_clocks:clock[key]=score_clocks[identity].position(sample)
        for row in rounding:
            identity=row.get('device_id')
            if identity in score_clocks:
                row['timebase']='vgmticks_to_score_steps'
                row['step']=score_clocks[identity].position(row['sample'])
                row['shift_samples']=float(Fraction(row['step'])/ratio-row['sample'])
    def points(unit):
        return score_guide.points(unit) if score_guide else _pitch_points(unit)
    def step(sample,device_id=None):
        if device_id is not None:return clock.get((device_id,sample),round(sample*ratio))
        return max((clock.get((identity,sample),round(sample*ratio)) for identity in devices),default=round(sample*ratio))
    terminal_attacks = [event.event_id for event in performance.percussion
        if devices[event.device_id].chip == 'opll' and event.start_sample == performance.end_sample]
    terminal_tail = minimum if terminal_attacks else 0
    end_step = step(performance.end_sample)+terminal_tail
    def duration(note, count, tie=False, **context):
        if 0 < count < minimum:
            raise NativeBlueprintError('Blueprint interval is below the MGSC minimum duration',
                tempo=tempo, steps=count, minimum_steps=minimum, **context)
        return encoded_length(note, count, tie=tie, minimum=minimum)
    results = []
    for file_index, file in enumerate(packed):
        first_use = {}
        for part in file['parts'].values():
            for unit in part.units:
                for identity in _unit_voices(unit):
                    first_use[identity] = min(first_use.get(identity, unit.start_sample), unit.start_sample)
        mapping = {identity: number for number, identity in enumerate(
            sorted(file['voices'], key=lambda identity: (first_use.get(identity, 0), identity)))}
        lines = ['; Editable blueprint: dynamics and synthesis controls are omitted.',
                 '; All source volume commands and instrument definitions are removed.',
                 '; Audition defaults only: fixed v15, OPLL ROM1, SCC square wave; edit freely.',
                 '; Target clock approximates short intervals; native samples remain in the sidecar.',
                 '; Source timbres are documentary only; no source instrument selections are restored.',
                 '#opll_mode 0', f'#tempo {tempo}']
        if any(chip == 'scc' for chip, _ in file['parts']):
            lines.append('@s0={' + '80'*16 + '78'*16 + '}')
        lines.append(f'; Source duration {performance.end_sample} samples; projected duration {end_step} steps.')
        if terminal_tail:
            lines.append(f'; Terminal rhythm attacks receive {terminal_tail} target-only tail steps; source end is unchanged.')
        for row in excluded_percussion:
            lines.append('; Unmapped percussion: '+json.dumps(row, sort_keys=True))
        lines.append('; Maximum target clock shift '+str(round(max(
            (abs(row['shift_samples']) for row in rounding), default=0), 3))+' source samples.')
        documented = set().union(*(_unit_voices(unit) for part in file['parts'].values() for unit in part.units))
        for identity in sorted(documented, key=lambda identity: (mapping.get(identity, 99), identity)):
            label = f'Timbre {mapping[identity]+1}' if identity in mapping else 'internal timbre (removed)'
            lines.append(f'; {label}: source voice {identity}')
            if identity in voices:
                voice = voices[identity]
                description='Voice parameters: '+json.dumps(dict(voice.parameters), ensure_ascii=True, sort_keys=True)
                lines.extend('; '+line for line in textwrap.wrap(description, width=106,
                             break_long_words=True, break_on_hyphens=False))
        allocations, loop_rows, unknown, removed_timbres, collapsed = [], [], [], [], []
        for (target_chip, target_ch), part in sorted(file['parts'].items()):
            device_id, section, channel = part.identity
            device = devices[device_id]
            track = TRACKS[target_chip][target_ch]
            commands, cursor = [], 0
            for unit in part.units:
                start, stop = step(unit.start_sample,device_id), step(unit.end_sample,device_id)
                if device_id in score_clocks:
                    start,stop=score_clocks[device_id].span(unit.start_sample,unit.end_sample)
                    if stop<=start:
                        collapsed.append(dict(unit_id=unit.unit_id,source_start=unit.start_sample,
                            source_end=unit.end_sample,reason='score_duration_below_1_64'))
                        continue
                if start < cursor:
                    raise NativeBlueprintError('MML clock rounding overlaps source sounding units',
                                               unit_id=unit.unit_id)
                if start > cursor:
                    commands.append(duration('r', start-cursor, part=part.identity,
                                             step_start=cursor, step_end=start))
                midi = None
                for at, frequency in unit.pitch_curve:
                    if at <= unit.start_sample:
                        midi = _midi(frequency)
                voice = _voice_at_start(unit)
                changes = defaultdict(dict)
                changes[start].update(midi=midi, voice=voice)
                for at, value in points(unit)[1:]:
                    change_step=step(at,device_id)
                    if change_step<stop:
                        changes[max(start,change_step)]['midi'] = value
                for at, identity in unit.voice_curve:
                    if unit.start_sample < at < unit.end_sample:
                        removed_timbres.append(dict(unit_id=unit.unit_id, sample=at, voice_id=str(identity)))
                # Removing volume controls must remove their note subdivisions too.
                spans, current, previous_at = [], dict(midi=midi, voice=voice), start
                for at in sorted(changes):
                    updated = dict(current, **changes[at])
                    if updated == current:
                        continue
                    if at > previous_at:
                        spans.append((previous_at, at, current))
                    previous_at, current = at, updated
                if stop > previous_at:
                    spans.append((previous_at, stop, current))
                body = []
                for number, (at, end, state) in enumerate(spans):
                    note_midi = state['midi']
                    if note_midi is None:
                        note_midi = 60
                        unknown.append(dict(unit_id=unit.unit_id, step=at,
                                            reason='pitch_unknown', placeholder_midi=60))
                    octave = note_midi//12 - (target_chip != 'opll')
                    if not 1 <= octave <= 8:
                        original = note_midi
                        low, high = (12, 107) if target_chip == 'opll' else (24, 119)
                        while note_midi < low:
                            note_midi += 12
                        while note_midi > high:
                            note_midi -= 12
                        unknown.append(dict(unit_id=unit.unit_id, step=at, reason='octave_fold',
                                            source_midi=original, projected_midi=note_midi))
                        octave = note_midi//12 - (target_chip != 'opll')
                    body.append(' '.join((f'o{octave}',
                                 duration(NOTES[note_midi % 12], end-at, tie=number > 0,
                                          unit_id=unit.unit_id, sample_start=unit.start_sample,
                                          sample_end=unit.end_sample, step_start=at, step_end=end))))
                text = ' '.join(body)
                atom_start=len(commands)
                commands.extend(body)
                allocations.append(dict(unit_id=unit.unit_id, source_chip=device.chip,
                    source_instance=device.instance, source_section=section, source_channel=channel,
                    target_chip=target_chip, target_channel=target_ch, track=track,
                    sample_start=unit.start_sample, sample_end=unit.end_sample,
                    step_start=start, step_end=stop, voice_ids=sorted(_unit_voices(unit)), mml=text,
                    score_atom_start=atom_start,score_atom_end=len(commands)))
                cursor = stop
            if cursor < end_step:
                commands.append(duration('r', end_step-cursor,
                                         part=part.identity, step_start=cursor,
                                         step_end=end_step))
            plan = SourceLoopPlan.build(commands, strategy='structural')
            body, loops = plan.render(commands)
            loop_rows.extend(dict(row, source_part=part.identity) for row in loops)
            lines.append(f'; Source: {device.chip.upper()} #{device.instance+1} / {section} ch {channel+1}'
                         f' -> {target_chip.upper()} ch {target_ch+1} (track {track})')
            lines.append(f'; Device {device_id}, clock {device.clock_hz} Hz, native channel index {channel}.')
            if part.chunk:
                lines.append(f'; Additional overlapping source part lane {part.chunk+1}; timeline starts at zero.')
            lines.append(f'; Units {len(part.units)}, source samples {part.units[0].start_sample}..{part.units[-1].end_sample}, timbres {len(part.voices)}')
            pitches = [value for unit in part.units for _, value in points(unit) if value is not None]
            if pitches:
                lines.append(f'; Source MIDI range {min(pitches)}..{max(pitches)}; roles '+', '.join(sorted({unit.role for unit in part.units}))+'.')
            setup = '/1 v15' if target_chip == 'psg' else '@0 v15' if target_chip == 'scc' else '@1 v15'
            lines.append(f'{track} q8 {setup} ' + body)
        text = finish('\n'.join(lines)+'\n')
        report = dict(status='success', tempo=tempo, file_index=file_index, file_count=len(packed),
            sounding_units=len(allocations), omitted_units=len(collapsed), allocations=allocations, loops=loop_rows,
            score_collapsed_units=collapsed,
            structure_basis='score pitch/duration/rest/attack-or-hold events; timbre and volume excluded',
            voice_mapping=[dict(voice_id=identity, comment_number=number+1,
                                source_device=voices[identity].device_id if identity in voices else None)
                           for identity, number in sorted(mapping.items(), key=lambda item: item[1])],
            documented_voices=[dict(voice_id=identity,
                                   source_device=voices[identity].device_id if identity in voices else None,
                                   parameters=dict(voices[identity].parameters) if identity in voices else {})
                               for identity in sorted(documented)],
            excluded_units=excluded, percussion_events=len(performance.percussion),
            excluded_percussion=excluded_percussion, terminal_rhythm_attacks=terminal_attacks,
            timing_terminal_tail_steps=terminal_tail,
            pitch_placeholders=unknown, timing_rounding=rounding,
            timing_policy='sample_to_score_grid_for_applied_devices; constrained_target_clock_for_abstentions' if score_clocks else 'per_device_monotone_interval_constraints; target_only',
            timing_max_shift_samples=max((abs(row['shift_samples']) for row in rounding), default=0),
            timing_duration_expansion_steps=end_step-round(performance.end_sample*ratio),
            removed_internal_timbres=removed_timbres,
            volume_policy='source_volume_commands_removed; fixed audition volume only; native curves retained',
            timbre_policy='all source timbres documentary only; fixed audition defaults are target-only',
            audition_defaults=dict(volume=15,opll_rom=1,scc_wave='square32'),
            source_sha256=performance.source_sha256)
        results.append((text, report))
    rhythm_devices = defaultdict(list)
    rhythm_occupancy=defaultdict(set)
    for event in performance.percussion:
        if devices[event.device_id].chip == 'opll':
            layer=0
            key=(step(event.start_sample,event.device_id),event.instrument_family.upper())
            while key in rhythm_occupancy[event.device_id,layer]:layer+=1
            rhythm_occupancy[event.device_id,layer].add(key)
            rhythm_devices[event.device_id,layer].append(event)
    if rhythm_devices and len(results) == 1 and not results[0][1]['allocations']:
        results = []
    for (device_id,rhythm_layer), events in sorted(rhythm_devices.items()):
        device = devices[device_id]
        groups = defaultdict(list)
        for event in events:
            groups[step(event.start_sample,event.device_id)].append(event)
        times, commands, allocations = sorted(groups), [], []
        if times and times[0]:
            commands.append(duration('r', times[0], device_id=device_id))
        letters = {'BD': 'b', 'SD': 's', 'TOM': 'm', 'CYM': 'c', 'HH': 'h'}
        channels = {'BD': 6, 'SD': 7, 'TOM': 8, 'CYM': 8, 'HH': 7}
        for index, at in enumerate(times):
            following = times[index+1] if index+1 < len(times) else end_step
            count = following-at
            if count < minimum:
                raise NativeBlueprintError('Rhythm interval is below the MGSC minimum duration',
                                           step_start=at, step_end=following, minimum_steps=minimum)
            seen = set()
            for event in groups[at]:
                family = event.instrument_family.upper()
                if family not in letters or family in seen:
                    raise NativeBlueprintError('Rhythm attacks cannot share one blueprint step',
                                               event_id=event.event_id, step=at, instrument=family)
                seen.add(family)
                allocations.append(dict(unit_id=event.event_id, source_chip=device.chip,
                    source_instance=device.instance, source_section='rhythm',
                    source_channel=channels[family], target_chip='opll', target_channel=6,
                    track='f', sample_start=event.start_sample, sample_end=event.stop_sample,
                    step_start=at, step_end=None if event.stop_sample is None else step(event.stop_sample,event.device_id),
                    voice_ids=[event.instrument_id], mml=letters[family]))
            held = min(count, 255)
            if 0 < count-held < minimum:
                held -= minimum-(count-held)
            commands.append(''.join(letters[family] for family in sorted(seen))+f'%{held}')
            if count > held:
                commands.append(duration('r', count-held, device_id=device_id))
        loop_plan = SourceLoopPlan.build(commands, strategy='structural')
        body, loop_rows = loop_plan.render(commands)
        text = finish('\n'.join([
            '; Editable rhythm blueprint: source dynamics are omitted.', '#opll_mode 1',
            f'#tempo {tempo}', f'; Source: OPLL #{device.instance+1} / rhythm instruments -> rhythm track f, layer {rhythm_layer+1}',
            f'; Terminal target-only tail steps: {terminal_tail}; source end is unchanged.',
            'f '+body])+'\n')
        results.append((text, dict(status='success', tempo=tempo, file_index=len(results),
            sounding_units=len(events), omitted_units=0, allocations=allocations, loops=loop_rows,
            voice_mapping=[], excluded_units=excluded, percussion_events=len(events),
            excluded_percussion=excluded_percussion, terminal_rhythm_attacks=terminal_attacks,
            timing_terminal_tail_steps=terminal_tail,
            pitch_placeholders=[], timing_rounding=rounding,
            timing_policy='per_device_monotone_interval_constraints; target_only',
            timing_max_shift_samples=max((abs(row['shift_samples']) for row in rounding), default=0),
            timing_duration_expansion_steps=end_step-round(performance.end_sample*ratio),
            volume_policy='all_volume_commands_removed; native curves retained',
            timbre_policy='native OPLL rhythm identities retained as score labels',
            rhythm_policy='attack-grid/preset-decay; independent stops retained in source evidence',
            source_sha256=performance.source_sha256)))
    for _, report in results:
        report['file_count'] = len(results)
    return results
