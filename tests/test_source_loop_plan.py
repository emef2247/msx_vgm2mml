import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from source_loop_plan import SourceLoopPlan, expanded_tokens
from opll_target import render
from mml_sync import analyze_mml, _leaves
from test_rhythm_patterns import segment


class SourceLoopPlanTests(unittest.TestCase):
    def test_plan_is_used_after_initialization_changes_first_iteration(self):
        plan = SourceLoopPlan.build(['note'] * 4)
        commands = ['@0 v12 o4 c%12', 'c%12', 'c%12', 'c%12']
        text, rows = plan.render(commands)
        self.assertIn('[c%12]3', text)
        self.assertEqual(expanded_tokens(text), expanded_tokens(' '.join(commands)))
        self.assertEqual(rows[0]['repeats'], 4)
        self.assertEqual(rows[0]['emitted_repeats'], 3)

    def test_nested_plan_retains_source_boundaries_after_projection(self):
        plan = SourceLoopPlan.build(list('aaabaaab'))
        commands = ['c%12' if k == 'a' else 'd%12' for k in 'aaabaaab']
        text, rows = plan.render(commands)
        self.assertTrue(any(r['depth'] == 1 and r['status'] == 'applied' for r in rows))
        self.assertEqual(expanded_tokens(text), tuple(commands))

    def test_different_controls_expand_without_fabricated_repeat(self):
        plan = SourceLoopPlan.build(['note'] * 2)
        commands = ['v12 c%12', 'v11 c%12']
        text, rows = plan.render(commands)
        self.assertEqual(expanded_tokens(text), expanded_tokens(' '.join(commands)))
        self.assertEqual(rows[0]['emitted_repeats'], 0)

    def test_opll_edges_and_control_changes_survive_actual_renderer(self):
        rows = [segment(i * 4, tick_end=(i+1)*4, inst=1, fnum=290,
                        block=3, key_on_edge=int(i % 2 == 0)) for i in range(8)]
        normal = render({0: rows}, raw_ticks=True)
        planned = render({0: rows}, raw_ticks=True, source_loops=True)
        def timeline(text):
            return {ch: [(n.text, n.start, n.end) for n in _leaves(nodes)]
                    for ch, nodes in analyze_mml(text)[0].items()}
        self.assertEqual(timeline(normal), timeline(planned))
        after = render({0: rows}, raw_ticks=True, source_loops='after')
        self.assertEqual(timeline(after), timeline(planned))
        immediate = render({0: rows}, raw_ticks=True, source_loops=True, source_strategy='immediate')
        self.assertEqual(timeline(immediate), timeline(planned))


if __name__ == '__main__':
    unittest.main()
