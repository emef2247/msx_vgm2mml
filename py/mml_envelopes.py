"""Target-stage PSG/SCC notes and exact, 60 Hz software volume envelopes.

The input Segments remain unchanged. Constant-pitch volume runs are an
interpretation, separated at register pitch writes, state changes and attacks.
"""
import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from fractions import Fraction
from mml_utils import compact_state_token
from psg_scc_target import TUNING_HEADER, period_detune, envelope_period_tokens, rendered_period
from psg_scc_performance import analyze as build_performance, audible, settings
from psg_scc_execution import accepted_note_decision


@dataclass
class Note:
    segment: object
    start: int
    length: int
    rest: bool
    runs: list = field(default_factory=list)
    envelope: int | None = None
    segment_indices: list = field(default_factory=list)


class EnvelopeBank:
    def __init__(self, deferred=False):
        self.curves = {((15, 1),): 0}
        self.aliases = {}
        self.deferred = deferred
        self.pending = []
        self.prepared = False

    def select(self, counts):
        # Rank observed varying curves by duration, not expanded repetition count.
        ranked = sorted(counts, key=lambda c: (-sum(n for _, n in c), -len(c), c))
        for curve in ranked:
            if counts[curve] <= 1 and len(curve) < 3:
                continue
            match = next((number for existing, number in self.curves.items()
                          if len(existing) > 1 and curve_prefix(curve, existing)), None)
            if match is not None:
                self.aliases[curve] = match
            else:
                self.register(curve)
        # Short, single-use curves can share already selected longer curves too.
        for curve in ranked:
            if curve not in self.curves and curve not in self.aliases:
                match = next((number for existing, number in self.curves.items()
                              if len(existing) > 1 and curve_prefix(curve, existing)), None)
                if match is not None:
                    self.aliases[curve] = match

    def submit(self, segments, chip, output_path, **kwargs):
        if kwargs.get('performance') is None:
            kwargs['performance'] = build_performance(segments, chip)
        if kwargs.get('dump_path'):
            from psg_scc_performance import dump
            dump(kwargs['performance'], str(kwargs['dump_path']).replace('.target_notes.csv', ''))
        if self.deferred:
            self.pending.append((segments, chip, output_path, kwargs))
        else:
            Path(output_path).write_text(render(segments, chip, self, **kwargs), encoding='utf-8')

    def flush(self):
        counts = Counter()
        for segments, chip, _, kwargs in self.pending:
            counts.update(candidate_curves(dict(kwargs['performance'].channels),kwargs['performance'].tick_clock_hz))
        if any(kwargs.get('score_timing') and kwargs['score_timing'].tempo!=225
               for _,_,_,kwargs in self.pending):counts.clear()
        self.select(counts)
        self.prepared = True
        for segments, chip, path, kwargs in self.pending:
            dump_path = kwargs.get('dump_path')
            if dump_path:
                report = str(dump_path).replace('.target_notes.csv', '.envelope_candidates.csv')
                with open(report, 'w', newline='', encoding='utf-8') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(('envelope_id', 'selection', 'ticks', 'occurrences', 'volume_runs'))
                    local = candidate_curves(dict(kwargs['performance'].channels),kwargs['performance'].tick_clock_hz)
                    for curve, count in sorted(local.items()):
                        number = self.curves.get(curve, self.aliases.get(curve))
                        status = ('definition' if curve in self.curves else
                                  'exact_prefix' if curve in self.aliases else 'inline')
                        writer.writerow(('' if number is None else number, status,
                                         sum(n for _, n in curve), count,
                                         ';'.join(f'{v}:{n}' for v, n in curve)))
            Path(path).write_text(render(segments, chip, self, **kwargs), encoding='utf-8')
        self.pending.clear()

    def register(self, runs):
        curve = tuple(runs)
        if curve in self.curves:
            return self.curves[curve]
        if len(self.curves) >= 32 or len(envelope_data(curve)) > 220:
            return None
        number = len(self.curves)
        self.curves[curve] = number
        return number

    def definitions(self, used):
        return [f'@e{number:02d} = {{ 0, 0, {envelope_data(curve)} }}'
                for curve, number in self.curves.items() if number in used]


