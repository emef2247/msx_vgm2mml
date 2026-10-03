import sys
from pathlib import Path
import tempfile
from dataclasses import replace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from chip_segments import SccSegment
from mml_envelopes import EnvelopeBank,extract_notes,candidate_curves
from pre_envelope_loops import LoopFirstEnvelopeBank,EnvelopeFirstStructuredBank,prepare
from source_loop_plan import SourceLoopPlan
from test_mml_envelopes import sounding_timeline

class PreEnvelopeLoopTests(unittest.TestCase):
    def segments(self):
        base=SccSegment('vCtrl',0,0,0,2,400,10,4,'c',0,(),400,1,1,0,'',1)
        return {0:[replace(base,ticks=i*4,ev_type='f1Ctrl') if j==0
                   else replace(base,ticks=i*4+2,volume=8)
                   for i in range(4) for j in range(2)]}

    def test_loop_body_count_precedes_envelope_assignment(self):
        notes=extract_notes(self.segments(),'scc')
        plans,selected=prepare(notes,'scc')
        self.assertEqual(sum(candidate_curves(notes).values()),4)
        self.assertEqual(sum(candidate_curves(selected).values()),1)
        self.assertEqual(len(plans[0].representatives()),1)
        self.assertTrue(all(n.envelope is None for n in notes[0]))
        self.assertEqual(len(notes[0]),4)

    def test_changed_selection_preserves_every_tick(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs=[];banks=[]
            for i,bank in enumerate([EnvelopeBank(deferred=True),LoopFirstEnvelopeBank(deferred=True)]):
                path=Path(tmp)/f'{i}.mml'
                bank.submit(self.segments(),'scc',path,raw_ticks=True)
                bank.flush();outputs.append(path.read_text(encoding='utf-8'));banks.append(bank)
            self.assertNotEqual(len(banks[0].curves),len(banks[1].curves))
            self.assertEqual(sounding_timeline(outputs[0]),sounding_timeline(outputs[1]))

    def test_selection_and_tree_build_really_change_order(self):
        for factory,expected in [(LoopFirstEnvelopeBank,['tree','select']),
                                 (EnvelopeFirstStructuredBank,['select','tree'])]:
            bank=factory(deferred=True)
            events=[]
            build,select=SourceLoopPlan.build,bank.select
            def observe_build(*args,**kwargs):
                events.append('tree')
                return build(*args,**kwargs)
            def observe_select(*args,**kwargs):
                events.append('select')
                return select(*args,**kwargs)
            with tempfile.TemporaryDirectory() as tmp:
                bank.submit(self.segments(),'scc',Path(tmp)/'test.mml',raw_ticks=True)
                with patch.object(SourceLoopPlan,'build',side_effect=observe_build), patch.object(bank,'select',side_effect=observe_select):
                    bank.flush()
            self.assertEqual(events,expected)

if __name__=='__main__':unittest.main()
