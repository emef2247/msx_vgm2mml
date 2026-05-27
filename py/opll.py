"""
opll_mml.py - OPLL (YM2413) melody MML generator (EXTENDED)
Adds: dynamic NUM_CH, voice_id, rhythm columns, extended CSV output for MIDI/rendering.

Channels: dynamic (auto-detect from CSV, supports 6~9~)
"""

import sys
import os
import math
import csv
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import (
    estimate_mml_used, estimate_alloc, track_id_to_mgsdrv,
    compress_mml_text, get_mgs_note_token_pct, ticks_to_mml_length, get_ticks
)

from segment_utils import (
    _int, _Segment,pass0_read_csv,
    pass1_compute_l, pass1_dump_csv,
	pass2_compute_onsets_and_ioi,pass2_mark_legato_vibrato_portamento_envelope,pass2_expand_rhythm,pass2_compute_fl_kl_vl,pass2_dump_csv,
	pass3_merge_silent_rests,pass3_merge_retrigger_note,pass3_dump_csv,
	pass4_compute_beats,pass4_dump_csv,
)

CH_OFFSET = 9        # OPLL ch0 → MGSDRV track 9
_MML_MELODY_CHS = list(range(0, 6))       # ch 0-5 -> MGSDRV track 9-e

_FREQ_NTSC: float = 59.988527908187
_MML_RHYTHM_CHS = {9, 10, 11, 12, 13}     # RHYTHM_CH_MAP values
_MML_RHYTHM_TRACK = 15                     # MGSDRV track 'f'

# Trace CSV column indices (existing)
_COL_TYPE   = 0
_COL_TIME   = 1
_COL_CH     = 2
_COL_TICKS  = 3
_COL_KEYON  = 4
_COL_FNUM   = 5
_COL_BLOCK  = 6
_COL_INST   = 7
_COL_VOL    = 8
_COL_SUS    = 9 

# -----------------------------------------------------------------------------
# OPLL Fnum + Block → (octave, scale_name) conversion (for MS2, MIDI, MML等)
# -----------------------------------------------------------------------------
_SCALE_NAMES = ['c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b']

def _opll_note(fnum: int, block: int):
    """
    Return (octave, scale_name) for the given OPLL Fnum+Block pair.
    Returns ('r', 0) for invalid notes (fnum==0 or frequency out-of-range).
    """
    if fnum == 0:
        return 1, 'r'
    freq = 49716.0 * fnum * (1 << block) / (1 << 19)
    if freq < 16.0:
        return 1, 'r'
    midi = 69.0 + 12.0 * math.log2(freq / 440.0)
    midi_int = round(midi)
    octave = midi_int // 12 - 1
    octave = max(1, min(8, octave))
    scale_idx = midi_int % 12
    return octave, _SCALE_NAMES[scale_idx]
    
# -----------------------------------------------------------------------------
# Detect channel count
# -----------------------------------------------------------------------------
def detect_num_ch(trace_csv):
    max_ch = -1
    with open(trace_csv, "r") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.split(",")
            try:
                ch = int(parts[_COL_CH])
                if ch > max_ch:
                    max_ch = ch
            except Exception:
                continue
    return (max_ch + 1) if max_ch >= 0 else 9

# -----------------------------------------------------------------------------
# Rhythm state tracker
# -----------------------------------------------------------------------------
class RhythmState:
    def __init__(self):
        self.is_ryt = 0 # Rhythm mode ON/OFF
        self.bd     = 0
        self.sd     = 0
        self.tom    = 0
        self.tc     = 0
        self.hh     = 0
        self.last_tick = -1
    def update(self, regval, tick):
        self.is_ryt = (regval >> 5) & 1
        bits = regval & 0x1F
        self.bd  = (bits >> 0) & 1
        self.sd  = (bits >> 1) & 1
        self.tom = (bits >> 2) & 1
        self.tc  = (bits >> 3) & 1
        self.hh  = (bits >> 4) & 1
        self.last_tick = tick
    def as_tuple(self):
        return (self.is_ryt, self.bd, self.sd, self.tom, self.tc, self.hh)

