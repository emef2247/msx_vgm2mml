"""Keep an observed PSG hardware envelope running across pitch partitions."""
import csv
from pathlib import Path


def continuation_starts(performance):
    result = set()
    if performance.chip != 'psg':return result
    for channel, notes in performance.channels:
        previous = None
        for note in notes:
            if (previous is not None and not previous.rest and not note.rest
                    and previous.segment.envelope_enabled and note.segment.envelope_enabled
                    and previous.start + previous.length == note.start
                    and 'hardware_envelope_reset' not in note.boundary_reasons):
                result.add((channel, note.start))
            previous = note
    return result


def dump_decisions(dump_path, rows):
    if dump_path is None or not rows:return
    path = Path(str(dump_path).replace('.target_notes.csv', '.hw_envelope.csv'))
    if path == Path(dump_path):path = Path(str(dump_path) + '.hw_envelope.csv')
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('channel', 'tick_start', 'tick_end', 'shape', 'continuation', 'source_segment_indices'))
        writer.writerows(rows)
