import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from hierarchical_loops import experiment
from performed_patterns import Unit

class HierarchicalLoops(unittest.TestCase):
    def run_sequence(self,seq,strategy,keys=None,depth=3):
        commands=[c*8 for c in seq]
        units=[Unit(i,i+1,'note',(keys[i] if keys else c,)) for i,c in enumerate(seq)]
        return experiment(units,commands,strategy,max_phrase=8,max_depth=depth)

    def test_overlapping_short_repeat_must_not_hide_larger_choice(self):
        greedy,_=self.run_sequence('aaaabab','immediate')
        retained,_=self.run_sequence('aaaabab','retained')
        self.assertLess(len(retained),len(greedy))

    def test_nested_tree_preserves_complete_sequence(self):
        for strategy in ('immediate','retained'):
            _,rows=self.run_sequence('aaabaaab',strategy)
            self.assertTrue(any(r['depth']==2 for r in rows))
            self.assertTrue(any(r['parent'] != '' for r in rows))

    def test_equal_commands_with_different_source_state_do_not_repeat(self):
        for strategy in ('immediate','retained'):
            _,rows=self.run_sequence('aa',strategy,keys=['first','second'])
            self.assertEqual(rows,[])

    def test_different_commands_with_equal_source_state_do_not_repeat(self):
        for strategy in ('immediate','retained'):
            _,rows=self.run_sequence('ab',strategy,keys=['same','same'])
            self.assertEqual(rows,[])

    def test_depth_limit(self):
        _,rows=self.run_sequence('aaabaaab','retained',depth=1)
        self.assertTrue(all(r['depth']==1 for r in rows))

if __name__=='__main__':
    unittest.main()
