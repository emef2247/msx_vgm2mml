#!/usr/bin/env python3
"""Differential check: MGSEXC vs the MGSC oracle (mgsc-js).

Usage:
    python3 scripts/check_mgsexc.py FILE.mml [FILE.mml ...]
    python3 scripts/check_mgsexc.py --dir DIR   (all *.mml under DIR)

For each MML, compiles with scripts/compile_mgs.mjs (oracle) and with
py/mgsexc.py, then compares the MGS bytes. Exit code 0 iff every
input is byte-identical or the oracle itself fails (reported as
ORACLE-FAIL, which is the class MGSEXC exists to cover).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py"))


def compile_oracle(mml: Path, out: Path) -> bool:
    r = subprocess.run(
        ["node", str(ROOT / "scripts" / "compile_mgs.mjs"), str(mml), str(out)],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and out.exists()


def compile_mgsexc(mml: Path, out: Path) -> tuple[bool, str]:
    import mgsexc

    try:
        data = mgsexc.compile_mml(mml.read_bytes())
    except Exception as e:  # noqa: BLE001 - report any compiler failure
        return False, f"{type(e).__name__}: {e}"
    out.write_bytes(data)
    return True, ""


def first_diff(a: bytes, b: bytes) -> str:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            lo = max(0, i - 8)
            return (
                f"first diff at {i} (0x{i:x}): oracle {a[lo:i+8].hex(' ')} "
                f"vs mgsexc {b[lo:i+8].hex(' ')}"
            )
    return f"common prefix {n} bytes, sizes {len(a)} vs {len(b)}"


def main(argv: list[str]) -> int:
    files: list[Path] = []
    if argv[:1] == ["--dir"]:
        files = sorted(Path(argv[1]).rglob("*.mml"))
    else:
        files = [Path(a) for a in argv]
    if not files:
        print("no MML files given", file=sys.stderr)
        return 2

    ok = fail = oracle_fail = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for mml in files:
            oracle_out = td / "oracle.mgs"
            exc_out = td / "exc.mgs"
            if not compile_oracle(mml, oracle_out):
                print(f"ORACLE-FAIL {mml}")
                oracle_fail += 1
                continue
            good, err = compile_mgsexc(mml, exc_out)
            if not good:
                print(f"MGSEXC-FAIL {mml}: {err}")
                fail += 1
                continue
            a, b = oracle_out.read_bytes(), exc_out.read_bytes()
            if a == b:
                print(f"IDENTICAL   {mml} ({len(a)} bytes)")
                ok += 1
            else:
                print(f"DIFF        {mml}: {first_diff(a, b)}")
                fail += 1
    print(f"summary: identical={ok} diff/fail={fail} oracle-fail={oracle_fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
