"""Pure hit decisions are shared by MML and executable output consumers."""
from pathlib import Path
import sys
from unittest.mock import patch
import unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'py'),str(Path(__file__).resolve().parent)]
from drum_enhancement import project_groups, project
from test_drum_enhancement import candidate
from test_rhythm_patterns import segment
from rhythm_mml import render_groups
from rhythm_notation import optimize


class DrumExecutionTests(unittest.TestCase):
    def test_pure_groups_never_render_mml_and_preserve_native_priority(self):
        native={9:[segment(2,volume=1)]}
        items=[candidate(2,'BD'),candidate(4,volume=3),
               candidate(4,volume=10,candidate_id='strong')]
        with patch('drum_enhancement.render_groups',side_effect=AssertionError('MML rendering forbidden')):
            groups,end,summary,decisions=project_groups(items,native,[])
        self.assertEqual(summary['added_hits'],1)
        self.assertEqual([(g.tick,[(h.instrument,h.channel,h.state[0]) for h in g.hits]) for g in groups],
                         [(2,[('BD',9,1)]),(4,[('HH',-1,5)])])
        self.assertEqual([r['status'] for r in decisions],['omitted','omitted','added'])
        self.assertGreater(end,4)
        self.assertEqual(native[9][0].vol,1)

    def test_existing_mml_projection_consumes_identical_pure_groups(self):
        items=[candidate(2,'BD'),candidate(2,'SD',candidate_id='sd'),candidate(8,'HH')]
        groups,end,summary,decisions=project_groups(items,{},[])
        text,render_summary,render_decisions=project(items,{},[])
        self.assertEqual(text,optimize(render_groups(groups,end_tick=end)))
        self.assertEqual(render_summary,summary)
        self.assertEqual(render_decisions,decisions)
        self.assertEqual([h.instrument for h in groups[0].hits],['BD','SD'])

    def test_overlay_hits_are_explicitly_separate_from_native_shared_state(self):
        native={9:[segment(2,volume=2)]}
        groups,_,_,decisions=project_groups([candidate(2,'HH')],native,[])
        native_hits=[h for g in groups for h in g.hits if h.channel>=0]
        inferred=[h for g in groups for h in g.hits if h.channel==-1]
        self.assertEqual(len(native_hits),1)
        self.assertEqual(len(inferred),1)
        self.assertEqual(inferred[0].state[1:],(None,)*9)
        self.assertEqual(decisions[0]['status'],'added')
        self.assertEqual(decisions[0]['instrument'],'HH')

if __name__=='__main__':unittest.main()
