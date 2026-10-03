import itertools
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'py'))
from loop_structure import LoopStructure, candidates, expanded_indices, unroll
from source_loop_plan import SourceLoopPlan, expanded_tokens


class LoopStructureTests(unittest.TestCase):
    def test_complete_catalog_against_brute_force(self):
        for size in range(8):
            for keys in itertools.product('ab', repeat=size):
                found = {(r.start, r.width, count) for rows in candidates(keys) for r in rows
                         for count in range(2, r.max_repeats + 1)}
                expected = set()
                for start in range(size):
                    for width in range(1, (size-start)//2+1):
                        for count in range(2, (size-start)//width+1):
                            if keys[start:start+width]*count == keys[start:start+width*count]:
                                expected.add((start,width,count))
                self.assertEqual(found, expected)
                structure = LoopStructure.build(keys)
                self.assertEqual(tuple(keys[i] for i in expanded_indices(structure.tree)),keys)

    def test_inner_marker_does_not_hide_outer_repeat(self):
        phrase = tuple('aaabbbbbbcccddd')
        structure = LoopStructure.build(phrase*2)
        outer = structure.tree[0]
        self.assertEqual((outer.start,outer.end,outer.repeats),(0,len(phrase)*2,2))
        self.assertTrue(any(child.children for child in outer.children))
        flattened = unroll(outer)
        self.assertEqual(tuple(expanded_indices(flattened)),tuple(range(len(phrase)*2)))
        self.assertEqual(tuple(structure.keys[i] for i in expanded_indices(flattened)),phrase*2)
        self.assertTrue(any(r.width==3 and r.max_repeats==2 for r in structure.catalog[3]))

    def test_phrase_longer_than_128_is_retained(self):
        phrase=tuple(range(140))
        structure=LoopStructure.build(phrase*2)
        self.assertEqual((structure.tree[0].end,structure.tree[0].repeats),(280,2))

    def test_nesting_deeper_than_three(self):
        keys=('a',)
        for symbol in 'bcdef':
            keys=keys*2+(symbol,)
        structure=LoopStructure.build(keys)
        def depth(nodes):
            return max((1+depth(n.children) if n.children else 0 for n in nodes),default=0)
        self.assertGreater(depth(structure.tree),3)
        self.assertEqual(tuple(keys[i] for i in expanded_indices(structure.tree)),keys)

    def test_target_repeat_limit_does_not_limit_structure(self):
        plan=SourceLoopPlan.build(('a',)*300,strategy='structural')
        self.assertEqual(plan.tree[0].repeats,300)
        text,_=plan.render(['c%12']*300)
        self.assertIn(']255',text)
        self.assertEqual(expanded_tokens(text),('c%12',)*300)

    def test_six_levels_survive_target_projection(self):
        commands = ('c%12',) * 4
        for note in 'defga':
            commands = (commands + (note + '%12',)) * 2
        plan = SourceLoopPlan.build(commands, strategy='structural')
        text, report = plan.render(commands)
        self.assertEqual(expanded_tokens(text), commands)
        self.assertEqual(max(row['depth'] for row in report), 5)
        depth = maximum = 0
        for char in text:
            if char == '[':
                depth += 1
                maximum = max(maximum, depth)
            elif char == ']':
                depth -= 1
        self.assertEqual(maximum, 6)
        self.assertEqual(depth, 0)

    def test_different_state_is_not_equal_even_when_pitch_matches(self):
        keys=(('c',12),('c',11))
        self.assertFalse(any(candidates(keys)))


if __name__=='__main__':unittest.main()
