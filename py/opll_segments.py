"""Inspectable OPLL Segments before target voice assignment or rendering."""
import csv


def dump_segments(segments, path):
    """Retain native fields, including rhythm channels and source time."""
    from segment_utils import _Segment

    # The legacy class declares r_tempo twice; CSV columns must be unique.
    fields = list(dict.fromkeys(_Segment.__slots__))
    with open(path, 'w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for ch in sorted(segments):
            for segment in segments[ch]:
                writer.writerow({field: getattr(segment, field, '') for field in fields})
