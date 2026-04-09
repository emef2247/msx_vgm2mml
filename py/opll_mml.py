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
from mml_utils import (get_ticks, estimate_mml_used, estimate_alloc,
                       track_id_to_mgsdrv, ticks_to_mml_length,
                       compress_mml_text, get_mgs_octave_prefix,
                       get_mgs_vol_prefix, get_mgs_note_token_pct)

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
                 'inst', 'vol', 'voice_id', 'at_token')

    def __init__(self, tick_start, keyon, fnum, block, inst, vol):
        self.tick_start = tick_start
        self.tick_end   = tick_start   # will be updated
        self.keyon      = keyon
        self.fnum       = fnum
        self.block      = block
        self.inst       = inst
        self.vol        = vol
        self.voice_id   = 0    # assigned later by _assign_voice_ids
        self.at_token   = ''   # MML instrument token (e.g. '@5' or '@v1')

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
# Voice table: voice CSV columns
# ---------------------------------------------------------------------------

_VCOL_TYPE      = 0
_VCOL_TIME      = 1
_VCOL_CH        = 2
_VCOL_TICKS     = 3
_VCOL_INST      = 4
_VCOL_VOL       = 5
_VCOL_PATCH_HEX = 6

# Known OPLL preset voice names (inst 1..15; 0 = user defined)
_OPLL_PRESET_NAMES = [
    'User Defined',      # 0
    'Violin',            # 1
    'Guitar',            # 2
    'Piano',             # 3
    'Flute',             # 4
    'Clarinet',          # 5
    'Oboe',              # 6
    'Trumpet',           # 7
    'Organ',             # 8
    'Horn',              # 9
    'Synthesizer',       # 10
    'Harpsichord',       # 11
    'Vibraphone',        # 12
    'Synthesizer Bass',  # 13
    'Acoustic Bass',     # 14
    'Electric Guitar',   # 15
]


def _ym2413_patch_to_mgsdrv(patch_bytes: bytes) -> dict:
    """Decode YM2413 user patch registers (0x00–0x07) into MGSDRV ``@v`` parameters.

    YM2413 user-patch register layout
    ──────────────────────────────────
    R0: AM(7) PM/VIB(6) EG(5) KR(4) MULT(3:0)  – Modulator
    R1: KL(7:6) TL(5:0)                          – Modulator
    R2: AR(7:4) DR(3:0)                           – Modulator
    R3: SL(7:4) RR(3:0)                           – Modulator
    R4: AM(7) PM/VIB(6) EG(5) KR(4) MULT(3:0)  – Carrier
    R5: KL(7:6) DC(4) DM(3) FB(2:0)             – Carrier
    R6: AR(7:4) DR(3:0)                           – Carrier
    R7: SL(7:4) RR(3:0)                           – Carrier

    MGSDRV ``@v`` format
    ────────────────────
    ``@vNN = { TL, FB, mod_AR, mod_DR, ..., mod_DT, car_AR, car_DR, ..., car_DT }``

    Returns a dict with keys ``tl``, ``fb``, ``mod`` (11-tuple), ``car`` (11-tuple).
    Each operator tuple is: (AR, DR, SL, RR, KL, MT, AM, VB, EG, KR, DT).
    """
    r = patch_bytes
    if len(r) < 8:
        r = bytes(r) + bytes(8 - len(r))

    tl = r[1] & 0x3F
    fb = r[5] & 0x07

    # Modulator operator fields
    m_ar = (r[2] >> 4) & 0x0F
    m_dr =  r[2]       & 0x0F
    m_sl = (r[3] >> 4) & 0x0F
    m_rr =  r[3]       & 0x0F
    m_kl = (r[1] >> 6) & 0x03
    m_mt =  r[0]       & 0x0F
    m_am = (r[0] >> 7) & 0x01
    m_vb = (r[0] >> 6) & 0x01   # VB (vibrato/PM)
    m_eg = (r[0] >> 5) & 0x01   # EG type (sustain)
    m_kr = (r[0] >> 4) & 0x01   # key-scale rate
    m_dt = (r[5] >> 3) & 0x01   # DT: waveform (0=sine, 1=half-sine); DM in YM2413 R5

    # Carrier operator fields
    c_ar = (r[6] >> 4) & 0x0F
    c_dr =  r[6]       & 0x0F
    c_sl = (r[7] >> 4) & 0x0F
    c_rr =  r[7]       & 0x0F
    c_kl = (r[5] >> 6) & 0x03
    c_mt =  r[4]       & 0x0F
    c_am = (r[4] >> 7) & 0x01
    c_vb = (r[4] >> 6) & 0x01   # VB (vibrato/PM)
    c_eg = (r[4] >> 5) & 0x01   # EG type (sustain)
    c_kr = (r[4] >> 4) & 0x01   # key-scale rate
    c_dt = (r[5] >> 4) & 0x01   # DT: waveform (0=sine, 1=half-sine); DC in YM2413 R5

    return {
        'tl':  tl,
        'fb':  fb,
        'mod': (m_ar, m_dr, m_sl, m_rr, m_kl, m_mt, m_am, m_vb, m_eg, m_kr, m_dt),
        'car': (c_ar, c_dr, c_sl, c_rr, c_kl, c_mt, c_am, c_vb, c_eg, c_kr, c_dt),
    }


