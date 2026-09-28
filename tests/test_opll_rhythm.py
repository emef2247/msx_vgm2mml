"""Rhythm edge semantics and optional vgm2tx802 reference parity."""
import csv
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opll import _build_segments, RHYTHM_CH_MAP, RHYTHM_VOICE_ID_MAP
from segment_utils import pass2_expand_rhythm
from vgm_reader import parse_vgm
from opll_mml import process_opll_csv


class RhythmEdges(unittest.TestCase):
    def event(self, tick, **bits):
        return dict({'#type': 'rhythm', 'ch': -1, 'is_ryt': 1,
                     'ticks': tick, 'l': 0, 'bd_vol': 3, 'sd_vol': 5}, **bits)

    def triggers(self, events):
        return [(e['ticks'], e['ch'], e['vol']) for e in
                pass2_expand_rhythm(events, RHYTHM_CH_MAP, RHYTHM_VOICE_ID_MAP)
                if e.get('#type') == 'rhythm_expand' and e['keyon']]

    def test_held_bit_does_not_retrigger(self):
        self.assertEqual(self.triggers([self.event(0), self.event(1, bd=1),
                                       self.event(2, bd=1)]), [(1, 9, 3)])

    def test_same_tick_off_on_preserves_two_edges(self):
        self.assertEqual(self.triggers([self.event(1, bd=1), self.event(1),
                                       self.event(1, bd=1)]), [(1, 9, 3), (1, 9, 3)])

    def test_simultaneous_instruments_and_volume_only_write(self):
        volume = {'#type': 'rhythmVol', 'ch': 6, 'is_ryt': 1, 'bd_vol': 7}
        self.assertEqual(self.triggers([self.event(1, bd=1, sd=1), volume,
                                       self.event(2, bd=1, sd=1)]),
                         [(1, 9, 3), (1, 10, 5)])


class RhythmReferences(unittest.TestCase):
    def check_reference(self, relative):
        base = ROOT / 'tests/fixtures' / relative
        stem = base.name
        reference = base / 'reference/vgm2tx802'
        if not (reference / f'{stem}_trace.opll.pass4.csv').exists():
            self.skipTest('Optional vgm2tx802 reference is not installed')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            parse_vgm(str(base / f'{stem}.vgm'), folder)
            trace = output / f'{stem}_trace.opll.csv'
            with contextlib.redirect_stdout(io.StringIO()):
                _build_segments(str(trace), debug=True)
            for suffix in ('_trace.opll.csv', '_trace.opll_regs.csv',
                           '_trace.opll.pass1.csv', '_trace.opll.pass2.csv',
                           '_trace.opll.pass3.csv', '_trace.opll.pass4.csv'):
                self.assertEqual((output / (stem + suffix)).read_text(),
                                 (reference / (stem + suffix)).read_text(), suffix)
            process_opll_csv(str(trace), folder, stem=stem, dump_passes=True, debug=False)
            with (output / f'{stem}.opll.segments.csv').open(newline='') as stream:
                actual = list(csv.DictReader(stream))
            with (reference / f'{stem}_trace.opll.pass4.csv').open(newline='') as stream:
                expected = list(csv.DictReader(stream))
            fields = ('ch', 'tick_start', 'tick_end', 'keyon', 'fnum', 'block',
                      'vol', 'bd', 'sd', 'tom', 'tc', 'hh')
            def values(rows):
                return sorted(tuple(float(row.get(f) or 0) for f in fields)
                              for row in rows if row['ch'] in ('9','10','11','12','13')
                              and row['keyon'] == '1' and row['is_ryt'] == '1')
            self.assertTrue(values(expected))
            self.assertEqual(values(actual), values(expected))
            self.assertTrue(any(row['ch'] == '0' for row in actual))

    def test_sample(self):
        self.check_reference('public/psg_opll/msxplay.com/sample')

    def test_grider(self):
        self.check_reference('local_only/opll/msxplay.com/grider')

    def test_sx01v(self):
        self.check_reference('local_only/opll/msxplay.com/sx01v')
