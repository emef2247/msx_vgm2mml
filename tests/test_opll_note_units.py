import csv
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from opll_note_units import group_notes
from performed_patterns import compress
from opll_target import render
from test_rhythm_patterns import segment
from test_melody_loops import expand


def grouped(rows):
    return group_notes(rows, [SimpleNamespace(patch=None, patch_changes=()) for _ in rows])


class OpllNoteUnits(unittest.TestCase):
    def test_continuations_group_but_zero_tick_edges_and_release_split(self):
        rows = [segment(0, tick_end=2, inst=1, key_on_edge=1),
                segment(2, tick_end=4, inst=1, vol=5),
                segment(4, tick_end=4, inst=1, key_on_edge=1),
                segment(4, tick_end=8, inst=1),
                segment(8, tick_end=10, keyon=0, inst=1)]
        notes, units = grouped(rows)
        self.assertEqual([n.segment_indices for n in notes], [[0, 1], [2, 3], [4]])
        self.assertEqual([u.signature() for u in units], [('note', 4), ('note', 4), ('rest', 2)])

    def test_duration_candidates_reject_different_pitch_even_if_commands_match(self):
        rows = [segment(i*4, tick_end=i*4+4, inst=1, key_on_edge=1,
                        fnum=290 if i%2 else 291) for i in range(2)]
        _, units = grouped(rows)
        text, report = compress(units, ['c4']*2)
        self.assertEqual(expand(text), ['c4']*2)
        self.assertTrue(any(r['status']=='different_state' for r in report))
        self.assertNotIn('[c4]2', text)

    def test_source_partition_does_not_change_note_trajectory_signature(self):
        rows = [segment(0, tick_end=2, inst=1, key_on_edge=1),
                segment(2, tick_end=4, inst=1),
                segment(4, tick_end=8, inst=1, key_on_edge=1)]
        _, units = grouped(rows)
        self.assertEqual(units[0].validation_key, units[1].validation_key)
        text, _ = compress(units, ['c4', 'c4'])
        self.assertEqual(expand(text), ['c4', 'c4'])

    def test_custom_patch_differences_cannot_be_hidden_by_duration_candidates(self):
        rows = [segment(0,tick_end=4,key_on_edge=1,inst=0),
                segment(4,tick_end=8,key_on_edge=1,inst=0)]
        items = [SimpleNamespace(patch=p,patch_changes=()) for p in ('patch_a','patch_b')]
        _, units = group_notes(rows,items)
        text, report = compress(units,['@16 c4','@16 c4'])
        self.assertEqual(text,'@16 c4 @16 c4')
        self.assertTrue(any(r['candidate_status']=='different_state' for r in report))

    def test_zero_duration_non_key_updates_are_retained_but_do_not_block_note_equality(self):
        rows = [segment(0, tick_end=0, inst=1, fnum=100, key_on_edge=1),
                segment(0, tick_end=4, inst=1, fnum=290),
                segment(4, tick_end=4, inst=1, fnum=200, key_on_edge=1),
                segment(4, tick_end=8, inst=1, fnum=290)]
        notes, units = grouped(rows)
        self.assertEqual([n.segment_indices for n in notes], [[0,1],[2,3]])
        self.assertEqual(units[0].validation_key, units[1].validation_key)

    def test_pitch_and_volume_updates_remain_inside_attack_and_source_membership_is_dumped(self):
        rows = []
        for i in range(6):
            t=i*8
            rows += [segment(t, tick_end=t+2, inst=1, fnum=290, vol=3, key_on_edge=1),
                     segment(t+2, tick_end=t+4, inst=1, fnum=291, vol=4),
                     segment(t+4, tick_end=t+8, inst=1, keyon=0)]
        for raw in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                dump=Path(tmp)/'test.opll.target_notes.csv'
                text=render({0:rows}, raw_ticks=raw, dump_path=dump)
                before=(Path(tmp)/'test.opll.melody.before.target.mml').read_text()
                body=lambda s:' '.join(line[2:] for line in s.splitlines() if line.startswith('9 '))
                self.assertEqual(expand(body(text)), expand(body(before)))
                with (Path(tmp)/'test.opll.performed.units.csv').open() as f:
                    units=list(csv.DictReader(f))
                self.assertEqual(len(units),12)
                self.assertEqual(units[0]['segment_indices'],'[0, 1]')
                self.assertIn('[',body(text))


if __name__=='__main__':
    unittest.main()
