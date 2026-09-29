"""Audit reference MML note settings against observed PSG/SCC period sequences.

This deliberately compares pitch changes, not timing or articulation. Unmatched
changes are reported, never silently accepted as equivalent performances.
"""
import argparse
import csv
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from mml_sync import analyze_mml, _leaves
from psg_scc_target import BASE_PERIODS


def reference_notes(text, loop_count=1):
    match = re.search(r'#psg_tune\s*\{([^}]+)\}', text)
    if not match:
        raise ValueError('An explicit reference #psg_tune is required')
    table = tuple(int(v.strip()) for v in match[1].split(','))
    if len(table) != 12:
        raise ValueError('Expected 12 tuning entries')
    # The shared analyzer accepts individual track prefixes. Expand grouped ones.
    text = re.sub(r'^([1-8]{2,})\s+(.+)$',
                  lambda m: '\n'.join(ch + ' ' + m[2] for ch in m[1]), text, flags=re.M)
    # Explicit finite inspection window for a source's infinite song loop.
    text = re.sub(r'\]0\b', ']' + str(loop_count), text)
    tracks, _, _ = analyze_mml(text)
    result = {}
    for ch, nodes in tracks.items():
        if ch not in '12345678':
            continue
        octave, detune, volume, mode = 4, 0, 15, 1
        notes = []
        for token in _leaves(nodes):
            t = token.text.lower()
            if re.fullmatch(r'o\d+', t): octave = int(t[1:])
            elif t == '>': octave += 1
            elif t == '<': octave -= 1
            elif re.fullmatch(r'\\[-+]?\d+', t): detune = int(t[1:])
            elif re.fullmatch(r'v\d+', t): volume = int(t[1:])
            elif re.fullmatch(r'/\d+', t): mode = int(t[1:])
            elif t.startswith(('(', ')')):
                volume += (1 if t[0] == ')' else -1) * int(t[1:] or 1)
            elif re.fullmatch(r'[a-g][+#-]?(?:%\d+|\d+)?\.*', t):
                if volume == 0 or (ch in '123' and not mode & 1):
                    continue
                name = re.match(r'[a-g][+#-]?', t)[0]
                index = dict(c=0,d=2,e=4,f=5,g=7,a=9,b=11)[name[0]]
                index += 1 if name.endswith(('+','#')) else -1 if name.endswith('-') else 0
                shift, index = divmod(index, 12)
                period = (table[index] >> (octave + shift - 1)) - detune
                if not notes or notes[-1]['period'] != period:
                    notes.append(dict(note=name, octave=octave, detune=detune,
                                      step=token.start, period=period,
                                      current_table_period=(BASE_PERIODS[index] >> (octave + shift - 1))-detune))
        result[ch] = notes
    return result, table


def observed(path, chip, ch):
    notes = []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for line, row in enumerate(csv.DictReader(stream), 2):
            if int(row['ch']) != ch or int(row['l']) <= 0 or row['scale'] == 'r':
                continue
            if chip == 'psg' and not int(row['mode']) & 1:
                continue
            period = int(row['tone_period'])
            if not notes or notes[-1]['period'] != period:
                notes.append(dict(period=period, line=line, tick=row['tick_start']))
    return notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mml', type=Path)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--loop-count', type=int, default=1, help='Iterations of source ]0 loops')
    args = parser.parse_args()
    if args.outdir.resolve() == args.reference.resolve() or args.reference.resolve() in args.outdir.resolve().parents:
        parser.error('Do not write audit outputs into reference')
    if args.loop_count < 1:
        parser.error('--loop-count must be positive')
    tracks, table = reference_notes(args.mml.read_text(encoding='utf-8-sig'), args.loop_count)
    args.outdir.mkdir(parents=True, exist_ok=True)
    rows, stats = [], {}
    for ch, notes in tracks.items():
        chip = 'psg' if int(ch) <= 3 else 'scc'
        channel = int(ch) - (1 if chip == 'psg' else 4)
        actual = observed(args.reference / f'{args.mml.stem}.{chip}.segments.csv', chip, channel)
        matcher = SequenceMatcher(None, [n['period'] for n in notes], [n['period'] for n in actual], autojunk=False)
        matched = 0
        for kind, a, b, c, d in matcher.get_opcodes():
            if kind == 'equal': matched += b-a
            for i in range(max(b-a, d-c)):
                n = notes[a+i] if a+i < b else {}
                s = actual[c+i] if c+i < d else {}
                rows.append(dict(channel=ch, status=kind, reference_step=n.get('step',''),
                                 note=n.get('note',''), octave=n.get('octave',''), detune=n.get('detune',''),
                                 expected_period=n.get('period',''), observed_period=s.get('period',''),
                                 segment_csv_line=s.get('line',''), segment_tick=s.get('tick',''),
                                 current_table_same_note_period=n.get('current_table_period','')))
        stats[ch] = dict(reference_changes=len(notes), observed_changes=len(actual), matched=matched)
    with (args.outdir / 'reference_pitch.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    report = dict(table=table, channels=stats, loop_count=args.loop_count,
                  scope='Ordered pitch-change correspondence only; equal is not timing/articulation validation')
    (args.outdir / 'summary.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
