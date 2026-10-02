"""Bounded musical projection, clock inference and retained source evidence."""
import csv
import json
from pathlib import Path
import random
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from note_normalization import (TimingPlan, infer_timing, length_token, _gate,
                                render_melody, retime_controls, compact_melody, melodic_timeline)
from mml_sync import analyze_mml, _leaves


def segment(start, end, key=1, edge=1, fnum=217, volume=2):
    return SimpleNamespace(vgmticks=start, vgmticks_end=end, keyon=key,
                           key_on_edge=edge, fnum=fnum, block=3, inst=1, vol=volume, sus=0)


class NoteNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = TimingPlan(120, 12, 5518.15, 973.6, 1.0, 735)

    def test_infers_clock_from_events_without_reference_notes(self):
        rows = [segment(round(1000 + i * 5518.15 + (i % 5 - 2) * 35), 0) for i in range(48)]
        before = [vars(s).copy() for s in rows]
        plan = infer_timing({0: rows})
        self.assertIsNotNone(plan)
        self.assertEqual((plan.tempo, plan.grid), (120, 12))
        self.assertAlmostEqual(plan.samples_per_grid, 5518.15, delta=2)
        self.assertEqual(before, [vars(s) for s in rows])

    def test_uncertain_or_sparse_clock_abstains(self):
        rng = random.Random(123)
        samples, now = [], 0
        for i in range(70):
            now += rng.randint(1200, 19000)
            samples.append(segment(now, now))
        self.assertIsNone(infer_timing({0: samples}))
        self.assertIsNone(infer_timing({0: samples[:5]}))

    def test_position_has_one_origin_for_every_channel(self):
        start = round(self.plan.phase_samples + self.plan.samples_per_grid * 4)
        self.assertEqual(self.plan.onset(start), self.plan.origin_step + 48)
        self.assertEqual(self.plan.onset(start + 100), self.plan.onset(start))
        self.assertEqual(self.plan.onset(start + round(self.plan.samples_per_grid)), self.plan.onset(start) + 12)

    def test_gate_can_represent_fractional_step_without_rounding_to_rest(self):
        length, gate, fitted = _gate(10.5, 12, 7, self.plan)
        self.assertEqual((length, gate, fitted), (12, 7, True))

    def test_high_tempo_avoids_one_step_tail_and_invalid_divisors(self):
        plan = TimingPlan(160, 12, 4138.6, 839, 1, 735)
        self.assertEqual(_gate(11, 12, 8, plan)[:2], (12, 8))
        self.assertEqual(length_token('r', 2), 'r%2')
        self.assertEqual(length_token('c', 1), 'c%1')
        with self.assertRaises(ValueError):
            length_token('c', 1, minimum=2)
        text = length_token('c', 193, minimum=2)
        self.assertNotIn('c%1 ', text)
        self.assertEqual(sum(n.end - n.start for n in _leaves(analyze_mml('9 '+text)[0]['9'])), 193)

    def test_projection_retains_attacks_and_records_intermediate_states(self):
        rows = []
        for i in range(8):
            start = round(self.plan.phase_samples + i * self.plan.samples_per_grid)
            end = round(start + 9 * self.plan.samples_per_step)
            rows += [segment(start, start + 1, fnum=194),
                     segment(start + 1, end, edge=0), segment(end, end, key=0, edge=0)]
        before = [vars(s).copy() for s in rows]
        with tempfile.TemporaryDirectory() as folder:
            voice = Path(folder) / 'voice.csv'
            voice.write_text('#type,vgmticks,patch_hex\n')
            compressed, expanded, evidence, loops = render_melody({0: rows}, voice, self.plan)
        self.assertEqual(len(evidence), 8)
        self.assertTrue(all(r['quantized_state_runs'] == '[0]' for r in evidence))
        self.assertEqual(before, [vars(s) for s in rows])
        def timeline(text):
            return [(n.text, n.start, n.end) for n in _leaves(analyze_mml(text)[0]['9'])]
        self.assertEqual(timeline(compressed), timeline(expanded))
        self.assertTrue(any(r['status'] == 'applied' for r in loops))

    def test_projection_rejects_attacks_that_would_collide(self):
        rows = [segment(1000, 1020), segment(1020, 1040, key=0, edge=0),
                segment(1040, 1060), segment(1060, 1060, key=0, edge=0)]
        with tempfile.TemporaryDirectory() as folder:
            voice = Path(folder) / 'voice.csv'
            voice.write_text('#type,vgmticks,patch_hex\n')
            with self.assertRaisesRegex(ValueError, 'merge attacks'):
                render_melody({0: rows}, voice, self.plan)

    def test_control_retiming_does_not_rewrite_software_envelope_frames(self):
        text = '#tempo 225\n@e1 = { 0, 0, F:3, A:2 }\n1 @e1 v15 c%36 r%36\n'
        result = retime_controls(text, self.plan)
        self.assertIn('@e1 = { 0, 0, F:3, A:2 }', result)
        self.assertIn('#tempo 120', result)
        self.assertEqual(text.count('@e1'), result.count('@e1'))

    def test_notation_compaction_preserves_first_and_repeated_loop_entries(self):
        text = '#tempo 120\n9 l16 @1 v14 q6 o3 [@1 v14 o3 c o4 d]3 o4 e\n'
        compacted = compact_melody(text)
        self.assertLess(len(compacted), len(text))
        self.assertEqual(melodic_timeline(compacted), melodic_timeline(text))
        self.assertIn('o3 c', compacted)  # Needed after the first iteration's o4.

    def test_nested_gate_and_voice_changes_are_not_removed_unsafely(self):
        text = '#tempo 160\n9 l16 @1 v14 [q0 o3 c & q8 o4 d [@2 v13 e @1 v14 f]2]3\n'
        compacted = compact_melody(text)
        self.assertEqual(melodic_timeline(compacted), melodic_timeline(text))

    def test_public_sample_cli_preserves_native_segment_evidence(self):
        fixture = ROOT / 'tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm'
        if not fixture.exists():
            self.skipTest('Optional public sample unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for variant in ('baseline', 'normalized'):
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                           '--outdir', str(root / variant), '--vgmticks', '--dump-passes']
                if variant == 'normalized':
                    command.append('--normalize-lengths')
                result = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
            baseline, corrected = root / 'baseline', root / 'normalized'
            for chip in ('psg', 'opll'):
                filename = f'sample.{chip}.segments.csv'
                self.assertEqual((baseline / filename).read_bytes(), (corrected / filename).read_bytes())
            report = json.loads((corrected / 'sample.normalization.json').read_text())
            self.assertEqual(report['status'], 'applied', report['reason'])
            self.assertEqual(report['timing']['tempo'], 120)
            self.assertEqual(report['target_note_count'], 609)
            self.assertTrue(report['notation_preserves_effective_states'])
            original = (baseline / 'sample.mml').read_text(encoding='utf-8')
            normalized = (corrected / 'sample.mml').read_text(encoding='utf-8')
            self.assertIn('#tempo 120', normalized)
            self.assertLess(len(normalized), len(original))
            # A rejected re-run must not leave successful normalization evidence.
            from note_normalization import normalize_outputs
            from unittest.mock import patch
            with patch('note_normalization.infer_timing', return_value=None):
                tempo = normalize_outputs(corrected / 'sample_trace.opll.csv',
                                          corrected / 'sample_trace.opll_voice.csv',
                                          corrected, 'sample', dump=True)
            self.assertIsNone(tempo)
            self.assertFalse((corrected / 'sample.opll.normalized.notes.csv').exists())

    def test_raw_ticks_and_normalization_are_mutually_exclusive(self):
        command = [sys.executable, str(ROOT / 'vgm2mml.py'), 'not-needed.vgm',
                   '--raw-ticks', '--normalize-lengths']
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'cannot be combined', result.stderr)


if __name__ == '__main__':
    unittest.main()
