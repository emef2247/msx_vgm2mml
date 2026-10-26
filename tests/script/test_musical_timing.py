"""Authored accepted timing decisions shared by MML and direct execution."""
from dataclasses import FrozenInstanceError
from fractions import Fraction
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from musical_timing import (AcceptedTimingMapper, control_boundary_step,
                            plan_melody, choose_timing)
from note_normalization import TimingPlan, render_melody, retime_controls


def segment(start, end, *, key=1, edge=1, fnum=217, volume=2, inst=1, sustain=0):
    return SimpleNamespace(vgmticks=start, vgmticks_end=end, keyon=key,
        key_on_edge=edge, fnum=fnum, block=3, inst=inst, vol=volume, sus=sustain)


class TimingMapperTests(unittest.TestCase):
    def test_default_mapper_matches_existing_tick_quirk(self):
        mapper = AcceptedTimingMapper()
        self.assertFalse(mapper.applied)
        self.assertEqual(mapper.sample(2), 1470)
        self.assertEqual(mapper.sample(2, source_sample=1), 1470)
        self.assertEqual([mapper.source_sample(x) for x in (0, 1, 734, 735, 736, 44100)],
                         [0, 0, 0, 0, 1470, 44100])

    def test_declared_output_tempo_is_rational_not_measured_float(self):
        plan = TimingPlan(120, 12, 5518.15, 0, 1, 735)
        mapper = AcceptedTimingMapper(plan)
        self.assertTrue(mapper.applied)
        self.assertEqual(mapper.step_sample(8), 3675)
        self.assertEqual(mapper.step_sample(10.5), round(Fraction(21, 2) * Fraction(3675, 8)))
        self.assertEqual(mapper.step_sample(1234567), round(Fraction(1234567 * 44100 * 60, 120 * 48)))
        self.assertNotEqual(mapper.step_sample(12000), round(12000 * plan.samples_per_step))

    def test_control_end_fitting_is_the_same_pure_decision_used_by_mml(self):
        plan = TimingPlan(120, 12, 5518.15, 973.6, 1, 735)
        mapper = AcceptedTimingMapper(plan)
        tick_ends = (12, 24)
        steps, previous = [], 0
        for tick in tick_ends:
            previous = control_boundary_step(tick, plan, previous)
            steps.append(previous)
        self.assertEqual(mapper.boundaries(tick_ends), tuple(mapper.step_sample(s) for s in steps))
        with patch('musical_timing.control_boundary_step', wraps=control_boundary_step) as boundary:
            retime_controls('#tempo 225\n1 c%36 r%36\n', plan)
        self.assertEqual(boundary.call_count, 2)

    def test_excessive_boundary_shift_is_rejected_without_mutation(self):
        plan = TimingPlan(200, 12, 3307.5, 0, 1, 1)
        mapper = AcceptedTimingMapper(plan)
        with self.assertRaisesRegex(ValueError, 'correction tolerance'):
            mapper.boundaries((0.0001,))
        self.assertEqual(plan.tempo, 200)


