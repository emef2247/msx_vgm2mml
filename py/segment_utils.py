import sys
import os
import math
import csv
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from mml_utils import get_ticks

_FREQ_NTSC: float = 59.988527908187

# ---------------------------------------------------------------------------
# OPLL-specific helpers (independent of PSG mml_utils.get_scale)
# ---------------------------------------------------------------------------
_OPLL_SCALE_NAMES = ['c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b']

def _opll_scale(fnum: int, block: int) -> str:
    """Return scale name (e.g. 'c', 'c+', 'g') for an OPLL F-Number + Block pair.

    Uses the same formula as opll_mml._opll_note() to avoid a circular import.
    Returns 'r' for fnum==0 or out-of-range frequencies.
    """
    if fnum == 0:
        return 'r'
    freq = 49716.0 * fnum * (1 << block) / (1 << 19)
    if freq < 16.0:
        return 'r'
    midi_int = round(69.0 + 12.0 * math.log2(freq / 440.0))
    return _OPLL_SCALE_NAMES[midi_int % 12]


def _int(ev, key, default=0):
    """空文字列や欠損値を安全に int に変換するヘルパー"""
    v = ev.get(key, default)
    if v == '' or v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default

# -----------------------------------------------------------------------------
# Segment representation (with extended fields)
# -----------------------------------------------------------------------------
class _Segment:
    """
    Segment for one OPLL channel (melody + rhythm + retrigger + MS2 support)
    """

    __slots__ = (
        'ev_type',      # trace.csv type（fNumL / fNumH / keyBlk / vol / inst / rhythm)今のところレジスタアクセスの区別。意図としてはeventのタイプ
        'time',         # global time [s], そのeventが起きた時間
        'ch',           # チェンネル
        'ticks',        # 1 tick = 1/60s
        'tick_start',   # keyon=1区間の開始点 [tick]
        'tick_end',     # keyon=1区間の終了点 [tick]
        'tempo',        # BPM. 今のところ曲全体のBPM
        'onset',        #　keyon=1の開始点であることを示すマーカー 0:　keyon=1を維持又はkeyon=0 1: 1: keyon区間の開始 keyon: 0--> 1
        'ioi',          # IOI（Inter‑Onset Interval). keyon=1 区間の 実際の長さ（tick). keyon=1でioi=0はまだkeyonが継続中を表す(ioi未確定のためioi=0)
        'min_ioi',      # ioi の最小値 音符の最小長さ. tempo 計算の基準
        'mode_ioi',     # ioi の最繁値(mode) 
        'l',            # そのＳｅｇｍｅｎｔの長さ [tick] Next ticks = current ticks + l
        'fl',           # 同じfnumの継続期間 [tick] keyonのposedgeでlにリセット. fl > lはkeyoffを挟まずにfnumが変化していることを表す
        'kl',           # 同じkeyonの継続期間 [tick] keyonのposedgeでlにリセット. kl > lは_Segmentを跨いで同じkeyon状態が継続中であることを示す
        'vl',           # 同じvolの継続期間 [tick] keyonのposedgeでlにリセット. vl > lはkeyoffを挟まずにvolが変化していることを表す
        'min_l',        # min_l　vgmのイベントの最小区間　beat = l / min_l
        'beat_start',   # keyon=1の開始点 [beat]
        'beat_end',     # keyon=1の終了点 [beat]
        'beat_pos',     # _Segmentの開始 [beat] beat_pos = それまでのbeatの累計。 next beat_pos = beat_pos + beat
        'beat',         # vgmのイベントをmin_lで正規化した値。
        'fb',           # flのbeat換算 [beat] keyonのposedgeでbeatにリセット.　fb > beat はkeyoffを挟まずにfnumが変化していることを表す
        'kb',           # kbのbeat換算 [beat] keyonのposedgeでbeatにリセット.　kb > beat は同じkeyon状態が_Segmentを跨いで継続中であることを示す
        'vb',           # vlのbeat換算 [beat] keyonのposedgeでbeatにリセット.　vb > beat はkeyoffを挟まずにvolが変化していることを表す
        'keyon',        # keyonの状態
        'is_legato',    # 一つ前のeventがkeyon=1であり、keyon=0を挟まずkeyon=1が続いている場合に1となる(スラー、タイ)
        'is_vibrato',   # keyon=1区間内でkeyon=0を挟まずfnumが変化、但し同一scale(note)内での微小な変化
        'is_portamento', # keyon=1区間内でkeyon=0を挟まずscale(note)が変化
        'is_envelope',  # keyon=1区間内でkeyon=0を挟まずvolが変化
        'fnum',         # frequency
        'block',        # block, octave
        'inst',         # instrument no
        'vol',          # volume
        'sus',          # sustain
        'scale',        # scale
        'voice_id',     # voice id
        'odiff',        # 一つ前のSegmentとのblock(octave)の差分。　MML生成用
        'vdiff',        #　一つ前のSegmentとのvolumeの差分。　MML生成用
        'is_ryt',       # リズムモード 0: メロディモード 1:リズムモード  OPLL 0xEのD5の値が入る
        'r_tempo',      # リズムで計測したtempo
        'r_ioi',        # rhythm 全体の IOI [tick]
        'r_mode_ioi',   # rhythm の最頻 IOI [tick] (mode)
        'r_tempo',      # rhythm の BPM
        'r_hh_ioi',     # ハイハット専用 IOI [tick]
        'r_hh_mode_ioi', # ハイハットの最頻 IOI [tick] (mode)
        'bd',           # Bass  Drum エッジトリガ 1: ON 0: OFF
        'sd',           # Snare Drum エッジトリガ 1: ON 0: OFF
        'tom',          # Tom-tom    エッジトリ  1: ON 0: OFF
        'tc',           # Top Cymbal エッジトリ  1: ON 0: OFF
        'hh',           # High-Hat   エッジトリ  1: ON 0: OFF
        'fnum_ch6',     # リズムモード(ryt==1)時、参照用 ch6のfnum
        'vol_ch6',      # リズムモード(ryt==1)時、参照用 ch6のvol
        'sus_ch6',      # リズムモード(ryt==1)時、参照用 ch6のsus
        'block_ch6',    # リズムモード(ryt==1)時、参照用 ch6のblock
        'fnum_ch7',     # リズムモード(ryt==1)時、参照用 ch7のfnum
        'vol_ch7',      # リズムモード(ryt==1)時、参照用 ch7のvol
        'sus_ch7',      # リズムモード(ryt==1)時、参照用 ch7のsus
        'block_ch7',    # リズムモード(ryt==1)時、参照用 ch8のblock
        'fnum_ch8',     # リズムモード(ryt==1)時、参照用 ch8のfnum
        'vol_ch8',      # リズムモード(ryt==1)時、参照用 ch8のvol
        'sus_ch8',      # リズムモード(ryt==1)時、参照用 ch8のsus
        'block_ch8',    # リズムモード(ryt==1)時、参照用 ch8のblock
        'ms2_vol',      # ms2用volume (0: 最大 63: 無音)
        'ms2_len',      # MS2 の 1 グリッド（grid_sz beat）を何個並べるか
        'beat_sz',      # beatは何ticksか (== min_l)
        'grid_sz',      # 何分音符にするか
        'at_token',
    )

    def __init__(
        self,
        ev_type       ,
        time          ,
        ch            ,
        ticks         ,
        onset         ,
        tempo         ,
        ioi           ,
        min_ioi       ,
        mode_ioi      ,
        l             ,
        fl            ,
        kl            ,
        vl            ,
        beat_pos      ,
        beat          ,
        fb            ,
        kb            ,
        vb            ,
        keyon         ,
        is_legato     ,
        is_vibrato    ,
        is_portamento ,
        is_envelope   ,
        fnum          ,
        block         ,
        inst          ,
        vol           ,
        sus           ,
        scale         ,
        is_ryt        ,
        r_tempo       ,
        r_ioi         ,
        r_mode_ioi    ,
        r_hh_ioi      ,
        r_hh_mode_ioi ,
        bd            ,
        sd            ,
        tom           ,
        tc            ,
        hh            ,
        fnum_ch6      ,
        vol_ch6       ,
        sus_ch6       ,
        block_ch6     ,
        fnum_ch7      ,
        vol_ch7       ,
        sus_ch7       ,
        block_ch7     ,
        fnum_ch8      ,
        vol_ch8       ,
        sus_ch8       ,
        block_ch8     ,

    ):

        self.ev_type       = ev_type
        self.time          = time
        self.ch            = ch
        self.ticks         = ticks
        self.tick_start   = 0
        self.tick_end     = 0
        self.tempo         = tempo
        self.onset         = onset
        self.ioi           = ioi
        self.min_ioi       = min_ioi
        self.mode_ioi      = mode_ioi
        self.l             = l
        self.fl            = fl
        self.kl            = kl
        self.vl            = vl
        self.min_l         = 0
        self.beat_start    = 0
        self.beat_end      = 0
        self.beat_pos      = beat_pos
        self.beat          = beat
        self.fb            = fb
        self.kb            = kb
        self.vb            = vb
        self.keyon         = keyon
        self.is_legato     = is_legato
        self.is_vibrato    = is_vibrato
        self.is_portamento = is_portamento
        self.is_envelope   = is_envelope
        self.fnum          = fnum
        self.block         = block
        self.inst          = inst
        self.vol           = vol
        self.sus           = sus
        self.scale         = scale
        self.voice_id      = -1
        self.odiff         = 0
        self.vdiff         = 0
        self.is_ryt        = is_ryt
        self.r_tempo       = r_tempo
        self.r_ioi         = r_ioi
        self.r_mode_ioi    = r_mode_ioi
        self.r_tempo       = 0
        self.r_hh_ioi      = r_hh_ioi
        self.r_hh_mode_ioi = r_hh_mode_ioi
        self.bd            = bd
        self.sd            = sd
        self.tom           = tom
        self.tc            = tc
        self.hh            = hh
        self.fnum_ch6      = fnum_ch6
        self.vol_ch6       = vol_ch6
        self.sus_ch6       = sus_ch6
        self.block_ch6     = block_ch6
        self.fnum_ch7      = fnum_ch7
        self.vol_ch7       = vol_ch7
        self.sus_ch7       = sus_ch7
        self.block_ch7     = block_ch7
        self.fnum_ch8      = fnum_ch8
        self.vol_ch8       = vol_ch8
        self.sus_ch8       = sus_ch8
        self.block_ch8     = block_ch8
        self.ms2_vol       = 0
        self.ms2_len       = 0
        self.beat_sz       = 0
        self.grid_sz       = 0
        self.at_token      = ''

    def mml_vol(self):
        return 15 - self.vol

