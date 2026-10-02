"""Inspect reference finite-loop windows against existing Segment CSVs.

This is a bounded audit parser, not a replacement for MGSC. Window positions
use a declared approximate libkss frame length and a reported first-note anchor.
Exact signature differences under that mapping do not certify a conversion bug.
"""
import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from mml_sync import _TOKEN, _RHYTHM_TOKEN, _NOTE, _RHYTHM_NOTE, _duration


@dataclass
class Loop:
    body: list
    count: int
    line: int
    identity: int


def parse_reference(text):
    """Handle these fixtures' grouped tracks, finite/infinite loops and exits."""
    bodies, macros = {}, {}
    depth = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        code = line.split(';', 1)[0]
        macro = re.match(r'^\*(\d+)\s*=\s*\{(.*)\}', code)
        if macro:
            macros[macro[1]] = [(macro[2], line_number)]
        track = re.match(r'^([1-9a-fA-F]+)\s+(.*)$', code) if depth == 0 else None
        if track:
            for ch in track[1].lower():
                bodies.setdefault(ch, []).append((track[2], line_number))
        depth += code.count('{') - code.count('}')
    tempo = int(re.search(r'^#tempo\s+(\d+)', text, re.M)[1])
    result = {}
    for ch, lines in bodies.items():
        base = _RHYTHM_TOKEN.pattern if ch == 'f' else _TOKEN.pattern
        lexer = re.compile(r'\||\^(?:%\d+|\d+)?\.*|_(?:[-+]?\d+)?|' + base, re.I)
        root, current, stack, identities = [], [], [], 0
        root = current
        for code, line in lines:
            position = 0
            for match in lexer.finditer(code):
                if match.start() != position:
                    raise ValueError(f'Unsupported reference syntax at line {line}: {code[position:]}')
                position = match.end()
                token = match[0]
                if token.isspace():
                    continue
                if token == '[':
                    identities += 1
                    node = Loop([], 0, line, identities)
                    current.append(node)
                    stack.append(current)
                    current = node.body
                elif token.startswith(']'):
                    if not stack:
                        raise ValueError('Unmatched loop end')
                    parent = stack.pop()
                    parent[-1].count = int(token[1:] or 2)
                    current = parent
                else:
                    current.append((token, line))
            if position != len(code):
                raise ValueError(f'Unsupported reference syntax at line {line}')
        if stack:
            def has_duration(items):
                note = _RHYTHM_NOTE if ch == 'f' else _NOTE
                return any(has_duration(x.body) if isinstance(x, Loop) else
                           bool(note.fullmatch(x[0].lower())) for x in items)
            # sample initializes an unused grouped track without closing it.
            # Never accept an unclosed loop on a track that consumes time.
            if has_duration(root):
                raise ValueError(f'Unclosed reference loop on channel {ch}')
            continue
        result[ch] = root
    return result, macros, tempo


def windows(nodes, macros, rhythm=False, infinite_passes=8):
    records, commands = [], []
    state = dict(step=0, default=48, volume=15, first_note=None)
    def visit(nodes, last=False, parents=(), expanding=()):
        for node in nodes:
            if isinstance(node, Loop):
                count = node.count or infinite_passes
                for repeat in range(count):
                    start, cut = state['step'], len(commands)
                    visit(node.body, last=node.count != 0 and repeat == count-1,
                          parents=parents+(node.identity,), expanding=expanding)
                    records.append(dict(loop_id=node.identity, line=node.line,
                                        parent_loop=parents[-1] if parents else '',
                                        count=node.count, iteration=repeat,
                                        step_start=start, step_end=state['step'],
                                        commands=tuple(commands[cut:])))
                continue
            token, line = node
            if token == '|':
                if last:
                    break
                continue
            if token.startswith('*'):
                name = token[1:]
                if name in expanding or name not in macros:
                    raise ValueError('Undefined or recursive reference macro')
                # These fixtures have single-line macro bodies without loops.
                body = macros[name][0][0]
                lexer = _RHYTHM_TOKEN if rhythm else _TOKEN
                tokens = [(m[0], line) for m in lexer.finditer(body) if not m[0].isspace()]
                if ''.join(m[0] for m in lexer.finditer(body)) != body:
                    raise ValueError('Unsupported macro syntax')
                visit(tokens, expanding=expanding+(name,))
                continue
            commands.append(token)
            lower = token.lower()
            if lower.startswith('l'):
                match = re.fullmatch(r'l(%\d+|\d+)(\.*)', lower)
                state['default'] = _duration(*match.groups(), state['default'])
            elif re.fullmatch(r'v[-+]?\d+', lower):
                state['volume'] = state['volume'] + int(lower[1:]) if lower[1] in '+-' else int(lower[1:])
            elif lower.startswith(('(', ')')):
                state['volume'] += (1 if lower[0] == ')' else -1)*int(lower[1:] or 1)
            else:
                match = (_RHYTHM_NOTE if rhythm else _NOTE).fullmatch(lower)
                tie = re.fullmatch(r'\^(%\d+|\d+)?(\.*)', lower)
                if match or tie:
                    length, dots = (tie or match).groups()
                    duration = _duration('' if length == ':' else length, dots, state['default'])
                    if match and not lower.startswith('r') and state['volume'] > 0 and state['first_note'] is None:
                        state['first_note'] = state['step']
                    state['step'] += duration
    visit(nodes)
    return records, state


def read_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return [dict(row, csv_line=i) for i, row in enumerate(csv.DictReader(stream), 2)]


