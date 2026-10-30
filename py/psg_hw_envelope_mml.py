"""Emit PSG hardware-envelope notes as adjacent, untied notes.

Target policy (owner decision, 2026-10-30): pitch partitions of one
source envelope are NOT tied with '&'. A tie merges the attacks into a
single sustained note, so the envelope stops restarting at each
partition and drum-like articulation is lost; ties also lengthen the
MML and consume MGSDRV track buffer. MGSDRV restarts the hardware
envelope on every untied note, so gapless adjacent notes keep the
source timing exactly while each note keeps its own attack. Loop and
macro compression may still group the resulting adjacent notes; that
grouping must not merge the notes themselves.
"""
import csv
from pathlib import Path


def continuation_starts(performance):
    """No target continuations: see the module docstring.

    Kept as the single policy point both envelope renderers consult.
    The hardware-envelope notes themselves are still recorded per note
    by dump_decisions.
    """
    return set()


def dump_decisions(dump_path, rows):
    if dump_path is None or not rows:return
    path = Path(str(dump_path).replace('.target_notes.csv', '.hw_envelope.csv'))
    if path == Path(dump_path):path = Path(str(dump_path) + '.hw_envelope.csv')
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('channel', 'tick_start', 'tick_end', 'shape', 'continuation', 'source_segment_indices'))
        writer.writerows(rows)
