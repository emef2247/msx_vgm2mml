"""Timing audits compare source samples, not rounded 60 Hz lengths."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from compare_reference_vgmticks import reference_notes, source_notes, reference_hits, psg_decay_notes
from audit_reference_loop_windows import parse_reference


def row(start, stop, key, edge, fnum=217, block=3):
    return dict(vgmticks=str(start), vgmticks_end=str(stop), keyon=str(key),
                key_on_edge=str(edge), fnum=str(fnum), block=str(block),
                inst='0', vol='1', sus='0', tick_start='0', tick_end='0')


class ReferenceVgmTicksTests(unittest.TestCase):
    def test_rhythm_group_volume_and_last_iteration_exit(self):
        tracks, _, _ = parse_reference('#tempo 120\nf l16 vb12 vh10 [bh: vh-1 h: | b:]2')
        hits = reference_hits(tracks['f'])
        self.assertEqual([h['start'] for h in hits], [0, 12, 24, 36, 48])
        self.assertEqual(hits[0]['voices'], ((9, 12), (13, 10)))
        self.assertEqual(hits[-1]['voices'], ((13, 8),))

    def test_psg_volume_reset_candidates_keep_decay_and_shared_origin(self):
        def psg(start, end, volume):
            return dict(vgmticks=str(start), vgmticks_end=str(end), volume=str(volume),
                        mode='1', envelope_enabled='0', tone_period='200', noise_period='0',
                        envelope_period='0', envelope_shape='0', octave='4', scale='c')
        notes = psg_decay_notes([psg(100, 110, 12), psg(110, 120, 8),
                                 psg(120, 130, 8), psg(130, 140, 12), psg(140, 140, 0)])
        self.assertEqual([n['start'] for n in notes], [100, 130])
        self.assertEqual([n['gate'] for n in notes], [30, 10])
        self.assertEqual(notes[0]['trajectory'][-1][:2], (110, 130))
        bad = psg(0, 10, 15)
        bad['envelope_enabled'] = '1'
        with self.assertRaises(ValueError):
            psg_decay_notes([bad])

    def test_reference_tie_and_gate_form_one_attack(self):
        tracks, macros, _ = parse_reference('#tempo 120\n9 o4l16q6 c&d r c')
        notes = reference_notes(tracks['9'], macros)
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0]['parts'], [(4, 'c'), (4, 'd')])
        self.assertEqual(notes[0]['start'], 0)
        self.assertEqual(notes[0]['end'], 21)
        self.assertEqual(notes[1]['start'], 36)

    def test_zero_tick_intervals_still_have_physical_gate_and_ioi(self):
        notes = source_notes([row(100, 120, 1, 1), row(120, 130, 0, 0),
                              row(130, 155, 1, 1), row(155, 155, 0, 0)])
        self.assertEqual([n['gate'] for n in notes], [20, 25])
        self.assertEqual(notes[0]['ioi'], 30)
        self.assertEqual(notes[0]['trajectory'][0][:2], (100, 120))

    def test_one_sample_transient_is_retained_but_not_used_for_alignment(self):
        notes = source_notes([row(10, 11, 1, 1, fnum=194), row(11, 100, 1, 0),
                              row(100, 100, 0, 0)])
        self.assertEqual(len(notes[0]['trajectory']), 2)
        self.assertEqual(notes[0]['parts'], [(4, 'e')])
        self.assertEqual(notes[0]['gate'], 90)

    def test_unclosed_gate_is_not_invented_from_eof(self):
        notes = source_notes([row(10, 10, 1, 1)])
        self.assertIsNone(notes[0]['end'])
        self.assertIsNone(notes[0]['gate'])

    def test_old_csv_is_rejected_instead_of_reconstructing_samples(self):
        bad = row(0, 0, 0, 0)
        del bad['vgmticks']
        with self.assertRaises(ValueError):
            source_notes([bad])


if __name__ == '__main__':
    unittest.main()
