"""Score-loop lengths, exits, nesting and grouped-track source counts."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_mml_loops import analyze, summarize


class MmlLoopAuditTests(unittest.TestCase):
    def test_last_pass_exit_is_not_a_full_repeat(self):
        rows, _ = analyze('#tempo 120\n9 l16 [c d | e f]3\n')
        row = rows[0]
        self.assertEqual((row['body_steps_min'], row['final_steps_min'],
                          row['common_steps_min'], row['expanded_steps_min']), (48,24,24,120))

    def test_nested_counts_are_definition_counts_not_execution_counts(self):
        rows, _ = analyze('#tempo 120\n9 l16 [[c d]4 e4]2\n')
        inner = next(r for r in rows if r['depth']==2)
        outer = next(r for r in rows if r['depth']==1)
        self.assertEqual((inner['body_steps_min'],inner['expanded_steps_min']), (24,96))
        self.assertEqual((outer['body_steps_min'],outer['expanded_steps_min']), (144,288))
        self.assertEqual(len(rows),2)

    def test_shared_outer_loop_has_child_on_one_track(self):
        rows, _ = analyze('#tempo 120\n9F [\n9 c1\nF l16 [bh:]4\n9F ]0\n')
        stats = summarize([dict(file='fixture.mml',**r) for r in rows])
        self.assertEqual((stats['source_loops'],stats['channel_loops']), (2,3))
        self.assertEqual(stats['source_loops_with_children'],1)
        self.assertTrue(all(r['expanded_steps_min']=='' for r in rows if r['infinite']))

    def test_comments_do_not_create_loops_or_exits(self):
        rows, _ = analyze('; [comment]9\n#tempo 120\n9 l8 [c ; | [fake]2\n9 d]2\n')
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['has_exit'])
        self.assertEqual(rows[0]['body_steps_min'],48)

    def test_dotted_lengths_and_tied_extensions(self):
        rows, _ = analyze('#tempo 120\n4 l8 [c4. ^8 d%7]2\n')
        self.assertEqual(rows[0]['body_steps_min'],103)

    def test_unbounded_child_is_not_claimed_as_finite_duration(self):
        with self.assertRaisesRegex(ValueError, 'unbounded'):
            analyze('#tempo 120\n9 [[c4]0]2\n')


if __name__ == '__main__':
    unittest.main()
