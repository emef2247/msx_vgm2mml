"""Continuous-note children preserve source members and exact target controls."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from melody_patterns import analyze
from opll_inner_loops import OpllLoopPlan
from opll_note_units import group_notes
from opll_target import render
from source_loop_plan import expanded_tokens
from structured_macros import expanded
from test_rhythm_patterns import segment


class OpllInnerLoops(unittest.TestCase):
    def rows(self, pitches=(290, 315, 340, 315) * 8):
        return [segment(i*4, tick_end=(i+1)*4, inst=1, fnum=pitch, block=3,
                        key_on_edge=int(i == 0)) for i, pitch in enumerate(pitches)]

    def plan(self, rows):
        items = analyze({0: rows}, 'opll')[0][0]
        members, units = group_notes(rows, items)
        return OpllLoopPlan.build(members, units, items)

    def test_long_keyed_note_contains_inner_repeats_without_new_attacks(self):
        rows = self.rows()
        before = repr(rows)
        old = render({0: rows}, raw_ticks=True)
        text = render({0: rows}, raw_ticks=True, source_loops=True, source_strategy='structural')
        self.assertEqual(expanded(old), expanded(text))
        self.assertIn('[', text)
        self.assertEqual(repr(rows), before)
        plan = self.plan(rows)
        self.assertEqual(len(plan.members), 1)
        self.assertTrue(any(plan.inner[0].structure.catalog))

    def test_true_edge_and_zero_length_member_stay_in_distinct_source_spans(self):
        rows = self.rows()
        rows.insert(16, segment(64, tick_end=64, inst=1, fnum=290, block=3, key_on_edge=1))
        plan = self.plan(rows)
        self.assertEqual(tuple(i for group in plan.members for i in group), tuple(range(len(rows))))
        self.assertEqual(len(plan.members), 2)
        self.assertEqual(plan.members[1][0], 16)
        self.assertEqual(expanded(render({0: rows}, raw_ticks=True)),
                         expanded(render({0: rows}, raw_ticks=True, source_loops=True,
                                         source_strategy='structural')))

    def test_pitch_volume_and_patch_changes_prevent_false_inner_equality(self):
        rows = self.rows((290, 315, 340, 315) * 2)
        rows[4].vol = 4
        rows[5].fnum = 316
        plan = self.plan(rows)
        self.assertNotEqual(plan.inner[0].keys[:4], plan.inner[0].keys[4:])
        self.assertEqual(expanded(render({0: rows}, raw_ticks=True)),
                         expanded(render({0: rows}, raw_ticks=True, source_loops=True,
                                         source_strategy='structural')))
        rows = self.rows((290, 315) * 4)
        for row in rows:
            row.inst = 0
        # Unknown user patches remain distinct source evidence.
        plan = self.plan(rows)
        self.assertFalse(any(plan.inner[0].structure.catalog))

    def test_inner_markers_do_not_hide_equal_outer_notes(self):
        rows = self.rows((290, 315, 340, 315) * 16)
        for i, row in enumerate(rows):
            row.key_on_edge = int(i % 16 == 0)
        plan = self.plan(rows)
        self.assertTrue(plan.outer.tree[0].children)
        commands = ['c%4' if row.fnum == 290 else 'd%4' for row in rows]
        text, _ = plan.render(commands, {i: i for i in range(len(rows)+1)})
        self.assertEqual(expanded_tokens(text), tuple(commands))
        depth = maximum = 0
        for token in text:
            if token == '[':
                depth += 1
                maximum = max(maximum, depth)
            elif token == ']':
                depth -= 1
        self.assertEqual(maximum, 2)
        self.assertTrue(any(row['status'] == 'applied' for row in plan.marker_rows()))

    def test_initializer_and_gate_spelling_is_preserved(self):
        rows = self.rows()
        for raw in (False, True):
            old = render({0: rows}, raw_ticks=raw)
            new = render({0: rows}, raw_ticks=raw, source_loops=True, source_strategy='structural')
            self.assertEqual(expanded(old), expanded(new))
            self.assertEqual(sum(n[0] == 'q0' for n in expanded(new)['9']), 1)
            self.assertEqual(sum(n[0] == 'q8' for n in expanded(new)['9']), 1)

    def test_segment_dump_retains_cells_and_adds_note_and_marker_paths(self):
        rows = self.rows()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.opll.segments.csv'
            original = [dict(ch=0, segment_index=i, fnum=row.fnum, key_on_edge=row.key_on_edge)
                        for i, row in enumerate(rows)]
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(original[0]))
                writer.writeheader()
                writer.writerows(original)
            target = Path(folder) / 'test.opll.target_notes.csv'
            render({0: rows}, raw_ticks=True, dump_path=target,
                   source_loops=True, source_strategy='structural')
            with path.open(newline='', encoding='utf-8') as stream:
                actual = list(csv.DictReader(stream))
            self.assertEqual([{k: str(v) for k, v in row.items()} for row in original],
                             [{k: row[k] for k in original[0]} for row in actual])
            self.assertTrue(all(row['opll_note_unit_id'] == '0' for row in actual))
            paths = [json.loads(row['opll_inner_loop_path']) for row in actual]
            self.assertTrue(any(paths))
            self.assertTrue(any(item['target_selected'] and item['status'] == 'applied'
                                for path in paths for item in path))
            self.assertTrue((Path(folder) / 'test.opll.ch0.source_loops.inner_loops.csv').exists())


if __name__ == '__main__':
    unittest.main()
