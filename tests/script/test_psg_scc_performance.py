"""Authored native Segments: preserve source controls and legacy partitions."""
import csv
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))
from chip_segments import PsgSegment, SccSegment
from psg_scc_performance import analyze, audible, dump, settings


def psg(tick=0, length=2, **kwargs):
    values = dict(ev_type='v', time=0.0, ch=0, ticks=tick, l=length,
                  tone_period=100, volume=12, octave=4, scale='c', volume_delta=0,
                  pass3_row=('authored',), mode=1, noise_period=3,
                  envelope_enabled=0, envelope_period=10, envelope_shape=9,
                  mixer=0, amplitude_register=12, vgmticks=tick * 735,
                  vgmticks_end=(tick + length) * 735)
    values.update(kwargs)
    return PsgSegment(**values)


def scc(tick=0, length=2, **kwargs):
    values = dict(ev_type='v', time=0.0, ch=0, ticks=tick, l=length,
                  tone_period=100, volume=12, octave=4, scale='c', volume_delta=0,
                  pass3_row=('authored',), previous_tone_period=100, enabled=1,
                  volume_run_count=1, waveform_id=0, waveform_hex='00' * 32,
                  enable_register=1, vgmticks=tick * 735,
                  vgmticks_end=(tick + length) * 735)
    values.update(kwargs)
    return SccSegment(**values)


def legacy_partition(rows, chip):
    """Frozen pre-IR partition behavior, independent of the new implementation."""
    notes, boundary = [], False
    pitch_events = {'fCA', 'fCB'} if chip == 'psg' else {'f1Ctrl', 'f2Ctrl'}
    for index, seg in enumerate(rows):
        if seg.ev_type in pitch_events or (chip == 'psg' and seg.ev_type == 'evS'):
            boundary = True
        if seg.l <= 0:
            continue
        rest = not audible(seg, chip)
        previous = notes[-1] if notes else None
        same = previous is not None and previous[1] + previous[2] == seg.ticks and previous[3] == rest
        if same and not rest:
            same = (not boundary and settings(previous[0], chip) == settings(seg, chip)
                    and seg.volume <= previous[4][-1][0])
        if not same:
            notes.append([seg, seg.ticks, 0, rest, [], []])
        note = notes[-1]
        note[2] += seg.l
        note[5].append(index)
        if not rest:
            if note[4] and note[4][-1][0] == seg.volume:
                v, n = note[4][-1]
                note[4][-1] = (v, n + seg.l)
            else:
                note[4].append((seg.volume, seg.l))
        boundary = False
    return [(n[0], n[1], n[2], n[3], tuple(n[4]), tuple(n[5])) for n in notes]


