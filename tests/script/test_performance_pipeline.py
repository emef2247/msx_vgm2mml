"""The immutable performance stage is consumed by loops, bank selection and MML."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'py'),str(Path(__file__).resolve().parent)]
from chip_segments import SccSegment
from mml_envelopes import build_performance, render
from pre_envelope_loops import LoopFirstEnvelopeBank
from test_mml_envelopes import sounding_timeline


class PerformancePipelineTests(unittest.TestCase):
    def test_one_interpretation_drives_preparation_and_rendering(self):
        base=SccSegment('f1Ctrl',0,0,0,2,400,10,4,'c',0,(),400,1,1,0,'',1)
        rows=[replace(base,ticks=i*4,vgmticks=i*2940,vgmticks_end=i*2940+1470)
              if j==0 else replace(base,ev_type='vCtrl',ticks=i*4+2,volume=8,
                                     vgmticks=i*2940+1470,vgmticks_end=(i+1)*2940)
              for i in range(4) for j in range(2)]
        original=tuple(rows)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'test.scc.target.mml'
            bank=LoopFirstEnvelopeBank(deferred=True)
            with patch('mml_envelopes.build_performance',wraps=build_performance) as analyze:
                bank.submit({0:rows},'scc',target,raw_ticks=True,
                            dump_path=Path(tmp)/'test.scc.target_notes.csv')
                performance=bank.pending[0][3]['performance']
                with patch('pre_envelope_loops.render',wraps=render) as renderer:
                    bank.flush()
                self.assertEqual(analyze.call_count,1)
                self.assertIs(renderer.call_args.kwargs['performance'],performance)
            self.assertEqual(tuple(rows),original)
            self.assertEqual(len(dict(performance.channels)[0]),4)
            text=target.read_text()
            levels=[state[2] for state in sounding_timeline(text,raw=True)['4']]
            self.assertEqual(levels,[10,10,8,8]*4)
            self.assertTrue(list(Path(tmp).glob('test.scc.performance*.json')))
            self.assertTrue(list(Path(tmp).glob('test.scc.performance*.csv')))


if __name__=='__main__':
    unittest.main()
