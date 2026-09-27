"""Target-stage PSG/SCC notes and exact, 60 Hz software volume envelopes.

The input Segments remain unchanged. Constant-pitch volume runs are an
interpretation, separated at register pitch writes, state changes and attacks.
"""
import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Note:
    segment: object
    start: int
    length: int
    rest: bool
    runs: list = field(default_factory=list)
    envelope: int | None = None


class EnvelopeBank:
    def __init__(self):
        self.curves = {((15, 1),): 0}

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
        for seg in rows:
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
    notes = extract_notes(segments, chip)
    counts = Counter(tuple(n.runs) for rows in notes.values() for n in rows
                     if not n.rest and len(n.runs) > 1
                     and not getattr(n.segment, 'envelope_enabled', False))
    # Prefer reused curves when the 32 definition slots are scarce.
    for curve, count in counts.most_common():
        if count > 1 or len(curve) >= 3:
            bank.register(curve)
    used = set()
    lines = []
    dump_rows = []
    for ch, rows in notes.items():
        track = ch + (1 if chip == 'psg' else 4)
        current = {}
        body = []
        cursor = 0

        def set_value(key, value, token):
            if current.get(key) != value:
                body.append(token)
                current[key] = value

        for note in rows:
            seg = note.segment
            if note.start > cursor:
                body.append(length_tokens('r', note.start - cursor, raw_ticks))
            cursor = note.start + note.length
            if note.rest:
                body.append(length_tokens('r', note.length, raw_ticks))
                dump_rows.append((track, note.start, cursor, 'rest', '', ''))
                continue
            hw = chip == 'psg' and seg.envelope_enabled
            env = bank.curves.get(tuple(note.runs)) if len(note.runs) > 1 and not hw else None
            note.envelope = env
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
            dump_rows.append((track, note.start, cursor, 'note', '' if env is None else env,
                              ';'.join(f'{v}:{n}' for v, n in note.runs)))
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
    return '\n'.join(header + [''] + lines) + '\n'
