"""Source-linked OPLL performed notes, with duration-first repeat candidates."""
from dataclasses import dataclass
from types import SimpleNamespace
from performed_patterns import Unit


@dataclass(frozen=True)
class NoteUnit(Unit):
    duration: int

    def signature(self):
        # Nominate phrases by note/rest duration, then verify complete state.
        return self.kind, self.duration

    @property
    def validation_key(self):
        return self.key


def group_notes(rows, items):
    """Group continuous keyed intervals; never move or delete a source row.

    Rising edges (including zero-duration edges), key-off, and timing gaps
    delimit units. Analysis flags do not define audible trajectory equality.
    """
    if not rows:
        return [], []
    cuts = [0]
    previous_key = False
    for i, seg in enumerate(rows):
        edge = bool(getattr(seg, 'key_on_edge', seg.keyon and not previous_key))
        if i and (edge or bool(seg.keyon) != previous_key
                  or seg.tick_start != rows[i - 1].tick_end):
            cuts.append(i)
        previous_key = bool(seg.keyon)
    cuts.append(len(rows))
    notes, units = [], []
    for start, stop in zip(cuts, cuts[1:]):
        first, last = rows[start], rows[stop - 1]
        trajectory = []
        for i in range(start, stop):
            seg, item = rows[i], items[i]
            state = (seg.keyon, seg.fnum, seg.block, seg.inst, seg.vol, seg.sus,
                     item.patch, item.patch_changes)
            duration = seg.tick_end - seg.tick_start
            offset = seg.tick_start - first.tick_start
            if duration <= 0:
                # Rendering skips these states; source rows remain members,
                # and key transitions already delimit their own units above.
                continue
            # Equal adjacent positive states can be compared independently of
            # harmless source partitioning.
            if (duration > 0 and trajectory and trajectory[-1][1] > 0
                    and trajectory[-1][2] == state
                    and trajectory[-1][0] + trajectory[-1][1] == offset):
                old_offset, old_duration, _ = trajectory[-1]
                trajectory[-1] = (old_offset, old_duration + duration, state)
            else:
                trajectory.append((offset, duration, state))
        length = last.tick_end - first.tick_start
        index = len(notes)
        kind = 'note' if first.keyon else 'rest'
        notes.append(SimpleNamespace(start=first.tick_start, length=length,
                                     segment_indices=list(range(start, stop))))
        units.append(NoteUnit(index, index + 1, kind, tuple(trajectory), length))
    return notes, units
