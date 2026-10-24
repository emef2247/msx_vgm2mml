"""Authored controls exercise explicitly heuristic percussion classification."""
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))
from chip_segments import PsgSegment, SccSegment
from drum_inference import infer, _spectrum
from psg_scc_performance import analyze


def psg(start=0, end=2205, **kwargs):
    values = dict(ev_type='v', time=start / 44100, ch=0, ticks=round(start / 735),
                  l=round(end / 735) - round(start / 735), tone_period=100,
                  volume=12, octave=4, scale='c', volume_delta=0, pass3_row=(),
                  vgmticks=start, vgmticks_end=end, mode=2, noise_period=3,
                  envelope_enabled=0, envelope_period=10, envelope_shape=9,
                  mixer=0, amplitude_register=12)
    values.update(kwargs)
    return PsgSegment(**values)


def scc(start=0, end=2205, **kwargs):
    values = dict(ev_type='v', time=start / 44100, ch=0, ticks=round(start / 735),
                  l=round(end / 735) - round(start / 735), tone_period=100,
                  volume=12, octave=4, scale='c', volume_delta=0, pass3_row=(),
                  vgmticks=start, vgmticks_end=end, enabled=1,
                  previous_tone_period=100, volume_run_count=1,
                  waveform_id=0, waveform_hex='7f' + '00' * 31, enable_register=1)
    values.update(kwargs)
    return SccSegment(**values)


def catalog(rows, chip='psg'):
    return infer([analyze({rows[0].ch: rows}, chip)])