def parse_opll_regs_for_rhythm(regs_csv_path):
    """
    _trace.opll_regs.csv から type=rhythm 行だけ抜き出して
    (tick, regval) のリストを返す
    """
    timeline = []
    with open(regs_csv_path, newline='') as f:
        for row in csv.reader(f):
            if not row or row[0].startswith('#') or len(row) < 5:
                continue
            if row[0] == 'rhythm':
                try:
                    tick = int(float(row[2]))
                    regval = int(row[4])
                    timeline.append((tick, regval))
                except Exception:
                    continue
    return timeline
    

# -----------------------------------------------------------------------------
# Build per-channel segment lists from the trace CSV - with dynamic NUM_CH
# -----------------------------------------------------------------------------

NUM_CH = 18  # ch=0~17

# rhythmチャンネル mapping
RHYTHM_CH_MAP = {
    "bd": 9,  # Bass Drum
    "sd": 10,  # Snare Drum
    "tom": 11, # Tom
    "tc": 12,  # Top Cymbal
    "hh": 13,  # Hi-Hat
}

RHYTHM_VOICE_ID_MAP = {
    "bd": 16,
    "sd": 17,
    "tom": 18,
    "tc": 19,
    "hh": 20,
}

NUM_CH = 18  # 0-8: OPLL, 13-17: Rhythm など
IMPLICIT_RETRIGGER_MIN_GAP = 2
IMPLICIT_RETRIGGER_MAX_GAP = 32
NUM_CH = 18

def _opll_vol_to_ms2(vol_opll: int) -> int:
   """
    OPLL vol: 0 (max) ... 15 (mute)
    MS2 file VOL: 0 (max) ... 63 (mute)  ← OPL4 TL 値そのまま
    """
   v = int(round(max(0, min(15, vol_opll)) * 63 / 15))
   return v

