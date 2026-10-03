import csv,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from opll_mode import mode_from_trace
from opll_target import render
from test_opll_target import segment
from mml_sync import analyze_mml

class OpllMode(unittest.TestCase):
    def mode(self,rows):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=('#type','is_ryt','bd','sd','tom','tc','hh'));w.writeheader();w.writerows(rows)
            return mode_from_trace(p)
    def test_initial_rhythm_enable_then_disable(self):
        self.assertEqual(self.mode([{'#type':'rhythm','is_ryt':1},{'#type':'rhythm','is_ryt':0}]),0)
    def test_rhythm_used_before_final_disable(self):
        self.assertEqual(self.mode([{'#type':'rhythm','is_ryt':1,'bd':1},{'#type':'rhythm','is_ryt':0}]),1)
    def test_mode_stays_enabled_and_empty(self):
        self.assertEqual(self.mode([{'#type':'rhythm','is_ryt':1}]),1)
        self.assertEqual(self.mode([]),0)
    def test_nine_melodic_channels_projected(self):
        text=render({ch:[segment(0,tick_end=12,inst=1,fnum=290,block=3)]
                     for ch in range(9)},num_channels=9)
        self.assertEqual(set(analyze_mml('#opll_mode 0\n'+text)[0]),set('9abcdefgh'))
    def test_macros_include_high_channels_in_mode_zero(self):
        from structured_macros import enhance_macros,expanded
        text='#opll_mode 0\nf '+('o4 v12 c8 d8 e8 f8 g8 a8 '*8)+'\ng '+('o4 v12 c8 d8 e8 f8 g8 a8 '*8)+'\nh '+('o4 v12 c8 d8 e8 f8 g8 a8 '*8)+'\n'
        result=enhance_macros(text)
        self.assertLess(len(result),len(text))
        self.assertEqual(expanded(text),expanded(result))
