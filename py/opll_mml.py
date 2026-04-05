"""
opll_mml.py - OPLL (YM2413) melody MML generator
Converts an OPLL chronological trace CSV to MGSDRV MML.

Channels 0..5  →  MGSDRV tracks 9..14  (track 15 reserved).

Tick-based final-state evaluation
----------------------------------
OPLL has a well-known quirk where INST/VOL writes may arrive *after*
the KeyOn write within the same VGM frame.  This module handles it by
grouping all events that share the same tick, then evaluating the
*final* per-channel state at the end of each group before deciding
note events.  No delayed scheduler is required.

Usage:
    python opll_mml.py <trace_opll_csv> [output_dir]
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import get_ticks, estimate_mml_used, estimate_alloc, track_id_to_mgsdrv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CH_OFFSET  = 9        # OPLL ch0 → MGSDRV track 9
NUM_CH     = 6        # melody channels

# OPLL VOL is an attenuation: 0 = loudest, 15 = most attenuated.
# MGSDRV v command: 0 = silent, 15 = loudest.
# Conversion: mml_v = 15 - opll_vol

# Trace CSV column indices
_COL_TYPE   = 0
_COL_TIME   = 1
_COL_CH     = 2
_COL_TICKS  = 3
_COL_KEYON  = 4
_COL_FNUM   = 5
_COL_BLOCK  = 6
_COL_INST   = 7
_COL_VOL    = 8

# ---------------------------------------------------------------------------
# Pitch conversion: OPLL Fnum + Block → (octave, scale_name)
# ---------------------------------------------------------------------------

_SCALE_NAMES = ['c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b']


def _opll_note(fnum: int, block: int):
    """Return (octave, scale_name) for the given OPLL Fnum+Block pair.

    YM2413 frequency formula:
        f = 49716 * Fnum * 2^Block / 2^19

    The octave+scale are derived by comparing to A4=440 Hz using
    the standard equal-temperament semitone relationship.

    Returns ('r', 0) when fnum==0 or frequency is outside usable range.
    """
    if fnum == 0:
        return 1, 'r'
    freq = 49716.0 * fnum * (1 << block) / (1 << 19)
    if freq < 16.0:
        return 1, 'r'
    # Convert to MIDI note number (A4=440 Hz = MIDI 69)
    midi = 69.0 + 12.0 * math.log2(freq / 440.0)
    midi_int = round(midi)
    # MGSDRV: C1=MIDI24→o1, C4=MIDI60→o4  →  octave = midi // 12 - 1
    octave     = midi_int // 12 - 1
    octave     = max(1, min(8, octave))
    scale_idx  = midi_int % 12
    return octave, _SCALE_NAMES[scale_idx]


# ---------------------------------------------------------------------------
# Per-channel note state
# ---------------------------------------------------------------------------

class _ChState:
    """Current decoded state for one OPLL melody channel."""
    __slots__ = ('keyon', 'fnum', 'block', 'inst', 'vol')

    def __init__(self):
        self.keyon = 0
        self.fnum  = 0
        self.block = 0
        self.inst  = 0
        self.vol   = 0   # attenuation (0=max, 15=min)

    def copy(self):
        s = _ChState()
        s.keyon = self.keyon
        s.fnum  = self.fnum
        s.block = self.block
        s.inst  = self.inst
        s.vol   = self.vol
        return s

    def mml_vol(self):
        """MGSDRV v value (15=max, 0=silent)."""
        return 15 - self.vol

    def pitch_key(self):
        return (self.fnum, self.block)


# ---------------------------------------------------------------------------
# Segment representation
# ---------------------------------------------------------------------------

class _Segment:
    """A contiguous note-on or rest segment on one channel."""
    __slots__ = ('tick_start', 'tick_end', 'keyon', 'fnum', 'block',
                 'inst', 'vol')

    def __init__(self, tick_start, keyon, fnum, block, inst, vol):
        self.tick_start = tick_start
        self.tick_end   = tick_start   # will be updated
        self.keyon      = keyon
        self.fnum       = fnum
        self.block      = block
        self.inst       = inst
        self.vol        = vol

    def mml_vol(self):
        return 15 - self.vol


# ---------------------------------------------------------------------------
# Build per-channel segment lists from the trace CSV
# ---------------------------------------------------------------------------

def _build_segments(trace_path: str) -> dict:
    """Read trace CSV and return per-channel segment lists.

    Uses tick-based final-state evaluation:
      - Events at the same tick are all applied before evaluating state.
      - A note-on edge, pitch change, or instrument change while keyon=1
        closes the current segment and opens a new one.
    """
    # 1. Parse trace into per-channel lists of (tick, keyon, fnum, block, inst, vol)
    ch_events: dict[int, list] = {ch: [] for ch in range(NUM_CH)}

    with open(trace_path, 'r', newline='') as fh:
        for line in fh:
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 9:
                continue
            try:
                ch    = int(parts[_COL_CH])
                ticks = int(parts[_COL_TICKS])
                keyon = int(parts[_COL_KEYON])
                fnum  = int(parts[_COL_FNUM])
                block = int(parts[_COL_BLOCK])
                inst  = int(parts[_COL_INST])
                vol   = int(parts[_COL_VOL])
            except (ValueError, IndexError):
                continue
            if 0 <= ch < NUM_CH:
                ch_events[ch].append((ticks, keyon, fnum, block, inst, vol))

    # 2. For each channel, group by tick → final-state evaluation → segments
    segments: dict[int, list] = {ch: [] for ch in range(NUM_CH)}

    for ch in range(NUM_CH):
        events = ch_events[ch]
        if not events:
            continue

        state   = _ChState()
        cur_seg = None
        i       = 0
        n       = len(events)

        while i < n:
            tick = events[i][0]

            # Collect all events at the same tick
            j = i
            while j < n and events[j][0] == tick:
                j += 1

            # Apply all events in this tick group (final-state evaluation)
            for _, keyon, fnum, block, inst, vol in events[i:j]:
                state.keyon = keyon
                state.fnum  = fnum
                state.block = block
                state.inst  = inst
                state.vol   = vol

            # Evaluate state at end of this tick group
            if cur_seg is None:
                # First event: start the first segment
                cur_seg = _Segment(tick, state.keyon, state.fnum, state.block,
                                   state.inst, state.vol)
            else:
                # Check for state change that requires a new segment
                keyon_edge   = (state.keyon == 1 and cur_seg.keyon == 0)
                keyoff_edge  = (state.keyon == 0 and cur_seg.keyon == 1)
                pitch_change = (state.pitch_key() != (cur_seg.fnum, cur_seg.block)
                                and state.keyon == 1)
                inst_change  = (state.inst != cur_seg.inst and state.keyon == 1)
                vol_change   = (state.vol != cur_seg.vol   and state.keyon == 1)

                if keyon_edge or keyoff_edge or pitch_change or inst_change or vol_change:
                    cur_seg.tick_end = tick
                    segments[ch].append(cur_seg)
                    cur_seg = _Segment(tick, state.keyon, state.fnum,
                                       state.block, state.inst, state.vol)
                else:
                    # Extend the current segment
                    cur_seg.tick_end = tick

            i = j

        # Close the last segment
        if cur_seg is not None:
            segments[ch].append(cur_seg)

    return segments


# ---------------------------------------------------------------------------
# MML generation
# ---------------------------------------------------------------------------

def _generate_mml(segments: dict, stem: str) -> str:
    """Generate MGSDRV MML text from per-channel segment data."""
    mml_buffer: dict[int, list] = {ch: [] for ch in range(NUM_CH)}

    for ch in range(NUM_CH):
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        mml_buffer[ch].append(f'\n\n;ch{track_id} start')

        segs    = segments[ch]
        l_cnt   = 0
        o_stamp = 0
        v_stamp = -1
        at_stamp = -1
        mml     = ''
        note_cnt = 0

        for seg_idx, seg in enumerate(segs):
            length = seg.tick_end - seg.tick_start
            if length <= 0:
                continue

            octave, scale = _opll_note(seg.fnum, seg.block)
            v   = seg.mml_vol()

            if not seg.keyon or seg.fnum == 0:
                scale = 'r'

            remaining = length
            while remaining > 0:
                ltmp = min(remaining, 255)

                if note_cnt == 0:
                    at_val = seg.inst
                    mml = f'\n{track_id} @{at_val} v{v}'
                    at_stamp = at_val
                    v_stamp  = v

                if seg.inst != at_stamp and note_cnt != 0:
                    mml += f' @{seg.inst}'
                    at_stamp = seg.inst

                if v != v_stamp and note_cnt != 0:
                    mml += f' v{v}'
                    v_stamp = v

                if scale != 'r' and octave != o_stamp:
                    mml += f' o{octave}'
                    o_stamp = octave

                mml += f' {scale}%{ltmp}'
                l_cnt += ltmp

                remaining -= ltmp
                if remaining > 0:
                    mml_buffer[ch].append(mml)
                    mml = ''

            note_cnt += 1
            if note_cnt >= 8 or (not seg.keyon and v == 0):
                mml_buffer[ch].append(mml)
                mml = ''
                mml_buffer[ch].append(f'\n;tick count: {l_cnt}\n')
                note_cnt = 0

        if mml:
            mml_buffer[ch].append(mml)

        mml_buffer[ch].append(f'\n;{track_id} end: tick count: {l_cnt}\n')

    # Build header
    lines = []
    lines.append(';[name=opll]')
    lines.append('#opll_mode 1')
    lines.append('#tempo 75')
    lines.append(f'#title {{ "{stem}"}}')
    for ch in range(NUM_CH):
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        used  = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {track_id}={alloc}')
    lines.append('')
    lines.append('')

    header_text = '\n'.join(lines)

    body_parts = [header_text]
    for ch in range(NUM_CH):
        for item in mml_buffer[ch]:
            body_parts.append(item)

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_opll_csv(trace_path: str, output_dir: str, stem: str | None = None,
                     dump_passes: bool = False) -> str:
    """Run the OPLL MML generation pipeline.

    Args:
        trace_path  : path to ``*_trace.opll.csv``
        output_dir  : directory for output files
        stem        : base name for output files (e.g. ``"ym2413_patch_change_midnote"``).
                      When *None* the stem is derived from *trace_path*.
        dump_passes : when True write a pass0 segment CSV for debugging

    Returns:
        path to the generated ``*.opll.mml``
    """
    if stem is None:
        base = os.path.basename(trace_path)
        root = os.path.splitext(base)[0]          # stem_trace.opll
        root = os.path.splitext(root)[0]          # stem_trace
        if root.endswith('_trace'):
            stem = root[:-len('_trace')]
        else:
            stem = root

    os.makedirs(output_dir, exist_ok=True)

    # Build segments (tick-based final-state evaluation)
    segments = _build_segments(trace_path)

    if dump_passes:
        # Emit a simple segment dump for debugging
        seg_path = os.path.join(output_dir, f'{stem}.opll.pass0.csv')
        with open(seg_path, 'w', newline='\n') as fh:
            fh.write('#ch,tick_start,tick_end,keyon,fnum,block,inst,vol\n')
            for ch in range(NUM_CH):
                for seg in segments[ch]:
                    fh.write(f'{ch},{seg.tick_start},{seg.tick_end},'
                             f'{seg.keyon},{seg.fnum},{seg.block},'
                             f'{seg.inst},{seg.vol}\n')

    mml_text = _generate_mml(segments, stem)
    mml_path = os.path.join(output_dir, f'{stem}.opll.mml')
    with open(mml_path, 'w', newline='\n') as fh:
        fh.write(mml_text)

    return mml_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <trace_opll_csv> [output_dir]")
        sys.exit(1)

    in_csv = sys.argv[1]
    if len(sys.argv) > 2:
        out_dir = sys.argv[2]
    else:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        base = os.path.basename(in_csv)
        root = os.path.splitext(os.path.splitext(base)[0])[0]
        if root.endswith('_trace'):
            s = root[:-len('_trace')]
        else:
            s = root
        out_dir = os.path.join(script_dir, 'outputs', s)

    result = process_opll_csv(in_csv, out_dir)
    print(f"Wrote {result}")
