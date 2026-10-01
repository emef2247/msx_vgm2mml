"""Report per-VGM OPLL melodic key-on counts and channel-count differences."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_reader import parse_vgm
from opll import _build_segments
from opll_segments import dump_segments
from opll_comparison import compare_keyons


def extract(path):
    state, edges = {}, []
    rhythm_mode = False
    with open(path, newline='') as stream:
        for row in csv.DictReader(stream):
            address, value = int(row['addr'], 0), int(row['val'])
            if address == 0x0e:
                rhythm_mode = bool(value & 32)
                continue
            ch = address - 0x20
            if not 0 <= ch < 9:
                continue
            old = state.get(ch, 0)
            state[ch] = value
            if ch >= 6 and rhythm_mode:
                continue
            if (old ^ value) & 16:
                edges.append(dict(ch=ch, time=float(row['time']), tick=int(row['ticks']),
                                  keyon=int(bool(value & 16))))
    return edges


def compare_files(reference, actual, outdir):
    summary = {}
    edge_sets = {}
    for label, source in (('reference', reference), ('actual', actual)):
        output = outdir / label
        output.mkdir(parents=True, exist_ok=True)
        paths = parse_vgm(str(source), str(output))
        segments, _ = _build_segments(paths[5])
        dump_segments(segments, output / (source.stem + '.opll.segments.csv'))
        edges = extract(paths[7])
        edge_sets[label] = edges
        with (output / 'key_edges.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=('ch', 'time', 'tick', 'keyon'))
            writer.writeheader()
            writer.writerows(edges)
        summary[label] = dict(source=str(source.resolve()),
                              keyon_counts=dict(Counter(e['ch'] for e in edges if e['keyon'])))
    # These are channel-count shortages/excesses, not event matching results.
    # Counts retain terminal zero-duration edges; no time tolerance is applied.
    totals = compare_keyons(edge_sets['reference'], edge_sets['actual'])
    summary['totals'] = totals
    (outdir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path, nargs='?')
    parser.add_argument('actual', type=Path, nargs='?')
    parser.add_argument('--pairs', type=Path, help='CSV with reference,actual columns; optional input label')
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs:
        if args.reference or args.actual:
            parser.error('Use either reference/actual or --pairs')
        with args.pairs.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'reference', 'actual'} <= set(reader.fieldnames or ()):
                parser.error('--pairs CSV requires reference and actual columns')
            pairs = list(reader)
        if not pairs:
            parser.error('--pairs CSV contains no comparison cases')
        # Relative VGM paths resolve against the CSV's own directory.
        for pair in pairs:
            for side in ('reference', 'actual'):
                if not pair[side]:
                    parser.error('Pair paths must not be empty')
                path = Path(pair[side])
                pair[side] = path if path.is_absolute() else args.pairs.resolve().parent / path
    else:
        if not args.reference or not args.actual:
            parser.error('Provide reference and actual VGMs, or --pairs')
        pairs = [dict(reference=args.reference, actual=args.actual)]
    args.outdir.mkdir(parents=True, exist_ok=True)
    results = []
    fields = ('input', 'status', 'reference_keyon', 'actual_keyon', 'missing_keyon', 'extra_keyon', 'error')
    for index, pair in enumerate(pairs):
        row = dict.fromkeys(fields, '')
        row.update(input=pair.get('input') or str(pair['reference']), status='error')
        output = args.outdir / f'case_{index + 1:04d}' if args.pairs else args.outdir
        try:
            if not Path(pair['reference']).is_file() or not Path(pair['actual']).is_file():
                raise FileNotFoundError('Reference or actual VGM unavailable')
            row.update(compare_files(Path(pair['reference']), Path(pair['actual']), output), status='compared')
        except (OSError, ValueError) as error:
            row['error'] = str(error)
            output.mkdir(parents=True, exist_ok=True)
            (output / 'summary.json').write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))
        with (args.outdir / 'keyon_totals.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)
    return 0 if all(r['status'] == 'compared' for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