def source_state(row, chip):
    if chip == 'opll':
        fields = ('keyon', 'fnum', 'block', 'inst', 'vol', 'sus', 'voice_id')
    elif chip == 'psg':
        fields = ('tone_period', 'volume', 'mode', 'noise_period',
                  'envelope_enabled', 'envelope_period', 'envelope_shape')
    else:
        fields = ('tone_period', 'volume', 'enabled', 'waveform_hex')
    return tuple(row.get(field, '') for field in fields)


def audit(mml, segments_dir, stem, outdir, frame_samples=735):
    tracks, macros, tempo = parse_reference(mml.read_text(encoding='utf-8-sig'))
    output, anchors = [], []
    for ch, nodes in tracks.items():
        chip = 'opll' if ch in '9abcdef' else 'psg' if ch in '123' else 'scc'
        path = segments_dir / f'{stem}.{chip}.segments.csv'
        if not path.exists():
            continue
        channel = int(ch, 16) - (9 if chip == 'opll' else 1 if chip == 'psg' else 4)
        all_rows = read_rows(path)
        if ch == 'f':
            rows = [r for r in all_rows if 9 <= int(r['ch']) <= 13 and int(r['keyon'])]
        else:
            rows = [r for r in all_rows if int(r['ch']) == channel]
        rows.sort(key=lambda r: (int(r['tick_start']), r['csv_line']))
        records, timing = windows(nodes, macros, ch == 'f')
        active = rows if ch == 'f' else [r for r in rows if (int(r.get('tick_end', 0)) > int(r['tick_start'])
                  and (int(r['keyon']) and int(r['vol']) < 15 and int(r['fnum'])
                       if chip == 'opll' and ch != 'f' else
                       int(r['keyon']) if ch == 'f' else int(r['volume']) > 0))]
        if not active or timing['first_note'] is None:
            continue
        # Report this approximation explicitly; do not hide an inferred shift.
        scale = 75 / tempo * frame_samples / 735
        offset = int(active[0]['tick_start']) - timing['first_note']*scale
        anchors.append(dict(channel=ch, source_first_csv_line=active[0]['csv_line'],
                            source_first_tick=int(active[0]['tick_start']),
                            reference_first_step=timing['first_note'], offset_ticks=offset))
        end_tick = max(int(r['tick_end']) for r in rows)
        first = {}
        for r in sorted(records, key=lambda r:(r['loop_id'],r['step_start'])):
            start, stop = offset+r['step_start']*scale, offset+r['step_end']*scale
            if start < -1 or stop > end_tick+1:
                continue
            # CSVs are already quantized to whole 60 Hz ticks. Fractional
            # clipping would include a preceding/following boundary state.
            start, stop = round(start), round(stop)
            if ch == 'f':
                members = [x for x in rows if start <= int(x['tick_start']) < stop]
            else:
                members = [x for x in rows if int(x['tick_end']) > start and int(x['tick_start']) < stop
                           and int(x['tick_end']) > int(x['tick_start'])]
            sequence = []
            timed = []
            for member in members:
                value = (int(member['ch']), source_state(member,chip)) if ch=='f' else source_state(member,chip)
                if not sequence or sequence[-1] != value:
                    sequence.append(value)
                interval = (max(start,int(member['tick_start']))-start,
                            min(stop,int(member['tick_end']))-start,value)
                if ch != 'f' and timed and timed[-1][2] == value and timed[-1][1] == interval[0]:
                    timed[-1] = (timed[-1][0],interval[1],value)
                else:
                    timed.append(interval)
            identity = (r['loop_id'],r['parent_loop'])
            baseline = first.setdefault(identity,(tuple(sequence),tuple(timed),r['commands']))
            output.append(dict(channel=ch,loop_id=r['loop_id'],source_mml_line=r['line'],
                               declared_count=r['count'],iteration=r['iteration'],
                               reference_step_start=r['step_start'],reference_step_end=r['step_end'],
                               mapped_tick_start=round(start,4),mapped_tick_end=round(stop,4),
                               source_csv_first=members[0]['csv_line'] if members else '',
                               source_csv_last=members[-1]['csv_line'] if members else '',
                               commands_equal_first=r['commands']==baseline[2],
                               source_sequence_equal_first=tuple(sequence)==baseline[0],
                               source_timed_equal_first=tuple(timed)==baseline[1],
                               source_timed_states=json.dumps(timed,separators=(',',':')),
                               source_states=json.dumps(sequence,separators=(',',':'))))
    outdir.mkdir(parents=True,exist_ok=True)
    if output:
        with (outdir/'reference_loop_windows.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(output[0]));writer.writeheader();writer.writerows(output)
    summary=dict(mapping='approximate first-audible-note anchor; not exact command-address correspondence',
                 limitation='Window mismatches require inspection; boundary quantization is not a sound-state difference.',
                 frame_samples=frame_samples,tempo=tempo,anchors=anchors,windows=len(output),
                 later_windows=sum(r['iteration']>0 for r in output),
                 different_command_windows=sum(r['iteration']>0 and not r['commands_equal_first'] for r in output),
                 different_state_windows=sum(r['iteration']>0 and not r['source_sequence_equal_first'] for r in output))
    (outdir/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mml',type=Path);p.add_argument('--segments',type=Path,required=True)
    p.add_argument('--stem',required=True);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();print(json.dumps(audit(a.mml,a.segments,a.stem,a.outdir),indent=2))