class PerformanceTests(unittest.TestCase):
    def test_sample_clock_is_explicit_and_preserved_in_dumps(self):
        from psg_scc_volume_curves import project
        rows = {0: [psg(0, 441, vgmticks=0, vgmticks_end=441),
                    psg(441, 441, ev_type='evS', vgmticks=441, vgmticks_end=882)]}
        performance = analyze(rows, 'psg', tick_clock_hz=44100)
        projection = project(performance)
        self.assertEqual(projection.performance.tick_clock_hz, 44100)
        self.assertEqual(projection.summary()['tick_clock_hz'], 44100)
        self.assertEqual(dict(projection.performance.channels)[0][0].length, 882)
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder)/'source'
            dump(projection.performance, prefix)
            metadata = json.loads(Path(str(prefix)+'.performance.json').read_text())
            self.assertEqual(metadata['tick_clock_hz'], 44100)
        with self.assertRaises(ValueError):
            analyze(rows, 'psg', tick_clock_hz=0)

    def test_exact_legacy_partitions_both_chips(self):
        for chip, factory, pitch in [('psg', psg, 'fCA'), ('scc', scc, 'f1Ctrl')]:
            with self.subTest(chip=chip):
                rows = [factory(), factory(2, volume=9), factory(4, volume=11),
                        factory(6, 0, ev_type=pitch), factory(6),
                        factory(8, volume=0), factory(10, volume=0), factory(12)]
                performance = analyze({0: rows}, chip)
                actual = [(n.segment, n.start, n.length, n.rest, n.runs, n.segment_indices)
                          for _, notes in performance.channels for n in notes]
                self.assertEqual(legacy_partition(rows, chip), actual)
                self.assertTrue(performance.validate({0: rows}))

    def test_volume_curve_falls_inside_gate_and_rise_partitions_score(self):
        performance = analyze({0: [psg(), psg(2, volume=8), psg(4, volume=10)]}, 'psg')
        notes = dict(performance.channels)[0]
        self.assertEqual(1, len(performance.gates))
        self.assertEqual(2, len(notes))
        self.assertEqual(((12, 2), (8, 2)), notes[0].runs)
        self.assertIn('volume_rise', notes[1].boundary_reasons)
        self.assertEqual([12, 8, 10], [dict(p.native_value)['volume']
                                     for p in performance.controls if p.kind == 'volume'])

    def test_pitch_write_and_changed_pitch_are_distinct_retained_controls(self):
        rows = [psg(), psg(2, 0, ev_type='fCA'), psg(2), psg(4, tone_period=101)]
        performance = analyze({0: rows}, 'psg')
        notes = dict(performance.channels)[0]
        self.assertEqual(3, len(notes))
        self.assertIn('pitch_write', notes[1].boundary_reasons)
        self.assertIn('settings_change', notes[2].boundary_reasons)
        controls = [p for p in performance.controls if p.kind == 'pitch']
        self.assertEqual(['v', 'fCA', 'v', 'v'], [p.source_event for p in controls])
        self.assertEqual([100, 100, 100, 101], [dict(p.native_value)['tone_period'] for p in controls])

    def test_scc_waveform_changes_are_internal_timbre_controls(self):
        rows = [scc(), scc(2, waveform_id=1, waveform_hex='01' * 32)]
        performance = analyze({0: rows}, 'scc')
        self.assertEqual(1, len(performance.gates))
        self.assertEqual(2, len(dict(performance.channels)[0]))
        waves = [dict(p.native_value)['waveform_id'] for p in performance.controls if p.kind == 'timbre']
        self.assertEqual([0, 1], waves)

    def test_repeated_same_value_envelope_reset_survives_zero_time(self):
        rows = [psg(envelope_enabled=1),
                psg(2, 0, ev_type='evS', envelope_enabled=1),
                psg(2, envelope_enabled=1),
                psg(4, 0, ev_type='evS', envelope_enabled=1),
                psg(4, envelope_enabled=1)]
        performance = analyze({0: rows}, 'psg')
        notes = dict(performance.channels)[0]
        self.assertEqual(3, len(notes))
        resets = [p for p in performance.controls if p.kind == 'hardware_envelope'
                  and dict(p.native_value)['reset_event']]
        self.assertEqual([1, 3], [p.segment_index for p in resets])
        self.assertEqual([1470, 2940], [p.source_sample for p in resets])
        self.assertEqual(1, len(performance.gates))
        self.assertEqual('source_audibility', performance.gates[0].interpretation)

    def test_positive_subtick_silence_breaks_source_gate_not_legacy_note(self):
        rows = [psg(vgmticks=0, vgmticks_end=1460),
                psg(2, 0, volume=0, vgmticks=1460, vgmticks_end=1470),
                psg(2, vgmticks=1470, vgmticks_end=2940)]
        performance = analyze({0: rows}, 'psg')
        self.assertEqual(2, len(performance.gates))
        note, = dict(performance.channels)[0]
        self.assertTrue(note.gate_ambiguity)
        self.assertEqual((0, 2), note.segment_indices)
        self.assertEqual((0, 1, 2), tuple(p.segment_index for p in performance.controls if p.kind == 'pitch'))
        self.assertEqual(rows, performance.reconstruct_segments()[0])

    def test_unknown_samples_never_derived_from_float_or_ticks(self):
        rows = [psg(vgmticks=None, vgmticks_end=None, time=123.456),
                psg(2, vgmticks=None, vgmticks_end=None)]
        performance = analyze({0: rows}, 'psg')
        self.assertIsNone(performance.gates[0].source_sample_start)
        self.assertIsNone(performance.gates[0].source_sample_end)
        self.assertTrue(all(p.source_sample is None and p.relative_source_sample is None
                            for p in performance.controls))
        self.assertEqual([0, 2], [p.tick for p in performance.controls if p.kind == 'pitch'])

    def test_all_rest_and_zero_rows_still_retained_without_renderer_channel(self):
        rows = [psg(0, 0, volume=0), psg(0, volume=0)]
        performance = analyze({0: rows}, 'psg')
        self.assertEqual((), performance.channels)
        self.assertEqual((), performance.gates)
        self.assertEqual(rows, performance.reconstruct_segments()[0])
        self.assertTrue(performance.validate())

    def test_missing_source_timing_with_positive_tick_gap_splits_gate(self):
        rows = [psg(vgmticks=None, vgmticks_end=None),
                psg(4, vgmticks=None, vgmticks_end=None)]
        performance = analyze({0: rows}, 'psg')
        self.assertEqual(2, len(performance.gates))
        self.assertEqual('audibility_after_tick_gap', performance.gates[1].boundary_reason)
        self.assertIsNone(performance.gates[1].source_sample_start)

    def test_known_source_continuity_not_split_by_tick_rounding_gap(self):
        rows = [psg(vgmticks=0, vgmticks_end=1460),
                psg(4, vgmticks=1460, vgmticks_end=2940)]
        performance = analyze({0: rows}, 'psg')
        self.assertEqual(1, len(performance.gates))
        self.assertEqual(2, len(dict(performance.channels)[0]))

    def test_immutable_ir_and_mutable_legacy_adapter_are_separate(self):
        from mml_envelopes import Note
        performance = analyze({0: [psg(), psg(2, volume=8)]}, 'psg')
        note = dict(performance.channels)[0][0]
        with self.assertRaises(FrozenInstanceError):
            note.length = 99
        with self.assertRaises(FrozenInstanceError):
            note.segment.volume = 0
        adapted = performance.to_notes(Note)
        adapted[0][0].runs.append((0, 99))
        adapted[0][0].segment_indices.append(999)
        adapted[0][0].envelope = 3
        self.assertEqual(((12, 2), (8, 2)), note.runs)
        self.assertEqual((0, 1), note.segment_indices)

    def test_structural_repeat_keys_exclude_source_ids_and_offsets(self):
        first = analyze({0: [psg(), psg(2, volume=8)]}, 'psg')
        shifted = analyze({2: [replace(psg(), ch=2, ticks=10, vgmticks=7350, vgmticks_end=8820),
                               replace(psg(2, volume=8), ch=2, ticks=12,
                                       vgmticks=8820, vgmticks_end=10290)]}, 'psg')
        a, b = dict(first.channels)[0][0], dict(shifted.channels)[2][0]
        self.assertEqual(a.structural_key, b.structural_key)
        self.assertNotEqual(a.gate_ids, b.gate_ids)
        self.assertEqual(a.structural_equality_key(), b.structural_equality_key())

    def test_segment_order_validation_rejects_changed_evidence(self):
        rows = [psg(), psg(2, volume=8)]
        performance = analyze({0: rows}, 'psg')
        with self.assertRaisesRegex(ValueError, 'order/state'):
            performance.validate({0: list(reversed(rows))})

    def test_dumps_label_clocks_lineage_unknowns_and_controls(self):
        rows = [psg(vgmticks=None, vgmticks_end=None), psg(2, 0, ev_type='evS')]
        performance = analyze({0: rows}, 'psg')
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / 'authored.psg'
            dump(performance, prefix)
            summary = json.loads(Path(str(prefix) + '.performance.json').read_text())
            self.assertEqual(1, summary['source_samples_unknown'])
            self.assertEqual(44100, summary['source_clock_hz'])
            self.assertEqual(60, summary['tick_clock_hz'])
            with Path(str(prefix) + '.performance.controls.csv').open(newline='') as stream:
                controls = list(csv.DictReader(stream))
            self.assertEqual('', controls[0]['source_sample'])
            self.assertEqual('0', controls[0]['tick'])
            with Path(str(prefix) + '.performance.segments.csv').open(newline='') as stream:
                source = list(csv.DictReader(stream))
            self.assertEqual(2, len(source))
            self.assertEqual('evS', source[1]['ev_type'])
            self.assertEqual('0', source[1]['l'])


if __name__ == '__main__':
    unittest.main()
