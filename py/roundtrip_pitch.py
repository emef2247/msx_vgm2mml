"""Compare PSG/SCC pitch on the existing Segment tick timeline."""
import csv
from pathlib import Path


def timeline(path, chip):
    channels = {}
    with open(path, encoding='utf-8-sig', newline='') as stream:
        for line, row in enumerate(csv.DictReader(stream), 2):
            start, end = int(row['tick_start']), int(row['tick_end'])
            if end <= start:
                continue
            ch = int(row['ch'])
            active = row['scale'] != 'r'
            if chip == 'psg':
                active = active and bool(int(row['mode']) & 1)
            period = int(row['tone_period']) if active else None
            states = channels.setdefault(ch, {})
            for tick in range(start, end):
                if tick in states:
                    raise ValueError(f'{path}:{line}: overlapping channel {ch}, tick {tick}')
                states[tick] = (period, line)
    return channels


def compare(expected, actual, chip, offset=0, tolerance=1):
    """offset is actual tick minus expected tick; never infer pitch-dependent shifts.

    Boundary differences remain reported, even within tolerance. Missing coverage
    cannot be excused by tolerance. This checks tone pitch, not complete audio.
    """
    if tolerance < 0:
        raise ValueError('tolerance must be nonnegative')
    diffs = []
    for ch in sorted(expected.keys() | actual.keys()):
        left, right = expected.get(ch, {}), actual.get(ch, {})
        ticks = sorted(left.keys() | {t - offset for t in right})
        for tick in ticks:
            a, b = left.get(tick), right.get(tick + offset)
            # Omitted silent channels and trailing silence do not affect pitch.
            if (a is None or a[0] is None) and (b is None or b[0] is None):
                continue
            if a is not None and b is not None and a[0] == b[0]:
                continue
            kind = 'pitch' if a and b and a[0] is not None and b[0] is not None else 'activity'
            if a is None or b is None:
                kind = 'coverage'
            elif tolerance and any(
                right.get(tick + offset + delta, (object(),))[0] == a[0]
                for delta in range(-tolerance, tolerance + 1)
            ) and any(
                left.get(tick + delta, (object(),))[0] == b[0]
                for delta in range(-tolerance, tolerance + 1)
            ):
                kind = 'boundary'
            row = dict(chip=chip, ch=ch, tick_start=tick, tick_end=tick + 1,
                       actual_tick_start=tick + offset, kind=kind,
                       expected_period=a[0] if a else '', actual_period=b[0] if b else '',
                       expected_csv_line=a[1] if a else '', actual_csv_line=b[1] if b else '')
            keys = ('chip', 'ch', 'kind', 'expected_period', 'actual_period',
                    'expected_csv_line', 'actual_csv_line')
            if diffs and diffs[-1]['tick_end'] == tick and all(diffs[-1][k] == row[k] for k in keys):
                diffs[-1]['tick_end'] = tick + 1
            else:
                diffs.append(row)
    return diffs


def compare_directories(reference, actual, stem, offset=0, tolerance=1):
    diffs = []
    for chip in ('psg', 'scc'):
        filename = f'{stem}.{chip}.segments.csv'
        diffs.extend(compare(timeline(Path(reference) / filename, chip),
                             timeline(Path(actual) / filename, chip), chip, offset, tolerance))
    return diffs
