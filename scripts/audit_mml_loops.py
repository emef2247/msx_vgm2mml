"""Inventory MGSDRV reference loops and their score lengths (quarter = 48 steps).

Reuses the bounded reference lexer. Unsupported syntax is reported, never
silently counted. This measures score duration, not KEYON gates or VGM time.
"""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

from audit_reference_loop_windows import parse_reference, Loop
from mml_sync import _NOTE, _RHYTHM_NOTE, _duration


def analyze(text):
    tracks, macros, tempo = parse_reference(text)
    rows = []
    for ch, nodes in tracks.items():
        definitions, serials, visits = {}, Counter(), defaultdict(list)

        def inventory(items, depth=1, parent=''):
            for item in items:
                if isinstance(item, Loop):
                    serials[item.line] += 1
                    source_id = f'{item.line}:{serials[item.line]}'
                    definitions[item.identity] = dict(channel=ch, loop_id=item.identity,
                        source_id=source_id, line=item.line, depth=depth, parent_loop=parent,
                        repeats=item.count, infinite=item.count == 0,
                        has_exit=any(not isinstance(n, Loop) and n[0] == '|' for n in item.body),
                        child_loops=sum(isinstance(n, Loop) for n in item.body))
                    inventory(item.body, depth + 1, item.identity)
        inventory(nodes)
        state = dict(step=0, default=48, operations=0)

        def visit(items, last=False, in_loop=False):
            common = None
            for item in items:
                state['operations'] += 1
                if state['operations'] > 1_000_000:
                    raise ValueError('Loop expansion exceeds bounded audit limit')
                if isinstance(item, Loop):
                    def has_infinite_child(body):
                        return any(isinstance(n, Loop) and (n.count == 0 or has_infinite_child(n.body)) for n in body)
                    if has_infinite_child(item.body):
                        raise ValueError('Loop body contains an infinite child; its duration is unbounded')
                    # A single inspection pass for ]0; never claim finite total.
                    for repeat in range(item.count or 1):
                        start = state['step']
                        prefix = visit(item.body, last=bool(item.count and repeat == item.count-1), in_loop=True)
                        visits[item.identity].append(dict(iteration=repeat,
                            steps=state['step']-start,
                            common_steps=None if prefix is None else prefix-start))
                    continue
                token = item[0].lower()
                if token == '|':
                    common = state['step']
                    if last:
                        break
                    continue
                if token.startswith('*'):
                    # Do not silently drop duration carried by a macro.
                    raise ValueError('Macro calls require a separate macro-aware length audit')
                if token == '_' and in_loop:
                    raise ValueError('Portamento inside a loop has unsupported duration semantics')
                if match := re.fullmatch(r'l(%\d+|\d+)(\.*)', token):
                    state['default'] = _duration(*match.groups(), state['default'])
                else:
                    note = (_RHYTHM_NOTE if ch == 'f' else _NOTE).fullmatch(token)
                    tie = re.fullmatch(r'\^(%\d+|\d+)?(\.*)', token)
                    if note or tie:
                        length, dots = (note or tie).groups()
                        state['step'] += _duration('' if length == ':' else length, dots, state['default'])
            return common
        visit(nodes)
        for identity, row in definitions.items():
            observed = visits[identity]
            # Nested loops have multiple invocations; retain duration ranges.
            full = [v['steps'] for v in observed if row['infinite'] or v['iteration'] < row['repeats']-1]
            final = [v['steps'] for v in observed if not row['infinite'] and v['iteration'] == row['repeats']-1]
            common = [v['common_steps'] for v in observed if v['common_steps'] is not None]
            # Plain ]1 loops have only their final (and sole) pass.
            body = full or final
            row.update(body_steps_min=min(body), body_steps_max=max(body),
                body_whole_notes_min=min(body)/192, body_whole_notes_max=max(body)/192,
                final_steps_min=min(final) if final else '', final_steps_max=max(final) if final else '',
                common_steps_min=min(common) if common else '', common_steps_max=max(common) if common else '',
                inspected_iterations=len(observed))
            if not row['infinite']:
                totals = [sum(v['steps'] for v in observed[i:i+row['repeats']])
                          for i in range(0, len(observed), row['repeats'])]
                row.update(expanded_steps_min=min(totals), expanded_steps_max=max(totals))
            else:
                row.update(expanded_steps_min='', expanded_steps_max='')
            rows.append(row)
    return rows, tempo


