import sys
import csv
import json
from pathlib import Path
import tempfile
from dataclasses import replace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from chip_segments import SccSegment, PsgSegment
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
        self.assertIsNotNone(plans[0].structure)

    def test_short_nested_notes_are_structured_without_envelope_ids(self):
        base = self.segments()[0][0]
        rows = [replace(base, ticks=i, l=1, ev_type='f1Ctrl',
                        scale='c' if pitch == 'a' else 'd',
                        tone_period=400 if pitch == 'a' else 350)
                for i, pitch in enumerate('aaabaaab')]
        notes = extract_notes({0: rows}, 'scc')
        plans, _ = prepare(notes, 'scc')
        self.assertTrue(all(n.envelope is None for n in notes[0]))
        self.assertTrue(any(child.children for node in plans[0].tree for child in node.children))
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for i, bank in enumerate((EnvelopeBank(deferred=True), LoopFirstEnvelopeBank(deferred=True))):
                path = Path(tmp) / f'{i}.mml'
                bank.submit({0: rows}, 'scc', path, raw_ticks=True)
                bank.flush()
                outputs.append(path.read_text(encoding='utf-8'))
            self.assertEqual(sounding_timeline(outputs[0]), sounding_timeline(outputs[1]))

    def test_shared_bank_preserves_psg_hardware_and_scc_software_curves(self):
        base = PsgSegment('evS', 0, 0, 0, 2, 400, 0, 4, 'c', 0, (),
                          1, 0, 1, 100, 9, 0, 16)
        psg = {0: [replace(base, ticks=i * 2) for i in range(4)]}
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for i, bank in enumerate((EnvelopeBank(deferred=True), LoopFirstEnvelopeBank(deferred=True))):
                texts = []
                for chip, segments in (('psg', psg), ('scc', self.segments())):
                    path = Path(tmp) / f'{i}.{chip}.mml'
                    bank.submit(segments, chip, path, raw_ticks=True)
                bank.flush()
                for chip in ('psg', 'scc'):
                    text = (Path(tmp) / f'{i}.{chip}.mml').read_text(encoding='utf-8')
                    texts.append(sounding_timeline(text))
                outputs.append(texts)
            self.assertEqual(outputs[0], outputs[1])

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

    def test_source_plan_does_not_repeat_legacy_segment_search(self):
        bank = LoopFirstEnvelopeBank(deferred=True)
        with tempfile.TemporaryDirectory() as tmp:
            bank.submit(self.segments(), 'scc', Path(tmp) / 'test.mml', raw_ticks=True)
            with patch('melody_patterns.analyze', side_effect=AssertionError('unused legacy search')):
                bank.flush()

    def test_dump_links_markers_and_envelopes_to_source_segments(self):
        from chip_segments import dump_segments
        segments = self.segments()
        bank = LoopFirstEnvelopeBank(deferred=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.scc.segments.csv'
            dump_segments(path, segments, SccSegment)
            bank.submit(segments, 'scc', Path(tmp) / 'test.scc.target.mml', raw_ticks=True,
                        dump_path=Path(tmp) / 'test.scc.target_notes.csv')
            bank.flush()
            with path.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 8)
            self.assertTrue(all(row['performed_unit_id'] != '' for row in rows))
            self.assertTrue(all(json.loads(row['performed_loop_path']) for row in rows))
            self.assertTrue(all(row['envelope_kind'] == 'inline' for row in rows))
            self.assertTrue((Path(tmp) / 'test.scc.ch0.source_loops.loop_structure.csv').exists())

if __name__=='__main__':unittest.main()