def curve_prefix(short, long):
    """Compare every observed tick, including release; never infer a tail."""
    i = j = 0
    a = b = 0
    while i < len(short):
        if j >= len(long) or short[i][0] != long[j][0]:
            return False
        take = min(short[i][1] - a, long[j][1] - b)
        a += take
        b += take
        if a == short[i][1]:
            i += 1
            a = 0
        if b == long[j][1]:
            j += 1
            b = 0
    return True


def frame_curve(runs,clock_hz=60):
    """Lower only software-envelope holds to the driver's real 60 Hz clock."""
    if clock_hz==60:return tuple(runs)
    result=[];cursor=previous=0
    for volume,duration in runs:
        cursor+=duration
        end=round(Fraction(cursor*60,clock_hz));length=end-previous;previous=end
        if length<=0:continue
        if result and result[-1][0]==volume:result[-1]=(volume,result[-1][1]+length)
        else:result.append((volume,length))
    return tuple(result)


def candidate_curves(notes,clock_hz=60):
    return Counter(frame_curve(n.runs,clock_hz) for rows in notes.values() for n in rows
                   if not n.rest and len(n.runs) > 1
                   and len(frame_curve(n.runs,clock_hz))>1
                   and not getattr(n.segment, 'envelope_enabled', False))


def envelope_data(curve):
    # Explicit holds avoid assuming how MGSDRV rounds interpolated ramps.
    parts = []
    for volume, duration in curve:
        while duration:
            length = min(duration, 255)
            parts.append(f'{volume:X}' + (f':{length}' if length > 1 else ''))
            duration -= length
    return ', '.join(parts)


def extract_notes(segments, chip):
    """Compatibility adapter; immutable source-linked units own interpretation."""
    return build_performance(segments, chip).to_notes(Note)


def length_tokens(pitch, ticks, raw_ticks, tie=False):
    # Standard output has 3 target steps per source tick at tempo 225.
    steps = ticks if raw_ticks else ticks * 3
    parts = []
    while steps:
        chunk = min(steps, 255)
        if not raw_ticks and 192 % chunk == 0:
            token = f'{pitch}{192 // chunk}'
        else:
            token = f'{pitch}%{chunk}'
        parts.append(('&' if pitch != 'r' and (parts or tie) else '') + token)
        steps -= chunk
    return ' '.join(parts)