def _build_segments(trace_csv_path,
                    include_rhythm=True,
                    rhythm_reg_timeline=None,
                    ticks_per_step_override=None,
                    debug=False):
    # ------------------------------------------------------
    # vgmの情報 (trace_csv_path)からevent情報を作成
    # ------------------------------------------------------
    # pass0 : <stem>_trace.opll.csvをeventsに読み込む
    events = pass0_read_csv(trace_csv_path)

    # pass1 : ticksの差分から各eventのlを算出
    # Next eventのticks = ticks + l
    events = pass1_compute_l(events)
    if debug:
        pass1_dump_csv(events, trace_csv_path)

    # pass2 (1): fl, kl, vlの算出
    # fl : 同じfnumが継続する期間[ticks]
    # kl : 同じkeyonが継続する期間[ticks]
    # vl : 同じvolが継続する期間[ticks]
    # 但しこれらはkeyon 0->1でlと同じ値にリセットされる
    events = pass2_compute_fl_kl_vl(events)

    # type="rhythm", ch=-1のeventをRHYTHM_CH_MAP, RHYTHM_VOICE_ID_MAPをベースに展開
    events = pass2_expand_rhythm(events,RHYTHM_CH_MAP,RHYTHM_VOICE_ID_MAP)

    # onsetの検出とIOI(Inter‑Onset Interval:IOIの間隔)の算出, tempoの導出
    events = pass2_compute_onsets_and_ioi(events)

    # l=0を削除した後、fl,kl,blからlegato, vibrate, volume envelopeを判定
    events = pass2_mark_legato_vibrato_portamento_envelope(events)
    if debug:
        pass2_dump_csv(events, trace_csv_path)

    # 無音状態(v=15 又は keyon=0) の連続したeventをマージ
    events = pass3_merge_silent_rests(events)

    # retriggerのためのkeyoffを一つのeventにマージ
    events = pass3_merge_retrigger_note(events) 

    if debug:
        pass3_dump_csv(events, trace_csv_path)

    # beat, beat_posを算出
    # beatは最小の音価 (min_l)で正規化した単位。grid幅を示す
    # beat_pos は前のeventのbeatの累計。そのeventのスタート地点を表す
    events, min_l, min_ioi, mode_ioi, bpm, ticks_per_step = pass4_compute_beats(events)
    if debug:
        pass4_dump_csv(events, trace_csv_path)
        
    if ticks_per_step_override is not None:
        ticks_per_step = max(2, int(ticks_per_step_override))
        # override 時は ticks_per_step が16分音符長の代わりになるので
        # mode_ioi = ticks_per_step * 2 と見なして計算
        bpm = max(1, round(_FREQ_NTSC * 15 / (ticks_per_step * 2)))
        if debug:
            print(f"  bpm:{bpm} ticks_per_step:{ticks_per_step} (override) min_ioi:{min_ioi} mode_ioi:{mode_ioi}")
    else:
        if debug:
            print(f"  bpm:{bpm} ticks_per_step:{ticks_per_step} (auto, Nyquist) min_ioi:{min_ioi} mode_ioi:{mode_ioi}")

    # ------------------------------------------------------
    # pass4まで処理されたeventsをベースに_Segmentを生成する
    # ------------------------------------------------------
    events_by_ch = defaultdict(list)

    for ev in events:
        ev_type = ev.get("#type", "")
        ch = int(ev["ch"])
        is_ryt = _int(ev, "is_ryt", 0)

        # まず ch 範囲チェック（安全のため最初に）
        if ch < -1 or ch >= NUM_CH:
            continue

        # ------------------------------------------------------
        # 1. リズムイベント（0x0E の行）だけ特別扱い
        # ------------------------------------------------------
        if ev_type == "rhythm_expand":
            if is_ryt != 1:
                continue
            # ch は pass2_expand_rhythm によって RHYTHM_CH_MAP (9-13) に設定済み
            # keyon=1 のイベントのみ対象
            if _int(ev, "keyon", 0) != 1:
                continue
            events_by_ch[ch].append(ev)
            continue

        # ------------------------------------------------------
        # 2. メロディイベント（#type != rhythm）
        # ------------------------------------------------------
        # ch0〜5 → 常にメロディ
        if 0 <= ch <= 5:
            events_by_ch[ch].append(ev)
            continue

        # ------------------------------------------------------
        # 3. ch6〜8 の通常レジスタ書き込み
        # ------------------------------------------------------
        # rhythm_mode=1 のときは「イベントではない」
        if is_ryt == 1:
            continue

        # rhythm_mode=0 のときはメロディ扱い（VGM によっては使われる）
        if 6 <= ch <= 8:
            events_by_ch[ch].append(ev)
            continue

        # それ以外は無視
        continue

    # ticks でソート
    for ch in events_by_ch:
        events_by_ch[ch].sort(key=lambda e: int(e["ticks"]))

    segments_by_ch = {ch: [] for ch in range(NUM_CH)}
    for ch, evs in events_by_ch.items():
        prev_seg = None

        for ev in evs:
            ev_type = ev.get("#type", "")
            vol_opll = _int(ev, "vol", 15)
            is_ryt   = _int(ev, "is_ryt", 0)

            # --- イベント種別判定 ---
            is_rhythm_on = (ev_type == "rhythm") and (is_ryt == 1)
            is_melody_on = (ev_type != "rhythm") and (0 <= ch < NUM_CH)

            if not (is_melody_on or (include_rhythm and is_rhythm_on)):
                continue

            ms2_vol = _opll_vol_to_ms2(vol_opll)

            seg = _Segment(
                ev_type       = ev["#type"],
                time          = float(ev["time"]),
                ch            = _int(ev, "ch", 0),
                ticks         = _int(ev, "ticks", 0),
                onset         = _int(ev, "onset", 0),
                tempo         = _int(ev, "tempo", 0),
                ioi           = _int(ev, "ioi", 0),
                min_ioi       = min_ioi,
                mode_ioi      = mode_ioi,
                l             = _int(ev, "l", 0),
                fl            = _int(ev, "fl", 0),
                kl            = _int(ev, "kl", 0),
                vl            = _int(ev, "vl", 0),
                beat_pos      = _int(ev, "beat_pos", 0),
                beat          = _int(ev, "beat", 0),
                fb            = _int(ev, "fb", 0),
                kb            = _int(ev, "kb", 0),
                vb            = _int(ev, "vb", 0),
                keyon         = _int(ev, "keyon", 0),
                is_legato     = _int(ev, "is_legato", 0),
                is_vibrato    = _int(ev, "is_vibrato", 0),
                is_portamento = _int(ev, "is_portamento", 0),
                is_envelope   = _int(ev, "is_envelope", 0),
                fnum          = _int(ev, "fnum", 0),
                block         = _int(ev, "block", 0),
                inst          = _int(ev, "inst", 0),
                vol           = _int(ev, "vol", 0),
                sus           = _int(ev, "sus", 0),
                scale         = ev["scale"],
                is_ryt        = _int(ev, "is_ryt", 0),
                r_tempo       =  _int(ev, "r_tempo", 0),
                r_ioi         = _int(ev, "r_ioi", 0),
                r_mode_ioi    = _int(ev, "r_mode_ioi", 0),
                r_hh_ioi      = _int(ev, "r_hh_ioi", 0),
                r_hh_mode_ioi = _int(ev, "r_hh_mode_ioi", 0),
                bd            = _int(ev, "bd", 0),
                sd            = _int(ev, "sd", 0),
                tom           = _int(ev, "tom", 0),
                tc            = _int(ev, "tc", 0),
                hh            = _int(ev, "hh", 0),
                fnum_ch6      = _int(ev, "fnum_ch6", 0),
                vol_ch6       = _int(ev, "vol_ch6", 0),
                sus_ch6       = _int(ev, "sus_ch6", 0),
                block_ch6     = _int(ev, "block_ch6", 0),
                fnum_ch7      = _int(ev, "fnum_ch7", 0),
                vol_ch7       = _int(ev, "vol_ch7", 0),
                sus_ch7       = _int(ev, "sus_ch7", 0),
                block_ch7     = _int(ev, "block_ch7", 0),
                fnum_ch8      = _int(ev, "fnum_ch8", 0),
                vol_ch8       = _int(ev, "vol_ch8", 0),
                sus_ch8       = _int(ev, "sus_ch8", 0),
                block_ch8     = _int(ev, "block_ch8", 0),
            )
            seg.tick_start = _int(ev, "ticks", 0)
            seg.tick_end   = _int(ev, "ticks", 0) + _int(ev, "l", 0) 
            seg.beat_start = _int(ev, "beat_pos", 0)
            seg.beat_end   = _int(ev, "beat_pos", 0) + _int(ev, "beat", 0)
            seg.grid_sz    = 1
            seg.ms2_vol    = ms2_vol
            seg.ms2_len    = _int(ev, "l", 0)
            seg.min_l      = ticks_per_step
            seg.beat_sz    = min_l
            seg.grid_sz    = 1
            if prev_seg:
                seg.odiff = seg.block  - prev_seg.block
                seg.vdiff = seg.vol - prev_seg.vol
            else:
                seg.odiff = 0
                seg.vdiff = 0
            
            prev_seg = seg
            segments_by_ch[ch].append(seg)

    return segments_by_ch, bpm


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
    """
    Correct YM2413 user-patch decoder (0x00–0x07).
    Matches the official OPLL register map:

        00: M AM/VB/EG/KR/ML
        01: C AM/VB/EG/KR/ML
        02: M KL/TL
        03: C KL/DC/DM/FB
        04: M AR/DR
        05: C AR/DR
        06: M SL/RR
        07: C SL/RR
    """

    r = patch_bytes
    if len(r) < 8:
        r = bytes(r) + bytes(8 - len(r))

    # -------------------------
    # Modulator (M)
    # -------------------------
    m_mt =  r[0] & 0x0F
    m_kr = (r[0] >> 4) & 0x01
    m_eg = (r[0] >> 5) & 0x01
    m_vb = (r[0] >> 6) & 0x01
    m_am = (r[0] >> 7) & 0x01

    m_kl = (r[2] >> 6) & 0x03
    m_tl =  r[2] & 0x3F

    m_ar = (r[4] >> 4) & 0x0F
    m_dr =  r[4] & 0x0F

    m_sl = (r[6] >> 4) & 0x0F
    m_rr =  r[6] & 0x0F

    m_dt = 0   # OPLL has no DT

    # -------------------------
    # Carrier (C)
    # -------------------------
    c_mt =  r[1] & 0x0F
    c_kr = (r[1] >> 4) & 0x01
    c_eg = (r[1] >> 5) & 0x01
    c_vb = (r[1] >> 6) & 0x01
    c_am = (r[1] >> 7) & 0x01

    c_kl = (r[3] >> 6) & 0x03
    c_tl = 0   # carrier has no TL

    c_ar = (r[5] >> 4) & 0x0F
    c_dr =  r[5] & 0x0F

    c_sl = (r[7] >> 4) & 0x0F
    c_rr =  r[7] & 0x0F

    c_dt = 0   # OPLL has no DT

    # -------------------------
    # Feedback (FB)
    # -------------------------
    fb = (r[3] >> 1) & 0x07   # ★正しい FB

    return {
        'tl':  m_tl,
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


# -----------------------------------------------------------------------------
# Assign voice_id, at_token, etc to each segment
# -----------------------------------------------------------------------------

def _assign_voice_ids(segments: dict,
                      voice_csv_path: str | None) -> tuple[dict, dict, list[str]]:
    """Assign voice_id and at_token to every segment.

    Voice key definition:
      - inst != 0 : ('preset', inst)
      - inst == 0 : ('user', patch_bytes_tuple)  where patch_bytes is the
                    8-byte user patch current at the segment's beat_start.

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
    NUM_CH = max(segments.keys()) + 1
    # ── Read voice CSV ───────────────────────────────────────────
    # Build a sorted list of (tick, patch_bytes) for all 'patch' events.
    # These are global user-patch register updates (addr 0x00-0x07).
    patch_timeline: list[tuple[int, bytes]] = []   # (tick, patch_bytes)
    instVol_timeline_by_ch: dict[int, list[tuple[int, bytes]]] = {}

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
                elif vtype == 'instVol':
                    try:
                        ch = int(parts[_VCOL_CH])
                        inst = int(parts[_VCOL_INST])
                    except (ValueError, IndexError):
                        continue
                    if inst == 0:
                        if ch not in instVol_timeline_by_ch:
                            instVol_timeline_by_ch[ch] = []
                        instVol_timeline_by_ch[ch].append((ticks, patch_bytes))
                        has_patch_events = True
    # patch_timeline and instVol_timeline_by_ch are in chronological order
    # (voice CSV is ordered)

    def _get_patch_at_tick(tick: int) -> bytes:
        """Return the effective user patch at or before *tick* (global fallback)."""
        result = bytes(8)
        for t, p in patch_timeline:
            if t <= tick:
                result = p
            else:
                break
        return result

    def _get_patch_at_tick_for_ch(ch: int, tick: int) -> bytes:
        """Return the effective user patch for *ch* at or before *tick*.
        Uses per-channel instVol snapshots; falls back to global patch timeline."""
        timeline = instVol_timeline_by_ch.get(ch, [])
        result = bytes(8)
        for t, p in timeline:
            if t <= tick:
                result = p
            else:
                break
        # If no channel-specific data found, fall back to global patch timeline
        if result == bytes(8) and not timeline:
            result = _get_patch_at_tick(tick)
        return result

    # ── Assign voice IDs ─────────────────────────────────────────
    voice_table: dict[tuple, int] = {}   # voice_key -> voice_id (sequential, for CSV dump)
    next_id = 0

    # User-patch specific: map patch_bytes -> at_v_num (1-based) and
    # collect user_patches ordered dict for @vNN definition generation.
    user_patch_ids: dict[bytes, int] = {}   # patch_bytes -> at_v_num
    user_patches: dict[int, bytes]   = {}   # at_v_num -> patch_bytes
    next_user_v  = 15

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
        for seg in segments.get(ch, []):
            if seg.inst != 0:
                key = ('preset', seg.inst)
                seg.at_token = f'@{seg.inst}'
            else:
                if has_voice_csv:
                    patch = _get_patch_at_tick_for_ch(seg.ch, seg.tick_start)
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


def _collect_rhythm_segments(segments: dict) -> list:
    rhythm_segs = []
    for rch in sorted(_MML_RHYTHM_CHS):
        rhythm_segs.extend(segments.get(rch, []))
    rhythm_segs.sort(key=lambda s: s.ticks)
    return rhythm_segs


def _rhythm_scale(seg) -> str:
    tokens = []
    if getattr(seg, 'bd', 0) == 1:
        tokens.append('b')
    if getattr(seg, 'sd', 0) == 1:
        tokens.append('s')
    if getattr(seg, 'tom', 0) == 1:
        tokens.append('m')
    if getattr(seg, 'tc', 0) == 1:
        tokens.append('c')
    if getattr(seg, 'hh', 0) == 1:
        tokens.append('h')
    return ''.join(tokens) if tokens else 'r'


def _build_rhythm_mml_buffer(rhythm_segs: list, rhythm_track_id: str) -> list[str]:
    rhythm_mml_buffer: list[str] = [f'\n\n;ch{rhythm_track_id} start']
    l_cnt = 0
    note_cnt = 0
    mml = ''

    for seg in rhythm_segs:
        length = seg.tick_end - seg.tick_start
        if length <= 0:
            continue

        scale = _rhythm_scale(seg)
        remaining = length
        while remaining > 0:
            ltmp = min(remaining, 255)
            if note_cnt == 0:
                mml = f'\n{rhythm_track_id}'

            mml += f' {scale}%{ltmp}'
            l_cnt += ltmp
            remaining -= ltmp

            if remaining > 0:
                rhythm_mml_buffer.append(mml)
                mml = ''

        note_cnt += 1
        if note_cnt >= 8:
            rhythm_mml_buffer.append(mml)
            mml = ''
            rhythm_mml_buffer.append(f'\n;tick count: {l_cnt}\n')
            note_cnt = 0

    if mml:
        rhythm_mml_buffer.append(mml)
    rhythm_mml_buffer.append(f'\n;ch{rhythm_track_id} end: tick count: {l_cnt}\n')
    return rhythm_mml_buffer



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
    mml_buffer: dict[int, list] = {ch: [] for ch in _MML_MELODY_CHS}

    for ch in _MML_MELODY_CHS:
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        mml_buffer[ch].append(f'\n\n;ch{track_id} start')

        segs = segments.get(ch,[])
        if not segs:
            continue
        l_cnt   = 0
        o_stamp = 0
        v_stamp = -1
        at_stamp = ''
        is_first_group = True
        mml     = ''
        note_cnt = 0

        for seg_idx, seg in enumerate(segs):
            if ch >= 6 and getattr(seg, "is_ryt", 0) == 1:
                continue  
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

    rhythm_segs = _collect_rhythm_segments(segments)
    rhythm_mml_buffer: list[str] = []
    if rhythm_segs:
        rhythm_track_id = track_id_to_mgsdrv(_MML_RHYTHM_TRACK)
        rhythm_mml_buffer = _build_rhythm_mml_buffer(rhythm_segs, rhythm_track_id)

    # Build header
    tempo = 75 if raw_ticks else 225
    lines = []
    lines.append(';[name=opll]')
    lines.append('#opll_mode 1')
    lines.append(f'#tempo {tempo}')
    lines.append(f'#title {{ "{stem}"}}')
    for ch in _MML_MELODY_CHS:
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        used  = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {track_id}={alloc}')
    if rhythm_segs:
        rhythm_track_id = track_id_to_mgsdrv(_MML_RHYTHM_TRACK)
        used = estimate_mml_used(rhythm_mml_buffer)
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {rhythm_track_id}={alloc}')
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
    for ch in _MML_MELODY_CHS:
        for item in mml_buffer[ch]:
            body_parts.append(item)
    if rhythm_mml_buffer:
        for item in rhythm_mml_buffer:
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
    mml_buffer: dict[int, list] = {ch: [] for ch in _MML_MELODY_CHS}

    for ch in _MML_MELODY_CHS:
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        mml_buffer[ch].append(f'\n\n;ch{track_id} start')

        segs = segments.get(ch,[])
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

    rhythm_segs = _collect_rhythm_segments(segments)
    rhythm_mml_buffer: list[str] = []
    if rhythm_segs:
        rhythm_track_id = track_id_to_mgsdrv(_MML_RHYTHM_TRACK)
        rhythm_mml_buffer = _build_rhythm_mml_buffer(rhythm_segs, rhythm_track_id)

    # Build header
    lines = []
    lines.append(';[name=opll]')
    lines.append('#opll_mode 1')
    lines.append('#tempo 75')
    lines.append(f'#title {{ "{stem}"}}')
    for ch in _MML_MELODY_CHS:
        ch_num   = ch + CH_OFFSET
        track_id = track_id_to_mgsdrv(ch_num)
        used  = estimate_mml_used(mml_buffer[ch])
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {track_id}={alloc}')
    if rhythm_segs:
        rhythm_track_id = track_id_to_mgsdrv(_MML_RHYTHM_TRACK)
        used = estimate_mml_used(rhythm_mml_buffer)
        alloc = estimate_alloc(used)
        lines.append(f'#alloc {rhythm_track_id}={alloc}')
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
    for ch in _MML_MELODY_CHS:
        for item in mml_buffer[ch]:
            body_parts.append(item)
    if rhythm_mml_buffer:
        for item in rhythm_mml_buffer:
            body_parts.append(item)

    result = ''.join(body_parts)
    if not result.endswith('\n'):
        result += '\n'
    return result
              
# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------

def process_opll_csv(trace_path, output_dir, stem=None,
                     dump_passes=False, debug=True,
                     voice_csv_path=None, rhythm_reg_timeline=None):
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
        root = os.path.splitext(base)[0]
        stem = os.path.splitext(root)[0]
        if stem.endswith('_trace'):
            stem = stem[:-len('_trace')]
    os.makedirs(output_dir, exist_ok=True)
    # Build segments (tick-based final-state evaluation)
    segments_by_ch, _bpm = _build_segments(
        trace_path,
        include_rhythm=True,
        rhythm_reg_timeline=rhythm_reg_timeline,
    )
    
    # Assign voice IDs using the voice CSV (user-patch tracking)
    voice_table, user_patches, warnings = _assign_voice_ids(segments_by_ch, voice_csv_path)

    if dump_passes:
        # Emit a simple segment dump for debugging
        seg_path = os.path.join(output_dir, f'{stem}.opll.pass0.csv')
        with open(seg_path, 'w', newline='\n') as fh:
            fh.write('#ch,beat_start,beat_end,keyon,fnum,block,inst,vol,voice_id,at_token\n')
            # Dump all channels (melody 0-5 and rhythm 9-13) for full debug visibility.
            for ch in sorted(segments_by_ch):
                for seg in segments_by_ch[ch]:
                    fh.write(f'{ch},{seg.beat_start},{seg.beat_end},'
                             f'{seg.keyon},{seg.fnum},{seg.block},'
                             f'{seg.inst},{seg.vol},{seg.voice_id},{seg.at_token}\n')

    # ---- pass3.compress.MGS_pct.mml – always produced (merge source + non-debug output) ----
    simple_mgs_pct_text = _generate_mml_mgs_pct(segments_by_ch, stem,
                                                   voice_table=voice_table,
                                                   user_patches=user_patches,
                                                   warnings=warnings)
    compress_mgs_pct_path = os.path.join(output_dir, f'{stem}.opll.pass3.compress.MGS_pct.mml')
    with open(compress_mgs_pct_path, 'w', newline='\n') as fh:
        fh.write(compress_mml_text(simple_mgs_pct_text))

    if not debug:
        return compress_mgs_pct_path

    # ---- debug-only variants ----

    mml_text = _generate_mml(segments_by_ch, stem, voice_table=voice_table,
                              user_patches=user_patches, warnings=warnings)
    mml_path = os.path.join(output_dir, f'{stem}.opll.mml')
    with open(mml_path, 'w', newline='\n') as fh:
        fh.write(mml_text)

    # pass3.simple.mml – raw tick (%N) notation, #tempo 75
    simple_raw_text = _generate_mml_impl(segments_by_ch, stem, raw_ticks=True,
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

_COL_TYPE   = 0
_COL_TIME   = 1
def build_segments_trace_compatible(trace_path, NUM_CH=18,_COL_TYPE=0,_COL_TIME=1, _COL_CH=2, _COL_TICKS=3, _COL_KEYON=4, _COL_FNUM=5, _COL_BLOCK=6, _COL_INST=7, _COL_VOL=8):
    """
    旧バージョン風。メロディ部に限定/汎用化も可能
    """
    ch_events = {ch: [] for ch in range(NUM_CH)}
    with open(trace_path, 'r', newline='') as fh:
        for line in fh:
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 9:
                continue
            try:
                _type =  int(parts[_COL_TYPE])
                _time = int(parts[_COL_TIME])
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
                ch_events[ch].append((_type, time, ticks, keyon, fnum, block, inst, vol))
    segments = {ch: [] for ch in range(NUM_CH)}
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
            # 同tick内eventをまとめて終端状態を見る
            j = i
            while j < n and events[j][0] == tick:
                j += 1
            tick_has_keyoff = any(ev[1] == 0 for ev in events[i:j])
            for _, keyon, fnum, block, inst, vol in events[i:j]:
                state.keyon = keyon
                state.fnum  = fnum
                state.block = block
                state.inst  = inst
                state.vol   = vol
            if cur_seg is None:
                cur_seg = _Segment(tick, state.keyon, state.fnum, state.block,
                                   state.inst, state.vol)
            else:
                hidden_retrigger = (
                    cur_seg.keyon == 1 and tick_has_keyoff and state.keyon == 1
                )
                if hidden_retrigger:
                    cur_seg.beat_end = tick
                    segments[ch].append(cur_seg)
                    # ゼロ長keyoff
                    off_seg = _Segment(tick, 0, state.fnum, state.block,
                                       state.inst, state.vol)
                    off_seg.beat_end = tick
                    segments[ch].append(off_seg)
                    cur_seg = _Segment(tick, state.keyon, state.fnum,
                                       state.block, state.vol)
                else:
                    keyon_edge   = (state.keyon == 1 and cur_seg.keyon == 0)
                    keyoff_edge  = (state.keyon == 0 and cur_seg.keyon == 1)
                    pitch_change = (state.fnum != cur_seg.fnum or state.block != cur_seg.block) and state.keyon == 1
                    inst_change  = (state.inst != cur_seg.inst and state.keyon == 1)
                    vol_change   = (state.vol != cur_seg.vol   and state.keyon == 1)
                    if keyon_edge or keyoff_edge or pitch_change or inst_change or vol_change:
                        cur_seg.beat_end = tick
                        segments[ch].append(cur_seg)
                        cur_seg = _Segment(tick, state.keyon, state.fnum,
                                           state.block, state.inst, state.vol)
                    else:
                        cur_seg.beat_end = tick
            i = j
        if cur_seg is not None:
            segments[ch].append(cur_seg)
    return segments
