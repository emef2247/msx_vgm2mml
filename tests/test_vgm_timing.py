"""Source sample evidence must survive rounding and use a shared chip origin."""
import csv
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_reader import parse_vgm
from vgm_timing import command_times
from opll import _build_segments
from psg import build_segments as build_psg
from scc import build_segments as build_scc
from test_vgm_loop import vgm


def rows(path):
    with open(path, newline='') as stream:
        return list(csv.DictReader(stream))


class VgmTimingTests(unittest.TestCase):
    def test_all_short_and_fixed_waits_and_override(self):
        commands = (bytes(range(0x70, 0x80)) + bytes(range(0x80, 0x90))
                    + b'\x61\x34\x12\x62\x63\x64\x62\x07\x00\x62\x66')
        records = list(command_times(vgm(commands)))
        self.assertEqual(records[-1].vgmticks, sum(range(1, 17)) + sum(range(16))
                         + 0x1234 + 735 + 882 + 7)
        self.assertEqual([r.wait_samples for r in records[:16]], list(range(1, 17)))

    def test_data_block_payload_and_writes_are_not_waits(self):
        payload = b'\x77\x7a\x51\x62\x66'
        commands = (b'\x67\x66\x00' + struct.pack('<I', len(payload)) + payload
                    + b'\x51\x10\x77\x62\x66')
        records = list(command_times(vgm(commands)))
        self.assertEqual([r.command for r in records], [0x67, 0x51, 0x62, 0x66])
        self.assertEqual(records[-1].vgmticks, 735)

    def test_unknown_truncated_and_missing_end_are_rejected(self):
        for commands in (b'\x01\x66', b'\x61', b'\x62'):
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                list(command_times(vgm(commands)))

    def test_shared_absolute_origin_and_integer_segments(self):
        # All three first writes occur after a wait. Simultaneous events must
        # share a timestamp even though each chip begins at a different time.
        commands = (b'\x62\xa0\x08\x0a\x77\x51\x20\x10\x7a'
                    b'\xd2\x02\x00\x0f\x51\x20\x00\xa0\x08\x00'
                    b'\x70\xd2\x02\x00\x00\x66')
        raw = bytearray(vgm(commands))
        struct.pack_into('<I', raw, 0x9c, 3579545)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'clock.vgm'
            path.write_bytes(raw)
            paths = parse_vgm(str(path), folder, include_vgmticks=True)
            psg, scc, opll = [rows(paths[i]) for i in (2, 3, 5)]
            self.assertEqual([int(r['vgmticks']) for r in psg], [735, 754])
            self.assertEqual([int(r['vgmticks']) for r in opll], [743, 754])
            self.assertEqual([int(r['vgmticks']) for r in scc], [754, 755])
            for r in psg + scc + opll:
                self.assertEqual(float(r['time']), int(r['vgmticks']) / 44100)
            melodic, _ = _build_segments(paths[5])
            self.assertEqual((melodic[0][0].vgmticks, melodic[0][0].vgmticks_end), (743, 754))
            self.assertEqual(melodic[0][0].tick_start, melodic[0][0].tick_end)
            # Positive physical duration can coexist with zero 60 Hz length.
            self.assertGreater(melodic[0][0].vgmticks_end, melodic[0][0].vgmticks)
            ps = build_psg(paths[2], folder, stem='clock', dump_passes=True)[0]
            sc = build_scc(paths[3], folder, stem='clock', dump_passes=True).segments[0]
            self.assertEqual((ps[0].vgmticks, ps[0].vgmticks_end), (735, 754))
            self.assertEqual((sc[0].vgmticks, sc[0].vgmticks_end), (754, 755))
            self.assertEqual(ps[-1].vgmticks, ps[-1].vgmticks_end)
            self.assertEqual(sc[-1].vgmticks, sc[-1].vgmticks_end)
            for chip in ('psg', 'scc'):
                for stage in range(4):
                    evidence = rows(Path(folder) / f'clock.{chip}.pass{stage}.csv')
                    self.assertIsNone(evidence[0].get(None), 'CSV columns shifted')
                    self.assertIn('vgmticks', evidence[0])

    def test_optional_evidence_does_not_change_clock_or_render_inputs(self):
        commands = b'\x62\x51\x10\x77\x77\x51\x20\x10\x7a\x51\x20\x00\x66'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'clock.vgm'
            path.write_bytes(vgm(commands))
            old = parse_vgm(str(path), str(Path(folder) / 'plain'))
            new = parse_vgm(str(path), str(Path(folder) / 'source'), include_vgmticks=True)
            self.assertEqual([{k: v for k, v in row.items() if k} for row in rows(old[5])],
                             [{k: v for k, v in row.items() if k and k != 'vgmticks'}
                              for row in rows(new[5])])
            plain, _ = _build_segments(old[5])
            enriched, _ = _build_segments(new[5])
            for a, b in zip(plain[0], enriched[0]):
                for field in ('time', 'ticks', 'l', 'key_on_edge', 'fnum', 'block', 'vol'):
                    self.assertEqual(getattr(a, field), getattr(b, field))
                self.assertIsNone(a.vgmticks)
                self.assertIsNotNone(b.vgmticks)


if __name__ == '__main__':
    unittest.main()
