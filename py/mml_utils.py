"""
mml_utils.py - Port of mml_utils.tcl
Tone table and note/octave/scale conversion utilities for MSX PSG/SCC.
"""

import math


def estimate_mml_used(items):
    """Estimate used bytes from a list of MML item strings.

    - Split each item into lines.
    - Ignore blank lines.
    - Ignore comment lines that start with ';' after optional whitespace.
    - For remaining lines, count non-whitespace characters.
    - Sum across the track.
    """
    used = 0
    for s in items:
        if not s:
            continue
        for line in s.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(';'):
                continue
            used += len(line.replace(' ', '').replace('\t', '').replace('\r', ''))
    return used


def estimate_alloc(used, overhead=32, ratio=0.15, min_margin=64, align=16):
    """Convert a used-byte estimate to an alloc value.

    alloc = used + overhead + max(min_margin, ceil(used * ratio))
    The result is aligned up to the nearest *align*-byte boundary.

    Defaults: overhead=32, ratio=0.15, min_margin=64, align=16.
    """
    margin = max(min_margin, math.ceil(used * ratio))
    alloc = used + overhead + margin
    if align and align > 1:
        alloc = ((alloc + (align - 1)) // align) * align
    return alloc


def track_id_to_mgsdrv(ch: int) -> str:
    """Convert a MGSDRV track number to its single-character track ID.

    MGSDRV track IDs are single characters:
      1-9  → '1'-'9'
      10   → 'a', 11 → 'b', ..., 17 → 'h'

    This matches the MGSDRV MML specification where the line-leading track
    designator must be exactly one character.
    """
    if 1 <= ch <= 9:
        return str(ch)
    if 10 <= ch <= 17:
        return chr(ord('a') + ch - 10)
    raise ValueError(f"Track number {ch} is outside the valid MGSDRV range 1-17")

# Register value -> tone string table (port of reg2tone dict in mml_utils.tcl)
REG2TONE = {
    3421: "o1c", 3228: "o1c+", 3047: "o1d", 2876: "o1d+", 2715: "o1e",
    2562: "o1f", 2419: "o1f+", 2283: "o1g", 2155: "o1g+", 2034: "o1a",
    1920: "o1a+", 1812: "o1b",
    1711: "o2c", 1614: "o2c+", 1524: "o2d", 1438: "o2d+", 1358: "o2e",
    1281: "o2f", 1210: "o2f+", 1142: "o2g", 1078: "o2g+", 1017: "o2a",
    960:  "o2a+", 906: "o2b",
    855: "o3c", 807: "o3c+", 762: "o3d", 719: "o3d+", 679: "o3e",
    641: "o3f", 605: "o3f+", 571: "o3g", 539: "o3g+", 509: "o3a",
    480: "o3a+", 453: "o3b",
    428: "o4c", 404: "o4c+", 381: "o4d", 360: "o4d+", 339: "o4e",
    320: "o4f", 302: "o4f+", 285: "o4g", 269: "o4g+", 254: "o4a",
    240: "o4a+", 227: "o4b",
    214: "o5c", 202: "o5c+", 190: "o5d", 180: "o5d+", 170: "o5e",
    160: "o5f", 151: "o5f+", 143: "o5g", 135: "o5g+", 127: "o5a",
    120: "o5a+", 113: "o5b",
    107: "o6c", 101: "o6c+", 95: "o6d", 90: "o6d+", 85: "o6e",
    80: "o6f", 76: "o6f+", 71: "o6g", 67: "o6g+", 64: "o6a",
    60: "o6a+", 57: "o6b",
    53: "o7c", 50: "o7c+", 48: "o7d", 45: "o7d+", 42: "o7e",
    40: "o7f", 38: "o7f+", 36: "o7g", 34: "o7g+", 32: "o7a",
    30: "o7a+", 28: "o7b",
    27: "o8c", 25: "o8c+", 24: "o8d", 22: "o8d+", 21: "o8e",
    20: "o8f", 19: "o8f+", 18: "o8g", 17: "o8g+", 16: "o8a",
    15: "o8a+", 14: "o8b",
    0: "rest",
}

# Sorted keys descending (for nearest-higher lookup)
_KEY_LIST_DESC = sorted(REG2TONE.keys(), reverse=True)


def get_tone(reg):
    """Get tone string for a register value (port of get_tone in mml_utils.tcl)."""
    reg = int(reg) if reg else 0
    if reg == 0:
        return "r"
    if reg in REG2TONE:
        return REG2TONE[reg]
    # Find nearest higher key
    key_stamp = 3421
    for key in _KEY_LIST_DESC:
        if key > reg:
            key_stamp = key
        else:
            return REG2TONE[key_stamp]
    return REG2TONE[key_stamp]


def get_octave(reg):
    """Get octave number for a register value."""
    reg = int(reg) if reg else 0
    tone = get_tone(reg)
    if tone == "r":
        return 1
    # tone is like "o3c+" - extract the digit after 'o'
    return int(tone[1])


def get_scale(reg):
    """Get scale (note letter) for a register value."""
    reg = int(reg) if reg else 0
    tone = get_tone(reg)
    if tone == "r":
        return "r"
    # tone is like "o3c+" - extract everything after the digit
    import re
    m = re.match(r'o\d+([a-z+]+)', tone)
    if m:
        return m.group(1)
    return "r"


def get_tone_frequency(reg16):
    """Get calculated frequency from register value."""
    if reg16 == 0:
        return int(111860.78125)
    return int(111860.78125 / reg16)


def get_ticks(time_s):
    """Convert time in seconds to ticks (60fps), with Tcl quirk: ticks==1 -> 0."""
    ticks = int(math.ceil(time_s * 60))
    if ticks == 1:
        ticks = 0
    return ticks


# Standard note lengths: (tick_count_per_note, mml_length_number)
# Assumes l64 base: 1 tick == one 64th note.
_NOTE_LEN_TABLE = [(64, 1), (32, 2), (16, 4), (8, 8), (4, 16), (2, 32), (1, 64)]


def ticks_to_mml_length(ticks, scale):
    """Convert a tick count to an MML note string (no '%' separator).

    Assumes *l64* as the default note length (1 tick == one 64th note).
    Decomposes *ticks* greedily into standard note lengths (1, 2, 4, 8, 16,
    32, 64) and concatenates them as tied same-pitch notes.

    Examples (scale='a'):
        1   → 'a64'
        2   → 'a32'
        4   → 'a16'
        3   → 'a32a64'
        64  → 'a1'
        128 → 'a1a1'
    """
    parts = []
    remaining = ticks
    for tick_val, mml_len in _NOTE_LEN_TABLE:
        while remaining >= tick_val:
            parts.append(f'{scale}{mml_len}')
            remaining -= tick_val
    if not parts:
        # ticks == 0: caller should ensure a positive tick count;
        # return a silent 64th note as a safe fallback.
        return f'r64'
    return ''.join(parts)


# ---------------------------------------------------------------------------
# MGS-format helpers (port of get_mml_MGS / get_volume_diff_in_mml in Tcl)
# ---------------------------------------------------------------------------

def mgs_length_to_str(scale: str, length: int) -> str:
    """Convert a tick length to an MGS-format note string.

    Uses the standard MGS length table:
        64 → note1,  48 → note2.,  32 → note2,  16 → note4,
        12 → note8., 8  → note8,   6  → note16., 4  → note16,
        3  → note32., 2 → note32,  1  → note (bare, no number)

    Unlike ``ticks_to_mml_length`` this never uses ``%ticks`` syntax.
    """
    result = ''
    body = scale
    while length > 0:
        if length >= 64:
            result += f'{body}1'
            length -= 64
        elif length >= 48:
            result += f'{body}2.'
            length -= 48
        elif length >= 32:
            result += f'{body}2'
            length -= 32
        elif length >= 16:
            result += f'{body}4'
            length -= 16
        elif length >= 12:
            result += f'{body}8.'
            length -= 12
        elif length >= 8:
            result += f'{body}8'
            length -= 8
        elif length >= 6:
            result += f'{body}16.'
            length -= 6
        elif length >= 4:
            result += f'{body}16'
            length -= 4
        elif length == 3:
            result += f'{body}32.'
            length -= 3
        elif length == 2:
            result += f'{body}32'
            length -= 2
        elif length == 1:
            result += body
            length -= 1
    return result


def get_mgs_octave_prefix(o: int, o_stamp: int) -> str:
    """Build the octave-adjustment prefix for an MGS note token.

    Uses ``<``/``>`` for differences of 1-3 octaves; ``o{N}`` for larger jumps.
    """
    o_diff = o - o_stamp
    if o_diff > 3 or o_diff < -3:
        return f'o{o}'
    if o_diff < 0:
        return '<' * abs(o_diff)
    if o_diff > 0:
        return '>' * o_diff
    return ''


def get_mgs_vol_prefix(v: int, v_diff: int, cnt: int, v_stamp: int) -> str:
    """Build the volume-adjustment prefix for an MGS note token.

    When cnt==1 the absolute difference ``v - v_stamp`` is used (matching
    Tcl's ``if {$cnt == 1} { set vDiff [expr {$v - $vStamp}] }``).

    Uses ``(``/``)`` for differences of 1-3; ``v{N}`` for larger jumps.
    '(' raises volume by 1 step, ')' lowers volume by 1 step.
    """
    if cnt == 1:
        v_diff = v - v_stamp
    if v_diff > 3 or v_diff < -3:
        return f'v{v}'
    if v_diff < 0:
        return '(' * abs(v_diff)
    if v_diff > 0:
        return ')' * v_diff
    return ''


def get_mgs_note_token(l: int, v: int, v_diff: int, scale: str, cnt: int,
                       o: int, o_stamp: int, v_stamp: int) -> str:
    """Generate a complete MGS-format note token.

    Combines octave prefix, volume prefix, and note body.
    When cnt > 1 wraps the body in ``[...]cnt``.

    Args:
        l       : tick length of the note
        v       : current volume (used when cnt==1 or |vDiff|>3)
        v_diff  : row-stored volume difference (used when cnt>1 and |vDiff|<=3)
        scale   : note letter (e.g. 'c', 'c+', 'r')
        cnt     : repeat count (>=1)
        o       : current octave
        o_stamp : previous octave (for diff encoding)
        v_stamp : previous volume (for diff encoding when cnt==1)

    Returns:
        MGS note token string.
    """
    o_prefix  = get_mgs_octave_prefix(o, o_stamp)
    vol_prefix = get_mgs_vol_prefix(v, v_diff, cnt, v_stamp)
    note_body = mgs_length_to_str(scale, l)
    body = vol_prefix + note_body
    if cnt > 1:
        return f'{o_prefix}[{body}]{cnt}'
    return f'{o_prefix}{body}'
