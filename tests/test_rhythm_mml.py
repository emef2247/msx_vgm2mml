"""Preserve rhythm onsets and per-instrument levels through rendering and sync."""
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from rhythm_mml import render
from mml_sync import analyze_mml, _leaves, annotate_sync_points
from test_rhythm_patterns import segment


def attacks(text):
    nodes = analyze_mml(text)[0].get('f', [])
    levels, result = dict.fromkeys('bsmch', 8), []
    for node in _leaves(nodes):
        token = node.text
        match = re.fullmatch(r'v([bsmch])([0-9]+)', token)
        if match:
            levels[match[1]] = int(match[2])
        elif node.end > node.start and not token.startswith('r'):
            letters = re.match('[bsmch]+', token)[0]
            result.extend((node.start, letter, levels[letter]) for letter in letters)
    return sorted(result)


class RhythmMml(unittest.TestCase):
    def test_final_keyoff_time_survives_attack_only_segments(self):
        for raw in (False, True):
            factor = 1 if raw else 3
            text = '#opll_mode 1\n' + render({12: [segment(40, volume=0)]}, raw, end_tick=77)
            self.assertEqual(attacks(text), [(40 * factor, 'c', 15)])
            self.assertEqual(analyze_mml(text)[0]['f'][-1].end, 77 * factor)

    def test_rhythm_only_02_keeps_final_trace_interval(self):
        stem = 'rhythm_only_test02'
        fixture = ROOT / 'tests/fixtures/public/opll' / stem / (stem + '.vgm')
        if not fixture.exists():
            self.skipTest('Optional rhythm-only fixture unavailable')
        for raw in (False, True):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                           '--outdir', folder, '--dump-passes']
                if raw:
                    command.append('--raw-ticks')
                run = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                with (Path(folder) / (stem + '_trace.opll.csv')).open(newline='') as stream:
                    end = max(int(row['ticks']) for row in csv.DictReader(stream))
                text = (Path(folder) / (stem + '.mml')).read_text()
                factor = 1 if raw else 3
                self.assertEqual(end, 77)
                self.assertEqual(analyze_mml(text)[0]['f'][-1].end, end * factor)
                self.assertEqual(attacks(text)[-1], (40 * factor, 'c', 15))

    def test_long_gap_does_not_retrigger_and_loop_levels_reset(self):
        segments = {9: [segment(t, volume=v) for t, v in
                        [(2, 0), (402, 3), (802, 0), (1202, 3), (1602, 0)]]}
        for raw in (False, True):
            factor = 1 if raw else 3
            text = '#opll_mode 1\n' + render(segments, raw)
            expected = [(t * factor, 'b', 15 - v) for t, v in
                        [(2, 0), (402, 3), (802, 0), (1202, 3), (1602, 0)]]
            self.assertEqual(attacks(text), expected)
            annotated = annotate_sync_points(text, min_gap=1000, drop_silent=True)
            self.assertEqual(attacks(annotated), expected)
            self.assertIn('f=15000', annotated)

    def test_duplicate_same_instrument_is_not_silently_lost(self):
        with self.assertRaisesRegex(ValueError, 'multiple BD triggers'):
            render({9: [segment(2), segment(2)]})

    def test_identical_zero_time_retrigger_is_target_only(self):
        rows = {13: [segment(0, tick_end=0), segment(0, tick_end=9)]}
        before = repr(rows)
        with self.assertWarnsRegex(RuntimeWarning, 'zero-duration same-time'):
            text = '#opll_mode 1\n' + render(rows)
        self.assertEqual(attacks(text), [(0, 'h', 12)])
        self.assertEqual(analyze_mml(text)[0]['f'][-1].end, 27)
        self.assertEqual(repr(rows), before)
        with self.assertWarns(RuntimeWarning):
            text = '#opll_mode 1\n' + render({13: [segment(0, tick_end=0),
                segment(0, time=0.001, vol=4)]})
        self.assertEqual(attacks(text), [(0, 'h', 11)])

    def test_quantized_collisions_keep_last_state_and_source_evidence(self):
        rows = {9: [segment(2, tick_end=2),
                    segment(2, time=2/60+0.01, vol=5, tick_end=4)],
                13: [segment(2), segment(5)]}
        before = repr(rows)
        for raw in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'collisions.csv'
                with self.assertWarnsRegex(RuntimeWarning, 'quantized-tick'):
                    text = '#opll_mode 1\n' + render(rows, raw, collision_path=path)
                factor = 1 if raw else 3
                self.assertEqual(attacks(text), [(2*factor, 'b', 10),
                                                (2*factor, 'h', 12), (5*factor, 'h', 12)])
                with path.open(newline='') as stream:
                    report = list(csv.DictReader(stream))
                self.assertEqual(len(report), 1)
                self.assertEqual(report[0]['kept_segment_index'], '1')
                self.assertEqual(json.loads(report[0]['kept_state'])[0], 5)
        self.assertEqual(repr(rows), before)

    def test_one_sample_startup_retrigger(self):
        with self.assertWarnsRegex(RuntimeWarning, 'one-sample'):
            text = '#opll_mode 1\n' + render({10: [segment(0, tick_end=0),
                segment(0, time=1/44100, tick_end=10)]})
        self.assertEqual(attacks(text), [(0, 's', 12)])
        with self.assertRaises(ValueError):
            render({10: [segment(1, tick_end=1), segment(1, time=0)]})

    def test_silent_rhythm_removed_and_mode_zero_f_is_melodic(self):
        text = '#opll_mode 1\n' + render({9: [segment(2, volume=15)]})
        self.assertNotIn('\nf ', annotate_sync_points(text, drop_silent=True))
        nodes = analyze_mml('#opll_mode 0\nf c8 d8\n')[0]['f']
        self.assertEqual(nodes[-1].end, 48)

    def test_rhythm_default_colon_and_combined_notes_count_once(self):
        text = '#opll_mode 1\nf vb15vs13vh12 l16 cb8 h: sh: [h:]2\n'
        nodes = analyze_mml(text)[0]['f']
        self.assertEqual(nodes[-1].end, 72)
        self.assertEqual(attacks(text), [(0, 'b', 15), (0, 'c', 8), (24, 'h', 12),
                                       (36, 'h', 12), (36, 's', 13),
                                       (48, 'h', 12), (60, 'h', 12)])

    def test_sample_final_mml_matches_dumped_groups_in_both_modes(self):
        fixture = ROOT / 'tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm'
        if not fixture.exists():
            self.skipTest('Optional sample fixture unavailable')
        mapping = {'BD':'b', 'SD':'s', 'TOM':'m', 'CYM':'c', 'HH':'h'}
        for raw in (False, True):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                           '--outdir', folder, '--dump-passes']
                if raw:
                    command.append('--raw-ticks')
                run = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                output = Path(folder)
                with (output / 'sample.opll.rhythm.groups.csv').open(newline='') as stream:
                    groups = list(csv.DictReader(stream))
                factor = 1 if raw else 3
                expected = sorted((int(g['tick']) * factor, mapping[h['instrument']], 15-h['vol'])
                                  for g in groups for h in json.loads(g['hits']))
                text = (output / 'sample.mml').read_text()
                self.assertEqual(attacks(text), expected)
                self.assertIn('; chf --- step', text)
                allocation = re.search(r'#alloc \{([^}]+)\}', text)[1]
                self.assertEqual(sum(map(int, re.findall(r'=(\d+)', allocation))), 15000)
                self.assertRegex(allocation, r'\bf=\d+')
