"""Optional musical timing projection; native Segment samples never change.

Estimate one clock from source OPLL attacks, then project target durations.
Reference MML is deliberately not an input to the estimator or renderer.
"""
import csv
import json
import re
from pathlib import Path
import statistics
from bisect import bisect_right
from dataclasses import dataclass
from types import SimpleNamespace


SAMPLE_RATE = 44100
MAX_ERROR = 735  # One nominal 60 Hz frame, further bounded by the note spacing.


@dataclass(frozen=True)
class TimingPlan:
    tempo: int
    grid: int
    samples_per_grid: float
    phase_samples: float
    coverage: float
    tolerance_samples: float

    @property
    def samples_per_step(self):
        return self.samples_per_grid / self.grid

    @property
    def origin_step(self):
        return round(self.phase_samples / self.samples_per_step)

    def position(self, sample):
        return (sample - self.phase_samples) / self.samples_per_step + self.origin_step

    def onset(self, sample):
        nearest = self.origin_step + round((sample - self.phase_samples) / self.samples_per_grid) * self.grid
        if abs(nearest - self.position(sample)) * self.samples_per_step <= self.tolerance_samples:
            return max(0, nearest)
        return max(0, round(self.position(sample)))


def _cluster(samples, distance=44):
    groups = []
    for sample in sorted(set(samples)):
        if not groups or sample - groups[-1][0] > distance:
            groups.append([sample])
        else:
            groups[-1].append(sample)
    return [statistics.median(group) for group in groups]


def infer_timing(segments):
    """Accept a single regular clock only with >=95% anchor coverage.

    Half/double-tempo ambiguity is resolved by preferring a sixteenth-note
    lattice to a thirty-second lattice and the nearest integer effective BPM.
    Irregular/variable-tempo material falls back to the unchanged converter.
    """
    channels = []
    for ch, rows in segments.items():
        if ch >= 9:
            continue
        attacks = [s.vgmticks for s in rows if s.key_on_edge and s.vgmticks is not None]
        if attacks:
            channels.append(attacks)
    anchors = _cluster([sample for attacks in channels for sample in attacks], 500)
    intervals = [b - a for attacks in channels for a, b in zip(attacks, attacks[1:]) if b - a > MAX_ERROR]
    if len(anchors) < 16 or len(intervals) < 8:
        return None
    tolerance = min(MAX_ERROR, min(intervals) / 4)
    candidates = []
    for bpm in range(80, 201):
        for grid in (12, 6):
            nominal = SAMPLE_RATE * 60 / bpm * grid / 48
            period = nominal
            for _ in range(4):
                pairs = [(d, max(1, round(d / period))) for d in intervals]
                valid = [(d, k) for d, k in pairs if abs(d - k * period) <= tolerance]
                if not valid:
                    break
                period = sum(d * k for d, k in valid) / sum(k * k for d, k in valid)
            if abs(period / nominal - 1) > .01:
                continue
            phase = anchors[0]
            for _ in range(3):
                phase += statistics.median((s - phase + period / 2) % period - period / 2 for s in anchors)
            for _ in range(3):
                points = [(round((s - phase) / period), s) for s in anchors]
                valid = [(x, y) for x, y in points if abs(y - phase - period * x) <= tolerance]
                if len(valid) < 8:
                    break
                mx, my = statistics.mean(x for x, y in valid), statistics.mean(y for x, y in valid)
                variance = sum((x - mx)**2 for x, y in valid)
                if not variance:
                    break
                period = sum((x - mx) * (y - my) for x, y in valid) / variance
                phase = my - period * mx
            if abs(period / nominal - 1) > .01:
                continue
            errors = [abs((s - phase + period / 2) % period - period / 2) for s in anchors]
            coverage = sum(error <= tolerance for error in errors) / len(errors)
            if coverage < .95:
                continue
            # Reduce an arbitrary number of whole lattice periods in the phase.
            phase %= period
            effective_bpm = SAMPLE_RATE * 60 * grid / (48 * period)
            plan = TimingPlan(round(effective_bpm), grid, period, phase, coverage, tolerance)
            candidates.append((round(coverage, 3), grid, -statistics.median(errors),
                               -abs(effective_bpm - round(effective_bpm)), plan))
    return max(candidates, key=lambda item: item[:-1])[-1] if candidates else None