def _user_patch_mml_defs(user_patches: dict) -> list[str]:
    """Return MML lines for all ``@vNN = {...}`` user-patch definitions.

    *user_patches* maps ``at_v_num (int) → patch_bytes (bytes)``, ordered by
    ``at_v_num``.  Emits one definition block per entry with MGSDRV-style
    comments showing the field labels.
    """
    lines = []
    for at_v_num in sorted(user_patches):
        patch_bytes = user_patches[at_v_num]
        d = _ym2413_patch_to_mgsdrv(patch_bytes)
        tl, fb = d['tl'], d['fb']
        m = d['mod']
        c = d['car']
        lines.append(f'@v{at_v_num} = {{')
        lines.append(';       TL FB')
        lines.append(f'        {tl:2d}, {fb},')
        lines.append('; AR DR SL RR KL MT AM VB EG KR DT')
        m_vals = ', '.join(f'{x:2d}' for x in m)
        lines.append(f'  {m_vals},')
        c_vals = ', '.join(f'{x:2d}' for x in c)
        lines.append(f'  {c_vals} }}')
        lines.append('')
    return lines


def _assign_voice_ids(segments: dict,
                      voice_csv_path: str | None) -> tuple[dict, dict, list[str]]:
    """Assign voice_id and at_token to every segment.

    Voice key definition:
      - inst != 0 : ('preset', inst)
      - inst == 0 : ('user', patch_bytes_tuple)  where patch_bytes is the
                    8-byte user patch current at the segment's tick_start.

    For preset instruments, ``seg.at_token`` is set to ``'@{inst}'`` (e.g. ``'@5'``).
    For user patches, ``seg.at_token`` is set to ``'@v{N}'`` where N is a
    stable 1-based integer assigned per unique 8-byte patch content.

    When *voice_csv_path* is None or missing, falls back to treating inst=0 as
    an all-zero user patch (produces a ``@v1`` definition with all zeros).

    Returns:
        voice_table  : dict mapping voice_key -> voice_id (0-indexed, for CSV dumps)
        user_patches : dict mapping at_v_num (int) -> patch_bytes (bytes), ordered
                       by first encounter; used to generate ``@vNN = {...}`` blocks
        warnings     : list of warning strings for caller to emit as comments
    """
    warnings: list[str] = []

    # ── Read voice CSV ───────────────────────────────────────────
    # Build a sorted list of (tick, patch_bytes) for all 'patch' events.
    # These are global user-patch register updates (addr 0x00-0x07).
    patch_timeline: list[tuple[int, bytes]] = []   # (tick, patch_bytes)

    has_voice_csv = False
    has_patch_events = False
    if voice_csv_path and os.path.exists(voice_csv_path):
        has_voice_csv = True
        with open(voice_csv_path, 'r', newline='') as fh:
            for line in fh:
                line = line.rstrip('\r\n')
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if len(parts) < 7:
                    continue
                try:
                    vtype = parts[_VCOL_TYPE]
                    ticks = int(parts[_VCOL_TICKS])
                    patch_hex = parts[_VCOL_PATCH_HEX].strip()
                    patch_bytes = bytes(int(patch_hex[i:i+2], 16)
                                        for i in range(0, 16, 2))
                except (ValueError, IndexError):
                    continue
                if vtype == 'patch':
                    patch_timeline.append((ticks, patch_bytes))
                    has_patch_events = True
    # patch_timeline is already in chronological order (voice CSV is ordered)

    def _get_patch_at_tick(tick: int) -> bytes:
        """Return the effective user patch at or before *tick*."""
        result = bytes(8)
        for t, p in patch_timeline:
            if t <= tick:
                result = p
            else:
                break
        return result

    # ── Assign voice IDs ─────────────────────────────────────────
    voice_table: dict[tuple, int] = {}   # voice_key -> voice_id (sequential, for CSV dump)
    next_id = 0

    # User-patch specific: map patch_bytes -> at_v_num (1-based) and
    # collect user_patches ordered dict for @vNN definition generation.
    user_patch_ids: dict[bytes, int] = {}   # patch_bytes -> at_v_num
    user_patches: dict[int, bytes]   = {}   # at_v_num -> patch_bytes
    next_user_v  = 1

    def _get_voice_id(key: tuple) -> int:
        nonlocal next_id
        if key not in voice_table:
            voice_table[key] = next_id
            next_id += 1
        return voice_table[key]

    def _get_user_v_num(patch: bytes) -> int:
        nonlocal next_user_v
        if patch not in user_patch_ids:
            user_patch_ids[patch] = next_user_v
            user_patches[next_user_v] = patch
            next_user_v += 1
        return user_patch_ids[patch]

    warned_no_voice_csv = False
    warned_no_patch_events = False
    for ch in range(NUM_CH):
        for seg in segments[ch]:
            if seg.inst != 0:
                key = ('preset', seg.inst)
                seg.at_token = f'@{seg.inst}'
            else:
                if has_voice_csv:
                    patch = _get_patch_at_tick(seg.tick_start)
                    # Warn once if user patch registers were never written
                    if not has_patch_events and not warned_no_patch_events:
                        warnings.append(
                            '; NOTE: inst=0 used but no user patch registers '
                            '(0x00-0x07) were written; using all-zero patch')
                        warned_no_patch_events = True
                    key = ('user', patch)
                else:
                    # No voice CSV: treat inst=0 as unknown user patch (all zeros)
                    patch = bytes(8)
                    key = ('user', patch)
                    if not warned_no_voice_csv:
                        warnings.append(
                            '; WARNING: no voice CSV provided; '
                            'inst=0 user patches treated as all-zero')
                        warned_no_voice_csv = True
                user_v_num = _get_user_v_num(patch)
                seg.at_token = f'@{user_v_num}'

            seg.voice_id = _get_voice_id(key)

    return voice_table, user_patches, warnings


