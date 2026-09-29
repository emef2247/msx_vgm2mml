"""Performed-unit grouping and nested projection preserve exact commands."""
import csv
import re
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from chip_segments import PsgSegment, dump_segments
from mml_envelopes import extract_notes, render, EnvelopeBank
from performed_patterns import Unit, compress, group_notes
from test_melody_loops import expand


class PerformedPatterns(unittest.TestCase):
    def test_nested_phrase_and_relative_commands_expand_exactly(self):
        phrase = ['< c8', '> d8'] * 4 + ['r4']
        commands = ['o4 v12 c4'] + phrase * 3
        units = [Unit(i, i+1, 'note', (text,)) for i, text in enumerate(commands)]
        text, report = compress(units, commands)
        self.assertEqual(expand(text), expand(' '.join(commands)))
        self.assertIn('[[< c8 > d8]4 r4]3', text)
        self.assertTrue(any(r['parent_id'] != '' and r['status'] == 'applied' for r in report))

    def test_different_initialization_and_counts_over_255(self):
        commands = ['o4 c8'] + ['c8'] * 600
        units = [Unit(i, i+1, 'note', ('same',)) for i in range(len(commands))]
        text, _ = compress(units, commands)
        self.assertEqual(expand(text), expand(' '.join(commands)))
        self.assertTrue(all(1 < int(n) <= 255 for n in re.findall(r'\](\d+)', text)))
        self.assertLess(len(text), len('o4 c8 [c8]255 [c8]255 [c8]90'))
        self.assertTrue(text.startswith('o4 c8'))

    def test_tied_envelope_is_one_unit_and_release_difference_is_distinct(self):
        units = [Unit(0, 1, 'note', (12, 8, 4)), Unit(1, 2, 'note', (12, 7, 4))]
        commands = ['@e1 c%255 &c%45', '@e2 c%255 &c%45']
        text, report = compress(units, commands)
        self.assertEqual(text, ' '.join(commands))
        self.assertFalse(report)

    def test_cost_selection_never_grows_greedy_output(self):
        from performed_patterns import _compress
        # Overlapping musical repetitions and varying entry commands.
        for repeats in range(2, 10):
            commands = ['o4 c8'] + (['c8', 'd8'] * repeats + ['r4']) * 3
            units = [Unit(i, i+1, 'note', (text.split()[-1],))
                     for i, text in enumerate(commands)]
            before, _ = _compress(units, commands, 2, False)
            after, report = compress(units, commands)
            self.assertLessEqual(len(after), len(before))
            self.assertEqual(expand(after), expand(' '.join(commands)))
            self.assertTrue(all(r['strategy'] in ('unit_count', 'text_cost') for r in report))

    def test_noise_gesture_keeps_mode_changes_and_trailing_rest(self):
        base = PsgSegment('aVC', 0, 0, 0, 2, 400, 12, 4, 'c', 0, (), 2, 5, 0, 0, 0, 0, 12)
        segments = [base, replace(base, ticks=2, mode=1, volume=8),
                    replace(base, ticks=4, mode=0, volume=0, scale='r')]
        notes = extract_notes({0: segments}, 'psg')[0]
        units = group_notes(notes, 'psg')
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].kind, 'percussion_candidate')
        self.assertEqual((units[0].start, units[0].end), (0, 3))
        changed = extract_notes({0: [replace(segments[0], noise_period=6), *segments[1:]]}, 'psg')[0]
        self.assertNotEqual(units[0].signature(), group_notes(changed, 'psg')[0].signature())
        # Without an ending rest this coarse detector makes no drum claim.
        self.assertTrue(all(u.kind != 'percussion_candidate' for u in group_notes(notes[:2], 'psg')))

    def test_dump_preserves_source_cells_and_adds_hierarchy(self):
        base = PsgSegment('aVC', 0, 0, 0, 2, 400, 12, 4, 'c', 0, (), 2, 5, 0, 0, 0, 0, 12)
        segments = []
        for tick in range(0, 24, 6):
            segments.extend([replace(base, ticks=tick), replace(base, ticks=tick+2, mode=1),
                             replace(base, ticks=tick+4, mode=0, volume=0, scale='r')])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.psg.segments.csv'
            dump_segments(path, {0: segments}, PsgSegment)
            with path.open(newline='') as f: before = list(csv.DictReader(f))
            target = Path(folder) / 'test.psg.target_notes.csv'
            render({0: segments}, 'psg', EnvelopeBank(), dump_path=target)
            with path.open(newline='') as f: after = list(csv.DictReader(f))
            self.assertEqual(before, [{k:r[k] for k in before[0]} for r in after])
            self.assertEqual({r['performed_unit_kind'] for r in after}, {'percussion_candidate'})
            self.assertTrue(all(r['performed_loop_path'] != '[]' for r in after))


if __name__ == '__main__':
    unittest.main()
