#!/usr/bin/env python3
"""Black-box probes against the MGSC oracle for MGSEXC development.

Compiles small MML snippets with scripts/compile_mgs.mjs and prints
the decoded track streams, so encoding rules can be read off the
observable output. Usage: python3 scripts/probe_mgsexc.py [name ...]
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def compile_oracle(mml: str) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "probe.mml"
        out = Path(td) / "probe.mgs"
        src.write_bytes(mml.encode("ascii"))
        r = subprocess.run(
            ["node", str(ROOT / "scripts" / "compile_mgs.mjs"), str(src), str(out)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise SystemExit(f"oracle failed for {mml!r}: {r.stdout} {r.stderr}")
        return out.read_bytes()


def tracks(data: bytes) -> dict[int, bytes]:
    i = data.find(b"\x1a")
    hdr = data[i + 1 :]
    offs = struct.unpack("<18H", hdr[4:40])
    result = {}
    for tnum, off in enumerate(offs):
        if off:
            end = len(hdr)
            for other in offs:
                if other > off:
                    end = min(end, other)
            result[tnum] = hdr[off:end]
    return result


def show(name: str, mml: str) -> None:
    data = compile_oracle(mml)
    i = data.find(b"\x1a")
    offs = struct.unpack("<18H", data[i + 1 + 4 : i + 1 + 40])
    print(f"== {name}: {mml.strip()!r} -> {len(data)} bytes, offsets={[(t, o) for t, o in enumerate(offs) if o]}")
    for tnum, seg in sorted(tracks(data).items()):
        print(f"  track {tnum}: {seg.hex(' ')}")


PROBES = {
    "track0_empty": "#opll_mode 0\n#tempo 120\n1 c\n",
    "note_forms": "#opll_mode 0\n#tempo 120\n1 o4 l8 c8 c c16 c%48 c4^8 c&c b+ c\n",
    "rest_forms": "#opll_mode 0\n#tempo 120\n1 o4 l8 r8 r r16 r%48\n",
    "loop_basic": "#opll_mode 0\n#tempo 120\n1 o4 l8 [ c d ]3 e\n",
    "loop_exit": "#opll_mode 0\n#tempo 120\n1 o4 l8 [ c | d ] e\n",
    "loop_after": "#opll_mode 0\n#tempo 120\n1 o4 l8 [ c d ] e [ f ]2 g\n",
    "voice_doc": (
        "#opll_mode 0\n#tempo 120\n"
        "@v15 = { 25, 7, 8, 8, 1, 2, 0, 0, 0, 1, 0, 0, 0,"
        " 8, 2, 1, 1, 1, 1, 0, 1, 0, 0, 0 }\n9 @15 c\n"
    ),
    "env_forms": (
        "#opll_mode 0\n#tempo 120\n"
        "@e01 = { 1, 5, f, e:10, 8=20, n4, /2, [ a, ] @3 y1,2 \\-5 }\n"
        "1 @e1 c\n"
    ),
    "accidentals": "#opll_mode 0\n#tempo 120\n1 o4 l8 c c+ c- d- b b+ > c < b+ a- g+\n",
    "accidentals2": "#opll_mode 0\n#tempo 120\n1 o4 l8 b+4 c c- b\n",
    "scc_wave": (
        "#opll_mode 0\n#tempo 120\n"
        "@s00 = {000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f}\n"
        "4 @0 c\n"
    ),
}


def tempo_tables() -> None:
    for tempo in (57, 100, 118, 120, 150, 200, 240, 255, 480):
        data = compile_oracle(f"#opll_mode 0\n#tempo 120\n1 t{tempo} c\n")
        seg = tracks(data)[1]
        assert seg[0] == 0x41
        table = seg[3:51]
        print(f"tempo {tempo}: header={seg[1] | (seg[2] << 8)} table={table.hex(' ')}")


def main(argv: list[str]) -> int:
    names = argv or list(PROBES) + ["tempo"]
    for name in names:
        if name == "tempo":
            tempo_tables()
        else:
            show(name, PROBES[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
