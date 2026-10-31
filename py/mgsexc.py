"""MGSEXC - clean-room extended compiler for MGSDRV MML.

Compiles MGSC-dialect MML to MGS (MGSDRV v3.13) data without the
16 KB track-buffer pool of the original MGSC. `#alloc` directives
are parsed and ignored: allocation sizes never influenced MGSC's
output bytes (verified by differential probing), so exact sizing by
construction replaces the pool entirely.

Behavior is specified from public documents (MGSC111.DOC by
Gigamix, DSA's mgs-format.md) and from black-box probing of the
reference compiler's observable outputs. No original source code
was consulted.

Public entry point: compile_mml(source: bytes) -> bytes
"""

from __future__ import annotations

import re
from fractions import Fraction

__all__ = ["compile_mml", "MgsExcError"]


class MgsExcError(Exception):
    """Raised for MML MGSEXC cannot compile (yet)."""


# ---------------------------------------------------------------------------
# Source handling
# ---------------------------------------------------------------------------

# Work on raw bytes: titles may carry Shift-JIS payloads that must be
# copied through unchanged.
_LINE_SPLIT = re.compile(rb"\r\n|\r|\n")


def _strip_comment(line: bytes) -> bytes:
    """MGSC treats ';' as comment start; quoted strings are exempt."""
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == 0x22:
                if i + 1 < len(line) and line[i + 1] == 0x22:
                    i += 2
                    continue
                in_str = False
        else:
            if c == 0x22:
                in_str = True
            elif c == 0x3B:  # ;
                return line[:i]
        i += 1
    return line


class _Source:
    """Logical lines of the MML with brace-block joining.

    Header directives and definitions that use { ... } may span
    several physical lines; join them into one logical line first.
    """

    def __init__(self, data: bytes):
        self.lines: list[bytes] = []
        # MGSC reads each physical line into a 255-byte buffer:
        # longer lines are truncated (the remainder is discarded),
        # and when any line overflows, the output file's first byte
        # is written as 0x00 instead of 'M'. Both effects measured
        # from oracle outputs (2026-10-31).
        self.truncated = False
        raw = _LINE_SPLIT.split(data)
        buf: bytes | None = None
        depth = 0
        for phys0 in raw:
            if len(phys0) >= 255:
                self.truncated = True
                phys0 = phys0[:255]
            phys = _strip_comment(phys0)
            if buf is None:
                buf = phys
            else:
                buf = buf + b"\n" + phys
            # brace balance outside of quoted strings is enough for
            # the generated dialect (titles may contain braces only
            # inside quotes; count quotes naively).
            depth += _brace_delta(phys)
            if depth <= 0:
                self.lines.append(buf)
                buf = None
                depth = 0
        if buf is not None:
            self.lines.append(buf)


def _brace_delta(line: bytes) -> int:
    delta = 0
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == 0x22:  # "
                if i + 1 < len(line) and line[i + 1] == 0x22:
                    i += 2
                    continue
                in_str = False
        else:
            if c == 0x22:
                in_str = True
            elif c == 0x7B:  # {
                delta += 1
            elif c == 0x7D:  # }
                delta -= 1
        i += 1
    return delta


# ---------------------------------------------------------------------------
# Numbers and lengths
# ---------------------------------------------------------------------------


def _parse_int(tok: bytes, what: str) -> int:
    try:
        return int(tok.decode("ascii").strip())
    except Exception:
        raise MgsExcError(f"bad number for {what}: {tok!r}")


def length_to_steps(num: int | None, dots: int, percent: int | None) -> int:
    """Convert an MML length to steps (quarter note = 48, max 256).

    num: note value denominator (4 = quarter). percent: direct steps.
    Dots augment by halves. Result must be integral (as in MGSC for
    the dialect we accept)."""
    if percent is not None:
        steps = Fraction(percent, 1)
    else:
        if num is None:
            raise MgsExcError("length without value")
        steps = Fraction(192, num)
    add = steps
    for _ in range(dots):
        add = add / 2
        steps += add
    if steps.denominator != 1:
        raise MgsExcError(f"non-integral step length: {steps}")
    v = int(steps)
    if not (1 <= v <= 256):
        raise MgsExcError(f"step length out of range: {v}")
    return v


def _len_byte(steps: int) -> int:
    return 0 if steps == 256 else steps


# ---------------------------------------------------------------------------
# Track state and emission
# ---------------------------------------------------------------------------


class _Track:
    def __init__(self, number: int):
        self.number = number
        self.data = bytearray()
        self.octave = 4  # MML octave state (o4 default)
        self.deflen = 48  # current l value in steps (l4 default)
        self.started = False  # any content emitted
        self.ignored = False  # after '!' command

    def emit(self, *bs: int) -> None:
        self.data.extend(bs)
        self.started = True


NOTE_CLASS = {
    ord("c"): 0,
    ord("d"): 2,
    ord("e"): 4,
    ord("f"): 5,
    ord("g"): 7,
    ord("a"): 9,
    ord("b"): 11,
}