class DrumInferenceTests(unittest.TestCase):
    def test_noise_volume_control_curve_is_one_hit(self):
        rows = [psg(0, 882), psg(882, 1764, volume=8), psg(1764, 2646, volume=4)]
        candidate, = catalog(rows)
        self.assertEqual('HH', candidate.instrument)
        self.assertEqual((0, 1, 2), candidate.segment_indices)
        self.assertEqual(8, candidate.volume)
        self.assertEqual(60, dict(candidate.features)['duration_ms'])

    def test_continuous_gate_volume_reattacks(self):
        rows = [psg(0, 882), psg(882, 1764, volume=4),
                psg(1764, 2646), psg(2646, 3528, volume=5)]
        candidates = catalog(rows)
        self.assertEqual(2, len(candidates))
        self.assertEqual(['HH', 'HH'], [c.instrument for c in candidates])
        self.assertIn('strong_volume_rise', candidates[1].reasons)
        self.assertEqual((2, 3), candidates[1].segment_indices)

    def test_downward_pitch_writes_are_one_tonal_hit(self):
        rows = [psg(0, 882, mode=1, tone_period=400),
                psg(882, 1764, mode=1, tone_period=500, volume=8, ev_type='fCA'),
                psg(1764, 2646, mode=1, tone_period=600, volume=4, ev_type='fCA')]
        candidate, = catalog(rows)
        self.assertEqual('BD', candidate.instrument)
        self.assertEqual((0, 1, 2), candidate.segment_indices)
        # A mixed tonal/noise sweep should still prefer the tonal drum decision.
        mixed = [replace(row, mode=3) for row in rows]
        self.assertEqual('BD', catalog(mixed)[0].instrument)

    def test_hardware_envelope_register_decline_is_not_tonal_decay(self):
        rows = [psg(0, 882, mode=1, tone_period=400, envelope_enabled=1),
                psg(882, 2646, mode=1, tone_period=600, volume=4, envelope_enabled=1)]
        candidate, = catalog(rows)
        self.assertIsNone(candidate.instrument)
        self.assertIn('hardware_envelope_curve_not_observed_as_fixed_volume', candidate.reasons)
        # Noise needs no inferred fixed-volume decay, so the short-gesture
        # classifier may still supply a percussion hypothesis.
        mixed = [replace(row, mode=3) for row in rows]
        candidate, = catalog(mixed)
        self.assertEqual('HH', candidate.instrument)
        self.assertNotIn('downward_pitch_sweep_with_decay', candidate.reasons)

    def test_sustained_noise_and_decaying_melody_are_rejected(self):
        for rows in ([psg(0, 22050)], [psg(0, 2205, mode=1), psg(2205, 4410, mode=1, volume=4)]):
            with self.subTest(rows=rows):
                candidate, = catalog(rows)
                self.assertIsNone(candidate.instrument)
                self.assertTrue(candidate.reasons)

    def test_scc_broadband_decay_and_sine_melody(self):
        broad = [scc(0, 2205), scc(2205, 4410, volume=4)]
        self.assertEqual('SD', catalog(broad, 'scc')[0].instrument)
        wave = bytes(round(100 * math.sin(2 * math.pi * i / 32)) & 255 for i in range(32)).hex()
        sine = [replace(row, waveform_hex=wave) for row in broad]
        self.assertIsNone(catalog(sine, 'scc')[0].instrument)
        self.assertLess(_spectrum(wave)[0], .25)
        self.assertGreater(_spectrum(broad[0].waveform_hex)[0], .25)

    def test_scc_tonal_sweep_needs_decay(self):
        wave = bytes(round(100 * math.sin(2 * math.pi * i / 32)) & 255 for i in range(32)).hex()
        rows = [scc(0, 882, waveform_hex=wave),
                scc(882, 2646, tone_period=150, volume=4, waveform_hex=wave)]
        self.assertEqual('TOM', catalog(rows, 'scc')[0].instrument)
        self.assertIsNone(catalog([replace(row, volume=12) for row in rows], 'scc')[0].instrument)

    def test_same_sample_initialization_is_not_extra_attack(self):
        rows = [psg(0, 0, volume=2, mode=1), psg(0, 0, ev_type='evS', envelope_enabled=1),
                psg(0, 2205, envelope_enabled=1), psg(2205, 2205, volume=10)]
        candidate, = catalog(rows)
        self.assertEqual((0, 1, 2, 3), candidate.segment_indices)
        self.assertEqual('HH', candidate.instrument)

    def test_same_value_hardware_envelope_reset_splits_after_sound(self):
        rows = [psg(0, 2205, envelope_enabled=1),
                psg(2205, 2205, ev_type='evS', envelope_enabled=1),
                psg(2205, 4410, envelope_enabled=1)]
        candidates = catalog(rows)
        self.assertEqual(2, len(candidates))
        self.assertEqual((1, 2), candidates[1].segment_indices)
        self.assertIn('hardware_envelope_reset', candidates[1].reasons)

    def test_noise_transition_and_unknown_source_timing(self):
        candidates = catalog([psg(0, 2205, mode=1), psg(2205, 4410)])
        self.assertEqual(2, len(candidates))
        self.assertIsNone(candidates[0].instrument)
        self.assertEqual('HH', candidates[1].instrument)
        unknown = [replace(psg(), vgmticks=None, vgmticks_end=None)]
        candidate, = catalog(unknown)
        self.assertIsNone(candidate.instrument)
        self.assertIsNone(candidate.source_sample)
        self.assertIsNone(dict(candidate.features)['duration_ms'])
        self.assertIn('unknown_source_sample_timing', candidate.reasons)

    def test_source_samples_override_rounded_ticks(self):
        row = replace(psg(0, 17640), ticks=0, l=1)
        candidate, = catalog([row])
        self.assertEqual(400, dict(candidate.features)['duration_ms'])
        self.assertIsNone(candidate.instrument)

    def test_immutable_catalog_native_segments_and_arbitrary_channels(self):
        rows = [replace(psg(0, 882), ch=2), replace(psg(882, 1764, volume=4), ch=2)]
        performance = analyze({2: rows}, 'psg')
        original = performance.reconstruct_segments()
        candidate, = infer(iter([performance]))
        self.assertEqual(2, candidate.channel)
        self.assertEqual(original, performance.reconstruct_segments())
        with self.assertRaises(FrozenInstanceError):
            candidate.volume = 15
        self.assertIsInstance(candidate.features, tuple)
        self.assertIsInstance(candidate.reasons, tuple)

    def test_invalid_waveform_does_not_qualify(self):
        for wave in ('nonsense', '00' * 32):
            self.assertIsNone(catalog([scc(0, 882, waveform_hex=wave),
                                       scc(882, 1764, volume=4, waveform_hex=wave)], 'scc')[0].instrument)


if __name__ == '__main__':
    unittest.main()
