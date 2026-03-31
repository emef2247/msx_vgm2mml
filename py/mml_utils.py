"""
mml_utils.py - Port of mml_utils.tcl
Tone table and note/octave/scale conversion utilities for MSX PSG/SCC.
"""

import math

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