def render(segments, chip, bank, raw_ticks=False, waveforms=(), dump_path=None, source_plans=None,
           performance=None,score_timing=None):
    from melody_patterns import analyze
    from melody_loops import project, dump_projection
    from performed_patterns import Unit, project_notes, dump_units
    performed = {}
    # A source plan already catalogs the repeats. The legacy Segment search
    # is not consumed by that projector and can dominate long PSG inputs.
    analysis = analyze(segments, chip) if source_plans is None else None
    before_lines, loop_report = [], []
    if performance is None:
        performance = build_performance(segments, chip)
        if dump_path:
            from psg_scc_performance import dump
            dump(performance, str(dump_path).replace('.target_notes.csv', ''))
    notes = performance.to_notes(Note)
    if score_timing and dump_path:
        timing_path=Path(str(dump_path).replace('.target_notes.csv','.score_notes.csv'))
        with timing_path.open('w',newline='',encoding='utf-8') as stream:
            fields=('channel','note_index','kind','source_start_samples','source_end_samples',
                    'score_start_step','score_end_step','discarded_duration_samples',
                    'source_timebase_hz','source_volume_runs','driver_frame_runs','score_grid_applied')
            writer=csv.writer(stream);writer.writerow(fields)
            for channel,members in notes.items():
                for index,note in enumerate(members):
                    start,stop=score_timing.span(note.start,note.start+note.length,rest=note.rest)
                    kept=Fraction((stop-start)*44100*60,score_timing.tempo*48)
                    writer.writerow((channel,index,'rest' if note.rest else 'note',note.start,note.start+note.length,start,stop,
                        str(Fraction(note.length)-kept),performance.tick_clock_hz,
                        repr(note.runs),repr(frame_curve(note.runs,performance.tick_clock_hz)),score_timing.quantize))
    if not bank.prepared:
        bank.select(candidate_curves(notes,performance.tick_clock_hz)
                    if not score_timing or score_timing.tempo==225 else {})
    used = set()
    lines = []
    dump_rows = []
    envelope_assignments = {}
    for ch, rows in notes.items():
        track = ch + (1 if chip == 'psg' else 4)
        current = {}
        body = []
        cursor = 0
        score_cursor=0
        boundaries = {}
        note_cuts = []

        def set_value(key, value, token):
            if current.get(key) != value:
                if key in ('octave', 'volume'):
                    prefix = 'o' if key == 'octave' else 'v'
                    token = compact_state_token(prefix, value, current.get(key))
                body.append(token)
                current[key] = value

        for note in rows:
            note_cuts.append(len(body))
            boundaries[note.segment_indices[0]] = len(body)
            seg = note.segment
            score_start,score_end=(score_timing.span(note.start,note.start+note.length,rest=note.rest)
                                   if score_timing else (0,0))
            if score_timing and score_end<=score_start:
                continue
            if score_timing and score_start<score_cursor:
                raise ValueError('Score projection overlaps a previously emitted note or rest')
            if score_timing and score_start>score_cursor:
                body.append(length_tokens('r',score_start-score_cursor,True))
            elif not score_timing and note.start > cursor:
                body.append(length_tokens('r', note.start - cursor, raw_ticks))
            cursor = note.start + note.length
            if score_timing:
                score_cursor=score_end
            def duration(pitch,tie=False):
                return length_tokens(pitch,score_end-score_start,True,tie) if score_timing else length_tokens(pitch,note.length,raw_ticks,tie)
            if note.rest:
                body.append(duration('r'))
                boundaries[note.segment_indices[-1] + 1] = len(body)
                dump_rows.append((track, note.start, cursor, 'rest', '', '', '', '', ''))
                continue
            decision = accepted_note_decision(note, chip)
            hw = decision.hardware_envelope
            curve=frame_curve(note.runs,performance.tick_clock_hz)
            env = bank.curves.get(curve, bank.aliases.get(curve)) if len(curve) > 1 and not hw else None
            note.envelope = env
            envelope_id = '' if hw else (env if env is not None else 0)
            envelope_kind = ('hardware' if hw else 'software' if env is not None
                             else 'inline' if len(note.runs) > 1 else 'constant')
            for source_index in note.segment_indices:
                envelope_assignments[ch, source_index] = (envelope_id, envelope_kind)
            if chip == 'scc':
                if current.get('wave') != seg.waveform_id:
                    set_value('wave', seg.waveform_id, f'@{seg.waveform_id}')
                    current.pop('env', None)
            else:
                if 'tone' not in current:
                    body.append('@0')
                    current['tone'] = 0
                set_value('mode', seg.mode, f'/{seg.mode}')
                if seg.mode & 2:
                    set_value('noise', seg.noise_period, f'n{seg.noise_period}')
            set_value('octave', seg.octave, f'o{seg.octave}')
            detune = period_detune(seg)
            set_value('detune', detune, f'\\{detune}')
            if hw:
                # v disables hardware envelopes, so apply it before s.
                set_value('volume', 15, 'v15')
                set_value('period', seg.envelope_period, envelope_period_tokens(seg.envelope_period))
                body.append(f's{seg.envelope_shape}')
                current['hw'] = True
                current.pop('env', None)
                body.append(duration(seg.scale))
            else:
                if current.pop('hw', False):
                    current.pop('volume', None)
                chosen = env if env is not None else 0
                used.add(chosen)
                set_value('env', chosen, f'@e{chosen}')
                if env is not None:
                    set_value('volume', 15, 'v15')
                    body.append(duration(seg.scale))
                else:
                    run_sample=note.start;emitted=False;run_step=score_start
                    for index, (volume, duration) in enumerate(note.runs):
                        if score_timing:
                            run_end=min(score_end,max(run_step,score_timing.position(run_sample+duration)))
                            run_sample+=duration
                            if run_end<=run_step:continue
                            set_value('volume', volume, f'v{volume}')
                            body.append(length_tokens(seg.scale,run_end-run_step,True,tie=emitted))
                            run_step=run_end;emitted=True
                            continue
                        set_value('volume', volume, f'v{volume}')
                        body.append(length_tokens(seg.scale, duration, raw_ticks, tie=index > 0))
            boundaries[note.segment_indices[-1] + 1] = len(body)
            dump_rows.append((track, note.start, cursor, 'note', '' if env is None else env,
                              ';'.join(f'{v}:{n}' for v, n in note.runs),
                              detune, decision.period, int(decision.period_exact)))
        note_cuts.append(len(body))
        before_lines.append(f'{track} ' + ' '.join(body))
        if source_plans is not None:
            plan = source_plans[ch]
            commands = [' '.join(body[note_cuts[i]:note_cuts[i + 1]]) for i in range(len(rows))]
            text, hierarchy = plan.render(commands)
            lines.append(f'{track} ' + text)
            units = [Unit(i, i + 1, 'rest' if n.rest else 'note', plan.keys[i])
                     for i, n in enumerate(rows)]
            fields = ('occurrence_id', 'parent_id', 'depth', 'pattern_id', 'unit_start',
                      'unit_end', 'unit_width', 'repeats', 'status', 'strategy', 'candidate_status')
            performed[ch] = (rows, units, [{key: entry[key] for key in fields}
                                         for entry in hierarchy])
            if dump_path:
                plan.dump(str(dump_path).replace('.target_notes.csv', f'.ch{ch}.source_loops.csv'),
                          [n.segment_indices for n in rows], hierarchy)
            continue
        performed_text, units, hierarchy = project_notes(rows, chip, body, note_cuts)
        performed[ch] = (rows, units, hierarchy)
        body, report = project(body, boundaries, analysis[ch], ch)
        # Choose the smaller equivalent projection, preserving both reports.
        selected = len(performed_text) <= len(' '.join(body))
        for entry in hierarchy:
            if not selected:
                entry['status'] = 'legacy_projection_selected'
        if selected:
            body = [performed_text]
            report = [(*r[:-1], 'performed_projection_selected') for r in report]
        loop_report.extend(report)
        lines.append(f'{track} ' + ' '.join(body))
    header = [f'#alloc {ch + (1 if chip == "psg" else 4)}=0' for ch in notes]
    if not header:
        header = ['#alloc 0=0']
    header.insert(0, f'#tempo {score_timing.tempo}' if score_timing else '#tempo 75' if raw_ticks else '#tempo 225')
    header.insert(0, TUNING_HEADER)
    header.extend(f'@s{i:02d} = {{{wave}}}' for i, wave in enumerate(waveforms))
    header.extend(bank.definitions(used))
    if dump_path:
        with Path(dump_path).open('w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(('track', 'tick_start', 'tick_end', 'kind', 'envelope_id', 'volume_runs', 'target_detune',
                             'target_tone_period', 'period_exact'))
            writer.writerows(dump_rows)
        segment_path = Path(str(dump_path).replace('.target_notes.csv', '.segments.csv'))
        if segment_path != Path(dump_path) and segment_path.exists():
            annotate_envelopes(segment_path, segments, envelope_assignments)
    approximated = sum(1 for row in dump_rows if row[3] == 'note' and row[-1] == 0)
    if approximated:
        import warnings
        warnings.warn(f'{chip}: {approximated} notes exceed MGSDRV detune range; '
                      'tone periods are approximated (see target_notes.csv with --dump-passes)')
    dump_units(dump_path, performed)
    result = '\n'.join(header + [''] + lines) + '\n'
    dump_projection(dump_path, '\n'.join(header + [''] + before_lines) + '\n', result, loop_report)
    return result


def annotate_envelopes(path, segments, assignments):
    """Attach actual target envelope selections to all contributing source rows."""
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields, rows = list(reader.fieldnames), list(reader)
    columns = ('envelope_id', 'envelope_kind')
    counts = Counter()
    for row in rows:
        ch = int(row['ch'])
        index = counts[ch]
        counts[ch] += 1
        seg = segments[ch][index]
        default = ('', 'zero_length' if seg.l <= 0 else 'rest')
        row.update(zip(columns, assignments.get((ch, index), default)))
    fields.extend(column for column in columns if column not in fields)
    temporary = Path(str(path) + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
