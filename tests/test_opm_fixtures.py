"""Check public migrated OPM patterns against their actual source writes."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/public/opm/from_fm'
sys.path.insert(0, str(ROOT / 'py'))
from opm import build_segments, key_counts
from vgm_io import read_vgm_bytes
from vgm_reader import parse_vgm
from vgm_timing import command_times
from test_opm_reader import read_rows


def source_writes(path):
    raw = read_vgm_bytes(path)
    events = list(command_times(raw))
    writes = [(i, e.address, e.vgmticks, raw[e.address + 1], raw[e.address + 2])
              for i, e in enumerate(events) if e.command == 0x54]
    return writes, events[-1].vgmticks


def source_key_counts(writes):
    masks = [0] * 8
    key_writes = attacks = on = off = 0
    channels = set()
    for _, _, _, register, data in writes:
        if register != 8:
            continue
        ch, mask = data & 7, data >> 3 & 15
        before = masks[ch]
        added, removed = mask & ~before, before & ~mask
        key_writes += 1
        attacks += bool(added)
        on += added.bit_count()
        off += removed.bit_count()
        masks[ch] = mask
        channels.add(ch)
    return {'key_writes': key_writes, 'channel_attack_events': attacks,
            'operator_keyons': on, 'operator_keyoffs': off}, channels


@unittest.skipUnless(FIXTURES.exists(), 'Public OPM fixtures are not installed')
class OpmFixtureTests(unittest.TestCase):
    def test_all_migrated_patterns_preserve_source_state_edges_and_intervals(self):
        paths = sorted(FIXTURES.glob('*/*.vgm'))
        self.assertEqual(len(paths), 16)
        with tempfile.TemporaryDirectory() as temp:
            for source in paths:
                with self.subTest(case=source.stem):
                    metadata = {}
                    parse_vgm(str(source), str(Path(temp) / source.stem),
                              opm_metadata=metadata, dump_opm_segments=True)
                    expected, end = source_writes(source)
                    raw_rows = read_rows(metadata['csv_path'])
                    self.assertEqual([(int(r['event_id']), int(r['address']), int(r['vgmticks']),
                                       int(r['register']), int(r['data'])) for r in raw_rows], expected)
                    self.assertEqual(metadata['source_end_vgmticks'], end)
                    analysis = build_segments(metadata['csv_path'], end_vgmticks=end)
                    counts, _ = source_key_counts(expected)
                    self.assertEqual(key_counts(analysis), counts)
                    self.assertEqual(sum(s.rising_mask.bit_count() for s in analysis.segments),
                                     counts['operator_keyons'])
                    self.assertEqual(sum(s.falling_mask.bit_count() for s in analysis.segments),
                                     counts['operator_keyoffs'])

                    # Independent raw-register oracle for every state boundary.
                    states = {}
                    for source_id, _, tick, register, data in expected:
                        affected = [e for e in analysis.events if e.source_event_id == source_id]
                        if register != 8:
                            states[register] = data
                        channels = [data & 7] if register == 8 else list(range(8)) \
                            if register < 0x20 else [register & 7]
                        self.assertEqual([e.ch for e in affected], channels)
                        for event in affected:
                            state = event.state
                            self.assertEqual(event.vgmticks, tick)
                            self.assertEqual(dict(state.channel_registers),
                                             {r: v for r, v in states.items() if r >= 0x20 and r % 8 == event.ch})
                            self.assertEqual(dict(state.shared_registers),
                                             {r: v for r, v in states.items() if r < 0x20})
                            for bank, operator in enumerate(state.operators):
                                tl = states.get(0x60 + 8 * bank + event.ch)
                                self.assertEqual(operator.tl, None if tl is None else tl & 127)
                            if register != 8:
                                self.assertEqual((event.rising_mask, event.falling_mask), (0, 0))

                    for ch in range(8):
                        segments = [s for s in analysis.segments if s.ch == ch]
                        self.assertEqual(segments[0].vgmticks, 0)
                        self.assertEqual(segments[-1].vgmticks_end, end)
                        self.assertEqual(sum(s.duration_samples for s in segments), end)
                        self.assertTrue(all(a.vgmticks_end == b.vgmticks for a, b in zip(segments, segments[1:])))
                    dumped = read_rows(metadata['segments_csv_path'])
                    self.assertEqual(len(dumped), len(analysis.segments))
                    self.assertTrue(all(None not in row for row in dumped))


if __name__ == '__main__':
    unittest.main()
