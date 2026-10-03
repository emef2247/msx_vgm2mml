import itertools
from functools import lru_cache
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'py'))
from loop_structure import LoopStructure, candidates, expanded_indices, unroll
from source_loop_plan import SourceLoopPlan, expanded_tokens
from hierarchical_loops import Node


class LoopStructureTests(unittest.TestCase):
    def test_reused_content_matches_original_interval_tree(self):
        # Independent interval memoization is the previous exact solver.
        # Its source tree, including deterministic ties and positions, is the oracle.
        def original(keys):
            catalog = candidates(keys)
            @lru_cache(None)
            def solve(lo, hi):
                if lo == hi:
                    return (), (0, 0)
                for repeat in catalog[lo]:
                    if repeat.end >= hi and (hi-lo) % repeat.width == 0:
                        body = keys[lo:lo+repeat.width]
                        if (hi-lo)//repeat.width > 1 and len(set(body)) == repeat.width:
                            return (Node(lo, hi, tuple(Node(i,i+1) for i in range(lo,lo+repeat.width)),
                                         (hi-lo)//repeat.width),), (repeat.width,1)
                costs, choices = {hi:(0,0)}, {}
                for start in range(hi-1,lo-1,-1):
                    costs[start] = costs[start+1][0]+1, costs[start+1][1]
                    choices[start] = Node(start,start+1), start+1
                    for repeat in catalog[start]:
                        maximum = min(repeat.max_repeats,(hi-start)//repeat.width)
                        if maximum < 2:
                            continue
                        body, cost = solve(start,start+repeat.width)
                        for count in range(2,maximum+1):
                            stop = start+repeat.width*count
                            candidate = cost[0]+costs[stop][0], cost[1]+costs[stop][1]+1
                            if candidate < costs[start]:
                                costs[start], choices[start] = candidate, (Node(start,stop,body,count),stop)
                tree, start = [], lo
                while start < hi:
                    node, start = choices[start]
                    tree.append(node)
                return tuple(tree), costs[lo]
            return solve(0,len(keys))[0]
        for size in range(9):
            for keys in itertools.product('ab', repeat=size):
                self.assertEqual(LoopStructure.build(keys).tree, original(keys))
        # Equal bodies occur at different offsets and with different surroundings.
        phrase = tuple('aaabbbbbbcccddd')
        for keys in ((('intro',)+phrase*3+('tail',)),
                     tuple('xyz')+phrase*2+tuple('pq')+phrase*2+tuple('rs')):
            self.assertEqual(LoopStructure.build(keys).tree, original(keys))

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
