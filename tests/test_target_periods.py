"""MGSDRV register-period projection; expected values checked with MGSC/libkss."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from chip_segments import PsgSegment
from psg_scc_target import period_detune, rendered_period, envelope_period_tokens
from mml_envelopes import EnvelopeBank, render

class TargetPeriods(unittest.TestCase):
    def segment(self, period=424):
        return PsgSegment('fCA',0,0,0,8,period,15,4,'c',0,(),1,0,1,66,10,0,16)

    def test_hardware_period_is_register_value_not_frequency(self):
        text=render({0:[self.segment()]},'psg',EnvelopeBank(),True)
        self.assertIn('m66',text)
        self.assertNotIn('m9440',text)

    def test_zero_period_uses_direct_register_writes(self):
        text=render({0:[replace(self.segment(),envelope_period=0)]},'psg',EnvelopeBank(),True)
        self.assertIn('y11,0 y12,0',text)
        self.assertNotIn('m0',text)

    def test_detune_preserves_distinct_source_periods(self):
        for source,offset in ((424,3),(425,2),(427,0),(428,-1)):
            seg=self.segment(source)
            self.assertEqual(period_detune(seg),offset)
            self.assertEqual(rendered_period(seg),source)
        text=render({0:[self.segment(),replace(self.segment(425),ticks=8)]},'psg',EnvelopeBank(),True)
        self.assertIn('\\3',text)
        self.assertIn('\\2',text)

    def test_unrepresentable_period_is_explicitly_detectable(self):
        seg=replace(self.segment(4095),octave=1)
        self.assertEqual(period_detune(seg),-127)
        self.assertNotEqual(rendered_period(seg),4095)
