"""Target-stage PSG/SCC notes and exact, 60 Hz software volume envelopes.

The input Segments remain unchanged. Constant-pitch volume runs are an
interpretation, separated at register pitch writes, state changes and attacks.
"""
import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from mml_utils import compact_state_token


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
        if self.deferred:
            self.pending.append((segments, chip, output_path, kwargs))
        else:
            Path(output_path).write_text(render(segments, chip, self, **kwargs), encoding='utf-8')

    def flush(self):
        counts = Counter()
        for segments, chip, _, _ in self.pending:
            counts.update(candidate_curves(extract_notes(segments, chip)))
        self.select(counts)
        self.prepared = True
        for segments, chip, path, kwargs in self.pending:
            dump_path = kwargs.get('dump_path')
            if dump_path:
                report = str(dump_path).replace('.target_notes.csv', '.envelope_candidates.csv')
                with open(report, 'w', newline='', encoding='utf-8') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(('envelope_id', 'selection', 'ticks', 'occurrences', 'volume_runs'))
                    local = candidate_curves(extract_notes(segments, chip))
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


def candidate_curves(notes):
    return Counter(tuple(n.runs) for rows in notes.values() for n in rows
                   if not n.rest and len(n.runs) > 1
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


def audible(segment, chip):
    if segment.scale == 'r':
        return False
    if chip == 'psg':
        return bool(segment.mode and (segment.volume or segment.envelope_enabled))
    return bool(segment.enabled and segment.volume)


def settings(segment, chip):
    pitch = (segment.tone_period, segment.octave, segment.scale)
    if chip == 'scc':
        return pitch + (segment.waveform_id, segment.enabled)
    return pitch + (segment.mode, segment.noise_period if segment.mode & 2 else 0,
                    segment.envelope_enabled,
                    segment.envelope_period if segment.envelope_enabled else 0,
                    segment.envelope_shape if segment.envelope_enabled else 0)


def extract_notes(segments, chip):
    result = {}
    pitch_events = {'fCA', 'fCB'} if chip == 'psg' else {'f1Ctrl', 'f2Ctrl'}
    for ch, rows in segments.items():
        notes = []
        boundary = False
        for segment_index, seg in enumerate(rows):
            if seg.ev_type in pitch_events or (chip == 'psg' and seg.ev_type == 'evS'):
                boundary = True
            if seg.l <= 0:
                continue
            rest = not audible(seg, chip)
            previous = notes[-1] if notes else None
            contiguous = previous is not None and previous.start + previous.length == seg.ticks
            same = contiguous and previous.rest == rest
            if same and not rest:
                same = (not boundary and settings(previous.segment, chip) == settings(seg, chip)
                        and seg.volume <= previous.runs[-1][0])
            if not same:
                notes.append(Note(seg, seg.ticks, 0, rest))
            note = notes[-1]
            note.segment_indices.append(segment_index)
            note.length += seg.l
            if not rest:
                if note.runs and note.runs[-1][0] == seg.volume:
                    volume, length = note.runs[-1]
                    note.runs[-1] = (volume, length + seg.l)
                else:
                    note.runs.append((seg.volume, seg.l))
            boundary = False
        if any(not n.rest for n in notes):
            result[ch] = notes
    return result


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


def render(segments, chip, bank, raw_ticks=False, waveforms=(), dump_path=None):
    from melody_patterns import analyze
    from melody_loops import project, dump_projection
    analysis = analyze(segments, chip)
    before_lines, loop_report = [], []
    notes = extract_notes(segments, chip)
    if not bank.prepared:
        bank.select(candidate_curves(notes))
    used = set()
    lines = []
    dump_rows = []
    envelope_assignments = {}
    for ch, rows in notes.items():
        track = ch + (1 if chip == 'psg' else 4)
        current = {}
        body = []
        cursor = 0
        boundaries = {}

        def set_value(key, value, token):
            if current.get(key) != value:
                if key in ('octave', 'volume'):
                    prefix = 'o' if key == 'octave' else 'v'
                    token = compact_state_token(prefix, value, current.get(key))
                body.append(token)
                current[key] = value

        for note in rows:
            boundaries[note.segment_indices[0]] = len(body)
            seg = note.segment
            if note.start > cursor:
                body.append(length_tokens('r', note.start - cursor, raw_ticks))
            cursor = note.start + note.length
            if note.rest:
                body.append(length_tokens('r', note.length, raw_ticks))
                boundaries[note.segment_indices[-1] + 1] = len(body)
                dump_rows.append((track, note.start, cursor, 'rest', '', ''))
                continue
            hw = chip == 'psg' and seg.envelope_enabled
            env = bank.curves.get(tuple(note.runs), bank.aliases.get(tuple(note.runs))) if len(note.runs) > 1 and not hw else None
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
            if hw:
                # v disables hardware envelopes, so apply it before s.
                set_value('volume', 15, 'v15')
                set_value('period', seg.envelope_period, f'm{int(143.03493 * seg.envelope_period)}')
                body.append(f's{seg.envelope_shape}')
                current['hw'] = True
                current.pop('env', None)
                body.append(length_tokens(seg.scale, note.length, raw_ticks))
            else:
                if current.pop('hw', False):
                    current.pop('volume', None)
                chosen = env if env is not None else 0
                used.add(chosen)
                set_value('env', chosen, f'@e{chosen}')
                if env is not None:
                    set_value('volume', 15, 'v15')
                    body.append(length_tokens(seg.scale, note.length, raw_ticks))
                else:
                    for index, (volume, duration) in enumerate(note.runs):
                        set_value('volume', volume, f'v{volume}')
                        body.append(length_tokens(seg.scale, duration, raw_ticks, tie=index > 0))
            boundaries[note.segment_indices[-1] + 1] = len(body)
            dump_rows.append((track, note.start, cursor, 'note', '' if env is None else env,
                              ';'.join(f'{v}:{n}' for v, n in note.runs)))
        before_lines.append(f'{track} ' + ' '.join(body))
        body, report = project(body, boundaries, analysis[ch], ch)
        loop_report.extend(report)
        lines.append(f'{track} ' + ' '.join(body))
    header = [f'#alloc {ch + (1 if chip == "psg" else 4)}=0' for ch in notes]
    if not header:
        header = ['#alloc 0=0']
    header.insert(0, '#tempo 75' if raw_ticks else '#tempo 225')
    header.extend(f'@s{i:02d} = {{{wave}}}' for i, wave in enumerate(waveforms))
    header.extend(bank.definitions(used))
    if dump_path:
        with Path(dump_path).open('w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(('track', 'tick_start', 'tick_end', 'kind', 'envelope_id', 'volume_runs'))
            writer.writerows(dump_rows)
        segment_path = Path(str(dump_path).replace('.target_notes.csv', '.segments.csv'))
        if segment_path != Path(dump_path) and segment_path.exists():
            annotate_envelopes(segment_path, segments, envelope_assignments)
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
