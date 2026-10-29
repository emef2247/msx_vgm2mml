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


def infer_timing(segments, *, normalization_ms=None):
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
    # Anchor eligibility remains independent of the target movement budget.
    from mgs_conversion_config import sample_threshold
    bound = MAX_ERROR if normalization_ms is None else sample_threshold(normalization_ms, '--normalization-ms')
    tolerance = min(bound, min(intervals) / 4)
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


def render_melody(segments, voice_path, plan, num_channels=6, source_loops=False, *,
                  fm_state_ms=1, state_evidence=None, decision_plan=None,score_guided=False):
    from opll_target import decode_patch
    from performed_patterns import Unit, compress
    from musical_timing import plan_melody
    if decision_plan is None:
        accepted = plan_melody(segments, voice_path, plan, num_channels,
                               fm_state_ms=fm_state_ms, state_evidence=state_evidence)
    else:
        accepted = decision_plan
        if state_evidence is not None:
            state_evidence.extend(accepted.state_evidence)
    if any(voice > 255 for _, voice in accepted.patches):
        raise ValueError('Normalized custom voices exceed the MGSDRV voice range')
    if any(track.channel >= num_channels and track.notes for track in accepted.tracks):
        raise ValueError('Accepted melodic voices exceed the selected MGSDRV OPLL layout')
    tracks, expanded, loop_rows = [], [], []
    minimum = max(1, plan.tempo // 75)
    for track_plan in accepted.tracks:
        ch = track_plan.channel
        default_gate = track_plan.default_gate
        prefix = [f'l16 q{default_gate}']
        if track_plan.constant_voice:
            prefix.append(f'@{track_plan.voice}')
        prefix.append(f'v{track_plan.default_volume}')
        commands, units, cursor = [], [], 0
        score_keys=[]
        for note in track_plan.notes:
            start = note.start_step
            if start > cursor:
                rest = length_token('r', start - cursor, minimum=minimum)
                commands.append(rest)
                units.append(Unit(len(units), len(units) + 1, 'rest', (start - cursor, rest)))
                score_keys.append(('rest',start-cursor))
            body, kept = [], []
            current_gate = default_gate
            current_volume = (track_plan.default_volume if track_plan.constant_volume
                              and note.source_end is not None else None)
            for item in note.states:
                octave, pitch, voice, volume, sustain, patch = item.value
                if kept:
                    body.append('&')
                if not track_plan.constant_voice and (not kept or kept[-1][2][2] != voice):
                    body.append(f'@{voice}')
                if current_volume != volume:
                    body.append(f'v{volume}')
                    current_volume = volume
                body.append(f'o{octave}')
                if current_gate != item.gate:
                    body.append(f'q{item.gate}')
                    current_gate = item.gate
                body.append(length_token(pitch, item.end_step - item.start_step, minimum=minimum))
                kept.append((item.start_step - start, item.gate_end_step - start, item.value))
            if current_gate != default_gate:
                body.append(f'q{default_gate}')
            commands.append(' '.join(body))
            units.append(Unit(len(units), len(units) + 1, 'note', (note.end_step - start, tuple(kept))))
            from score_structure import pitched_trajectory_key
            score_keys.append(('note',note.end_step-start,pitched_trajectory_key(
                (state.start_step-start,state.end_step-state.start_step,(state.value[0],state.value[1]))
                for state in note.states)))
            cursor = note.end_step
        if source_loops:
            from source_loop_plan import SourceLoopPlan
            structure = SourceLoopPlan.build(((u.kind, u.key) for u in units), strategy='structural')
            if score_guided:
                from score_structure import GuidedLoopPlan
                structure=GuidedLoopPlan(SourceLoopPlan.build(score_keys,strategy='structural'),structure)
            text, report = structure.render(commands)
        else:
            text, report = compress(units, commands)
        track = '9abcdefgh'[ch]
        lead = ' '.join(prefix) + ' '
        tracks.append(track + ' ' + lead + text)
        expanded.append(track + ' ' + lead + ' '.join(commands))
        loop_rows.extend(dict(ch=ch, **r) for r in report)
    header = [f'#tempo {plan.tempo}', '#alloc 9=0']
    for patch, voice in accepted.patches:
        values = decode_patch(patch)
        header.extend((f'@{voice} = {{', '; TL FB', f'{values[0]}, {values[1]},',
                       '; AR DR SL RR KL MT AM VB EG KR WF',
                       ', '.join(map(str, values[2:13])) + ',', ', '.join(map(str, values[13:])) + ' }'))
    return '\n'.join(header + tracks) + '\n', '\n'.join(header + expanded) + '\n', list(accepted.evidence), loop_rows


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
                from musical_timing import control_boundary_step
                minimum = max(1, plan.tempo // 75)
                end = control_boundary_step(node.end / 3, plan, previous, sample)
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


def retime_rhythm(segments, plan):
    """Copy rhythm timing only when every boundary fits and no new hit collides."""
    from rhythm_patterns import group_segments
    proxies, maximum = {}, 0
    for ch, rows in segments.items():
        if ch < 9:
            continue
        proxies[ch] = []
        for original in rows:
            proxy = SimpleNamespace(**{slot: getattr(original, slot) for slot in original.__slots__})
            proxy.tick_start = proxy.ticks = plan.onset(original.vgmticks)
            proxy.tick_end = max(proxy.tick_start, round(plan.position(original.vgmticks_end)))
            proxy.l = proxy.tick_end - proxy.tick_start
            for source, target in ((original.vgmticks, proxy.tick_start),
                                   (original.vgmticks_end, proxy.tick_end)):
                shift = abs(target - plan.position(source)) * plan.samples_per_step
                maximum = max(maximum, shift)
                if shift > plan.tolerance_samples:
                    raise ValueError('A rhythm boundary would exceed the correction tolerance')
            proxies[ch].append(proxy)
    # Native same-time hits already have an explicit target collision policy.
    # A newly inferred clock must not merge distinct source attack times.
    for group in group_segments(proxies):
        times = {}
        for hit in group.hits:
            previous = times.setdefault(hit.instrument, hit.source_time)
            if previous != hit.source_time:
                raise ValueError('Normalization would merge distinct rhythm attacks')
    return proxies, maximum


def normalize_outputs(opll_trace, voice_path, output_dir, stem, dump=False, controls=None, *,
                      opll_mode=1, source_loops=False, normalization_ms=8, fm_state_ms=1,
                      decision_mapper=None,score_guided=False):
    """Prepare all target projections before replacing files; abstain if unsafe."""
    from opll import _build_segments
    from rhythm_mml import render as render_rhythm
    from rhythm_notation import optimize
    from mml_sync import analyze_mml, _leaves
    from dataclasses import asdict
    segments, _ = _build_segments(opll_trace)
    plan = (decision_mapper.plan if decision_mapper is not None else
            infer_timing(segments, normalization_ms=normalization_ms))
    root = Path(output_dir)
    for suffix in ('expanded.mml', 'notes.csv', 'loops.csv'):
        (root / f'{stem}.opll.normalized.{suffix}').unlink(missing_ok=True)
    for chip in ('opll', 'psg', 'scc'):
        (root / f'{stem}.{chip}.before.normalize.mml').unlink(missing_ok=True)
    from mgs_conversion_config import sample_threshold
    state_rows = []
    state_path = root / f'{stem}.fm.short_states.csv'
    state_path.unlink(missing_ok=True)
    report = dict(status='unchanged', reason='no confident shared clock', source_segments_unchanged=True,
                  enabled=True, applied=False, normalization_ms=float(normalization_ms),
                  configured_threshold_samples=sample_threshold(normalization_ms, '--normalization-ms'),
                  fm_state_ms=float(fm_state_ms), fm_state_samples=sample_threshold(fm_state_ms, '--fm-state-ms'),
                  whole_gate_omission=False, fm_state_scope='OPLL melody only',
                  psg_scc_curves_filtered=False)
    if decision_mapper is not None:
        report['shared_musical_decisions'] = True
        report['shared_clock_applied'] = bool(decision_mapper.applied)
        if not decision_mapper.applied:
            report['reason'] = (decision_mapper.report or {}).get('reason', report['reason'])
    if plan:
        report['timing'] = asdict(plan)
        try:
            melody, expanded, evidence, loops = render_melody(segments, voice_path, plan,
                                                              num_channels=6 if opll_mode else 9,
                                                              source_loops=source_loops, fm_state_ms=fm_state_ms,
                                                              state_evidence=state_rows,
                                                              decision_plan=decision_mapper.melody if decision_mapper else None,
                                                              score_guided=score_guided)
            # Rhythm uses the same source clock, with a target-only proxy.
            proxies, maximum_rhythm_shift = retime_rhythm(segments, plan)
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
            report.update(status='applied', applied=True, reason='', target_note_count=len(evidence),
                          maximum_rhythm_shift_samples=maximum_rhythm_shift,
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
            if decision_mapper is not None and decision_mapper.applied:
                report['backend_rejected_shared_clock'] = True
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
    # Candidate decisions remain inspectable even when the atomic replacement
    # is rejected; never present those omissions as applied output losses.
    report['candidate_omitted_states'] = sum(r['action'] == 'omit_internal_state' for r in state_rows)
    report['omitted_states'] = report['candidate_omitted_states'] if report['applied'] else 0
    report['state_decisions_applied'] = report['applied']
    if state_rows:
        with state_path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(state_rows[0]) + ('applied',))
            writer.writeheader()
            writer.writerows(dict(r, applied=report['applied']) for r in state_rows)
    (root / f'{stem}.fm.short_states.json').write_text(json.dumps(dict(
        enabled=True, applied=report['applied'], reason=report['reason'],
        threshold_ms=float(fm_state_ms), threshold_samples=report['fm_state_samples'],
        scope=report['fm_state_scope'], source_unchanged=True,
        omitted_states=report['omitted_states'], candidate_omitted_states=report['candidate_omitted_states'],
        state_decisions_csv=str(state_path) if state_rows else None), indent=2), encoding='utf-8')
    (root / f'{stem}.normalization.json').write_text(json.dumps(report, indent=2), encoding='utf-8', newline='\n')
    if report.get('backend_rejected_shared_clock'):
        raise ValueError('MML backend cannot lower the accepted shared clock: ' + report['reason'])
    return plan.tempo if report['status'] == 'applied' else None