def summarize(rows):
    physical = {}
    for row in rows:
        key = (row['file'], row['source_id'])
        if key not in physical:
            physical[key] = dict(row)
        else:
            # Shared source brackets may contain children/exits on only one track.
            physical[key]['child_loops'] = max(physical[key]['child_loops'], row['child_loops'])
            physical[key]['has_exit'] |= row['has_exit']
            physical[key]['body_steps_min'] = min(physical[key]['body_steps_min'],row['body_steps_min'])
            physical[key]['body_steps_max'] = max(physical[key]['body_steps_max'],row['body_steps_max'])
    unique = list(physical.values())
    return dict(source_loops=len(unique), channel_loops=len(rows),
                finite_source_loops=sum(not r['infinite'] for r in unique),
                infinite_source_loops=sum(r['infinite'] for r in unique),
                source_loops_with_exit=sum(r['has_exit'] for r in unique),
                source_loops_with_children=sum(r['child_loops'] > 0 for r in unique),
                max_depth=max((r['depth'] for r in rows), default=0),
                repeats_histogram=dict(Counter(str(r['repeats']) for r in unique)),
                depth_histogram=dict(Counter(str(r['depth']) for r in unique)),
                source_phrase_steps_histogram=dict(Counter(str(r['body_steps_min']) for r in unique
                                                           if r['body_steps_min']==r['body_steps_max'])),
                variable_phrase_length_source_loops=sum(r['body_steps_min']!=r['body_steps_max'] for r in unique),
                # Durations are channel observations: shared tracks can differ.
                phrase_steps_histogram=dict(Counter(str(r['body_steps_min']) for r in rows
                                                    if r['body_steps_min'] == r['body_steps_max'])),
                variable_phrase_length_channel_loops=sum(r['body_steps_min'] != r['body_steps_max'] for r in rows))


def audit(source, output, exclude_dirs=()):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Input and output directory trees must be separate')
    if not source.is_dir():
        raise ValueError(f'Input directory not found: {source}')
    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() == '.mml'
                   and not set(p.relative_to(source).parts[:-1]).intersection(exclude_dirs))
    if not files:
        raise ValueError('No MML files found')
    rows, reports = [], []
    for path in files:
        relative = str(path.relative_to(source))
        try:
            raw = path.read_bytes()
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode('cp932')
            loops, tempo = analyze(text)
            loops = [dict(file=relative, **r) for r in loops]
            report = dict(file=relative, status='parsed', tempo=tempo, error='', **summarize(loops))
            rows.extend(loops)
        except (ValueError, KeyError, IndexError, ZeroDivisionError) as error:
            report = dict(file=relative, status='unsupported', error=str(error))
        reports.append(report)
    summary = dict(input=str(source), excluded_directories=list(exclude_dirs), files_found=len(files), files_parsed=sum(r['status']=='parsed' for r in reports),
                   files_unsupported=sum(r['status']=='unsupported' for r in reports),
                   unit='score steps; quarter=48, whole=192; whole-note equivalents do not assert meter',
                   scope='Source syntax and score length, not audio equivalence or VGM loop recovery',
                   **summarize(rows), files=reports)
    output.mkdir(parents=True, exist_ok=True)
    (output/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    def write(name, values):
        fields = list(dict.fromkeys(k for row in values for k in row))
        with (output/name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in values:
                writer.writerow({k: json.dumps(v) if isinstance(v, dict) else v for k,v in row.items()})
    write('loops.csv', rows)
    write('files.csv', reports)
    print(json.dumps({k:v for k,v in summary.items() if k!='files'}, indent=2, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--exclude-dir', action='append', default=[],
                        help='Exclude directories with this exact name (repeatable)')
    args = parser.parse_args()
    try:
        result = audit(args.input_dir, args.outdir, args.exclude_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error)+'\n')
    if result['files_unsupported']:
        parser.exit(1, 'Some files were unsupported; inspect files.csv\n')
