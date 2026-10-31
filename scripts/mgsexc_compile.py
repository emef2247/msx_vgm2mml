#!/usr/bin/env python3
"""MGSEXC CLI: compile MML to MGS without the 16 KB pool.

Usage: python3 scripts/mgsexc_compile.py INPUT.mml OUTPUT.mgs
Interface mirrors scripts/compile_mgs.mjs so callers can swap.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py"))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: mgsexc_compile.py INPUT.mml OUTPUT.mgs", file=sys.stderr)
        return 2
    import mgsexc

    data = mgsexc.compile_mml(Path(argv[0]).read_bytes())
    Path(argv[1]).write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