def pass0_read_csv(trace_csv_path):
    """
    PASS 0:
      CSV の行をそのまま event として読み込む。
      ticks, keyon, fnum, block, inst, vol, sus などは CSV のまま保持する。
      l, fl, kl はまだ空欄のまま。
    """
    events = []

    with open(trace_csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('#type', '').startswith('#'):
                continue

            # row をそのまま event として保持
            events.append(row)

    return events

def pass1_compute_l(events):
    """
    PASS 1 (l: ticksの差分から導出‘)
      - ch ごとに ticks 昇順で並べる
      - l = next_ticks - ticks
      - fl, kl はまだ計算しない（0 のまま）
    """

    def _ival(v, default=0):
        if v is None or v == "":
            return default
        try:
            return int(v)
        except:
            return default

    # ch ごとにグループ化
    ch_events = defaultdict(list)
    for ev in events:
        ch = _ival(ev.get("ch"), -1)
        ch_events[ch].append(ev)

    # 各 ch ごとに処理
    for ch, buf in ch_events.items():
        # ticks 昇順にソート（念のため）
        buf.sort(key=lambda e: _ival(e.get("ticks")))
        n = len(buf)

        for i, ev in enumerate(buf):
            tick = _ival(ev.get("ticks"))

            if i + 1 < n:
                next_tick = _ival(buf[i+1].get("ticks"))
                ev["l"] = next_tick - tick
            else:
                ev["l"] = 0  # 最後の行

            # fl, kl はとりあえず 0 に固定
            ev["fl"] = _ival(ev.get("fl"), 0)
            ev["kl"] = _ival(ev.get("kl"), 0)

    return events

def pass1_dump_csv(events, trace_csv_path):
    base, ext = os.path.splitext(trace_csv_path)
    out_csv_path = base + ".pass1.csv"

    fieldnames = list(events[0].keys())

    with open(out_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ev in events:
            writer.writerow(ev)

    print(f"[PASS1] Debug CSV written: {out_csv_path}")

def pass2_compute_onsets_and_ioi(events):

    def _ival(v, default=0):
        if v is None or v == "":
            return default

        try:
            return int(v)
        except:
            return default

    from statistics import mode, median

    # ------------------------------------------------------------
    # 1. scale をセット
    # ------------------------------------------------------------
    for ev in events:

        fnum = _ival(ev.get("fnum"))
        block = _ival(ev.get("block"))
        ev["scale"] = _opll_scale(fnum, block)

    # ------------------------------------------------------------
    # 2. melody onset / ioi
    # ------------------------------------------------------------
    events_by_ch = {}

    for idx, ev in enumerate(events):

        if ev.get("#type") == "rhythm_expand":
            continue

        ch = _ival(ev.get("ch"))
        events_by_ch.setdefault(ch, []).append((idx, ev))

    for ch, lst in events_by_ch.items():

        lst.sort(key=lambda x: _ival(x[1].get("ticks")))

        prev_keyon = 0
        prev_vol   = 15

        # --------------------------------------------------------
        # onset
        # --------------------------------------------------------
        for i in range(len(lst)):

            idx, ev = lst[i]

            keyon = _ival(ev.get("keyon"))
            vol   = _ival(ev.get("vol"))

            if ev.get("#type") == "rhythm":

                ev["onset"] = 0

            else:

                is_onset = False

                if prev_keyon == 0 and keyon == 1 and vol < 15:
                    is_onset = True

                elif prev_keyon == 1 and keyon == 1 and prev_vol == 15 and vol < 15:
                    is_onset = True

                ev["onset"] = 1 if is_onset else 0

            prev_keyon = keyon
            prev_vol   = vol

        # --------------------------------------------------------
        # ioi
        # --------------------------------------------------------
        total_l = 0

        for i in range(len(lst)):

            idx, ev = lst[i]

            keyon = _ival(ev.get("keyon"))
            vol   = _ival(ev.get("vol"))
            l     = _ival(ev.get("l"))

            if vol == 15 or ev.get("#type") == "rhythm" or keyon == 0:

                total_l = 0
                ev["ioi"] = 0
                continue

            if ev["onset"] == 1:
                total_l = l
            else:
                total_l += l

            if i + 1 < len(lst):

                next_ev = lst[i + 1][1]

                next_keyon = _ival(next_ev.get("keyon"))
                next_vol   = _ival(next_ev.get("vol"))

                if next_keyon == 0 or next_vol == 15:

                    ev["ioi"] = total_l
                    total_l = 0

                else:

                    ev["ioi"] = 0

            else:

                ev["ioi"] = total_l
                total_l = 0

    # ------------------------------------------------------------
    # 3. rhythm_expand onset / r_ioi
    # ------------------------------------------------------------
    rhythm_expand_by_ch = {}

    for idx, ev in enumerate(events):

        if ev.get("#type") != "rhythm_expand":
            continue

        ch = _ival(ev.get("ch"))
        rhythm_expand_by_ch.setdefault(ch, []).append((idx, ev))

    for ch, lst in rhythm_expand_by_ch.items():

        lst.sort(key=lambda x: _ival(x[1].get("ticks")))

        # --------------------------------------------------------
        # onset
        # --------------------------------------------------------
        for idx, ev in lst:

            keyon = _ival(ev.get("keyon"))

            # posedge 済みなので keyon=1 が onset
            ev["onset"] = 1 if keyon == 1 else 0

        # --------------------------------------------------------
        # r_ioi
        # --------------------------------------------------------
        total_l = 0

        for i in range(len(lst)):

            idx, ev = lst[i]

            l      = _ival(ev.get("l"))
            onset  = _ival(ev.get("onset"))
            keyon  = _ival(ev.get("keyon"))

            # l=0 は timing edge のみ
            if l <= 0:

                ev["r_ioi"] = 0
                continue

            if onset == 1:
                total_l = l
            else:
                total_l += l

            # ----------------------------------------------------
            # 次 onset で確定
            # ----------------------------------------------------
            if i + 1 < len(lst):

                next_ev = lst[i + 1][1]

                next_keyon = _ival(next_ev.get("keyon"))

                if next_keyon == 1:

                    ev["r_ioi"] = total_l
                    total_l = 0

                else:

                    ev["r_ioi"] = 0

            else:

                ev["r_ioi"] = total_l
                total_l = 0

    # ------------------------------------------------------------
    # 4. rhythm HH interval
    # ------------------------------------------------------------
    _r_hh_ioi = 0

    for ev in events:

        if ev.get("#type") != "rhythm":
            continue

        l  = _ival(ev.get("l"))
        hh = _ival(ev.get("hh"))

        if l == 0:
            continue

        _r_hh_ioi += l

        if hh == 1:

            ev["r_hh_ioi"] = _r_hh_ioi
            _r_hh_ioi = 0

        else:

            ev["r_hh_ioi"] = 0

    # ------------------------------------------------------------
    # 5. global rhythm statistics
    # ------------------------------------------------------------
    r_ioi_list = [
        _ival(ev.get("r_ioi"))
        for ev in events
        if ev.get("#type") == "rhythm_expand"
        and _ival(ev.get("r_ioi")) > 0
    ]

    r_hh_ioi_list = [
        _ival(ev.get("r_hh_ioi"))
        for ev in events
        if ev.get("#type") == "rhythm"
        and _ival(ev.get("r_hh_ioi")) > 0
    ]

    # ------------------------------------------------------------
    # helper
    # ------------------------------------------------------------
    def pick_mode(lst):

        if not lst:
            return 0

        try:
            return mode(lst)

        except:

            return int(median(lst))

    # ------------------------------------------------------------
    # statistics
    # ------------------------------------------------------------
    r_mode_ioi    = pick_mode(r_ioi_list)
    r_hh_mode_ioi = pick_mode(r_hh_ioi_list)

    r_tempo = 3600.0 / r_mode_ioi if r_mode_ioi > 0 else 0.0

    # ------------------------------------------------------------
    # broadcast
    # ------------------------------------------------------------
    for ev in events:

        ev["r_mode_ioi"]    = r_mode_ioi
        ev["r_hh_mode_ioi"] = r_hh_mode_ioi
        ev["r_tempo"]       = r_tempo

    return events
    
def pass2_mark_legato_vibrato_portamento_envelope(events):

    def _ival(v, default=0):
        try:
            return int(v)
        except:
            return default

    # ------------------------------------------------------------
    # 1. ch ごとにイベントを分離し、ticks でソート
    # ------------------------------------------------------------
    events_by_ch = {}
    for ev in events:
        ch = _ival(ev.get("ch"))
        events_by_ch.setdefault(ch, []).append(ev)

    for ch, lst in events_by_ch.items():
        lst.sort(key=lambda ev: _ival(ev.get("ticks")))

        prev_keyon = 0
        prev_fnum  = 0
        prev_vol   = 0
        prev_scale = ''

        # --------------------------------------------------------
        # 2. 各 ch 内で legato / vibrato / vol_envelope を判定
        # --------------------------------------------------------
        for ev in lst:

            if ev.get("#type") == "rhythm":
                ev["is_legato"] = 0
                ev["is_vibrato"] = 0
                ev["is_portamento"] = 0
                ev["is_envelope"] = 0
                continue

            keyon = _ival(ev.get("keyon"))
            fnum  = _ival(ev.get("fnum"))
            scale = _ival(ev.get("scale"))
            vol   = _ival(ev.get("vol"))

            l  = _ival(ev.get("l"))
            kl = _ival(ev.get("kl"))
            fl = _ival(ev.get("fl"))
            vl = _ival(ev.get("vl"))

            # keyon posedge → NOTE_ON → legato=0
            if prev_keyon == 0 and keyon == 1:
                ev["is_legato"] = 0

            # legato 条件：prev_keyon=1 かつ kl > l
            elif prev_keyon == 1 and kl > l:
                ev["is_legato"] = 1

            else:
                ev["is_legato"] = 0

            # vibrato / vol envelope は legato のときだけ
            ev["is_portamento"] = 1 if (ev["is_legato"] == 1 and prev_scale != scale) else 0
            ev["is_vibrato"] = 1 if (ev["is_legato"] == 1 and ev["is_portamento"] == 0 and prev_fnum != fnum) else 0
            ev["is_envelope"] = 1 if (ev["is_legato"] == 1 and prev_vol != vol) else 0

            prev_keyon = keyon
            prev_fnum  = fnum
            prev_vol   = vol
            prev_scale = scale

    # ------------------------------------------------------------
    # 3. 全 ch を結合して返す
    # ------------------------------------------------------------
    merged = []
    for ch in sorted(events_by_ch.keys()):
        merged.extend(events_by_ch[ch])

    return merged

def pass2_expand_rhythm(events, RHYTHM_CH_MAP, RHYTHM_VOICE_ID_MAP):
    """
    OPLL rhythm event を
    MS2 用 melody channel event に展開する。

    YM2413 rhythm bits (D0-D4) は
    posedge sensitive なので、

        0 -> 1

    の瞬間のみ keyon=1 を生成する。

    l=0 event を保持している前提なので、
    同一bitが連続して1になるケースでは
    keyonは再生成されない。
    """

    def _ival(v, default=0):
        if v is None or v == "":
            return default

        try:
            return int(v)
        except:
            return default

    new_events = []

    # ------------------------------------------------------------
    # 前回 rhythm bit 状態
    # ------------------------------------------------------------
    prev_state = {
        "bd":  0,
        "sd":  0,
        "tom": 0,
        "tc":  0,
        "hh":  0,
    }

    RHY_KEYS = ["bd", "sd", "tom", "tc", "hh"]

    # ------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------
    for ev in events:

        ev_type = ev.get("#type", "")
        ch      = _ival(ev.get("ch"))
        is_ryt  = _ival(ev.get("is_ryt"))

        # --------------------------------------------------------
        # rhythm 以外
        # --------------------------------------------------------
        if not ((ev_type == "rhythm") or (ch == -1 and is_ryt == 1)):
            new_events.append(ev)
            continue

        # --------------------------------------------------------
        # rhythm を 5 channel に展開
        # --------------------------------------------------------
        for key in RHY_KEYS:

            current  = _ival(ev.get(key))
            previous = prev_state[key]

            # ----------------------------------------------------
            # posedge detection
            # ----------------------------------------------------
            # 0 -> 1 の瞬間のみ keyon
            # ----------------------------------------------------
            keyonX = 1 if (previous == 0 and current == 1) else 0

            # 状態更新
            prev_state[key] = current

            # ----------------------------------------------------
            # channel mapping
            # ----------------------------------------------------
            ch_new = RHYTHM_CH_MAP[key]

            # ----------------------------------------------------
            # parameter extraction
            # ----------------------------------------------------
            if key == "bd":

                fnumX  = _ival(ev.get("fnum_ch6"))
                volX   = _ival(ev.get("bd_vol"))
                susX   = _ival(ev.get("sus_ch6"))
                blockX = _ival(ev.get("block_ch6"))

            elif key == "sd":

                fnumX  = _ival(ev.get("fnum_ch7"))
                volX   = _ival(ev.get("sd_vol"))
                susX   = _ival(ev.get("sus_ch7"))
                blockX = _ival(ev.get("block_ch7"))

            elif key == "tom":

                fnumX  = _ival(ev.get("fnum_ch8"))
                volX   = _ival(ev.get("tom_vol"))
                susX   = _ival(ev.get("sus_ch8"))
                blockX = _ival(ev.get("block_ch8"))

            elif key == "tc":

                fnumX  = _ival(ev.get("fnum_ch8"))
                volX   = _ival(ev.get("tc_vol"))
                susX   = _ival(ev.get("sus_ch8"))
                blockX = _ival(ev.get("block_ch8"))

            elif key == "hh":

                fnumX  = _ival(ev.get("fnum_ch8"))
                volX   = _ival(ev.get("hh_vol"))
                susX   = _ival(ev.get("sus_ch8"))
                blockX = _ival(ev.get("block_ch8"))

            # ----------------------------------------------------
            # new event
            # ----------------------------------------------------
            ev_new = dict(ev)

            # channel
            ev_new["ch"] = ch_new

            # keyon (posedge only)
            ev_new["keyon"] = keyonX

            # note params
            ev_new["fnum"]  = fnumX
            ev_new["block"] = blockX

            # rhythm -> dedicated MS2 voice
            ev_new["inst"]  = RHYTHM_VOICE_ID_MAP[key]

            # volume/sustain
            ev_new["vol"]   = volX
            ev_new["sus"]   = susX

            # type clarification
            ev_new["#type"] = "rhythm_expand"

            new_events.append(ev_new)

    return new_events

def pass2_compute_fl_kl_vl(events):
    """
    PASS2（レガート完全対応版）

      - keyon=0 または keyon=1 の最初のイベントは fl/kl/vl = l にセット
      - keyon=1 が続き、かつ fnum/block/inst/vol が同じならレガート継続として fl/kl/vl += l
      - ピッチ/音色/音量が変わったら fl/kl/vl = l（新しい音符）
      - keyon=1 かつ l==0 の行は「長さを持たない制御イベント」として fl/kl/vl を変えない
    """

    from collections import defaultdict

    def _ival(v, default=0):
        if v is None or v == "":
            return default
        try:
            return int(v)
        except:
            return default

    ch_events = defaultdict(list)
    for ev in events:
        ch_events[_ival(ev.get("ch"), -1)].append(ev)

    for ch, buf in ch_events.items():
        buf.sort(key=lambda e: _ival(e.get("ticks")))

        fnum_prev  = None
        block_prev = None
        inst_prev  = None
        vol_prev   = None
        keyon_prev = 0

        fl_acc = 0
        kl_acc = 0
        vl_acc = 0

        for ev in buf:
            l     = _ival(ev.get("l"))
            fnum  = _ival(ev.get("fnum"))
            block = _ival(ev.get("block"))
            inst  = _ival(ev.get("inst"))
            vol   = _ival(ev.get("vol"))
            keyon = _ival(ev.get("keyon"))

            # --- keyon=0: 音符が終わった区間 ---
            if keyon == 0:
                fl_acc = l
                kl_acc = l
                vl_acc = l

                ev["fl"] = fl_acc
                ev["kl"] = kl_acc
                ev["vl"] = vl_acc

                keyon_prev = 0
                fnum_prev  = fnum
                block_prev = block
                inst_prev  = inst
                vol_prev   = vol
                continue

            # --- keyon=1 かつ l==0: 制御イベント（長さなし） ---
            if keyon == 1 and l == 0:
                ev["fl"] = fl_acc
                ev["kl"] = kl_acc
                ev["vl"] = vl_acc

                keyon_prev = 1
                fnum_prev  = fnum
                block_prev = block
                inst_prev  = inst
                vol_prev   = vol
                continue

            # --- keyon=1 かつ l>0: 実際の音価 ---
            if keyon_prev == 0:
                # 新しい音符
                fl_acc = l
                kl_acc = l
                vl_acc = l
            else:
                # keyon_prev == 1 → 音が続いている
                same_pitch = (fnum == fnum_prev and block == block_prev)
                same_tone  = (inst == inst_prev)
                same_vol   = (vol == vol_prev)

                if same_pitch and same_tone and same_vol:
                    # ★ レガート継続
                    fl_acc += l
                    kl_acc += l
                    vl_acc += l
                else:
                    # ピッチ/音色/音量が変わった → 新しい音符
                    fl_acc = l
                    kl_acc = l
                    vl_acc = l

            ev["fl"] = fl_acc
            ev["kl"] = kl_acc
            ev["vl"] = vl_acc

            keyon_prev = 1
            fnum_prev  = fnum
            block_prev = block
            inst_prev  = inst
            vol_prev   = vol

    return events

def pass2_dump_csv(events, trace_csv_path):
    """
    PASS 2:
      l=0 event を吸収して削除する。
      time, ticks, l, fl, kl は前の event の値を維持。
      fnum, block, inst, vol, sus などのレジスタ値は l=0 event の値で上書き。
    """

    if not events:
        return

    # 元ファイル名: <stem>_trace.opll.csv
    base, ext = os.path.splitext(trace_csv_path)
    # 出力ファイル名: <stem>_trace.opll.pass1.csv
    out_csv_path = base + ".pass2.csv"

    fieldnames = list(events[0].keys())

    with open(out_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ev in events:
            writer.writerow(ev)

    print(f"[PASS2] Debug CSV written: {out_csv_path}")

def pass3_merge_silent_rests(events):
    """
    PASS3:
      - retrigger を除外しつつ休符をマージ
      - ただし rhythm(ch=-1) は絶対にマージしない（そのまま残す）
    """

    from collections import defaultdict

    def _ival(v, default=0):
        if v is None or v == "":
            return default
        try:
            return int(v)
        except:
            return default

    # tick_start / tick_end を準備
    for ev in events:
        ev["ticks"] = _ival(ev.get("ticks"))
        ev["l"]     = _ival(ev.get("l"))
        ev["tick_start"] = ev["ticks"]
        ev["tick_end"]   = ev["ticks"] + ev["l"]

    # --- rhythm は絶対にマージしない ---
    def is_rhythm(ev):
        return ev.get("#type") == "rhythm" or _ival(ev.get("ch")) == -1

    # --- 休符判定（melody のみ） ---
    def is_rest(ev):
        if is_rhythm(ev):
            return False  # rhythm は休符扱いしない
        return (
            _ival(ev["vol"]) == 15 or
            _ival(ev["keyon"]) == 0 or
            _ival(ev["fnum"]) == 0
        )

    # --- retrigger 判定（melody のみ） ---
    def is_retrigger(ev):
        if is_rhythm(ev):
            return False
        return (_ival(ev["keyon"]) == 1 and _ival(ev["vol"]) != 15)

    # チャンネルごとに処理
    from collections import defaultdict
    ch_events = defaultdict(list)
    for ev in events:
        ch_events[_ival(ev.get("ch"), -1)].append(ev)

    merged_all = []

    for ch, buf in ch_events.items():
        buf.sort(key=lambda e: e["tick_start"])

        # -------------------------
        # 第1段階：休符マージ（rhythm は除外）
        # -------------------------
        stage1 = []
        for ev in buf:

            if is_rhythm(ev):
                stage1.append(ev)
                continue

            if stage1:
                prev = stage1[-1]

                if is_rhythm(prev):
                    stage1.append(ev)
                    continue

                if is_retrigger(prev) or is_retrigger(ev):
                    stage1.append(ev)
                    continue

                if is_rest(prev) and is_rest(ev):
                    prev["tick_end"] = ev["tick_end"]
                    prev["l"] = prev["tick_end"] - prev["tick_start"]
                    continue

            stage1.append(ev)

        # -------------------------
        # 第2段階：vol=15 マージ（rhythm は除外）
        # -------------------------
        stage2 = []
        for ev in stage1:

            if is_rhythm(ev):
                stage2.append(ev)
                continue

            if stage2:
                prev = stage2[-1]

                if is_rhythm(prev):
                    stage2.append(ev)
                    continue

                if _ival(prev["vol"]) == 15 and _ival(ev["vol"]) == 15:
                    prev["tick_end"] = ev["tick_end"]
                    prev["l"] = prev["tick_end"] - prev["tick_start"]
                    continue

            stage2.append(ev)

        merged_all.extend(stage2)

    return merged_all

def pass3_merge_retrigger_note(events):
    """
    PASS3(4):
      melody 系のみ retrigger merge を行う。

      merge 対象:
        keyon=1 -> keyon=0 -> keyon=1
        かつ同一音色・同一音高

      merge 非対象:
        rhythm_expand

      OPLL rhythm は posedge sensitive のため、
      rhythm_expand の keyon=1 は独立発音として扱う。
    """

    from collections import defaultdict

    def _ival(v, default=0):

        if v is None or v == "":
            return default

        try:
            return int(v)

        except:
            return default

    # ------------------------------------------------------------
    # tick_start / tick_end を再計算
    # ------------------------------------------------------------
    for ev in events:

        ev["ticks"] = _ival(ev.get("ticks"))
        ev["l"]     = _ival(ev.get("l"))

        ev["tick_start"] = ev["ticks"]
        ev["tick_end"]   = ev["ticks"] + ev["l"]

    # ------------------------------------------------------------
    # same note 判定
    # ------------------------------------------------------------
    def same_note(a, b):

        return (
            _ival(a.get("fnum"))  == _ival(b.get("fnum"))  and
            _ival(a.get("block")) == _ival(b.get("block")) and
            _ival(a.get("inst"))  == _ival(b.get("inst"))  and
            _ival(a.get("vol"))   == _ival(b.get("vol"))   and
            _ival(a.get("sus"))   == _ival(b.get("sus"))
        )

    # ------------------------------------------------------------
    # ch ごとに整理
    # ------------------------------------------------------------
    ch_events = defaultdict(list)

    for ev in events:

        ch = _ival(ev.get("ch"), -1)
        ch_events[ch].append(ev)

    merged_all = []

    # ------------------------------------------------------------
    # merge
    # ------------------------------------------------------------
    for ch, buf in ch_events.items():

        buf.sort(key=lambda e: (
            _ival(e.get("tick_start")),
            _ival(e.get("keyon"))
        ))

        merged = []

        i = 0

        while i < len(buf):

            ev = buf[i]

            ev_type = ev.get("#type", "")

            # ----------------------------------------------------
            # rhythm_expand は merge 禁止
            # ----------------------------------------------------
            if ev_type == "rhythm_expand":

                merged.append(ev)

                i += 1
                continue

            # ----------------------------------------------------
            # retrigger merge pattern
            # ----------------------------------------------------
            can_merge = (
                i + 2 < len(buf)
            )

            if can_merge:

                ev1 = ev
                ev2 = buf[i + 1]
                ev3 = buf[i + 2]

                if (
                    _ival(ev1.get("keyon")) == 1 and
                    _ival(ev2.get("keyon")) == 0 and
                    _ival(ev3.get("keyon")) == 1 and

                    same_note(ev1, ev3) and

                    _ival(ev1.get("tick_end")) ==
                    _ival(ev2.get("tick_start")) and

                    _ival(ev2.get("tick_end")) ==
                    _ival(ev3.get("tick_start"))
                ):

                    # --------------------------------------------
                    # merge
                    # --------------------------------------------
                    ev_new = dict(ev1)

                    ev_new["tick_end"] = _ival(ev3.get("tick_end"))
                    ev_new["l"] = (
                        ev_new["tick_end"] -
                        _ival(ev_new.get("tick_start"))
                    )

                    merged.append(ev_new)

                    i += 3
                    continue

            # ----------------------------------------------------
            # no merge
            # ----------------------------------------------------
            merged.append(ev)

            i += 1

        merged_all.extend(merged)

    # ------------------------------------------------------------
    # ticks 再同期
    # ------------------------------------------------------------
    for ev in merged_all:

        ev["ticks"] = _ival(ev.get("tick_start"))

    # ------------------------------------------------------------
    # 全体ソート
    # ------------------------------------------------------------
    merged_all.sort(key=lambda e: (
        _ival(e.get("ticks")),
        _ival(e.get("ch")),
        _ival(e.get("keyon"))
    ))

    return merged_all

def pass3_dump_csv(events, trace_csv_path):
    """
    PASS 2:
      l=0 event を吸収して削除する。
      time, ticks, l, fl, kl は前の event の値を維持。
      fnum, block, inst, vol, sus などのレジスタ値は l=0 event の値で上書き。
    """

    if not events:
        return

    # 元ファイル名: <stem>_trace.opll.csv
    base, ext = os.path.splitext(trace_csv_path)
    # 出力ファイル名: <stem>_trace.opll.pass1.csv
    out_csv_path = base + ".pass3.csv"

    fieldnames = list(events[0].keys())

    with open(out_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ev in events:
            writer.writerow(ev)

    print(f"[PASS3] Debug CSV written: {out_csv_path}")

def compute_min_l(events):
    # ------------------------------------------------------------
    # 1. [EXP1] 最小音価クラスタ(min_l)の推定（全チャンネル共通）
    # ------------------------------------------------------------
    def _ival(v, default=0):
        try:
            return int(v)
        except:
            return default
    l_vals = []
    for ev in events:
        ch     = _ival(ev.get("ch"))
        l      = _ival(ev.get("l"))
        keyon  = _ival(ev.get("keyon"))
        vol    = _ival(ev.get("vol"))
        is_ryt = _ival(ev.get("is_ryt"))
        ev_type = ev.get("#type")

        # --- 無音(vol=15)は除外 ---
        if vol == 15:
            continue

        is_rhythm_on = ev["#type"] == "rhythm"
        is_melody_on = ev["#type"] != "rhythm" and (0 <= ch <= 5)
        # --- rhythm は除外 ---
        if is_rhythm_on:
            continue

        # --- instVol(keyon=1) と keyBlk(keyon=0) の両方を対象にする ---
        if l > 0:
            l_vals.append(l)

    if not l_vals:
        min_l_base = 1.0
        base  = 1
        cluster = []
    else:
        # 全チャンネルの最小値 base
        base = min(l_vals)

        # b = base + 1 : 1 tick分の揺らぎを抑える
        b = base + 1
        cluster_base = [lv for lv in l_vals if lv == base]
        cluster_b =    [lv for lv in l_vals if lv == b]
        if cluster_b:
            cluster = cluster_base + cluster_b
            min_l_base = int(sum(cluster) / len(cluster)) 
        else:
            cluster = []
            min_l_base = float(base)
    # min_l補正 + 0.4
    min_l = int(min_l_base) + 0.4
    return base, min_l

def pass4_compute_beats(events):
    """
    PASS4:
      1. min_l（beat 正規化用）を決定
      2. beat / beat_pos を計算（min_l ベース）
      3. fb/kb/vb を計算
      4. min_ioi（音符長の最小単位）を計算
      5. tempo（BPM）を IOI ベースで計算し ev["tempo"] に格納

    rhythm-only VGM に対応:
      - ioi が存在しない場合は r_ioi を使用
      - 完全に IOI が存在しない場合も安全に fallback
    """

    def _ival(v, default=0):
        if v is None or v == "":
            return default
        try:
            return int(v)
        except:
            return default

    def get_effective_ioi(ev):
        """
        melody の ioi を優先し、
        無ければ rhythm 用 r_ioi を使う
        """
        ioi = _ival(ev.get("ioi"))
        if ioi > 0:
            return ioi

        r_ioi = _ival(ev.get("r_ioi"))
        if r_ioi > 0:
            return r_ioi

        return 0

    # ------------------------------------------------------------
    # 1. min_l を 最小値又は「最小クラスタ」から決定
    # ------------------------------------------------------------
    base_exp1, min_l_exp1 = compute_min_l(events)

    min_l = min_l_exp1
    base  = base_exp1

    # ------------------------------------------------------------
    # 2. beat（音価）を min_l から計算（切り捨て）
    # ------------------------------------------------------------
    for ev in events:
        l = _ival(ev.get("l"))

        if l > 0:
            ev["beat"] = max(1, int(l / min_l))
        else:
            ev["beat"] = 0

    # ------------------------------------------------------------
    # 3. beat_pos（チャンネル独立）
    # ------------------------------------------------------------
    from collections import defaultdict
    from statistics import mode, median

    ch_events = defaultdict(list)

    for ev in events:
        ch_events[_ival(ev.get("ch"), -1)].append(ev)

    for ch, buf in ch_events.items():
        buf.sort(key=lambda e: _ival(e.get("ticks")))

        beat_pos = 0

        for ev in buf:
            ev["beat_pos"] = beat_pos
            beat_pos += ev["beat"]

    # ------------------------------------------------------------
    # 4. fb/kb/vb（レガート対応）
    # ------------------------------------------------------------
    ch_events_fb = defaultdict(list)

    for ev in events:
        ch_events_fb[_ival(ev.get("ch"), -1)].append(ev)

    for ch, buf in ch_events_fb.items():
        buf.sort(key=lambda e: _ival(e.get("ticks")))

        fnum_prev  = None
        block_prev = None
        inst_prev  = None
        vol_prev   = None
        keyon_prev = 0

        fb_acc = 0
        kb_acc = 0
        vb_acc = 0

        for ev in buf:
            beat  = _ival(ev.get("beat"))
            fnum  = _ival(ev.get("fnum"))
            block = _ival(ev.get("block"))
            inst  = _ival(ev.get("inst"))
            vol   = _ival(ev.get("vol"))
            keyon = _ival(ev.get("keyon"))

            if keyon == 0:
                fb_acc = beat
                kb_acc = beat
                vb_acc = beat

            else:
                same_note = (
                    keyon_prev == 1 and
                    fnum  == fnum_prev and
                    block == block_prev and
                    inst  == inst_prev and
                    vol   == vol_prev
                )

                if same_note:
                    fb_acc += beat
                    kb_acc += beat
                    vb_acc += beat
                else:
                    fb_acc = beat
                    kb_acc = beat
                    vb_acc = beat

            ev["fb"] = fb_acc
            ev["kb"] = kb_acc
            ev["vb"] = vb_acc

            keyon_prev = keyon
            fnum_prev  = fnum
            block_prev = block
            inst_prev  = inst
            vol_prev   = vol

    # ------------------------------------------------------------
    # 5. min_ioi（音符長の最小単位）を計算
    # ------------------------------------------------------------
    ioi_list = [
        get_effective_ioi(ev)
        for ev in events
        if get_effective_ioi(ev) > 0
    ]

    if not ioi_list:
        # 完全 fallback
        min_ioi = 1
        mode_ioi = 1
        ticks_per_step = 2  # fallback
        bpm_ntsc = max(1, round(_FREQ_NTSC * 15 / ticks_per_step))

        for ev in events:
            ev["tempo"] = bpm_ntsc

        return events, min_l, min_ioi, mode_ioi, bpm_ntsc, ticks_per_step

    # ------------------------------------------------------------
    # mode が最も安定（最頻値）
    # ------------------------------------------------------------
    try:
        mode_ioi = mode(ioi_list)
    except:
        mode_ioi = median(ioi_list)

    min_ioi = min(ioi_list)

    # ------------------------------------------------------------
    # 6. tempo（BPM）を IOI ベースで計算
    # ------------------------------------------------------------
    # ticks_per_step を mode_ioi から Nyquist 条件で決定
    ticks_per_step = max(2, int(mode_ioi // 2))

    # NTSC クロックベースの正確な BPM
    bpm_ntsc = max(1, round(_FREQ_NTSC * 15 / max(1, mode_ioi)))  

    # ------------------------------------------------------------
    # 7. tempo を ev に書き込む
    # ------------------------------------------------------------
    for ev in events:
        ev["tempo"] = bpm_ntsc

    # ------------------------------------------------------------
    # 8. rhythm の beat_pos を melody に同期
    # ------------------------------------------------------------
    events_sorted = sorted(
        events,
        key=lambda e: _ival(e.get("ticks"))
    )

    last_melody_beat_pos = 0

    for ev in events_sorted:
        is_ryt = (
            ev.get("is_ryt") == 1 or
            ev.get("#type") == "rhythm"
        )

        if not is_ryt:
            last_melody_beat_pos = _ival(ev.get("beat_pos"))
        else:
            ev["beat_pos"] = last_melody_beat_pos

    return events, min_l, min_ioi, mode_ioi, bpm_ntsc, ticks_per_step

def pass4_dump_csv(events, trace_csv_path):

    if not events:
        return

    # 元ファイル名: <stem>_trace.opll.csv
    base, ext = os.path.splitext(trace_csv_path)
    # 出力ファイル名: <stem>_trace.opll.pass4.csv
    out_csv_path = base + ".pass4.csv"

    fieldnames = list(events[0].keys())

    with open(out_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ev in events:
            writer.writerow(ev)

    print(f"[PASS4] Debug CSV written: {out_csv_path}")