def length_token(note, steps, default=12, minimum=1):
    if steps < minimum:
        raise ValueError('A normalized note must have positive length')
    parts = []
    while steps:
        length = min(192, steps)
        if 0 < steps - length < minimum:
            length -= minimum - (steps - length)
        suffix = ('' if length == default else str(192 // length)
                  if 192 % length == 0 and 192 // length in (1, 2, 4, 8, 16, 32, 64)
                  else f'%{length}')
        parts.append(note + suffix)
        steps -= length
        if steps and note != 'r':
            parts.append('&')
    return ' '.join(parts)


def _notes(rows):
    """Preserve explicit attacks and keyed state order, including sub-tick rows."""
    notes, active = [], None
    for index, seg in enumerate(rows):
        if seg.key_on_edge:
            if active is not None:
                active.end = seg.vgmticks
            active = SimpleNamespace(start=seg.vgmticks, end=None, members=[])
            notes.append(active)
        if not seg.keyon:
            if active is not None:
                active.end = seg.vgmticks
                active = None
        elif active is not None:
            active.members.append((index, seg))
    return notes


def _gate(observed, available, default_gate, plan):
    minimum = max(1, plan.tempo // 75)
    options = []
    lengths = [3, 6, 12, 24, 48, 96, 192]
    if available <= 192 and available >= minimum:
        lengths.append(available)
    for nominal in set(lengths):
        if nominal > available or nominal < minimum or 0 < available - nominal < minimum:
            continue
        for gate in range(1, 9):
            error = abs(nominal * gate / 8 - observed) * plan.samples_per_step
            if error <= plan.tolerance_samples:
                options.append((gate != default_gate, nominal < plan.grid, error, -gate, nominal, gate))
    if options:
        *_, nominal, gate = min(options)
        return nominal, gate, True
    nominal = max(minimum, min(available, round(observed)))
    if 0 < available - nominal < minimum:
        nominal = available
    return nominal, 8, False


def render_melody(segments, voice_path, plan, num_channels=6, source_loops=False):
    from opll_target import target_note, decode_patch
    from performed_patterns import Unit, compress
    updates = []
    with open(voice_path, newline='') as stream:
        for row in csv.DictReader(stream):
            if row['#type'] == 'patch':
                updates.append((int(row['vgmticks']), bytes.fromhex(row['patch_hex'])))
    times = [sample for sample, patch in updates]
    patches, tracks, expanded, evidence, loop_rows = {}, [], [], [], []
    minimum = max(1, plan.tempo // 75)

    def state(seg):
        octave, note = target_note(seg.fnum, seg.block)
        patch = None
        if seg.inst:
            voice = seg.inst - 1
        else:
            position = bisect_right(times, seg.vgmticks) - 1
            patch = updates[position][1] if position >= 0 else bytes(8)
            if patch not in patches:
                if 16 + len(patches) > 255:
                    raise ValueError('Normalized custom voices exceed the MGSDRV voice range')
                patches[patch] = 16 + len(patches)
            voice = patches[patch]
        return octave, note, voice, 15 - seg.vol, seg.sus, patch.hex() if patch else ''

    if num_channels == 6 and any(s.keyon and s.vgmticks_end > s.vgmticks for ch in (6, 7, 8)
           for s in segments.get(ch, ())):
        raise ValueError('Nine-channel melodic OPLL is outside the current target renderer')
    for ch in range(num_channels):
        notes = _notes(segments.get(ch, ()))
        usable = [n for n in notes if n.members and (n.end is None or n.end > n.start)]
        if not usable:
            continue
        runs_by_note = []
        for note in usable:
            runs = []
            for index, seg in note.members:
                stop = seg.vgmticks_end
                if stop is None or stop <= seg.vgmticks:
                    continue
                value = state(seg)
                if runs and runs[-1][2] == value and runs[-1][1] == seg.vgmticks:
                    runs[-1] = (runs[-1][0], stop, value)
                else:
                    runs.append((seg.vgmticks, stop, value))
            runs_by_note.append(runs)
        # Estimate the prevalent gate from the final held state of complete notes.
        gates = []
        for n, runs in zip(usable, runs_by_note):
            if n.end is None or not runs:
                continue
            observed = (n.end - runs[-1][0]) / plan.samples_per_step
            options = [(abs(length * q / 8 - observed), -q, q) for length in (12, 24, 48, 96, 192)
                       for q in range(1, 9) if abs(length * q / 8 - observed) * plan.samples_per_step <= plan.tolerance_samples]
            if options:
                gates.append(min(options)[-1])
        default_gate = statistics.mode(gates) if gates else 8
        all_states = [run[2] for runs in runs_by_note for run in runs]
        if not all_states:
            continue
        constant_voice = len({s[2] for s in all_states}) == 1
        default_volume = statistics.mode(s[3] for s in all_states)
        closed_states = [run[2] for note, runs in zip(usable, runs_by_note)
                         if note.end is not None for run in runs]
        constant_volume = len({s[3] for s in closed_states or all_states}) == 1
        prefix = [f'l16 q{default_gate}']
        if constant_voice:
            prefix.append(f'@{all_states[0][2]}')
        prefix.append(f'v{default_volume}')
        commands, units = [], []
        cursor = 0
        for ordinal, (note, runs) in enumerate(zip(usable, runs_by_note)):
            if not runs:
                continue
            start = plan.onset(note.start)
            if start < cursor:
                raise ValueError(f'Normalization would overlap an attack on channel {ch}')
            if start > cursor:
                rest = length_token('r', start - cursor, minimum=minimum)
                commands.append(rest)
                units.append(Unit(len(units), len(units) + 1, 'rest', (start - cursor, rest)))
            next_start = (plan.onset(usable[ordinal + 1].start) if ordinal + 1 < len(usable)
                          else max(start + minimum, round(plan.position(runs[-1][1]))))
            if next_start <= start:
                raise ValueError(f'Normalization would merge attacks on channel {ch}')
            # Intermediate writes remain in source CSVs; target states which
            # have no representable duration are recorded, not silently deleted.
            dropped = [i for i, (a, b, value) in enumerate(runs) if b - a <= 44 and len(runs) > 1]
            if len(dropped) == len(runs):
                # A source attack is never a disposable register intermediate.
                # Retain its final state, including a short unclosed EOF attack.
                dropped.remove(len(runs) - 1)
            retained = [run for i, run in enumerate(runs) if i not in dropped]
            if not retained:
                raise ValueError('An attack contains only unrepresentable intermediate states')
            positions = [start]
            for a, b, value in retained[1:]:
                positions.append(max(positions[-1] + minimum, round(plan.position(a))))
            body, kept, gate_end, nominal_end = [], [], start, start
            current_gate = default_gate
            current_volume = default_volume if constant_volume and note.end is not None else None
            for i, (a, b, value) in enumerate(retained):
                at = positions[i]
                end = positions[i + 1] if i + 1 < len(retained) else None
                if end is not None and end <= at:
                    raise ValueError('Distinct state intervals would collapse')
                if at >= next_start:
                    raise ValueError('Distinct state intervals would exceed the next attack')
                if end is not None:
                    length, gate, fitted = min(end, next_start) - at, 0, False
                else:
                    observed = (b - a) / plan.samples_per_step
                    length, gate, fitted = _gate(observed, next_start - at, default_gate, plan)
                if length < minimum or nominal_end > at:
                    raise ValueError('Distinct state intervals have no MGSC-representable length')
                if abs(at - plan.position(a)) * plan.samples_per_step > plan.tolerance_samples:
                    raise ValueError('A state boundary would exceed the correction tolerance')
                octave, pitch, voice, volume, sustain, patch = value
                if pitch == 'r':
                    raise ValueError('Keyed zero-frequency material requires unchanged target projection')
                if kept:
                    body.append('&')
                if not constant_voice and (not kept or kept[-1][2][2] != voice):
                    body.append(f'@{voice}')
                if current_volume != volume:
                    body.append(f'v{volume}')
                    current_volume = volume
                # Absolute octave at note entry makes a phrase independent of
                # the preceding phrase's octave; internal intervals use it too.
                body.append(f'o{octave}')
                if current_gate != gate:
                    body.append(f'q{gate}')
                    current_gate = gate
                body.append(length_token(pitch, length, minimum=minimum))
                gate_end = at + length * (gate / 8 if gate else 1)
                nominal_end = at + length
                kept.append((at - start, gate_end - start, value))
            if not kept:
                raise ValueError('A positive source attack became unrepresentable')
            if current_gate != default_gate:
                body.append(f'q{default_gate}')
            command = ' '.join(body)
            commands.append(command)
            units.append(Unit(len(units), len(units) + 1, 'note', (nominal_end - start, tuple(kept))))
            cursor = nominal_end
            evidence.append(dict(ch=ch, note_index=ordinal, segment_indices=';'.join(str(i) for i, s in note.members),
                source_start_samples=note.start, source_end_samples=note.end,
                target_start_step=start, target_gate_end_step=gate_end, target_end_step=nominal_end,
                onset_delta_samples=(start - plan.position(note.start)) * plan.samples_per_step,
                gate_delta_samples='' if note.end is None else (gate_end - plan.position(note.end)) * plan.samples_per_step,
                terminal_unclosed=note.end is None,
                quantized_state_runs=json.dumps(dropped), target_state_runs=json.dumps(kept)))
            if note.end is not None and abs(evidence[-1]['gate_delta_samples']) > plan.tolerance_samples:
                raise ValueError('A gate boundary would exceed the correction tolerance')
        if source_loops:
            from source_loop_plan import SourceLoopPlan
            structure = SourceLoopPlan.build(((u.kind, u.key) for u in units), strategy='structural')
            text, report = structure.render(commands)
        else:
            text, report = compress(units, commands)
        track = '9abcdefgh'[ch]
        lead = ' '.join(prefix) + ' '
        tracks.append(track + ' ' + lead + text)
        expanded.append(track + ' ' + lead + ' '.join(commands))
        loop_rows.extend(dict(ch=ch, **r) for r in report)
    header = [f'#tempo {plan.tempo}', '#alloc 9=0']
    for patch, voice in patches.items():
        values = decode_patch(patch)
        header.extend((f'@{voice} = {{', '; TL FB', f'{values[0]}, {values[1]},',
                       '; AR DR SL RR KL MT AM VB EG KR WF',
                       ', '.join(map(str, values[2:13])) + ',', ', '.join(map(str, values[13:])) + ' }'))
    return '\n'.join(header + tracks) + '\n', '\n'.join(header + expanded) + '\n', evidence, loop_rows


def retime_controls(text, plan, segments=None):
    """Recode PSG/SCC durations; keep frame-based software envelopes intact."""
    from mml_sync import analyze_mml, _leaves, _NOTE
    tracks, _, header = analyze_mml(text)
    boundary_samples = {}
    if segments:
        for ch, rows in segments.items():
            boundary_samples[ch] = {s.tick_start: s.vgmticks for s in rows if s.vgmticks is not None}
    lines = []
    for track, nodes in tracks.items():
        tokens = ['l16']
        previous = 0
        for node in _leaves(nodes):
            token = node.text
            match = _NOTE.fullmatch(token.lower())
            if token.lower().startswith('l'):
                continue
            if match:
                length, dots = match.groups()
                pitch = token[:len(token) - len(length or '') - len(dots)]
                ch = int(track) - 1 if track in '123' else int(track) - 4
                sample = boundary_samples.get(ch, {}).get(node.end / 3, node.end / 3 * 735)
                minimum = max(1, plan.tempo // 75)
                end = max(previous + minimum, round(plan.position(sample)))
                if abs(end - plan.position(sample)) * plan.samples_per_step > plan.tolerance_samples:
                    raise ValueError('A PSG/SCC boundary would exceed the correction tolerance')
                tokens.append(length_token(pitch, end - previous, minimum=minimum))
                previous = end
            else:
                tokens.append(token)
        lines.append(track + ' ' + ' '.join(tokens))
    header = [f'#tempo {plan.tempo}' if line.startswith('#tempo') else line for line in header]
    return '\n'.join(header + lines) + '\n'


def compact_melody(text):
    """Remove redundant absolute setters with both loop entries accounted for."""
    from mml_sync import analyze_mml, _parse, _text
    setter = re.compile(r'(@|[ovql])(\d+)$')

    def final_state(nodes, incoming):
        state = dict(incoming)
        for node in nodes:
            if isinstance(node, tuple):
                state = final_state(node[0], state)
            elif match := setter.fullmatch(node):
                state[match[1]] = int(match[2])
        return state

    def visit(nodes, incoming):
        state, output = dict(incoming), []
        for node in nodes:
            if isinstance(node, tuple):
                body, count = node
                final = final_state(body, state)
                entry = state if count == 1 else {key: value for key, value in state.items()
                                                 if final.get(key) == value}
                shortened, _ = visit(body, entry)
                output.append((shortened, count))
                state = final
            else:
                match = setter.fullmatch(node)
                if match:
                    key, value = match[1], int(match[2])
                    if state.get(key) == value:
                        continue
                    state[key] = value
                output.append(node)
        return output, state

    _, _, header = analyze_mml(text)
    # Recover the loop tree, since _leaves would expand it during optimization.
    bodies = {}
    for line in text.splitlines():
        match = re.match(r'^([9a-h])\s+(.*)$', line)
        if match:
            bodies.setdefault(match[1], []).append(match[2])
    result = []
    for track, parts in bodies.items():
        nodes = _parse(' '.join(parts))
        optimized, _ = visit(nodes, {'q': 8})
        result.append(track + ' ' + ' '.join(_text(node) for node in optimized))
    return '\n'.join(header + result) + '\n'


def melodic_timeline(text):
    """Compare effective states/times, rather than redundant setter spelling."""
    from mml_sync import analyze_mml, _leaves, _NOTE
    result = {}
    setter = re.compile(r'(@|[ovq])(\d+)$')
    for track, nodes in analyze_mml(text)[0].items():
        state, events, tied = {'@': 0, 'o': 4, 'v': 8, 'q': 8}, [], False
        for node in _leaves(nodes):
            token = node.text
            if match := setter.fullmatch(token):
                state[match[1]] = int(match[2])
            elif token == '&':
                tied = True
            elif _NOTE.fullmatch(token):
                events.append((token, node.start, node.end, tuple(sorted(state.items())), tied))
                tied = False
        result[track] = events
    return result


def normalize_outputs(opll_trace, voice_path, output_dir, stem, dump=False, controls=None, *,
                      opll_mode=1, source_loops=False):
    """Prepare all target projections before replacing files; abstain if unsafe."""
    from opll import _build_segments
    from rhythm_mml import render as render_rhythm
    from rhythm_notation import optimize
    from mml_sync import analyze_mml, _leaves
    from dataclasses import asdict
    segments, _ = _build_segments(opll_trace)
    plan = infer_timing(segments)
    root = Path(output_dir)
    for suffix in ('expanded.mml', 'notes.csv', 'loops.csv'):
        (root / f'{stem}.opll.normalized.{suffix}').unlink(missing_ok=True)
    for chip in ('opll', 'psg', 'scc'):
        (root / f'{stem}.{chip}.before.normalize.mml').unlink(missing_ok=True)
    report = dict(status='unchanged', reason='no confident shared clock', source_segments_unchanged=True)
    if plan:
        report['timing'] = asdict(plan)
        try:
            melody, expanded, evidence, loops = render_melody(segments, voice_path, plan,
                                                              num_channels=6 if opll_mode else 9,
                                                              source_loops=source_loops)
            # Rhythm uses the same source clock, with a target-only proxy.
            proxies = {}
            for ch, rows in segments.items():
                if ch < 9:
                    continue
                proxies[ch] = [SimpleNamespace(**{slot: getattr(s, slot) for slot in set(s.__slots__)},
                                  ) for s in rows]
                for original, proxy in zip(rows, proxies[ch]):
                    proxy.tick_start = proxy.ticks = plan.onset(original.vgmticks)
                    proxy.tick_end = max(proxy.tick_start, round(plan.position(original.vgmticks_end)))
                    proxy.l = proxy.tick_end - proxy.tick_start
            end = max((round(plan.position(s.vgmticks_end)) for rows in segments.values() for s in rows
                       if s.vgmticks_end is not None), default=0)
            minimum = max(1, plan.tempo // 75)
            end = max(end, max((s.tick_start + minimum for rows in proxies.values() for s in rows), default=0))
            rhythm = optimize(render_rhythm(proxies, raw_ticks=True, end_tick=end,
                                           minimum_steps=minimum), raw_ticks=False)
            replacements = {'opll': melody + rhythm}
            for chip, source_segments in (controls or {}).items():
                path = root / f'{stem}.{chip}.target.mml'
                replacements[chip] = retime_controls(path.read_text(encoding='utf-8'), plan, source_segments)
            def timeline(text):
                return {ch: [(n.text, n.start, n.end) for n in _leaves(nodes)]
                        for ch, nodes in analyze_mml(text)[0].items()}
            if timeline(melody) != timeline(expanded):
                raise ValueError('Normalized loop projection changed expanded commands/times')
            compacted = compact_melody(melody)
            if melodic_timeline(compacted) != melodic_timeline(melody):
                raise ValueError('Normalized notation optimization changed effective note states')
            replacements['opll'] = compacted + rhythm
            report.update(status='applied', reason='', target_note_count=len(evidence),
                          applied_loops=sum(r['status'] == 'applied' for r in loops),
                          compression_preserves_expanded_timeline=True,
                          notation_preserves_effective_states=True,
                          melody_characters_before_notation=len(melody),
                          melody_characters_after_notation=len(compacted),
                          maximum_onset_shift_samples=max((abs(r['onset_delta_samples']) for r in evidence), default=0),
                          maximum_gate_shift_samples=max((abs(r['gate_delta_samples']) for r in evidence
                                                          if r['gate_delta_samples'] != ''), default=0))
        except ValueError as error:
            report['reason'] = str(error)
        else:
            for chip, text in replacements.items():
                path = root / f'{stem}.{chip}.target.mml'
                if dump:
                    (root / f'{stem}.{chip}.before.normalize.mml').write_bytes(path.read_bytes())
                path.write_text(text, encoding='utf-8', newline='\n')
            if dump:
                (root / f'{stem}.opll.normalized.expanded.mml').write_text(expanded, encoding='utf-8', newline='\n')
                for suffix, rows in (('notes', evidence), ('loops', loops)):
                    if rows:
                        with (root / f'{stem}.opll.normalized.{suffix}.csv').open('w', newline='', encoding='utf-8') as stream:
                            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                            writer.writeheader()
                            writer.writerows(rows)
    (root / f'{stem}.normalization.json').write_text(json.dumps(report, indent=2), encoding='utf-8', newline='\n')
    return plan.tempo if report['status'] == 'applied' else None
