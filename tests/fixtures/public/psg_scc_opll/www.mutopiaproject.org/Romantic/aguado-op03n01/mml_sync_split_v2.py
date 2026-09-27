#!/usr/bin/env python3
"""
MGSC MML を「同期点」で注釈・分割する。

なぜ綺麗に切れるか
------------------
MGSC の時間はチャンネル独立。同期は「各CHの累積ステップが同じ値になる地点」
でしか保証されない。このスクリプトは:

  1. *マクロを展開してから音価を足す（見かけの行数ではなく実時間）
  2. [ ]n ループは「本体長 × 回数」で畳み込む
  3. 全CHがそのステップに“行の先頭”で乗っている点だけをマークする
     （音の途中で切るとアタックが欠けるので、行境界 = ループ境界を選ぶ）
  4. ブロック切り出し時、区間に完全包含されるループは [ ]n のまま残す
     境界をまたぐループだけ展開して、はみ出した音価を % で切り詰める
  5. 切り出し先頭に、その時点の o/v/@e/@//s/n を書き戻す
     （前のブロックの状態を失わない）
  6. 先に終わったCHは r% でパッドし、ブロック長を全CH一致させる
  7. %音価が MGSC 上限 256 を超える場合は分割する
     音符は & でタイ、休符は r%256 を並べる

同期点は解析フェーズが決める（曲固有の数字は埋め込まない）。
ソース上のトップレベル [ ]n の開始・終了が、複数CHで同じステップに
重なる点 + 0 + 終端。ネストした内側ループはマークしない。

使い方
------
  python3 mml_sync_split.py gra2_001.mml.txt
  python3 mml_sync_split.py gra2_001.mml.txt --annotate gra2_001_sync_marks.mml
  python3 mml_sync_split.py gra2_001.mml.txt --split-dir ./blocks
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from collections import defaultdict

# MGSC %n の上限。これを超えるとコンパイルエラーになる。
MAX_STEP = 256
# #opll_mode 1 の総バッファ目安 (16tr * 1016)。1ch 上限は 16333。
ALLOC_POOL = 16000
ALLOC_MIN = 64
ALLOC_MAX_ONE = 16333

TOK = re.compile(
    r"\*(?P<mac>\d+)"
    r"|@e(?P<env>\d+)"
    r"|@s(?P<sw>\d+)"
    r"|@(?P<wav>\d+)"
    r"|/(?P<mode>\d+)"
    r"|s(?P<sreg>\d+)"
    r"|m(?P<mreg>\d+)"
    r"|n(?P<noise>\d+)"
    r"|v(?P<vol>\d+)"
    r"|o(?P<oct>\d+)"
    r"|h(?P<hw>\d+(?:,\d+)*)"
    r"|hf"
    r"|\\(?P<det>-?\d+)"
    r"|(?P<shift>[<>()]+)"
    r"|(?P<pitch>[a-gr])(?P<acc>\+|\#)?"
    r"(?:%(?P<pstep>\d+)|(?P<plen>\d+)(?P<pdot>\.)?)?"
    r"|(?P<sp>\s+)",
    re.I,
)

STEP_TOKEN = re.compile(r"([a-gA-GrR])([+#])?%(\d+)")


def split_step_tokens(name: str, acc: str, duration: int) -> str:
    """1音/1休符を MAX_STEP 以下の % 列にする。

    休符: r%256 r%41
    音符: c+%256&c+%41   （エンベロープを切らない）
    """
    if duration <= 0:
        return ""
    is_rest = name.lower() == "r"
    head = f"{name}{acc}"
    parts: list[str] = []
    left = duration
    first = True
    while left > 0:
        chunk = min(MAX_STEP, left)
        token = f"{head}%{chunk}"
        if first or is_rest:
            parts.append(token)
        else:
            parts.append("&" + token)
        left -= chunk
        first = False
    return " ".join(parts) if is_rest else "".join(parts)


def rewrite_overlong_steps(s: str) -> str:
    """行内の %n (n>256) を分割。既に 256 以下ならそのまま。"""

    def repl(m: re.Match) -> str:
        name, acc, n = m.group(1), m.group(2) or "", int(m.group(3))
        if n <= MAX_STEP:
            return m.group(0)
        return split_step_tokens(name, acc, n)

    return STEP_TOKEN.sub(repl, s)


def emit_lines(lines: list[str]) -> list[str]:
    return [rewrite_overlong_steps(ln) for ln in lines]


def load_macros(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"^\*(\d+)\s*=\s*\{([^}]*)\}", text, re.M)
    }


def tokens_of(s: str, macros: dict[str, str], expand_macro: bool = True):
    """(text, duration, kind, extra) を順に出す。"""
    i = 0
    s = s.strip()
    while i < len(s):
        m = TOK.match(s, i)
        if not m:
            i += 1
            continue
        i = m.end()
        if m.group("sp") is not None:
            continue
        if m.group("mac") is not None:
            name = m.group("mac")
            body = macros.get(name, "")
            if expand_macro:
                yield from tokens_of(body, macros, True)
            else:
                dur = sum(d for _, d, _, _ in tokens_of(body, macros, True))
                yield (f"*{name}", dur, "macro", name)
            continue
        if m.group("pitch") is not None:
            name = m.group("pitch").lower()
            acc = m.group("acc") or ""
            if m.group("pstep"):
                d = int(m.group("pstep"))
            elif m.group("plen"):
                n = int(m.group("plen"))
                if n == 0:
                    continue
                d = 192 // n
                if m.group("pdot"):
                    d += d // 2
            else:
                continue
            kind = "rest" if name == "r" else "note"
            yield (f"{name}{acc}%{d}", d, kind, None)
            continue
        yield (m.group(0), 0, "cmd", None)


def line_dur(s: str, macros: dict[str, str]) -> int:
    return sum(d for _, d, _, _ in tokens_of(s, macros, True))


def loop_reps(n: int) -> int:
    """MGSC ]0 is infinite. Count one pass for timing / split."""
    return n if n > 0 else 1


CHANNEL_ORDER = "123456789abcdefg"
CHANNEL_RE = r"([1-9a-gA-G])"

def parse_channels(text: str) -> dict[str, list[str]]:
    """Parse all MGSDRV track IDs (1-9, A-G), preserving empty tracks."""
    ch = {c: [] for c in CHANNEL_ORDER}
    for line in text.splitlines():
        m = re.match(rf"^{CHANNEL_RE}\s+(.*)$", line)
        if m:
            key = m.group(1).lower()
            ch[key].append(m.group(2).strip())
    return ch


def parse_ast(lines: list[str], macros: dict[str, str]):
    """行リスト → AST。ノードは ('line', raw, dur) か ('loop', body, n, body_dur)。"""
    ast: list = []
    stack: list = []
    cur = ast
    for raw in lines:
        if raw == "[":
            stack.append(cur)
            nxt: list = []
            cur.append(("loop_open", nxt))
            cur = nxt
            continue
        mm = re.match(r"^\](\d+)$", raw)
        if mm:
            n = int(mm.group(1))
            body = cur
            cur = stack.pop()
            cur[-1] = ("loop", body, n, measure(body, macros))
            continue
        cur.append(("line", raw, line_dur(raw, macros)))
    return ast


def measure(ast, macros) -> int:
    t = 0
    for node in ast:
        if node[0] == "line":
            t += node[2]
        elif node[0] == "loop":
            t += node[3] * loop_reps(node[2])
        elif node[0] == "loop_open":
            t += measure(node[1], macros)
    return t


def emit_ast(ast) -> list[str]:
    out = []
    for node in ast:
        if node[0] == "line":
            out.append(node[1])
        elif node[0] == "loop":
            out.append("[")
            out.extend(emit_ast(node[1]))
            out.append(f"]{node[2]}")
    return out


def slice_line(raw: str, rel0: float, rel1: float, dur: int, macros: dict[str, str]) -> list[str]:
    """1行を [rel0, rel1) で切り、コマンドは残し音価だけ詰める。"""
    lo, hi = max(0, rel0), min(dur, rel1)
    if hi <= lo:
        return []
    acc = 0
    parts = []
    for text, d, kind, extra in tokens_of(raw, macros, expand_macro=False):
        a, b = acc, acc + d
        if d == 0:
            if a <= lo < hi or lo <= a < hi:
                parts.append(text)
            acc = b
            continue
        if b <= lo or a >= hi:
            acc = b
            continue
        nd = int(min(b, hi) - max(a, lo))
        if nd <= 0:
            acc = b
            continue
        if kind == "macro":
            parts.extend(slice_line(macros[extra], lo - a, hi - a, d, macros))
        else:
            m = re.match(r"([a-gr])(\+|#)?%\d+", text, re.I)
            if m:
                piece = split_step_tokens(m.group(1), m.group(2) or "", nd)
                if piece:
                    parts.append(piece)
            else:
                parts.append(text)
        acc = b
    return [" ".join(parts)] if parts else []


def slice_ast(ast, t0: int, t1: int, t_abs: int, macros) -> list[str]:
    """[t0, t1) に重なる部分だけを行リストで返す。完全包含ループは展開しない。"""
    out: list[str] = []
    t = t_abs
    for node in ast:
        if node[0] == "line":
            raw, dur = node[1], node[2]
            a, b = t, t + dur
            if b <= t0 or a >= t1:
                t = b
                continue
            if a >= t0 and b <= t1:
                out.append(raw)
            else:
                out.extend(slice_line(raw, t0 - a, t1 - a, dur, macros))
            t = b
        elif node[0] == "loop":
            body, n, body_dur = node[1], node[2], node[3]
            reps = loop_reps(n)
            total = body_dur * reps
            a, b = t, t + total
            if b <= t0 or a >= t1:
                t = b
                continue
            if a >= t0 and b <= t1:
                out.append("[")
                out.extend(emit_ast(body))
                out.append(f"]{n}")
            else:
                for k in range(reps):
                    ia = t + k * body_dur
                    ib = ia + body_dur
                    if ib <= t0 or ia >= t1:
                        continue
                    if ia >= t0 and ib <= t1:
                        out.extend(emit_ast(body))
                    else:
                        out.extend(slice_ast(body, t0, t1, ia, macros))
            t = b
    return emit_lines(out)


def apply_cmds(raw: str, st: dict, macros: dict[str, str]) -> None:
    for text, d, kind, _ in tokens_of(raw, macros, True):
        if kind != "cmd":
            continue
        if re.fullmatch(r"o\d+", text):
            st["o"] = text
        elif re.fullmatch(r"v\d+", text):
            st["v"] = text
        elif text.startswith("@e"):
            st["e"] = text
        elif text.startswith("@s") or re.fullmatch(r"@\d+", text):
            st["wave"] = text
        elif text.startswith("/"):
            st["mode"] = text
        elif re.fullmatch(r"s\d+", text):
            st["s"] = text
        elif re.fullmatch(r"m\d+", text):
            st["m"] = text
        elif re.fullmatch(r"n\d+", text):
            st["n"] = text
        elif text.startswith("\\"):
            st["det"] = text


def flatten_lines(ast) -> list[str]:
    out = []
    for node in ast:
        if node[0] == "line":
            out.append(node[1])
        elif node[0] == "loop":
            for _ in range(loop_reps(node[2])):
                out.extend(flatten_lines(node[1]))
    return out


def state_at(ast, t_target: int, macros: dict[str, str]) -> dict:
    """t_target 直前までの演奏状態。ブロック先頭に書き戻す。"""
    st = {k: None for k in ("o", "v", "e", "wave", "mode", "s", "m", "n", "det")}
    t = 0
    for raw in flatten_lines(ast):
        if t >= t_target:
            break
        apply_cmds(raw, st, macros)
        t += line_dur(raw, macros)
    return st


def fmt_state(st: dict) -> str:
    return " ".join(st[k] for k in ("mode", "s", "m", "n", "wave", "o", "v", "e", "det") if st.get(k))


def rest_pad(steps: int) -> list[str]:
    """r% を MAX_STEP 以下に分割した行リスト。"""
    if steps <= 0:
        return []
    chunks = []
    left = steps
    while left > 0:
        n = min(MAX_STEP, left)
        chunks.append(f"r%{n}")
        left -= n
    if len(chunks) <= 8:
        return [" ".join(chunks)]
    return [" ".join(chunks[i:i + 8]) for i in range(0, len(chunks), 8)]


def header_of(text: str, title: str | None = None, alloc_line: str | None = None) -> str:
    out = []
    saw_alloc = False
    for ln in text.splitlines():
        if re.match(r"^;\[name=", ln):
            continue
        if re.match(rf"^{CHANNEL_RE}\s", ln) or ln.startswith("12345678"):
            break
        if ln.startswith("#title") and title:
            out.append(f'#title {{ "{title}" }}')
            continue
        if re.match(r"^#alloc\b", ln):
            if alloc_line and not saw_alloc:
                out.append(alloc_line)
                saw_alloc = True
            continue
        out.append(ln)
    if alloc_line and not saw_alloc:
        # #tempo の直前、なければ末尾
        inserted = False
        for i, ln in enumerate(out):
            if ln.startswith("#tempo"):
                out.insert(i, alloc_line)
                inserted = True
                break
        if not inserted:
            out.append(alloc_line)
    return "\n".join(out).rstrip() + "\n"


def estimate_track_bytes(lines: list[str], macros: dict[str, str]) -> int:
    """マクロ展開後の概算バイト（空白除く）。ループは1周だけ見る。"""
    total = 0
    for ln in lines:
        def repl(m):
            return macros.get(m.group(1), m.group(0))
        expanded = re.sub(r"\*(\d+)", repl, ln)
        total += len(re.sub(r"\s+", "", expanded))
    return total


def plan_alloc(ch_lines: dict[str, list[str]], macros: dict[str, str], headroom: float = 2.0) -> dict[str, int]:
    """空きCHからバッファを回し、展開の多いCHを厚くする。"""
    raw = {}
    floors = {}
    for c, lines in ch_lines.items():
        est = estimate_track_bytes(lines, macros)
        only_rest = bool(lines) and all(re.fullmatch(r"(r%\d+\s*)+", ln) for ln in lines)
        if only_rest or est == 0:
            raw[c] = ALLOC_MIN
            floors[c] = ALLOC_MIN
        else:
            floor = min(ALLOC_MAX_ONE, est + 256)
            raw[c] = min(ALLOC_MAX_ONE, max(floor, int(est * headroom) + 256))
            floors[c] = floor
    total = sum(raw.values())
    if total > ALLOC_POOL:
        extra = total - ALLOC_POOL
        order = sorted(raw, key=lambda k: raw[k], reverse=True)
        for c in order:
            if extra <= 0:
                break
            can = raw[c] - floors.get(c, ALLOC_MIN)
            take = min(max(0, can), extra)
            raw[c] -= take
            extra -= take
    return raw

def parse_alloc(text: str) -> dict[str, int]:
    m = re.search(r"#alloc\s*\{([^}]*)\}", text)

    if not m:
        return {}

    result = {}

    for item in m.group(1).split(","):
        item = item.strip()

        mm = re.match(r"([0-9a-gA-G])\s*=\s*(\d+)", item)

        if mm:
            result[mm.group(1).lower()] = int(mm.group(2))

    return result

def plan_alloc_from_original(
    src_text: str,
    split_channels: dict[str, list[str]],
    macros: dict[str, str],
) -> dict[str, int]:
    """
    元の #alloc をベースにする。
    重要:
      - 元々 alloc 指定されていない CH は追加しない
      - ループ展開で増えた CH のみ増量する
      - 元alloc値を尊重する
    例:
        元:
            #alloc { 2=1400, 3=1300 }

        出力:
            #alloc { 2=3000, 3=1300 }
    """

    original_alloc = parse_alloc(src_text)

    if not original_alloc:
        return {}

    src_channels = parse_channels(src_text)
    result = dict(original_alloc)

    for ch, base_alloc in original_alloc.items():
        # 元トラックサイズ
        src_est = estimate_track_bytes(
            src_channels.get(ch, []),
            macros,
        )

        # 分割後サイズ
        split_est = estimate_track_bytes(
            split_channels.get(ch, []),
            macros,
        )

        # サイズ増加率
        if src_est <= 0:
            continue

        ratio = split_est / src_est

        # 増えていなければそのまま
        if ratio <= 1.0:
            continue

        # 元allocを比例拡大
        # 例:
        #   1400 -> 2800
        new_alloc = int(base_alloc * ratio)

        # 安全マージン
        new_alloc += 256

        result[ch] = min(ALLOC_MAX_ONE, new_alloc)

    return result

def fmt_alloc(sizes: dict[str, int]) -> str:
    parts = [f"{c}={sizes[c]}" for c in CHANNEL_ORDER if sizes.get(c)]
    return "#alloc { " + ", ".join(parts) + " }"


def annotate(text: str, marks: list[tuple[int, str]], macros, asts) -> str:
    ch_state = {c: {"step": 0, "stack": []} for c in CHANNEL_ORDER}
    out: list[str] = []
    injected: set[tuple[str, int]] = set()
    header_note = False
    for line in text.splitlines(keepends=True):
        raw = line.rstrip("\n")
        if raw.startswith("#tempo") and not header_note:
            out.append(line if line.endswith("\n") else line + "\n")
            out.append("; sync marks (loops expanded). clock: %48 = quarter\n")
            mark_s = " | ".join(f"{s} {lb.split()[0]}" for s, lb in marks)
            out.append(f"; {mark_s}\n")
            header_note = True
            continue
        m = re.match(rf"^{CHANNEL_RE}\s+(.*)$", raw)
        if not m:
            out.append(line if line.endswith("\n") else line + "\n")
            continue
        ch, body = m.group(1).lower(), m.group(2).strip()
        st = ch_state[ch]
        start = st["step"]
        for mark, label in marks:
            if start == mark and mark != marks[-1][0] and (ch, mark) not in injected:
                out.append(f"; ch{ch} --- step {mark} : {label} ---\n")
                injected.add((ch, mark))
        if body == "[":
            st["stack"].append(st["step"])
        elif re.match(r"^\]\d+$", body):
            n = int(body[1:])
            if st["stack"]:
                body_len = st["step"] - st["stack"].pop()
                st["step"] += body_len * (loop_reps(n) - 1)
        else:
            st["step"] += line_dur(body, macros)
        out.append(line if line.endswith("\n") else line + "\n")
        last = marks[-1][0]
        if st["step"] == last and (ch, last) not in injected:
            out.append(f"; ch{ch} --- step {last} : {marks[-1][1]} ---\n")
            injected.add((ch, last))
    return "".join(out)


def split_blocks(src_text: str, marks: list[tuple[int, str]], macros, asts, name_prefix: str):
    """連続する mark 間を 1 ファイルにする。"""
    files = []
    for i in range(len(marks) - 1):
        num = i + 1
        t0, label = marks[i]
        t1 = marks[i + 1][0]
        title = f"{name_prefix} / {num:02d} {label}"
        bodies: dict[str, list[str]] = {}
        meta: dict[str, tuple] = {}
        for c in CHANNEL_ORDER:
            st = state_at(asts[c], t0, macros)
            sliced = slice_ast(asts[c], t0, t1, 0, macros)
            sm = measure(parse_ast(sliced, macros), macros) if sliced else 0
            pad = (t1 - t0) - sm
            lines: list[str] = []
            init = fmt_state(st)
            # A channel that is completely empty in the original MML must stay
            # empty.  Padding such a channel with r%... wastes MGSC track-buffer
            # space and may cause "Track buffer full".
            channel_exists = bool(parse_channels(src_text).get(c, []))
            if channel_exists and (sliced or pad > 0):
                if init:
                    lines.append(init)
                lines.extend(rewrite_overlong_steps(ln) for ln in sliced)
                lines.extend(rest_pad(pad))
            bodies[c] = lines
            meta[c] = (st, sliced, sm, pad)

        # alloc は元MMLの指定を尊重する。
        # ループ展開で増えた CH のみ増量。
        sizes = plan_alloc_from_original(
            src_text,
            bodies,
            macros,
        )
        alloc_line = fmt_alloc(sizes) if sizes else None
        
        text = f";[name={name_prefix}{num:02d} lpf=1]\n\n"
        text += header_of(src_text, title, alloc_line)
        text += f"\n; block {num:02d}  steps {t0}-{t1}  ({t1-t0} steps)  {label}\n"
        text += "; clock %48 = quarter. early-ending ch padded with r%.\n"
        text += f"; % values > {MAX_STEP} are split (notes tied with &, rests repeated).\n"
        text += f"; {alloc_line}\n\n"
        for c in CHANNEL_ORDER:
            st, sliced, sm, pad = meta[c]
            text += f"; ----- ch{c}  start-state ----- steps {sm}"
            if pad:
                text += f"  pad {pad}"
            if sizes:
                alloc_info = sizes.get(c, "-")
            else:
                alloc_info = "-"
            text += f"  alloc {alloc_info}\n"
            
            if bodies[c]:
                for ln in bodies[c]:
                    text += f"{c} {ln}\n"
            text += "\n"
        files.append((num, t0, t1, text))
    return files


def collect_loop_bounds(ast, t=0, depth=0):
    """ソースASTを1回だけ歩く。展開はせず、トップレベル境界の絶対ステップを返す。"""
    events = []
    for node in ast:
        if node[0] == "line":
            t += node[2]
        elif node[0] == "loop":
            body, n, body_dur = node[1], node[2], node[3]
            reps = loop_reps(n)
            child_depth = depth if n == 0 else depth + 1
            if n != 0:
                events.append((t, depth, "open", n, body_dur))
            inner, _ = collect_loop_bounds(body, t, child_depth)
            events.extend(inner)
            t_end = t + body_dur * reps
            if n != 0:
                events.append((t_end, depth, "close", n, body_dur))
            t = t_end
    return events, t


def collect_token_boundaries(ast, macros, t0: int = 0) -> tuple[set[int], int]:
    """Return absolute note/rest token boundaries with loops expanded.

    A boundary is safe for splitting because no note/rest is sounding across it
    within that track.  Commands have zero duration and do not create time.
    """
    bounds = {t0}
    t = t0
    for node in ast:
        if node[0] == "line":
            raw = node[1]
            for _text, dur, kind, _extra in tokens_of(raw, macros, True):
                if dur > 0 and kind in ("note", "rest", "macro"):
                    t += dur
                    bounds.add(t)
        elif node[0] == "loop":
            body, n = node[1], node[2]
            for _ in range(loop_reps(n)):
                child, t = collect_token_boundaries(body, macros, t)
                bounds.update(child)
        elif node[0] == "loop_open":
            child, t = collect_token_boundaries(node[1], macros, t)
            bounds.update(child)
    return bounds, t


def analyze_sync(asts, macros, min_ch: int | None = None, min_gap: int = 0, min_span: int | None = None):
    """Find synchronization points from note/rest token boundaries.

    Default behavior is strict: every active channel must be at a token boundary.
    --min-ch can relax this for discovery.  0 and the longest track end are always
    included; shorter tracks are considered ended and can be padded by split_blocks.
    """
    totals = {c: measure(ast, macros) for c, ast in asts.items()}
    active = [c for c, total in totals.items() if total > 0]
    end = max((totals[c] for c in active), default=0)

    boundaries = {}
    for c in active:
        b, _ = collect_token_boundaries(asts[c], macros, 0)
        boundaries[c] = b

    if min_ch is None:
        min_ch = len(active)

    # min_span is retained as a compatibility alias for minimum mark spacing.
    effective_gap = max(min_gap, min_span or 0)

    votes = defaultdict(set)
    for c, bs in boundaries.items():
        total = totals[c]
        for step in bs:
            if 0 < step < end:
                votes[step].add(c)
        # Once a track has ended, it is silent and split_blocks can pad it.
        # Therefore later candidate boundaries do not need a vote from this track.

    raw = []
    for step in sorted(votes):
        required = [c for c in active if totals[c] >= step]
        present = [c for c in required if step in boundaries[c]]
        threshold = min(min_ch, len(required))
        if len(present) < threshold:
            continue
        # In strict/default mode, require every still-running channel.
        if min_ch >= len(active) and len(present) != len(required):
            continue
        raw.append((step, len(present), len(required)))

    picked = []
    for step, nch, nreq in raw:
        if effective_gap and picked and step - picked[-1][0] < effective_gap:
            continue
        picked.append((step, nch, nreq))

    marks = [(0, "start")]
    for step, nch, nreq in picked:
        marks.append((step, f"token-boundary {nch}/{nreq}ch"))
    if end > 0:
        marks.append((end, "end"))
    return marks, totals, min_ch


def main():
    ap = argparse.ArgumentParser(description="Annotate / split MGSC MML on sync marks")
    ap.add_argument("input", type=Path, help="source .mml / .mml.txt")
    ap.add_argument("--annotate", type=Path, help="write sync-commented copy")
    ap.add_argument("--split-dir", type=Path, help="write per-block MMLs here")
    ap.add_argument("--prefix", default="", help="split file prefix (default: <stem>_with_sync_mark)")
    ap.add_argument("--marks", default="", help="comma steps; omit to auto-detect")
    ap.add_argument("--min-ch", type=int, default=0, help="min channels sharing a token boundary (0=all active channels)")
    ap.add_argument("--min-gap", type=int, default=0, help="drop nearby marks (steps)")
    ap.add_argument("--min-span", type=int, default=0, help="minimum spacing between sync marks (compatibility option)")
    ap.add_argument("--discover", action="store_true", help="print analysis and exit")
    args = ap.parse_args()

    def _clean_path(p):
        if p is None:
            return None
        return Path(str(p).replace("\r", "").strip())

    args.input = _clean_path(args.input)
    args.annotate = _clean_path(args.annotate)
    args.split_dir = _clean_path(args.split_dir)
    args.prefix = args.prefix.replace("\r", "").strip()

    src = args.input.read_text()
    macros = load_macros(src)
    ch_lines = parse_channels(src)
    asts = {c: parse_ast(ch_lines[c], macros) for c in CHANNEL_ORDER}

    print("channel totals (expanded):")
    for c in CHANNEL_ORDER:
        print(f"  ch{c}  {measure(asts[c], macros)}")

    min_ch = args.min_ch or None
    min_span = args.min_span or None
    auto_marks, totals, used_min_ch = analyze_sync(
        asts, macros, min_ch=min_ch, min_gap=args.min_gap, min_span=min_span
    )
    print(f"analyze: min_ch={used_min_ch}  marks={[s for s, _ in auto_marks]}")
    for s, lb in auto_marks:
        print(f"  {s:6}  {lb}")

    if args.discover:
        return

    if args.marks:
        steps = [int(x) for x in args.marks.replace("\r", "").split(",") if x.strip()]
        labels = {s: lb for s, lb in auto_marks}
        marks = [(s, labels.get(s, f"step {s}")) for s in steps]
    else:
        marks = auto_marks

    if not args.prefix:
        args.prefix = f"{args.input.stem}_with_sync_mark"

    if args.annotate:
        dest = args.annotate
        if dest.exists() and dest.is_dir():
            dest = dest / f"{args.input.stem}_sync_marks.mml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(annotate(src, marks, macros, asts))
        print("wrote", dest)

    if args.split_dir:
        args.split_dir.mkdir(parents=True, exist_ok=True)
        for num, t0, t1, text in split_blocks(src, marks, macros, asts, args.prefix):
            p = args.split_dir / f"{args.prefix}{num:02d}.mml"
            p.write_text(text)
            print(f"wrote {p}  ({t0}-{t1})")


if __name__ == "__main__":
    main()
