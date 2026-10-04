"""Source-loop equality must be explainable from native channel Segments."""
from dataclasses import replace
from pathlib import Path
import sys, tempfile, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'py'), str(ROOT/'scripts')]
from opm_loops import build_source_loops, OpmSourceLoops, OpmLoopProjection
from test_opm_mdx import analyze
from opm_mdx_structure import build_structure
from opm_mdx import project_segments
from source_loop_plan import expanded_tokens


class OpmSourceLoopTests(unittest.TestCase):
    fixture = ROOT/'tests/fixtures/public/opm/from_mdx/nested_phrase_loops/nested_phrase_loops.vgm'

    def source(self, root):
        return analyze(self.fixture, root)

    def test_source_keys_ignore_ids_absolute_origin_and_target_notation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.source(Path(tmp))
            plan = build_source_loops(source.segments)[0, 0]
            moved = OpmSourceLoops.build(tuple(replace(s, segment_id=s.segment_id+10000,
                          source_event_id=None if s.source_event_id is None else s.source_event_id+10000,
                          vgmticks=s.vgmticks+44100, vgmticks_end=s.vgmticks_end+44100,
                          continuity_id=s.continuity_id+1000) for s in plan.rows))
            self.assertEqual(plan.outer.keys, moved.outer.keys)
            self.assertEqual([p.keys for p in plan.inner], [p.keys for p in moved.inner])
            self.assertTrue(any(v['opm_source_loop_path'] for v in plan.annotations().values()))
            self.assertEqual({i for u in plan.units for i in u.members}, set(range(len(plan.rows))))
            self.assertEqual(sum(len(u.members) for u in plan.units), len(plan.rows))

    def test_same_note_length_different_operator_level_is_not_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.source(Path(tmp))
            plan = build_source_loops(source.segments)[0, 0]
            unit = next(u for u in plan.units if u.kind == 'held')
            rows = tuple(plan.rows[i] for i in unit.members)
            original = OpmSourceLoops.build(rows)
            changed = tuple(replace(s, state=replace(s.state, operators=(
                         replace(s.state.operators[0], tl=s.state.operators[0].tl+1),
                         *s.state.operators[1:]))) for s in rows)
            self.assertNotEqual(original.outer.keys, OpmSourceLoops.build(changed).outer.keys)
            # Fine pitch and source sample duration also participate, without a score.
            changed = tuple(replace(s, state=replace(s.state, kf_raw=24)) for s in rows)
            self.assertNotEqual(original.outer.keys, OpmSourceLoops.build(changed).outer.keys)
            changed = tuple(replace(s, vgmticks_end=s.vgmticks_end+1) for s in rows)
            self.assertNotEqual(original.outer.keys, OpmSourceLoops.build(changed).outer.keys)

    def test_same_note_length_different_shared_lfo_is_not_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.source(Path(tmp))
            original = build_source_loops(source.segments)[0, 0]
            changed = tuple(replace(s, state=replace(s.state, pmd=12)) for s in original.rows)
            self.assertNotEqual(original.outer.keys, OpmSourceLoops.build(changed).outer.keys)

    def test_channels_are_independent_and_source_rows_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.source(Path(tmp))
            original = source.segments
            plans = build_source_loops(original)
            self.assertEqual(set(plans), {(0, ch) for ch in range(8)})
            for (_, ch), plan in plans.items():
                self.assertTrue(all(row.ch == ch for row in plan.rows))
            self.assertEqual(source.segments, original)
            with self.assertRaises(ValueError):
                OpmSourceLoops.build(original)

    def test_zero_time_source_attacks_remain_units(self):
        path = ROOT/'tests/fixtures/public/opm/from_mdx/same_sample_retrigger/same_sample_retrigger.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            source = analyze(path, Path(tmp))
            for plan in build_source_loops(source.segments).values():
                self.assertEqual(sum(bool(row.rising_mask) for row in plan.rows),
                                 sum(bool(plan.rows[i].rising_mask) for u in plan.units for i in u.members))
                for index, row in enumerate(plan.rows):
                    if row.rising_mask:
                        self.assertTrue(any(u.members[0] == index for u in plan.units))

    def test_target_commands_are_only_a_projection_and_may_reject_source_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.source(Path(tmp))
            projection = project_segments(source.segments, end_vgmticks=source.source_end_vgmticks)
            result = build_structure(projection, source.segments)
            for track, plan in result.plans.items():
                commands = [u.command for u in result.units[track]]
                text, _ = plan.render(commands)
                self.assertEqual(expanded_tokens(text), expanded_tokens(' '.join(commands)))
                changed = [command+' y2,'+str(i) for i, command in enumerate(commands)]
                text, _ = plan.render(changed)
                self.assertEqual(expanded_tokens(text), expanded_tokens(' '.join(changed)))
                self.assertEqual(plan.source.outer.keys, build_source_loops(source.segments)[0, ord(track)-65].outer.keys)


if __name__ == '__main__':
    unittest.main()