class _Compiler:
    def __init__(self):
        self.opll_mode = 0
        self.machine_id = 0
        self.lfo_mode = 0
        self.disenable_mgsrc = 0
        self.tempo = 120
        self.title = b""
        self.tracks: dict[int, _Track] = {n: _Track(n) for n in range(18)}
        self.macros: dict[int, bytes] = {}
        self.macro_offsets: dict[int, int] = {}  # letter byte -> offset
        self.at_m_next = 0  # for @m definitions with omitted number
        self.at_o_offset = 0

    # -- top level ---------------------------------------------------------
    def compile(self, data: bytes) -> bytes:
        src = _Source(data)
        self.truncated = src.truncated
        for logical in src.lines:
            self._line(logical)
        return self._assemble()

    def _line(self, raw: bytes) -> None:
        line = raw.strip()
        if not line:
            return
        if line.startswith(b"#"):
            self._directive(line)
            return
        if line.startswith(b"@") and b"=" in line:
            self._definition(line)
            return
        if line.startswith(b"*") and b"=" in line.split(b"{")[0]:
            self._macro_definition(line)
            return
        if line.startswith(b"@"):
            self._definition(line)
            return
        self._track_line(line)

    # -- directives --------------------------------------------------------
    def _directive(self, line: bytes) -> None:
        m = re.match(rb"#\s*([a-z_]+)\s*(.*)$", line, re.IGNORECASE | re.DOTALL)
        if not m:
            return
        name = m.group(1).lower()
        rest = m.group(2).strip()
        if name == b"opll_mode":
            self.opll_mode = _parse_int(rest.split()[0], "#opll_mode") & 1
        elif name == b"tempo":
            self.tempo = _parse_int(rest.split()[0], "#tempo")
        elif name == b"machine_id":
            self.machine_id = _parse_int(rest.split()[0], "#machine_id") & 7
        elif name == b"lfo_mode":
            self.lfo_mode = _parse_int(rest.split()[0], "#lfo_mode") & 1
        elif name == b"disenable_mgsrc":
            self.disenable_mgsrc = 1
        elif name == b"title":
            self.title = _extract_title(rest)
        elif name == b"alloc":
            # The values are ignored by design (they never affect
            # output bytes), but an allocated track exists in the
            # output even with no MML content: it gets an offset and
            # a lone FF terminator (measured from oracle outputs).
            for tnum in _alloc_tracks(rest):
                self.tracks[tnum].started = True
        elif name == b"psg_tune":
            vals = _extract_numbers(rest)
            self._track0_tune(0x04, vals, 4095)
        elif name == b"opll_tune":
            vals = _extract_numbers(rest)
            self._track0_tune(0x05, vals, 511)
        elif name == b"macro_offset":
            self._macro_offset(rest)
        elif name in (b"end",):
            raise _EndOfSource
        # all other directives (#play_start, #no_mgs, #track_status,
        # #play_track, ...) have no data effect

    def _track0_tune(self, opcode: int, vals: list[int], vmax: int) -> None:
        if len(vals) != 12:
            raise MgsExcError(f"tune table needs 12 values, got {len(vals)}")
        t0 = self.tracks[0]
        t0.emit(opcode)
        for v in vals:
            if not (0 <= v <= vmax):
                raise MgsExcError(f"tune value out of range: {v}")
            t0.emit(v & 0xFF, (v >> 8) & 0xFF)

    def _macro_offset(self, rest: bytes) -> None:
        body = rest.strip()
        if body.startswith(b"{"):
            body = body[1 : body.rfind(b"}")]
        for part in body.split(b","):
            part = part.strip()
            if not part:
                continue
            letter, _, val = part.partition(b"=")
            self.macro_offsets[letter.strip().lower()[0]] = _parse_int(
                val, "#macro_offset"
            )

    # -- definitions (track 0) ---------------------------------------------
    def _definition(self, line: bytes) -> None:
        # @m string definitions
        m = re.match(rb"@m\s*(\d*)\s*=\s*\{", line, re.IGNORECASE)
        if m:
            num = int(m.group(1)) if m.group(1) else self.at_m_next + 1
            self.at_m_next = num
            payload = _extract_quoted(_brace_body(line))
            t0 = self.tracks[0]
            t0.emit(0x06, num & 0x7F)
            t0.data.extend(_unescape_at_m(payload))
            t0.emit(0x00)
            return
        m = re.match(rb"@#\s*(\d+)\s*=\s*(\d+)", line, re.IGNORECASE)
        if m:
            self.tracks[0].emit(0x01, int(m.group(1)), int(m.group(2)))
            return
        m = re.match(rb"@s\s*(\d+)\s*=\s*\{", line, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            hexpart = re.sub(rb"[^0-9a-fA-F]", b"", _brace_body(line))
            if len(hexpart) != 64:
                raise MgsExcError(f"@s needs 32 bytes, got {len(hexpart)//2}")
            wave = bytes.fromhex(hexpart.decode("ascii"))
            t0 = self.tracks[0]
            t0.emit(0x03, num & 0x1F)
            t0.data.extend(wave)
            return
        m = re.match(rb"@v?\s*(\d+)\s*=\s*\{", line, re.IGNORECASE)
        if m and (line[1:2].lower() == b"v" or line[1:2].isdigit()):
            num = int(m.group(1))
            vals = _extract_numbers(_brace_body(line))
            t0 = self.tracks[0]
            t0.emit(0x00, num & 0x1F)
            t0.data.extend(_pack_opll_voice(vals))
            return
        m = re.match(rb"@e\s*(\d+)\s*=\s*\{", line, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            self._envelope(num, _brace_body(line), is_r=False)
            return
        m = re.match(rb"@r\s*(\d+)\s*=\s*\{", line, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            self._envelope(num, _brace_body(line), is_r=True)
            return
        raise MgsExcError(f"unknown definition: {line[:40]!r}")

    def _envelope(self, num: int, body: bytes, is_r: bool) -> None:
        parts = [p.strip() for p in _split_top(body)]
        if len(parts) < 2:
            raise MgsExcError("@e/@r needs at least Mode, Noise")
        mode = _parse_int(parts[0], "@e mode") if parts[0] else 1
        noise = _parse_int(parts[1], "@e noise") if parts[1] else 0
        t0 = self.tracks[0]
        if is_r:
            if len(parts) != 8:
                raise MgsExcError("@r needs 8 parameters")
            vals = [_parse_int(p, "@r") for p in parts[2:]]
            nn = 0x80 | ((mode & 3) << 5) | (noise & 0x1F)
            t0.emit(0x02, num & 0x1F, nn, *[v & 0xFF for v in vals])
            return
        data = _compile_envelope_data(parts[2:])
        nn = ((mode & 3) << 5) | (noise & 0x1F)
        t0.emit(0x02, num & 0x1F, nn, len(data))
        t0.data.extend(data)

    def _macro_definition(self, line: bytes) -> None:
        m = re.match(rb"\*\s*([0-9]+|[a-z])\s*(\d*)\s*=\s*\{", line, re.IGNORECASE)
        if not m:
            raise MgsExcError(f"bad macro definition: {line[:40]!r}")
        head = m.group(1)
        tail = m.group(2)
        if head.isdigit():
            num = int(head)
        else:
            num = self.macro_offsets.get(head.lower()[0], 0) + (
                int(tail) if tail else 0
            )
        self.macros[num] = _brace_body(line)

    # -- track lines ---------------------------------------------------------
    def _track_line(self, line: bytes) -> None:
        m = re.match(rb"([0-9a-hr]+)\s+(.*)$", line, re.IGNORECASE | re.DOTALL)
        if not m:
            raise MgsExcError(f"unrecognized line: {line[:40]!r}")
        designators = m.group(1).lower()
        body = m.group(2)
        for ch in designators:
            tnum = _designator_track(ch, self.opll_mode)
            track = self.tracks[tnum]
            if track.ignored:
                continue
            self._compile_mml(track, body, depth=0)

    # -- MML compilation -----------------------------------------------------
    def _compile_mml(self, track: _Track, body: bytes, depth: int) -> None:
        if depth > 8:
            raise MgsExcError("macro nesting too deep")
        if _is_rhythm(track, self.opll_mode):
            self._compile_rhythm(track, body, depth)
            return
        s = body.lower()
        i = 0
        n = len(s)
        while i < n:
            if track.ignored:
                return
            c = s[i]
            if c in b" \t\r\n,":
                i += 1
                continue
            if c in NOTE_CLASS:
                i = self._note(track, s, i)
                continue
            if c == ord("r"):
                i = self._rest(track, s, i)
                continue
            i = self._command(track, s, i, depth)

    # Rhythm track (mode 1, track 15) grammar, measured from the
    # oracle: instrument letters b/s/m/c/h accumulate into one event
    # bitmask; 'r' clears the mask; the group is flushed by a length
    # spec, by ':' (default length), or at the end of the MML text.
    # A group left open at any other command is an error in MGSC.
    _RHYTHM_BITS = {ord("b"): 0x10, ord("s"): 0x08, ord("m"): 0x04, ord("c"): 0x02, ord("h"): 0x01}
    _RHYTHM_TARGET = {ord("b"): 0, ord("s"): 1, ord("m"): 2, ord("c"): 3, ord("h"): 4}

    def _rhythm_flush(self, track: _Track, bits: int, steps: int) -> None:
        if steps == track.deflen:
            track.emit(0xA0 | bits)
        else:
            track.emit(0x20 | bits, _len_byte(steps))

    def _compile_rhythm(self, track: _Track, body: bytes, depth: int) -> None:
        s = body.lower()
        i = 0
        n = len(s)
        bits = 0
        group_open = False

        def need_closed() -> None:
            if group_open:
                raise MgsExcError("rhythm event group not closed by a length")

        while i < n:
            if track.ignored:
                return
            c = s[i]
            if c in b" \t\r\n,":
                i += 1
                continue
            if c in self._RHYTHM_BITS:
                bits |= self._RHYTHM_BITS[c]
                group_open = True
                i += 1
                continue
            if c == ord("r"):
                bits = 0
                group_open = True
                i += 1
                continue
            if c == ord(":"):
                self._rhythm_flush(track, bits, track.deflen)
                bits = 0
                group_open = False
                i += 1
                continue
            if c == ord("%") or (ord("0") <= c <= ord("9")):
                steps, i = self._length(s, i, None)
                steps, i = self._tie_chain(s, i, steps, track.deflen)
                self._rhythm_flush(track, bits, steps)
                bits = 0
                group_open = False
                continue
            if c == ord("v"):
                need_closed()
                i = self._rhythm_volume(track, s, i)
                continue
            if c == ord("k") and s[i + 1 : i + 2] in (b"o", b"f"):
                need_closed()
                track.emit(0x5A, 0x00 if s[i + 1 : i + 2] == b"o" else 0x01)
                i += 2
                continue
            need_closed()
            i = self._command(track, s, i, depth)
        if group_open:
            self._rhythm_flush(track, bits, track.deflen)

    def _rhythm_volume(self, track: _Track, s: bytes, i: int) -> int:
        # v<inst><n> -> 45 (target<<5)|n ; v<inst>+|-<n> -> 47 ...
        # plain v<n> / v+<n> / v-<n> use the generic forms (Cn / 46).
        n = len(s)
        j = i + 1
        if j < n and s[j] in self._RHYTHM_TARGET:
            target = self._RHYTHM_TARGET[s[j]]
            j += 1
            if j < n and s[j] in (ord("+"), ord("-")):
                sign = 1 if s[j] == ord("+") else -1
                j += 1
                k = j
                while k < n and s[k : k + 1].isdigit():
                    k += 1
                off = sign * int(s[j:k] or b"0")
                track.emit(0x47, ((target << 5) | (off & 0x1F)) & 0xFF)
                return k
            k = j
            while k < n and s[k : k + 1].isdigit():
                k += 1
            vol = int(s[j:k] or b"0")
            track.emit(0x45, ((target << 5) | (vol & 0xF)) & 0xFF)
            return k
        return self._command(track, s, i, 0)

    # -- length parsing ------------------------------------------------------
    def _length(self, s: bytes, i: int, default: int | None) -> tuple[int, int]:
        """Parse an optional length spec at s[i:]; returns (steps, next_i).

        Forms: [digits] dots | %steps dots | empty (-> default).
        Tie additions (^spec) are folded in by the caller via
        _tie_chain."""
        n = len(s)
        steps: int | None = None
        if i < n and s[i] == ord("%"):
            j = i + 1
            while j < n and s[j : j + 1].isdigit():
                j += 1
            steps = length_to_steps(None, 0, int(s[i + 1 : j]))
            i = j
        elif i < n and s[i : i + 1].isdigit():
            j = i
            while j < n and s[j : j + 1].isdigit():
                j += 1
            num = int(s[i:j])
            dots = 0
            k = j
            while k < n and s[k] == ord("."):
                dots += 1
                k += 1
            steps = length_to_steps(num, dots, None)
            i = k
        if steps is None:
            if default is None:
                raise MgsExcError("length required")
            return default, i
        # dots after a % length
        return steps, i

    def _tie_chain(self, s: bytes, i: int, first_steps: int, default: int) -> tuple[int, int]:
        """Fold ^ additions following a note/rest length."""
        total = first_steps
        n = len(s)
        while i < n and s[i] == ord("^"):
            add, i = self._length(s, i + 1, default)
            total += add
            if total > 256:
                raise MgsExcError("tied length exceeds 256 steps")
        return total, i

    # -- notes and rests -----------------------------------------------------
    def _note(self, track: _Track, s: bytes, i: int) -> int:
        letter = s[i]
        cls = NOTE_CLASS[letter]
        i += 1
        acc = 0
        while i < len(s) and s[i] in (ord("+"), ord("#"), ord("-")):
            acc += 1 if s[i] in (ord("+"), ord("#")) else -1
            i += 1
        steps, i = self._length(s, i, track.deflen)
        steps, i = self._tie_chain(s, i, steps, track.deflen)
        # Accidentals adjust the pitch-class nibble only; MGSC does
        # not emit octave changes for them. Observed oracle behavior:
        # c- wraps to B (11), while b+ clamps to B (11) as well.
        cls2 = cls + acc
        while cls2 < 0:
            cls2 += 12
        if cls2 > 11:
            cls2 = 11
        if steps == track.deflen:
            track.emit(0x30 | cls2)
        else:
            track.emit(0x20 | cls2, _len_byte(steps))
        # slur '&' immediately after a note
        if i < len(s) and s[i] == ord("&"):
            track.emit(0x40)
            i += 1
        return i

    def _rest(self, track: _Track, s: bytes, i: int) -> int:
        i += 1  # consume 'r'
        steps, i = self._length(s, i, track.deflen)
        steps, i = self._tie_chain(s, i, steps, track.deflen)
        if steps == track.deflen:
            track.emit(0x3C)
        else:
            track.emit(0x2C, _len_byte(steps))
        return i

    # -- other commands --------------------------------------------------------
    def _command(self, track: _Track, s: bytes, i: int, depth: int) -> int:
        c = s[i]
        n = len(s)

        def num(i: int) -> tuple[int, int]:
            sign = 1
            if i < n and s[i] == ord("-"):
                sign = -1
                i += 1
            elif i < n and s[i] == ord("+"):
                i += 1
            j = i
            while j < n and s[j : j + 1].isdigit():
                j += 1
            if j == i:
                raise MgsExcError(f"number expected in track {track.number}")
            return sign * int(s[i:j]), j

        if c == ord("t"):
            v, i = num(i + 1)
            table = tempo_frame_table(v)
            track.emit(0x41, v & 0xFF, (v >> 8) & 0xFF)
            track.data.extend(table)
            return i
        if c == ord("l"):
            steps, i = self._length(s, i + 1, None)
            track.deflen = steps
            track.emit(0x42, _len_byte(steps))
            return i
        if c == ord("o"):
            v, i = num(i + 1)
            track.octave = v
            track.emit(0xD0 | ((v - 1) & 0xF))
            return i
        if c == ord(">"):
            track.octave += 1
            track.emit(0x4E)
            return i + 1
        if c == ord("<"):
            track.octave -= 1
            track.emit(0x4F)
            return i + 1
        if c == ord("v"):
            # v<n> | v+<n> | v-<n> | rhythm v<inst>...
            j = i + 1
            if j < n and s[j] in (ord("+"), ord("-")):
                delta, j = num(j)
                track.emit(0x46, delta & 0xFF)
                return j
            v, j = num(j)
            track.emit(0xC0 | (v & 0xF))
            return j
        if c == ord(")"):
            v, j = num(i + 1) if i + 1 < n and (s[i + 1 : i + 2].isdigit()) else (1, i + 1)
            track.emit(0x46, v & 0xFF)
            return j
        if c == ord("("):
            v, j = num(i + 1) if i + 1 < n and (s[i + 1 : i + 2].isdigit()) else (1, i + 1)
            track.emit(0x46, (-v) & 0xFF)
            return j
        if c == ord("q"):
            v, j = num(i + 1)
            track.emit(0x44, v & 0xFF)
            return j
        if c == ord("k"):
            v, j = num(i + 1)
            track.emit(0x48, v & 0xFF)
            return j
        if c == ord("s"):
            v, j = num(i + 1)
            track.emit(0x4B, v & 0xFF)
            return j
        if c == ord("m"):
            v, j = num(i + 1)
            track.emit(0x4C, v & 0xFF, (v >> 8) & 0xFF)
            return j
        if c == ord("n"):
            v, j = num(i + 1)
            track.emit(0x4D, v & 0xFF)
            return j
        if c == ord("\\"):
            v, j = num(i + 1)
            # Measured: on PSG/SCC tracks (1-8) MGSC stores the
            # detune negated; on FM tracks (9-17) as written.
            if 1 <= track.number <= 8:
                v = -v
            track.emit(0x50, v & 0xFF)
            return j
        if c == ord("p"):
            v, j = num(i + 1)
            track.emit(0x52, v & 0xFF)
            return j
        if c == ord("_"):
            # glide: _ must be followed by [octave ops] note; the note
            # itself carries 53 nn first (nn = its pitch class form)
            j = i + 1
            # optional octave shifts before the note letter
            octv = track.octave
            while j < n and s[j] in (ord(">"), ord("<")):
                octv += 1 if s[j] == ord(">") else -1
                j += 1
            if j >= n or s[j] not in NOTE_CLASS:
                raise MgsExcError("_ must be followed by a note")
            cls = NOTE_CLASS[s[j]]
            acc = 0
            k = j + 1
            while k < n and s[k] in (ord("+"), ord("#"), ord("-")):
                acc += 1 if s[k] in (ord("+"), ord("#")) else -1
                k += 1
            absolute = octv * 12 + cls + acc
            o2, cls2 = divmod(absolute, 12)
            track.emit(0x53, cls2)
            if o2 != track.octave:
                track.emit(0xD0 | ((o2 - 1) & 0xF))
                track.octave = o2
            steps, k = self._length(s, k, track.deflen)
            steps, k = self._tie_chain(s, k, steps, track.deflen)
            if steps == track.deflen:
                track.emit(0x30 | cls2)
            else:
                track.emit(0x20 | cls2, _len_byte(steps))
            return k
        if c == ord("h"):
            # h<n1>,<n2>,<n3>,<n4> or ho/hf/hi
            if s[i + 1 : i + 2] == b"o":
                track.emit(0x5A, 0x01)
                return i + 2
            if s[i + 1 : i + 2] == b"f":
                track.emit(0x5A, 0x00)
                return i + 2
            if s[i + 1 : i + 2] == b"i":
                track.emit(0x64)
                return i + 2
            j = i + 1
            vals = []
            for k in range(4):
                v, j = num(j)
                vals.append(v)
                if k < 3:
                    if j < n and s[j] == ord(","):
                        j += 1
            track.emit(0x54, (1 + vals[0]) & 0xFF, vals[1] & 0xFF, (1 + vals[2]) & 0xFF, vals[3] & 0xFF)
            return j
        if c == ord("y"):
            r_, j = num(i + 1)
            if j < n and s[j] == ord(","):
                j += 1
            d_, j = num(j)
            track.emit(0x5C, r_ & 0xFF, d_ & 0xFF)
            return j
        if c == ord("/"):
            v, j = num(i + 1)
            if 1 <= track.number <= 3:
                track.emit(0xE0 | (v & 3))  # PSG: tone/noise mode
            elif track.number >= 9 and not _is_rhythm(track, self.opll_mode):
                track.emit(0x4A)  # FM: forced key off, parameter ignored
            # SCC and rhythm tracks: no-op per MGSC111.DOC
            return j
        if c == ord("$"):
            track.emit(0x5D)
            return i + 1
        if c == ord("!"):
            track.ignored = True
            return n
        if c == ord("["):
            return self._loop_start(track, s, i)
        if c == ord("]"):
            return self._loop_end(track, s, i)
        if c == ord("|"):
            return self._loop_exit(track, s, i)
        if c == ord("*"):
            j = i + 1
            if j < n and s[j : j + 1].isalpha() and not s[j : j + 1].isdigit():
                off = self.macro_offsets.get(s[j], 0)
                j += 1
                v, j = num(j) if j < n and s[j : j + 1].isdigit() else (0, j)
                mnum = off + v
            else:
                mnum, j = num(j)
            body = self.macros.get(mnum)
            if body is None:
                raise MgsExcError(f"undefined macro *{mnum}")
            self._compile_mml(track, body, depth + 1)
            return j
        if c == ord("@"):
            return self._at_command(track, s, i)
        if c == ord("&"):
            track.emit(0x40)
            return i + 1
        raise MgsExcError(f"unsupported MML command {chr(c)!r} in track {track.number}")

    def _at_command(self, track: _Track, s: bytes, i: int) -> int:
        n = len(s)
        j = i + 1
        if j >= n:
            raise MgsExcError("lone @")
        c2 = s[j]
        if c2 == ord("\\"):
            v, j = _signed_num(s, j + 1)
            if track.number >= 9 and self.opll_mode == 0 or track.number > 8:
                track.emit(0x5F, v & 0xFF)  # FM fine detune (unsigned)
            else:
                track.emit(0x51, v & 0xFF, (v >> 8) & 0xFF)
            return j
        if c2 == ord("e") or c2 == ord("r"):
            v, j = _macro_style_num(self, s, j + 1)
            if 1 <= track.number <= 3:
                # On PSG tracks @e behaves like @ (patch change).
                if v < 16:
                    track.emit(0x80 | v)
                else:
                    track.emit(0x90 | (v - 16))
            else:
                track.emit(0x49, v & 0xFF)
            return j
        if c2 == ord("p"):
            v, j = _signed_num(s, j + 1)
            track.emit(0x55, v & 0xFF, (v >> 8) & 0xFF)
            return j
        if c2 == ord("m"):
            v, j = _macro_style_num(self, s, j + 1, default_next=True)
            track.emit(0x60, v & 0xFF)
            return j
        if c2 == ord("o"):
            v, j = _macro_style_num(self, s, j + 1)
            self.at_o_offset = v
            track.emit(0x61, v & 0xFF)
            return j
        if c2 == ord("f"):
            track.emit(0x63)
            return j + 1
        if c2 == ord("l"):
            v, j = _signed_num(s, j + 1)
            track.emit(0x5C, 2, v & 0xFF)  # @l<n> == y2,<n>
            return j
        # @<number>: patch change
        v, j = _macro_style_num(self, s, j)
        if v < 16:
            track.emit(0x80 | v)
        else:
            track.emit(0x90 | (v - 16))
        return j

    # -- loops -----------------------------------------------------------------
    # Offset semantics measured from oracle outputs (2026-10-31):
    #   '[' payload (signed 16-bit LE) = pos(']') - pos('[') - 3
    #   ']' payload = (pos('[') + 1) - pos(']')   (negative, jumps back)
    #   '|' payload = (pos(']') + 1) - (pos('|') + 3)
    def _loop_start(self, track: _Track, s: bytes, i: int) -> int:
        j = i + 1
        count = 2
        if j < len(s) and s[j : j + 1].isdigit():
            k = j
            while k < len(s) and s[k : k + 1].isdigit():
                k += 1
            count = int(s[j:k])
            j = k
        stack = track.__dict__.setdefault("_loops", [])
        pos = len(track.data)
        track.emit(0x57, count & 0xFF, 0, 0)
        stack.append({"start": pos, "exit_patch": None})
        return j

    def _loop_exit(self, track: _Track, s: bytes, i: int) -> int:
        stack = track.__dict__.get("_loops") or []
        if not stack:
            raise MgsExcError("| outside loop")
        pos = len(track.data)
        track.emit(0x58, 0, 0)
        stack[-1]["exit_patch"] = pos
        return i + 1

    def _loop_end(self, track: _Track, s: bytes, i: int) -> int:
        j = i + 1
        # trailing count form: ]<n> overrides the [ count
        override = None
        if j < len(s) and s[j : j + 1].isdigit():
            k = j
            while k < len(s) and s[k : k + 1].isdigit():
                k += 1
            override = int(s[j:k])
            j = k
        stack = track.__dict__.get("_loops") or []
        if not stack:
            raise MgsExcError("] without [")
        info = stack.pop()
        start = info["start"]
        if override is not None:
            track.data[start + 1] = override & 0xFF
        pos = len(track.data)
        track.emit(0x59, 0x00, 0, 0)

        def put16(at: int, value: int) -> None:
            track.data[at] = value & 0xFF
            track.data[at + 1] = (value >> 8) & 0xFF

        put16(start + 2, pos - start - 3)  # '[' payload
        put16(pos + 2, (start + 1) - pos)  # ']' payload
        if info.get("exit_patch") is not None:
            ep = info["exit_patch"]
            put16(ep + 1, (pos + 1) - (ep + 3))  # '|' payload
        return j

    # -- assembly ---------------------------------------------------------------
    def _assemble(self) -> bytes:
        out = bytearray()
        out += b"\x00GS313\r\n" if self.truncated else b"MGS313\r\n"
        if self.title:
            out += self.title + b"\r\n"
        out += b"\x1a"
        mode_byte = (
            (self.disenable_mgsrc << 6)
            | ((self.machine_id & 7) << 3)
            | ((self.lfo_mode & 1) << 1)
            | (self.opll_mode & 1)
        )
        header = bytearray()
        header.append(0x00)
        header.append(mode_byte)
        header += bytes((self.tempo & 0xFF, (self.tempo >> 8) & 0xFF))
        offsets_at = len(header)
        # 18 track offsets plus one trailing zero word: oracle files
        # place the first track at offset 42, not 40.
        header += b"\x00\x00" * 19
        body = bytearray()
        offsets: list[int] = []
        for tnum in range(18):
            track = self.tracks[tnum]
            if track.started:
                offsets.append(len(header) + len(body))
                body += track.data
                body.append(0xFF)
            else:
                offsets.append(0)
        for idx, off in enumerate(offsets):
            header[offsets_at + 2 * idx] = off & 0xFF
            header[offsets_at + 2 * idx + 1] = (off >> 8) & 0xFF
        out += header
        out += body
        # MGSC writes in 128-byte records; the observable file is
        # zero-padded to a multiple of 128 bytes.
        pad = (-len(out)) % 128
        out += b"\x00" * pad
        return bytes(out)


class _EndOfSource(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _designator_track(ch: int, opll_mode: int) -> int:
    if ord("1") <= ch <= ord("9"):
        return ch - ord("0")
    if ord("a") <= ch <= ord("h"):
        return ch - ord("a") + 10
    if ch == ord("r"):
        return 15
    raise MgsExcError(f"bad track designator {chr(ch)!r}")


def _is_rhythm(track: _Track, opll_mode: int) -> bool:
    return opll_mode == 1 and track.number == 15


def _brace_body(line: bytes) -> bytes:
    """Return the content of the first balanced { ... } group.

    MGSC ends a definition at its closing brace and ignores any
    trailing garbage on the line (observed in fixture files)."""
    start = line.find(b"{")
    if start < 0:
        raise MgsExcError("missing { in definition")
    depth = 0
    in_str = False
    i = start
    while i < len(line):
        c = line[i]
        if in_str:
            if c == 0x22:
                if i + 1 < len(line) and line[i + 1] == 0x22:
                    i += 2
                    continue
                in_str = False
        else:
            if c == 0x22:
                in_str = True
            elif c == 0x7B:
                depth += 1
            elif c == 0x7D:
                depth -= 1
                if depth == 0:
                    return line[start + 1 : i]
        i += 1
    raise MgsExcError("unbalanced { in definition")


def _extract_title(rest: bytes) -> bytes:
    parts = re.findall(rb'"((?:[^"]|"")*)"', rest, re.DOTALL)
    if not parts:
        return b""
    joined = b"\r\n".join(parts)
    return joined.replace(b'""', b'"')


def _alloc_tracks(rest: bytes) -> list[int]:
    body = rest.strip()
    if body.startswith(b"{"):
        body = body[1 : body.rfind(b"}")]
    out = []
    for part in body.split(b","):
        part = part.strip()
        if not part:
            continue
        head = part.split(b"=")[0].strip().lower()
        if len(head) == 1:
            if head == b"0":
                out.append(0)
            else:
                out.append(_designator_track(head[0], 0))
    return out


def _extract_numbers(body: bytes) -> list[int]:
    body = body.strip()
    if body.startswith(b"{"):
        body = body[1 : body.rfind(b"}")]
    body = _strip_comment(body)
    out = []
    for tok in re.split(rb"[,\s]+", body):
        if tok:
            out.append(_parse_int(tok, "number list"))
    return out


def _extract_quoted(body: bytes) -> bytes:
    m = re.search(rb'"((?:[^"]|"")*)"', body, re.DOTALL)
    if not m:
        raise MgsExcError("quoted string expected")
    return m.group(1).replace(b'""', b'"')


def _unescape_at_m(payload: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(payload):
        c = payload[i]
        if c == 0x5C and i + 1 < len(payload):  # backslash
            nxt = payload[i + 1]
            if nxt == ord("x") and i + 3 < len(payload) + 1:
                out.append(int(payload[i + 2 : i + 4], 16))
                i += 4
                continue
            if nxt == 0x5C:
                out.append(0x5C)
            elif nxt == 0x22:
                out.append(0x22)
            else:
                out.append((nxt & 0xFF) - 0x40 if nxt >= 0x40 else nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


def _split_top(body: bytes) -> list[bytes]:
    return body.split(b",")


def _signed_num(s: bytes, i: int) -> tuple[int, int]:
    sign = 1
    if i < len(s) and s[i] == ord("-"):
        sign = -1
        i += 1
    elif i < len(s) and s[i] == ord("+"):
        i += 1
    j = i
    while j < len(s) and s[j : j + 1].isdigit():
        j += 1
    if j == i:
        raise MgsExcError("number expected")
    return sign * int(s[i:j]), j


def _macro_style_num(comp: _Compiler, s: bytes, i: int, default_next: bool = False) -> tuple[int, int]:
    """Number that may use a #macro_offset letter form (e.g. @ea8)."""
    if i < len(s) and s[i : i + 1].isalpha():
        off = comp.macro_offsets.get(s[i], 0)
        i += 1
        if i < len(s) and s[i : i + 1].isdigit():
            v, i = _signed_num(s, i)
            return off + v, i
        return off, i
    if i < len(s) and s[i : i + 1].isdigit():
        return _signed_num(s, i)
    if default_next:
        v = comp.at_m_next + 1
        comp.at_m_next = v
        return v + comp.at_o_offset, i
    raise MgsExcError("number expected after @")


def _pack_opll_voice(vals: list[int]) -> bytes:
    """Pack the 24-parameter @v form into the 8-byte OPLL voice.

    Layout per MGSC111.DOC: TL, FB, then per operator
    AR DR SL RR KL MT AM VB EG KR DT (modulator, then carrier).
    Byte packing measured from oracle outputs (2026-10-31):
      [0] mod: AM<<7 | VB<<6 | EG<<5 | KR<<4 | MT
      [1] car: same
      [2] KL_mod<<6 | TL
      [3] KL_car<<6 | DT_car<<4 | DT_mod<<3 | FB
      [4] AR_mod<<4 | DR_mod   [5] AR_car<<4 | DR_car
      [6] SL_mod<<4 | RR_mod   [7] SL_car<<4 | RR_car
    DT is a single bit (0 or 1); values above 1 are invalid in MGSC.
    """
    if len(vals) != 24:
        raise MgsExcError(f"@v needs 24 parameters, got {len(vals)}")
    tl, fb = vals[0], vals[1]
    mod = vals[2:13]
    car = vals[13:24]

    def flags(o: list[int]) -> int:
        _ar, _dr, _sl, _rr, _kl, mt, am, vb, eg, kr, _dt = o
        return ((am & 1) << 7) | ((vb & 1) << 6) | ((eg & 1) << 5) | ((kr & 1) << 4) | (mt & 0xF)

    return bytes(
        [
            flags(mod),
            flags(car),
            ((mod[4] & 3) << 6) | (tl & 0x3F),
            ((car[4] & 3) << 6) | ((car[10] & 1) << 4) | ((mod[10] & 1) << 3) | (fb & 7),
            ((mod[0] & 0xF) << 4) | (mod[1] & 0xF),
            ((car[0] & 0xF) << 4) | (car[1] & 0xF),
            ((mod[2] & 0xF) << 4) | (mod[3] & 0xF),
            ((car[2] & 0xF) << 4) | (car[3] & 0xF),
        ]
    )


def _compile_envelope_data(parts: list[bytes]) -> bytes:
    # The data tail is a continuous item stream; commas, dots and
    # whitespace separate items, except the comma inside y<r>,<d>
    # which belongs to the item. Scan it directly.
    tail = b",".join(parts).lower()
    out = bytearray()
    i = 0
    n = len(tail)
    while i < n:
        if tail[i] in b" \t\r\n,.":
            i += 1
            continue
        i = _envelope_item_at(out, tail, i)
    return bytes(out)


def _envelope_item_at(out: bytearray, tok: bytes, i: int) -> int:
    n = len(tok)
    c = tok[i]
    if c == ord("["):
        out.append(0x40)
        return i + 1
    if c == ord("]"):
        out.append(0x60)
        return i + 1
    if c in b"0123456789abcdef" and i + 1 < n and tok[i + 1] in (ord(":"), ord("=")):
        vol = int(chr(c), 16)
        op = tok[i + 1]
        j = i + 2
        k = j
        while k < n and tok[k : k + 1].isdigit():
            k += 1
        count = int(tok[j:k])
        out.append(((0xE0 if op == ord(":") else 0x20) | vol))
        out.append(count & 0xFF)
        return k
    if c == ord("n"):
        v, j = _signed_num(tok, i + 1)
        out.append(0x80 | (v & 0x1F))
        return j
    if c in (ord("/"), ord("*")):
        v, j = _signed_num(tok, i + 1)
        out.append(0xA0 | (v & 3))
        return j
    if c == ord("@"):
        v, j = _signed_num(tok, i + 1)
        out.append(0x10)
        out.append(v & 0xFF)
        return j
    if c == ord("y"):
        r_, j = _signed_num(tok, i + 1)
        if j < n and tok[j] == ord(","):
            j += 1
        d_, j = _signed_num(tok, j)
        out.append(0x11)
        out.append(r_ & 0xFF)
        out.append(d_ & 0xFF)
        return j
    if c == 0x5C:  # backslash detune
        v, j = _signed_num(tok, i + 1)
        out.append(0x12)
        out.append(v & 0xFF)
        return j
    if c in b"0123456789abcdef":
        out.append(int(chr(c), 16))
        return i + 1
    raise MgsExcError(f"bad envelope item near: {tok[i:i + 16]!r}")


# ---------------------------------------------------------------------------
# Tempo frame table
# ---------------------------------------------------------------------------

_TEMPO_TABLES: dict[int, bytes] | None = None


def tempo_frame_table(tempo: int) -> bytes:
    """The 48-byte table MGSC appends to a `t` command.

    Behavior data extracted from the reference compiler's output
    for every tempo in range (py/mgsexc_tempo_data.py), pending a
    fitted generating formula."""
    global _TEMPO_TABLES
    if _TEMPO_TABLES is None:
        from mgsexc_tempo_data import load_tables

        _TEMPO_TABLES = load_tables()
    table = _TEMPO_TABLES.get(tempo)
    if table is None:
        raise MgsExcError(f"tempo {tempo} out of range 57..2047")
    return table


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compile_mml(source: bytes) -> bytes:
    comp = _Compiler()
    try:
        return comp.compile(source)
    except _EndOfSource:
        return comp._assemble()