def _voice_table_comments(voice_table: dict) -> list[str]:
    """Return a list of MML comment lines describing the voice table."""
    if not voice_table:
        return []

    # Invert for display: voice_id -> voice_key
    inv = {vid: vk for vk, vid in voice_table.items()}
    lines = ['; === OPLL Voice Table ===']
    for vid in sorted(inv):
        vk = inv[vid]
        if vk[0] == 'preset':
            name = (_OPLL_PRESET_NAMES[vk[1]]
                    if vk[1] < len(_OPLL_PRESET_NAMES) else '?')
            lines.append(f';@voice {vid:02d} preset inst={vk[1]} ({name})')
        else:
            patch_hex = ''.join(f'{b:02x}' for b in vk[1])
            lines.append(f';@voice {vid:02d} user patch={patch_hex}')
    lines.append('; =========================')
    return lines


# ---------------------------------------------------------------------------
# MML generation
# ---------------------------------------------------------------------------

def _generate_mml_impl(segments: dict, stem: str, raw_ticks: bool = False,
                       voice_table: dict | None = None,
                       user_patches: dict | None = None,
                       warnings: list[str] | None = None) -> str:
    """Generate MGSDRV MML text from per-channel segment data.

    When *raw_ticks* is True, emit ``{scale}%{N}`` tick notation and use
    ``#tempo 75`` (pass3.simple.mml style).  When False (default), emit
    standard divisor notation with ``#tempo 225``.
    """
    mml_buffer: dict[int, list] = {ch: [] for ch in range(NUM_CH)}

    for ch in range(NUM_CH):
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        mml_buffer[ch].append(f'\n\n;ch{track_id} start')

        segs    = segments[ch]
        l_cnt   = 0
        o_stamp = 0
        v_stamp = -1
        at_stamp = ''
        is_first_group = True
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
                    at_token = seg.at_token
                    if is_first_group:
                        if raw_ticks:
                            mml = f'\n{track_id} {at_token} v{v}'
                        else:
                            mml = f'\n{track_id} {at_token} v{v} o{octave} l64'
                            o_stamp = octave
                        is_first_group = False
                    else:
                        mml = f'\n{track_id}'
                        if at_token != at_stamp:
                            mml += f' {at_token}'
                        if v != v_stamp:
                            mml += f' v{v}'
                    at_stamp = at_token
                    v_stamp  = v

                if seg.at_token != at_stamp and note_cnt != 0:
                    mml += f' {seg.at_token}'
                    at_stamp = seg.at_token

                if v != v_stamp and note_cnt != 0:
                    mml += f' v{v}'
                    v_stamp = v

                if scale != 'r' and octave != o_stamp:
                    mml += f' o{octave}'
                    o_stamp = octave

                if raw_ticks:
                    mml += f' {scale}%{ltmp}'
                else:
                    mml += f' {ticks_to_mml_length(ltmp, scale)}'
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

        mml_buffer[ch].append(f'\n;ch{track_id} end: tick count: {l_cnt}\n')

    # Build header
    tempo = 75 if raw_ticks else 225
    lines = []
    lines.append(';[name=opll]')
    lines.append('#opll_mode 1')
    lines.append(f'#tempo {tempo}')
    lines.append(f'#title {{ "{stem}"}}')
    for ch in range(NUM_CH):
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        used  = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {track_id}={alloc}')
    if user_patches:
        lines.append('')
        lines.extend(_user_patch_mml_defs(user_patches))
    if voice_table:
        lines.extend(_voice_table_comments(voice_table))
    if warnings:
        lines.extend(warnings)
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


