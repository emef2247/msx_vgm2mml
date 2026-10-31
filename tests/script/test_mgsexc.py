"""MGSEXC golden and behavior tests.

The golden byte strings were captured from the reference compiler's
observable output (MGSC via scripts/compile_mgs.mjs) for the same
inputs; MGSEXC must reproduce them exactly. The remaining tests pin
the extension behavior: no 16 KB pool, #alloc values ignored.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py"))

import mgsexc  # noqa: E402

NOTES_MML = b"#opll_mode 0\n#tempo 120\n1 o4 l8 c8 c c16 c%48 c4^8 c&c b+ c\n"
NOTES_MGS = bytes.fromhex("4d47533331330d0a1a0000780000002a0000000000000000000000000000000000000000000000000000000000000000000000d342183030200c203020483040303b30ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")

ENV_MML = b"#opll_mode 0\n#tempo 120\n@e01 = { 1, 5, f, e:10, 8=20, n4, /2, [ a, ] @3 y1,2 \\-5 }\n1 @e1 c\n"
ENV_MGS = bytes.fromhex("4d47533331330d0a1a000078002a00400000000000000000000000000000000000000000000000000000000000000000000000020125110fee0a281484a2400a60100311010212fbff8130ff00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")

LOOP_MML = b"#opll_mode 0\n#tempo 120\n1 o4 l8 [ c | d ] e\n"
LOOP_MGS = bytes.fromhex("4d47533331330d0a1a0000780000002a0000000000000000000000000000000000000000000000000000000000000000000000d342185702060030580200325900f8ff34ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")


class GoldenTest(unittest.TestCase):
    def test_note_forms(self):
        self.assertEqual(mgsexc.compile_mml(NOTES_MML), NOTES_MGS)

    def test_envelope_definition(self):
        self.assertEqual(mgsexc.compile_mml(ENV_MML), ENV_MGS)

    def test_loop_offsets(self):
        self.assertEqual(mgsexc.compile_mml(LOOP_MML), LOOP_MGS)


class ExtensionTest(unittest.TestCase):
    def test_alloc_values_do_not_change_output(self):
        plain = mgsexc.compile_mml(b"#opll_mode 0\n#tempo 120\n1 c d e\n")
        alloc = mgsexc.compile_mml(
            b"#opll_mode 0\n#tempo 120\n#alloc { 1=99999, 2=88888 }\n1 c d e\n"
        )
        # Track 2 is named only by #alloc: like MGSC, it appears as a
        # lone terminator; track 1's stream must be identical.
        import struct

        def track1(data: bytes) -> bytes:
            i = data.find(b"\x1a")
            offs = struct.unpack("<18H", data[i + 1 + 4 : i + 1 + 40])
            seg = data[i + 1 + offs[1] :]
            return seg[: seg.find(b"\xff") + 1]

        self.assertEqual(track1(plain), track1(alloc))
        self.assertEqual(len(alloc), len(plain))

    def test_track_data_beyond_16k_compiles(self):
        line = b"1 " + b" ".join([b"c8"] * 60) + b"\n"
        out = mgsexc.compile_mml(b"#opll_mode 0\n#tempo 120\n" + line * 300)
        self.assertGreater(len(out), 16384)
        self.assertEqual(out[:6], b"MGS313")

    def test_tempo_table_spot_check(self):
        table = mgsexc.tempo_frame_table(120)
        self.assertEqual(len(table), 48)
        self.assertEqual(table[:4], bytes.fromhex("45114511"))
        self.assertEqual(mgsexc.tempo_frame_table(240)[:4], bytes.fromhex("10410104"))


if __name__ == "__main__":
    unittest.main()
