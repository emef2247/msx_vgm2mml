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


def ticks_to_mml_length_inherited(ticks, scale, default_len):
    """Like ticks_to_mml_length but apply B-rule length inheritance.

    Omits the length number from a note/rest token when it matches
    *default_len* (the current inherited default).  When the length
    differs it is written explicitly and becomes the new default.

    Returns a tuple ``(mml_str, new_default_len)``.

    Examples (scale='c', default_len=64):
        1 tick  → ('c', 64)          length 64 == default → omit
        4 ticks → ('c16', 16)        length 16 != default → write, update
        3 ticks → ('c32c64', 64)     32 written, then 64==32? no → 'c64', final default=64
    """
    parts = []
    remaining = ticks
    cur_default = default_len
    for tick_val, mml_len in _NOTE_LEN_TABLE:
        while remaining >= tick_val:
            if mml_len == cur_default:
                parts.append(scale)
            else:
                parts.append(f'{scale}{mml_len}')
                cur_default = mml_len
            remaining -= tick_val
    if not parts:
        return f'r64', default_len
    return ''.join(parts), cur_default


def apply_repeat_compression(tokens):
    """Find and apply ``[...]N`` compression to a list of MML token strings.

    Searches for the most space-saving exact repetition of a contiguous
    sub-sequence and replaces it with a single ``[...]N`` token.  The
    function recurses until no further saving is possible.

    Grammar is always ``[...]N`` (never ``N[...]``).
    Only applied when the compressed form is strictly shorter.

    Parameters
    ----------
    tokens : list[str]
        Whitespace-split MML tokens (must not include comment tokens).

    Returns
    -------
    list[str]
        Compressed token list (may be the same object if no compression
        was possible).
    """
    n = len(tokens)
    if n < 4:
        return tokens

    best = None  # (saving, start, sub_len, count)
    for sub_len in range(1, n // 2 + 1):
        for start in range(n - sub_len * 2 + 1):
            sub = tokens[start:start + sub_len]
            count = 1
            pos = start + sub_len
            while pos + sub_len <= n and tokens[pos:pos + sub_len] == sub:
                count += 1
                pos += sub_len

            if count >= 2:
                # Size: each token joined by a single space
                sub_size = sum(len(t) for t in sub) + (len(sub) - 1)
                orig_size = sub_size * count + (count - 1)
                compressed_token = '[' + ' '.join(sub) + ']' + str(count)
                compressed_size = len(compressed_token)
                saving = orig_size - compressed_size
                if saving > 0:
                    if best is None or saving > best[0]:
                        best = (saving, start, sub_len, count)

    if best is None:
        return tokens

    _, start, sub_len, count = best
    sub = tokens[start:start + sub_len]
    compressed_token = '[' + ' '.join(sub) + ']' + str(count)
    new_tokens = (tokens[:start]
                  + [compressed_token]
                  + tokens[start + sub_len * count:])
    return apply_repeat_compression(new_tokens)


def compress_mml_channel(items):
    """Apply ``[...]N`` compression to all comment-bounded blocks in a channel.

    Takes the list of MML buffer strings for a single channel, groups
    adjacent *content* items (those not starting with ``;`` after stripping
    leading newlines/whitespace) into blocks, applies
    :func:`apply_repeat_compression` to each block, and returns a new list
    where each compressed block is a single string.

    Comment items and empty items act as block boundaries and are
    preserved unchanged in the output.

    This handles both the SCC/OPLL pattern (one content item per 8-note
    group) and the PSG pattern (one content item per individual note).
    """
    result = []
    i = 0
    while i < len(items):
        item = items[i]
        stripped = item.lstrip('\n').lstrip()

        if stripped.startswith(';') or not stripped:
            result.append(item)
            i += 1
            continue

        # Collect all consecutive non-comment, non-empty items
        block_items = []
        while i < len(items):
            cur = items[i]
            cur_stripped = cur.lstrip('\n').lstrip()
            if cur_stripped.startswith(';') or not cur_stripped:
                break
            block_items.append(cur)
            i += 1

        # Join the block into one string (they share one MML line)
        block_text = ''.join(block_items)
        leading_newline = '\n' if block_text.startswith('\n') else ''
        body = block_text.lstrip('\n')
        tokens = body.split()

        if len(tokens) < 3:
            result.append(block_text)
            continue

        ch_token = tokens[0]
        content_tokens = tokens[1:]
        compressed = apply_repeat_compression(content_tokens)
        result.append(leading_newline + ch_token + ' ' + ' '.join(compressed))

    return result