def _generate_mml(segments: dict, stem: str,
                  voice_table: dict | None = None,
                  user_patches: dict | None = None,
                  warnings: list[str] | None = None) -> str:
    """Generate MGSDRV MML text from per-channel segment data."""
    return _generate_mml_impl(segments, stem, raw_ticks=False,
                              voice_table=voice_table, user_patches=user_patches,
                              warnings=warnings)


def _generate_mml_mgs_pct(segments: dict, stem: str,
                           voice_table: dict | None = None,
                           user_patches: dict | None = None,
                           warnings: list[str] | None = None) -> str:
    """Generate OPLL MML with MGS delta-token octave/volume and raw tick (%) lengths.

    Applies the same ``<``/``>``/``(``/``)`` delta-token logic as
    :func:`get_mgs_note_token_pct` (±3 threshold):  emits relative octave
    and volume changes when the difference fits in ±3, otherwise emits
    absolute ``oN``/``vN`` tokens.  Note lengths are encoded as
    ``{scale}%{N}`` (raw ticks).  Uses ``#tempo 75``.

    This is the OPLL equivalent of the PSG/SCC ``MGS_pct`` variants.
    """
    mml_buffer: dict[int, list] = {ch: [] for ch in range(NUM_CH)}

    for ch in range(NUM_CH):
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        mml_buffer[ch].append(f'\n\n;ch{track_id} start')

        segs    = segments[ch]
        l_cnt   = 0
        o_stamp = 0
        v_stamp = 0
        at_stamp = ''
        is_first_group = True
        mml     = ''
        note_cnt = 0

        for seg in segs:
            length = seg.tick_end - seg.tick_start
            if length <= 0:
                continue

            octave, scale = _opll_note(seg.fnum, seg.block)
            v   = seg.mml_vol()

            if not seg.keyon or seg.fnum == 0:
                scale = 'r'
                octave = o_stamp if o_stamp != 0 else 1

            remaining = length
            while remaining > 0:
                ltmp = min(remaining, 255)

                if note_cnt == 0:
                    at_token = seg.at_token
                    if is_first_group:
                        mml = f'\n{track_id} {at_token} v{v} o{octave}'
                        at_stamp = at_token
                        v_stamp  = v
                        o_stamp  = octave
                        is_first_group = False
                    else:
                        mml = f'\n{track_id}'
                        if at_token != at_stamp:
                            mml += f' {at_token}'
                            at_stamp = at_token
                        mml += f' v{v}'
                        v_stamp = v

                # Build note token with delta-token logic (cnt always 1 for OPLL)
                note = get_mgs_note_token_pct(
                    ltmp, v, v - v_stamp, scale, 1, octave, o_stamp, v_stamp)
                mml += ' ' + note
                l_cnt += ltmp

                o_stamp = octave
                v_stamp = v

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

        mml_buffer[ch].append(f'\n;ch{track_id} end: tick count: {l_cnt}\n')

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
    if user_patches:
        lines.append('')
        lines.extend(_user_patch_mml_defs(user_patches))
    if voice_table:
        lines.extend(_voice_table_comments(voice_table))
    if warnings:
        lines.extend(warnings)
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
                     dump_passes: bool = False, debug: bool = True,
                     voice_csv_path: str | None = None) -> str:
    """Run the OPLL MML generation pipeline.

    Args:
        trace_path     : path to ``*_trace.opll.csv``
        output_dir     : directory for output files
        stem           : base name for output files (e.g. ``"mysong"``).
                         When *None* the stem is derived from *trace_path*.
        dump_passes    : when True write a pass0 segment CSV for debugging
        debug          : when True (default) write all MML variant files; when
                         False write only the ``pass3.compress.MGS_pct.mml``.
        voice_csv_path : optional path to ``*_trace.opll_voice.csv`` produced
                         by :func:`vgm_reader.parse_vgm`.  When provided the
                         voice table is built from user-patch register data so
                         that inst=0 segments are correctly distinguished by
                         their patch bytes.  When *None* inst=0 is treated as
                         an all-zero user patch.

    Returns:
        path to the generated MML file (``*.opll.mml`` in debug mode, or
        ``*.opll.pass3.compress.MGS_pct.mml`` in non-debug mode).
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

    # Assign voice IDs using the voice CSV (user-patch tracking)
    voice_table, user_patches, warnings = _assign_voice_ids(segments, voice_csv_path)

    if dump_passes:
        # Emit a simple segment dump for debugging
        seg_path = os.path.join(output_dir, f'{stem}.opll.pass0.csv')
        with open(seg_path, 'w', newline='\n') as fh:
            fh.write('#ch,tick_start,tick_end,keyon,fnum,block,inst,vol,voice_id,at_token\n')
            for ch in range(NUM_CH):
                for seg in segments[ch]:
                    fh.write(f'{ch},{seg.tick_start},{seg.tick_end},'
                             f'{seg.keyon},{seg.fnum},{seg.block},'
                             f'{seg.inst},{seg.vol},{seg.voice_id},{seg.at_token}\n')

    # ---- pass3.compress.MGS_pct.mml – always produced (merge source + non-debug output) ----
    simple_mgs_pct_text = _generate_mml_mgs_pct(segments, stem,
                                                  voice_table=voice_table,
                                                  user_patches=user_patches,
                                                  warnings=warnings)
    compress_mgs_pct_path = os.path.join(output_dir, f'{stem}.opll.pass3.compress.MGS_pct.mml')
    with open(compress_mgs_pct_path, 'w', newline='\n') as fh:
        fh.write(compress_mml_text(simple_mgs_pct_text))

    if not debug:
        return compress_mgs_pct_path

    # ---- debug-only variants ----

    mml_text = _generate_mml(segments, stem, voice_table=voice_table,
                              user_patches=user_patches, warnings=warnings)
    mml_path = os.path.join(output_dir, f'{stem}.opll.mml')
    with open(mml_path, 'w', newline='\n') as fh:
        fh.write(mml_text)

    # pass3.simple.mml – raw tick (%N) notation, #tempo 75
    simple_raw_text = _generate_mml_impl(segments, stem, raw_ticks=True,
                                          voice_table=voice_table,
                                          user_patches=user_patches,
                                          warnings=warnings)
    simple_raw_path = os.path.join(output_dir, f'{stem}.opll.pass3.simple.mml')
    with open(simple_raw_path, 'w', newline='\n') as fh:
        fh.write(simple_raw_text)

    # pass3.simple.MGS.mml – same as primary .opll.mml
    simple_mgs_path = os.path.join(output_dir, f'{stem}.opll.pass3.simple.MGS.mml')
    with open(simple_mgs_path, 'w', newline='\n') as fh:
        fh.write(mml_text)

    # pass3.compress.MGS.mml – divisor notation with token-level RLE compression
    compress_path = os.path.join(output_dir, f'{stem}.opll.pass3.compress.MGS.mml')
    with open(compress_path, 'w', newline='\n') as fh:
        fh.write(compress_mml_text(mml_text))

    # pass3.simple.MGS_pct.mml – MGS delta-token, raw tick (%) lengths, #tempo 75
    simple_mgs_pct_path = os.path.join(output_dir, f'{stem}.opll.pass3.simple.MGS_pct.mml')
    with open(simple_mgs_pct_path, 'w', newline='\n') as fh:
        fh.write(simple_mgs_pct_text)

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

    # Optionally look for a companion voice CSV next to the trace CSV.
    # Trace CSV: {dir}/{stem}_trace.opll.csv
    # Voice CSV: {dir}/{stem}_trace.opll_voice.csv
    voice_csv = in_csv.replace('_trace.opll.csv', '_trace.opll_voice.csv')
    if voice_csv == in_csv or not os.path.exists(voice_csv):
        voice_csv = None

    result = process_opll_csv(in_csv, out_dir, voice_csv_path=voice_csv)
    print(f"Wrote {result}")
