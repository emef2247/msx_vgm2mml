"""Grouping and repeat extraction must preserve every source hit and tick."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from rhythm_patterns import STATE_FIELDS, group_segments, find_patterns, dump_analysis


def segment(tick, volume=3, **changes):
    fields = dict(ev_type='rhythm_expand', is_ryt=1, keyon=1, time=tick / 60,
                  tick_start=tick, tick_end=tick + 1,
                  **{field: 0 for field in STATE_FIELDS})
    fields['vol'] = volume
    fields.update(changes)
    return SimpleNamespace(**fields)


class RhythmPatterns(unittest.TestCase):
    def test_groups_retain_duplicate_hits_and_source_indices(self):
        segments = {9: [segment(2), segment(2), segment(5, keyon=0)],
                    12: [segment(2), segment(8)]}
        before = repr(segments)
        groups = group_segments(segments)
        self.assertEqual([(g.tick, g.gap) for g in groups], [(2, 6), (8, None)])
        self.assertEqual([(h.channel, h.segment_index) for h in groups[0].hits],
                         [(9, 0), (9, 1), (12, 0)])
        self.assertEqual(repr(segments), before)

    def test_exact_repeats_roundtrip_including_initial_gap_and_tail(self):
        groups = group_segments({9: [segment(t) for t in (4, 20, 36)],
                                 13: [segment(t) for t in (12, 28, 44)]})
        patterns, occurrences = find_patterns(groups)
        self.assertTrue(any(o.repeats > 1 for o in occurrences))
        expanded = [key for o in occurrences for _ in range(o.repeats)
                    for key in patterns[o.pattern_id]]
        self.assertEqual(expanded, [g.signature() for g in groups])
        tick = groups[0].tick
        ticks = []
        for gap, _ in expanded:
            ticks.append(tick)
            tick += gap or 0
        self.assertEqual(ticks, [4, 12, 20, 28, 36, 44])
        self.assertIsNone(expanded[-1][0])

    def test_volume_pitch_and_single_tick_difference_prevent_match(self):
        for change in ({'vol': 4}, {'fnum_ch7': 10}, {'tick_end': 10}):
            with self.subTest(change=change):
                groups = group_segments({9: [segment(0), segment(8, **change), segment(16)]})
                self.assertNotEqual(groups[0].signature(), groups[1].signature())
        groups = group_segments({9: [segment(t) for t in (0, 8, 17)]})
        self.assertNotEqual(groups[0].signature(), groups[1].signature())

    def test_empty_and_single_hit(self):
        self.assertEqual(find_patterns(group_segments({})), ((), ()))
        patterns, occurrences = find_patterns(group_segments({9: [segment(3)]}))
        self.assertEqual(len(patterns), 1)
        self.assertEqual(occurrences[0].repeats, 1)

    def test_sample_cli_csvs_reconstruct_groups_and_source_hits(self):
        fixture = ROOT / 'tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm'
        if not fixture.exists():
            self.skipTest('Sample fixture not installed')
        with tempfile.TemporaryDirectory() as folder:
            run = subprocess.run([sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                                  '--outdir', folder, '--dump-passes'],
                                 capture_output=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            def read(suffix):
                with (Path(folder) / ('sample.opll.' + suffix + '.csv')).open(newline='') as stream:
                    return list(csv.DictReader(stream))
            groups = read('rhythm.groups')
            definitions = read('rhythm.patterns')
            occurrences = read('rhythm.occurrences')
            sources = {}
            for row in read('segments'):
                sources.setdefault(int(row['ch']), []).append(row)
            refs = []
            for group in groups:
                for hit in json.loads(group['hits']):
                    ref = (hit['channel'], hit['segment_index'])
                    refs.append(ref)
                    source = sources[ref[0]][ref[1]]
                    self.assertEqual(group['tick'], source['tick_start'])
                    self.assertEqual(hit['source_time'], float(source['time']))
                    for field in STATE_FIELDS:
                        self.assertEqual(hit[field], int(source[field]))
            expected = [(ch, i) for ch in range(9, 14)
                        for i, row in enumerate(sources.get(ch, []))
                        if row['keyon'] == '1' and row['is_ryt'] == '1']
            self.assertCountEqual(refs, expected)
            expanded = []
            for occurrence in occurrences:
                pattern = [r for r in definitions if r['pattern_id'] == occurrence['pattern_id']]
                tick = int(occurrence['tick_start'])
                self.assertEqual(int(occurrence['group_start']), len(expanded))
                for _ in range(int(occurrence['repeats'])):
                    for row in pattern:
                        expanded.append((tick, row['gap_ticks'], json.loads(row['hits'])))
                        tick += int(row['gap_ticks'] or 0)
            actual = []
            for group in groups:
                hits = [{k: v for k, v in hit.items()
                         if k not in ('channel', 'segment_index', 'source_time')}
                        for hit in json.loads(group['hits'])]
                actual.append((int(group['tick']), group['gap_ticks'], hits))
            self.assertEqual(expanded, actual)
            self.assertTrue(any(int(o['repeats']) > 1 for o in occurrences))
