"""Loop projection must expand to the original emitted command stream."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from melody_loops import project
from rhythm_patterns import Occurrence
from mml_sync import _parse


def expand(text):
    def walk(nodes):
        result = []
        for node in nodes:
            if isinstance(node, tuple): result.extend(walk(node[0]) * node[1])
            else: result.append(node)
        return result
    return walk(_parse(text))


class MelodyLoops(unittest.TestCase):
    def check(self, units, boundaries=None):
        body = [token for unit in units for token in unit]
        if boundaries is None:
            boundaries = {i: sum(map(len, units[:i])) for i in range(len(units) + 1)}
        analysis = ((), ((None,),), (Occurrence(0, 0, len(units)),))
        after, report = project(body, boundaries, analysis, 0)
        self.assertEqual(expand(' '.join(body)), expand(' '.join(after)))
        return ' '.join(after), report

    def test_first_iteration_initialization_is_kept(self):
        text, report = self.check([['v12', 'o4', 'c8', ')', '>', 'd8']] +
                                  [['(', '<', 'c8', ')', '>', 'd8']] * 4)
        self.assertIn('[( < c8 ) > d8]4', text)
        self.assertEqual(report[0][-2], 4)

    def test_no_envelope_or_tie_boundary_splitting(self):
        text, report = self.check([['@e1', 'c%255', '&c%45']] * 3,
                                  {0: 0, 3: 9})
        self.assertNotIn('[', text)
        self.assertEqual(report[0][-1], 'target_note_boundary')

    def test_exact_envelope_commands_and_large_counts(self):
        text, _ = self.check([['@e1', 'c%255', '&c%45', 'r8']] * 600)
        self.assertEqual(text.count(']255'), 2)
        self.assertIn(']90', text)

    def test_different_commands_and_no_saving_are_retained(self):
        text, report = self.check([['v12', 'c8'], ['v11', 'c8']])
        self.assertNotIn('[', text)
        text, _ = self.check([['r'], ['r']])
        self.assertEqual(text, 'r r')

    def test_separate_occurrences_preserve_unmatched_material(self):
        body = ['o4 c8', 'o4 c8', 'r4', 'v12 d8', 'v12 d8']
        analysis = ((), ((None,),), (Occurrence(0, 0, 2), Occurrence(0, 3, 2)))
        result, _ = project(body, dict(enumerate(range(6))), analysis, 0)
        self.assertEqual(expand(' '.join(body)), expand(' '.join(result)))
        self.assertEqual(len(result), 3)