class MelodyDecisionTests(unittest.TestCase):
    def setUp(self):
        self.plan = TimingPlan(120, 12, 5512.5, 0, 1, 735)

    def test_normalized_notes_retain_source_and_accepted_domains(self):
        rows = [segment(0, 10, fnum=194), segment(10, 5000, edge=0),
                segment(5000, 5000, key=0, edge=0)]
        before = [vars(row).copy() for row in rows]
        decisions = plan_melody({0: rows}, None, self.plan, num_channels=9, fm_state_ms=1)
        note = decisions.tracks[0].notes[0]
        self.assertEqual(note.source_indices, (0, 1))
        self.assertEqual((note.source_start, note.source_end), (0, 5000))
        self.assertEqual(note.states[0].source_indices, (1,))
        self.assertEqual(note.states[0].start_step, 0)
        self.assertEqual(decisions.state_evidence[0]['action'], 'omit_internal_state')
        self.assertTrue(decisions.state_evidence[1]['protected'])
        self.assertEqual([vars(row) for row in rows], before)
        with self.assertRaises(FrozenInstanceError):
            note.start_step = 99

    def test_mml_lowering_consumes_provided_decision_object(self):
        rows = [segment(0, 5512), segment(5512, 5512, key=0, edge=0)]
        decisions = plan_melody({0: rows}, None, self.plan, num_channels=9)
        with patch('musical_timing.plan_melody', side_effect=AssertionError('must not infer again')):
            compressed, expanded, evidence, loops = render_melody({0: rows}, None, self.plan,
                num_channels=9, decision_plan=decisions)
        self.assertIn('9 ', compressed)
        self.assertEqual(evidence, list(decisions.evidence))
        self.assertIn('9 ', expanded)

    def test_shared_planner_has_no_mml_parser_or_compiler_dependency(self):
        rows = [segment(0, 5512), segment(5512, 5512, key=0, edge=0)]
        with patch('mml_sync.analyze_mml', side_effect=AssertionError('text parsing is not a planner')):
            decisions = plan_melody({0: rows}, None, self.plan, num_channels=9)
        self.assertEqual(len(decisions.tracks[0].notes), 1)

    def test_terminal_and_timbre_sustain_states_are_never_short_state_candidates(self):
        rows = [segment(0, 1000),
                segment(1000, 2000, edge=0, inst=2, sustain=1),
                segment(2000, 5000, edge=0, inst=2, sustain=1, volume=4),
                segment(5000, 5000, key=0, edge=0, inst=2, sustain=1)]
        decisions = plan_melody({0: rows}, None, self.plan, num_channels=9, fm_state_ms=48)
        self.assertEqual(len(decisions.tracks[0].notes[0].states), 3)
        self.assertTrue(all(row['protected'] for row in decisions.state_evidence))
        self.assertTrue(all(row['action'] == 'retain' for row in decisions.state_evidence))
        self.assertEqual(decisions.tracks[0].notes[0].states[1].value[4], 1)

    def test_voice_limit_belongs_to_text_lowering(self):
        rows, changes = [], []
        for index in range(242):
            start = index * 5512
            rows.extend((segment(start, start + 5000, inst=0),
                         segment(start + 5000, start + 5000, key=0, edge=0, inst=0)))
            changes.append((start, bytes((index & 255, index >> 8, 0, 0, 0, 0, 0, 0))))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'voices.csv'
            path.write_text('#type,vgmticks,patch_hex\n' + ''.join(
                f'patch,{sample},{value.hex()}\n' for sample, value in changes))
            # This check targets backend independence; keep attack timestamps on
            # an exactly representable lattice rather than testing inference.
            plan = TimingPlan(120, 12, 5512, 0, 1, 735)
            decisions = plan_melody({0: rows}, path, plan, num_channels=9)
            self.assertEqual(len(decisions.patches), 242)
            with self.assertRaisesRegex(ValueError, 'MGSDRV voice range'):
                render_melody({0: rows}, path, plan, num_channels=9, decision_plan=decisions)

    def test_choose_timing_abstains_and_reports_without_encoding(self):
        mapper = choose_timing({0: [segment(0, 1000)]})
        self.assertFalse(mapper.applied)
        self.assertEqual(mapper.report['reason'], 'no confident shared clock')
        disabled = choose_timing({}, enabled=False)
        self.assertFalse(disabled.report['enabled'])

    def test_choose_timing_accepts_authored_regular_attacks(self):
        rows = []
        for i in range(40):
            start = round(i * 5512.5)
            end = round((i + 1) * 5512.5)
            rows += [segment(start, end), segment(end, end, key=0, edge=0)]
        mapper = choose_timing({0: rows}, num_channels=9)
        self.assertTrue(mapper.applied, mapper.report)
        self.assertEqual(len(mapper.melody.evidence), 40)
        self.assertEqual(mapper.tempo, 120)


if __name__ == '__main__':
    unittest.main()
