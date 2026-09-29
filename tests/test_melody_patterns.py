"""Exact candidates must reconstruct ordered source intervals without mutation."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from melody_patterns import FIELDS, analyze, dump_analysis, annotate_segments


def segment(chip, tick, duration=4, **changes):
    data = dict.fromkeys(FIELDS[chip], 0)
    data.update(ev_type='note', time=tick / 60, tick_start=tick,
                tick_end=tick + duration, ch=0)
    if chip == 'opll':
        data.update(inst=1, keyon=1, onset=1, fnum=290, block=3)
    data.update(changes)
    return SimpleNamespace(**data)


class MelodyPatterns(unittest.TestCase):
    def test_annotations_preserve_cells_and_handle_channel_indices(self):
        segments = {ch: [segment('opll', 0, duration=0), segment('opll', 0),
                         segment('opll', 4, duration=0), segment('opll', 4)]
                    for ch in (0, 1, 9)}
        original = [dict(ch=str(ch), tick_start=str(s.tick_start),
                         tick_end=str(s.tick_end), evidence='001, raw')
                    for ch, rows in segments.items() for s in rows]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.opll.segments.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=original[0])
                writer.writeheader()
                writer.writerows(original)
            analysis = dump_analysis(segments, 'opll', folder, 'test')
            first = path.read_bytes()
            annotate_segments(path, analysis)
            self.assertEqual(first, path.read_bytes())
            with path.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            for before, after in zip(original, rows):
                self.assertEqual(before, {key: after[key] for key in before})
            self.assertEqual([r['segment_index'] for r in rows], ['0', '1', '2', '3'] * 3)
            self.assertEqual([r['repeat_index'] for r in rows[:4]], ['0', '0', '1', '1'])
            self.assertEqual([r['pattern_step'] for r in rows[:4]], ['0', '1', '0', '1'])
            self.assertTrue(all(r['pattern_repeats'] == '2' for r in rows[:8]))
            self.assertTrue(all(r['pattern_id'] == '' for r in rows[8:]))

    def test_all_chips_roundtrip_and_nonmutation(self):
        for chip in FIELDS:
            rows = [segment(chip, t, **({'fnum': 290 + i % 2} if chip == 'opll'
                                       else {'tone_period': 200 + i % 2}))
                    for i, t in enumerate(range(7, 39, 4))]
            before = repr(rows)
            items, patterns, uses = analyze({0: rows}, chip)[0]
            self.assertEqual(repr(rows), before)
            self.assertEqual([(len(patterns[u.pattern_id]), u.repeats) for u in uses], [(2, 4)])
            expanded = [s for u in uses for _ in range(u.repeats) for s in patterns[u.pattern_id]]
            self.assertEqual(expanded, [s.signature() for s in items])

    def test_every_state_field_and_timing_difference_prevents_match(self):
        for chip, fields in FIELDS.items():
            for field in fields:
                a, b = segment(chip, 0), segment(chip, 4)
                setattr(b, field, 'different')
                if chip == 'opll' and field == 'inst': b.inst = 2
                items, patterns, uses = analyze({0: [a, b]}, chip)[0]
                self.assertTrue(all(u.repeats == 1 for u in uses), (chip, field))
            rows = [segment(chip, 0), segment(chip, 5)]
            self.assertNotEqual(*[s.signature() for s in analyze({0: rows}, chip)[0][0]])
            rows = [segment(chip, 0), segment(chip, 4, duration=5)]
            self.assertNotEqual(*[s.signature() for s in analyze({0: rows}, chip)[0][0]])

    def test_zero_length_events_and_channel_isolation(self):
        rows = [segment('opll', 0, duration=0), segment('opll', 0),
                segment('opll', 4, duration=0), segment('opll', 4)]
        result = analyze({0: rows, 1: rows, 9: rows}, 'opll')
        self.assertEqual(set(result), {0, 1})
        self.assertEqual(result[0][2][0].repeats, 2)
        self.assertEqual([s.segment_index for s in result[0][0]], [0, 1, 2, 3])

    def test_user_patch_content_and_interior_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'voice.csv'
            rows = [segment('opll', 0, inst=0), segment('opll', 4, inst=0)]
            for updates, expected_equal in [([(0, '00'), (4, '01')], False),
                                            ([(0, '00'), (4, '00')], True),
                                            ([(0, '00'), (2, '01'), (4, '00')], False)]:
                with path.open('w', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(('#type', 'ticks', 'patch_hex'))
                    writer.writerows(('patch', t, patch * 8) for t, patch in updates)
                items = analyze({0: rows}, 'opll', path)[0][0]
                self.assertEqual(items[0].signature() == items[1].signature(), expected_equal)
            items = analyze({0: rows}, 'opll')[0][0]
            self.assertNotEqual(items[0].signature(), items[1].signature())

    def test_csv_definitions_occurrences_and_markings_reconstruct_source(self):
        rows = [segment('scc', t, waveform_hex='12' * 32) for t in (10, 14, 18)]
        with tempfile.TemporaryDirectory() as folder:
            dump_analysis({2: rows}, 'scc', folder, 'test')
            def read(suffix):
                with (Path(folder) / f'test.scc.melody.{suffix}.csv').open(newline='') as stream:
                    return list(csv.DictReader(stream))
            defs, uses, marks = read('patterns'), read('occurrences'), read('markings')
            self.assertEqual(int(uses[0]['repeats']), 3)
            self.assertEqual(json.loads(defs[0]['state'])['waveform_hex'], '12' * 32)
            reconstructed = []
            for use in uses:
                unit = [d for d in defs if d['ch'] == use['ch'] and d['pattern_id'] == use['pattern_id']]
                span = sum(int(d['advance_ticks']) for d in unit)
                for repeat in range(int(use['repeats'])):
                    for d in unit:
                        start = int(use['tick_start']) + repeat * span + int(d['offset_ticks'])
                        reconstructed.append((start, start + int(d['duration_ticks'])))
            self.assertEqual(reconstructed, [(s.tick_start, s.tick_end) for s in rows])
            self.assertEqual([int(m['segment_index']) for m in marks], [0, 1, 2])

    def test_empty_and_invalid_timing(self):
        self.assertEqual(analyze({}, 'psg'), {})
        self.assertEqual(analyze({0: []}, 'scc')[0], ((), (), ()))
        with self.assertRaises(ValueError):
            analyze({0: [segment('opll', 4), segment('opll', 0)]}, 'opll')
