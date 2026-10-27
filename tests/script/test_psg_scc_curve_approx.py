"""Observed representative reuse must obey source and renderer error budgets."""
from dataclasses import asdict, replace
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'py'), str(Path(__file__).parent)]
from psg_scc_curve_approx import project, dump
from psg_scc_performance import analyze
from test_psg_scc_performance import psg, scc


ORIGINAL = (15, 11, 10, 6)
SIMPLER = (15, 10, 10, 6)


def fixture(chip='scc', curves=(ORIGINAL, SIMPLER), length=1, edges=None):
    factory = psg if chip == 'psg' else scc
    channels = {}
    for channel, curve in enumerate(curves):
        channels[channel] = [factory(index*length, length, ch=channel, volume=level,
            tone_period=400, vgmticks=(edges[index] if edges else index*length*735),
            vgmticks_end=(edges[index+1] if edges else (index+1)*length*735))
            for index, level in enumerate(curve)]
    return analyze(channels, chip)


def apply(performance, **kwargs):
    return project(performance, **dict(dict(state_ms=24, max_volume_error=1, max_mean_error=.25), **kwargs))


class CurveApproximationTests(unittest.TestCase):
    def test_disabled_is_identical_and_enabled_requires_explicit_budgets(self):
        performance = fixture()
        for state in (None, 0):
            projection = project(performance, state_ms=state)
            self.assertIs(projection.performance, performance)
            self.assertFalse(projection.summary()['enabled'])
        with self.assertRaisesRegex(ValueError, 'requires'):
            project(performance, state_ms=24)
        for field, value in (('state_ms', -1), ('state_ms', float('nan')),
                             ('max_volume_error', -1), ('max_volume_error', 16),
                             ('max_mean_error', float('inf'))):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                apply(performance, **{field: value})

    def test_near_observed_simpler_curve_replaces_only_derived_runs(self):
        for chip in ('psg', 'scc'):
            with self.subTest(chip=chip):
                performance = fixture(chip);before = asdict(performance)
                projection = apply(performance)
                source = dict(performance.channels)[0][0]
                result = dict(projection.performance.channels)[0][0]
                self.assertEqual(result.runs, ((15, 1), (10, 2), (6, 1)))
                self.assertEqual(replace(result, runs=source.runs), source)
                self.assertEqual(asdict(performance), before)
                for field in ('source_segments', 'controls', 'gates', 'boundaries'):
                    self.assertIs(getattr(projection.performance, field), getattr(performance, field))
                summary = projection.summary()
                self.assertEqual(summary['replaced_notes'], 1)
                self.assertEqual(summary['unique_curves_before'], 2)
                self.assertEqual(summary['unique_curves_after'], 1)
                self.assertEqual(summary['maximum_volume_error'], 1)
                self.assertEqual(summary['maximum_changed_samples'], 735)
                self.assertEqual(summary['maximum_mean_error'], .25)
                self.assertTrue(projection.performance.validate(dict(performance.source_segments)))

    def test_no_observed_simpler_curve_does_not_flatten_an_envelope(self):
        performance = fixture(curves=(ORIGINAL,))
        projection = apply(performance)
        self.assertIs(projection.performance, performance)
        self.assertEqual(projection.decisions[0]['reason'], 'no_bounded_simpler_observed_curve')

    def test_point_mean_and_contiguous_time_budgets_are_independent(self):
        cases = [(dict(max_volume_error=0), 'maximum_volume_error'),
                 (dict(max_mean_error=.24), 'mean_volume_error'),
                 (dict(state_ms=16), 'source_changed_interval_too_long')]
        for options, reason in cases:
            with self.subTest(options=options):
                performance = fixture();projection = apply(performance, **options)
                self.assertIs(projection.performance, performance)
                row = projection.decisions[0]
                self.assertIn(reason, row['rejected_candidates'])
                self.assertEqual(row['candidate_attempts'][0]['reason'], reason)

    def test_source_and_renderer_clocks_are_checked_separately(self):
        performance = fixture(edges=(0, 100, 2100, 2200, 2940))
        projection = apply(performance, max_mean_error=1)
        self.assertIs(projection.performance, performance)
        self.assertIn('source_changed_interval_too_long', projection.decisions[0]['rejected_candidates'])
        performance = fixture(curves=((15, 11, 9, 6), SIMPLER), edges=(0, 100, 200, 300, 2940))
        projection = apply(performance, max_mean_error=1)
        self.assertIs(projection.performance, performance)
        self.assertIn('renderer_changed_interval_too_long', projection.decisions[0]['rejected_candidates'])

    def test_source_duration_mismatch_and_endpoints_cannot_share(self):
        for curve in ((14, 10, 10, 6), (15, 10, 10, 5)):
            performance = fixture(curves=(ORIGINAL, curve))
            self.assertIs(apply(performance, max_volume_error=15, max_mean_error=15).performance, performance)
        performance = fixture()
        native = dict(performance.source_segments)
        native[1] = tuple(replace(row, vgmticks=row.vgmticks*2, vgmticks_end=row.vgmticks_end*2)
                          for row in native[1])
        performance = analyze(native, 'scc')
        self.assertIs(apply(performance, max_mean_error=15).performance, performance)

    def test_silence_and_unresolved_gate_are_never_approximated(self):
        performance = fixture(curves=((15, 0, 10, 6), SIMPLER))
        before = asdict(performance)
        projection = apply(performance, max_volume_error=15, max_mean_error=15)
        self.assertEqual(asdict(performance), before)
        self.assertEqual(projection.performance.channels, performance.channels)
        performance = fixture()
        channels = tuple((ch, tuple(replace(note, gate_ids=()) if ch == 0 else note for note in notes))
                         for ch, notes in performance.channels)
        projection = apply(replace(performance, channels=channels))
        self.assertEqual(projection.decisions[0]['reason'], 'ambiguous_or_missing_gate')

    def test_noise_hardware_envelope_wave_and_zero_sideeffects_protect(self):
        for chip, change in [('psg', dict(mode=3)), ('psg', dict(envelope_enabled=1)),
                             ('scc', dict(waveform_hex='01'*32, waveform_id=1))]:
            performance = fixture(chip);native = dict(performance.source_segments)
            if chip == 'scc':
                zero = replace(native[0][1], l=0, vgmticks_end=native[0][1].vgmticks,
                               ev_type='wtb', **change)
                native[0] = native[0][:1]+(zero,)+native[0][1:]
            else:
                native[0] = tuple(replace(row, **change) for row in native[0])
            performance = analyze(native, chip);projection = apply(performance)
            self.assertEqual(dict(projection.performance.channels)[0], dict(performance.channels)[0])
            self.assertTrue(any(row['action'] == 'protect' for row in projection.decisions if row['channel'] == 0))
        performance = fixture('psg');native = dict(performance.source_segments)
        zero = replace(native[0][1], l=0, vgmticks_end=native[0][1].vgmticks, ev_type='evS')
        native[0] = native[0][:1]+(zero,)+native[0][1:]
        performance = analyze(native, 'psg')
        projection = apply(performance)
        self.assertEqual(dict(projection.performance.channels)[0], dict(performance.channels)[0])

    def test_unknown_time_and_native_gap_cannot_be_inferred_from_ticks(self):
        for change in (dict(vgmticks=None), dict(vgmticks=736)):
            performance = fixture();native = dict(performance.source_segments)
            native[0] = native[0][:1]+(replace(native[0][1], **change),)+native[0][2:]
            performance = analyze(native, 'scc');projection = apply(performance)
            self.assertEqual(dict(projection.performance.channels)[0], dict(performance.channels)[0])
            self.assertTrue(any(row['action'] == 'protect' for row in projection.decisions if row['channel'] == 0))

    def test_renderer_disagreement_is_explicit_and_cannot_chain(self):
        performance = fixture()
        channels = tuple((ch, tuple(replace(note, runs=((15, 1), (9, 2), (6, 1)))
                                   if ch == 0 else note for note in notes))
                         for ch, notes in performance.channels)
        changed = replace(performance, channels=channels)
        self.assertEqual(apply(changed).decisions[0]['reason'], 'renderer_source_curve_disagreement')
        first = apply(performance)
        second = apply(first.performance)
        self.assertEqual(second.performance.channels, first.performance.channels)
        self.assertTrue(any(row['reason'] == 'renderer_source_curve_disagreement' for row in second.decisions))

    def test_representative_choice_does_not_depend_on_channel_iteration(self):
        performance = fixture(curves=(ORIGINAL, SIMPLER, (15, 11, 9, 6)))
        first = apply(performance, state_ms=34, max_mean_error=1)
        reordered = replace(performance, channels=tuple(reversed(performance.channels)))
        second = apply(reordered, state_ms=34, max_mean_error=1)
        self.assertEqual(dict(first.performance.channels), dict(second.performance.channels))
        self.assertEqual(first.decisions, second.decisions)

    def test_dump_exposes_original_projected_curves_and_candidate_rejections(self):
        projection = apply(fixture(), state_ms=16)
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)/'curve'
            dump(projection, prefix)
            summary = json.loads(Path(str(prefix)+'.json').read_text())
            self.assertFalse(summary['lossy'])
            with Path(str(prefix)+'.decisions.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(json.loads(rows[0]['original_source_runs']),
                             [[15, 735], [11, 735], [10, 735], [6, 735]])
            attempt = json.loads(rows[0]['candidate_attempts'])[0]
            self.assertEqual(attempt['source_metrics']['maximum_changed_duration'], 735)
            self.assertEqual(attempt['reason'], 'source_changed_interval_too_long')

    def test_rendered_envelope_matches_projected_runs_and_keeps_pitch_duration(self):
        from mml_envelopes import EnvelopeBank, render
        from test_mml_envelopes import sounding_timeline
        for chip in ('psg', 'scc'):
            performance = fixture(chip)
            projection = apply(performance)
            native = dict(performance.source_segments)
            before = sounding_timeline(render(native, chip, EnvelopeBank(), raw_ticks=True,
                                              performance=performance))
            after = sounding_timeline(render(native, chip, EnvelopeBank(), raw_ticks=True,
                                             performance=projection.performance))
            channel = '1' if chip == 'psg' else '4'
            self.assertEqual([row[2] for row in after[channel]], list(SIMPLER))
            self.assertEqual([row[:2]+row[3:] for row in before[channel]],
                             [row[:2]+row[3:] for row in after[channel]])
            other = '2' if chip == 'psg' else '5'
            self.assertEqual(before[other], after[other])


if __name__ == '__main__':
    unittest.main()
