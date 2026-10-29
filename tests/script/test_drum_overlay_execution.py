"""Inferred percussion respects native shared volumes and attack priority."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(Path(__file__).parent)]
from musical_plan import MusicalControl as C, MusicalPlan
from drum_execution import add_overlay
from rhythm_patterns import Hit, Group
from musical_timing import AcceptedTimingMapper
from test_musical_vgm import serialize, intervals


class DrumOverlayExecutionTests(unittest.TestCase):
    def test_shared_volume_nibble_tracks_native_updates_and_restores(self):
        controls = (C(0, 'opll', None, 'rhythm_register', (14, 32)),
                    C(0, 'opll', None, 'rhythm_register', (0x37, 0xa3)),
                    C(100, 'opll', None, 'rhythm_register', (0x37, 0xb5)),
                    C(0, 'opll', None, 'percussion', (1, 15, 1), order=100),
                    C(735, 'opll', None, 'percussion', (1, 15, 0), order=100))
        raw, _, _ = serialize(MusicalPlan((), controls, 1470, 1470))
        states = intervals(raw)
        self.assertEqual([row[3][0x37] for row in states], [0xa0, 0xb0, 0xb5])
        self.assertEqual([row[3][14] for row in states], [40, 40, 32])

    def test_held_native_instrument_wins_and_future_native_attack_clips_overlay(self):
        def run(native):
            plan = MusicalPlan((), tuple(native), 1470, 1470)
            hit = Hit('SD', -1, 0, 0, 0, (0,) + (None,) * 9)
            summary = dict(added_hits=1, omitted_hits=0, instruments={'SD': 1})
            decisions = [dict(status='added', instrument='SD', target_tick=0)]
            return add_overlay(plan, (Group(0, None, (hit,)),), 2, summary, decisions,
                               timing=AcceptedTimingMapper()), summary, decisions
        held = C(0, 'opll', None, 'rhythm_register', (14, 40))
        result, summary, decisions = run((held,))
        self.assertFalse(any(c.kind == 'percussion' for c in result.controls))
        self.assertEqual(summary['added_hits'], 0)
        self.assertEqual(decisions[0]['reason'], 'native_rhythm_already_held')
        later = C(200, 'opll', None, 'rhythm_register', (14, 40))
        result, _, _ = run((later,))
        self.assertEqual(next(c.sample for c in result.controls if c.kind == 'percussion' and not c.value[2]), 200)
        raw, _, _ = serialize(result)
        self.assertTrue(next(row for row in intervals(raw) if row[0] == 200)[3][14] & 8)

    def test_new_rhythm_uses_measured_pitch_initialization(self):
        hit = Hit('BD', -1, 0, 0, 0, (0,) + (None,) * 9)
        summary = dict(added_hits=1, omitted_hits=0, instruments={'BD': 1})
        plan = add_overlay(MusicalPlan((), (), 1470, 1470), (Group(0, None, (hit,)),), 2,
                           summary, [], timing=AcceptedTimingMapper())
        raw, _, _ = serialize(plan)
        state = intervals(raw)[0][3]
        self.assertEqual((state[0x16], state[0x17], state[0x18]), (32, 80, 192))
        self.assertEqual((state[0x26], state[0x27], state[0x28]), (5, 5, 1))
        self.assertTrue(state[14] & 16)


if __name__ == '__main__':
    unittest.main()
