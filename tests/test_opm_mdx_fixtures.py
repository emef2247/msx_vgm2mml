"""Original MDX/MML fixtures: authored intent plus raw VGM/Segment evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/public/opm/from_mdx'
sys.path.insert(0, str(ROOT / 'py'))
from opm import build_segments, key_counts
from vgm_io import read_vgm_bytes
from vgm_reader import parse_vgm
from vgm_timing import command_times


class OpmMdxFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURES / 'manifest.json').read_text(encoding='utf-8'))
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.cases = {}
        for name in cls.manifest['cases']:
            source = FIXTURES / name / (name + '.vgm')
            metadata = {}
            parse_vgm(str(source), str(Path(cls.temp.name) / name),
                      opm_metadata=metadata, dump_opm_segments=True)
            analysis = build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks'])
            cls.cases[name] = (source, metadata, analysis)

    def test_all_cases_preserve_source_evidence_and_authored_attack_counts(self):
        self.assertEqual(len(self.cases), 9)
        for name, (source, metadata, analysis) in self.cases.items():
            with self.subTest(case=name):
                expected = self.manifest['cases'][name]
                for path, digest in expected['sha256'].items():
                    self.assertEqual(hashlib.sha256((FIXTURES / path).read_bytes()).hexdigest(), digest)
                raw = read_vgm_bytes(source)
                events = list(command_times(raw))
                writes = [(i, e.address, e.vgmticks, raw[e.address + 1], raw[e.address + 2])
                          for i, e in enumerate(events) if e.command == 0x54]
                self.assertEqual(metadata['clock_hz'], 4000000)
                self.assertEqual(metadata['write_count'], len(writes))
                self.assertEqual(analysis.source_end_vgmticks, events[-1].vgmticks)
                # Key register events are one-to-one; channel writes and shared writes
                # otherwise fan out differently in the native state representation.
                self.assertEqual([(e.source_event_id, e.address, e.vgmticks, e.register, e.data)
                                  for e in analysis.events if e.register == 8],
                                 [w for w in writes if w[3] == 8])
                counts = key_counts(analysis)
                for field in ('channel_attack_events', 'operator_keyons', 'operator_keyoffs'):
                    self.assertEqual(counts[field], expected[field])
                self.assertEqual(sorted({e.ch for e in analysis.events if e.rising_mask}), expected['active_channels'])
                self.assertEqual(sum(s.rising_mask.bit_count() for s in analysis.segments), expected['operator_keyons'])
                self.assertEqual(sum(s.falling_mask.bit_count() for s in analysis.segments), expected['operator_keyoffs'])
                for ch in range(8):
                    spans = [s for s in analysis.segments if s.ch == ch]
                    self.assertEqual(spans[0].vgmticks, 0)
                    self.assertEqual(spans[-1].vgmticks_end, events[-1].vgmticks)
                    self.assertEqual(sum(s.duration_samples for s in spans), events[-1].vgmticks)
                    self.assertTrue(all(a.vgmticks_end == b.vgmticks for a, b in zip(spans, spans[1:])))

    def test_eight_channels_have_distinct_pitch_and_independent_pan(self):
        analysis = self.cases['eight_channels_pan'][2]
        first = [next(e for e in analysis.events if e.ch == ch and e.rising_mask) for ch in range(8)]
        self.assertEqual([(e.state.left_enabled, e.state.right_enabled) for e in first],
                         [(1, 0), (0, 1), (1, 1), (1, 0), (0, 1), (1, 1), (1, 0), (0, 1)])
        self.assertEqual(len({e.state.kc_raw for e in first}), 8)
        self.assertEqual(len({e.vgmticks for e in first}), 1)

    def test_partial_operator_keys_are_individual_edges(self):
        analysis = self.cases['partial_operator_keys'][2]
        edges = [e for e in analysis.events if e.register == 8 and e.changed]
        self.assertEqual([e.state.key_mask for e in edges], [15, 0, 1, 3, 7, 15, 14, 12, 8, 0])
        self.assertEqual([e.rising_mask for e in edges[2:6]], [1, 2, 4, 8])
        self.assertEqual([e.falling_mask for e in edges[6:]], [1, 2, 4, 8])
        self.assertTrue(all(e.ch == 3 for e in edges))
        self.assertTrue(all(a.vgmticks < b.vgmticks for a, b in zip(edges, edges[1:])))

    def test_held_pitch_patch_volume_and_pan_do_not_retrigger(self):
        analysis = self.cases['held_controls'][2]
        held = [e for e in analysis.events if e.state.key_mask == 15]
        self.assertGreater(len({e.state.kf_raw for e in held}), 1)
        self.assertEqual({e.state.algorithm for e in held}, {4, 7})
        self.assertGreater(len({e.state.operators[3].tl for e in held}), 1)
        self.assertTrue({(1, 0), (0, 1), (1, 1)} <= {(e.state.left_enabled, e.state.right_enabled) for e in held})
        self.assertEqual({e.continuity_id for e in held}, {1})

    def test_hardware_lfo_depth_latches_and_sensitivity(self):
        analysis = self.cases['hardware_lfo_depths'][2]
        states = [e.state for e in analysis.events if e.ch == 0]
        self.assertTrue(any(s.amd == 17 and s.pmd == 35 and s.lfo_rate_raw == 180
                            and s.lfo_waveform == 2 for s in states))
        self.assertTrue(any(s.amd == 9 and s.pmd == 35 for s in states))
        self.assertTrue(any(s.amd == 9 and s.pmd == 55 for s in states))
        held = [s for s in states if s.key_mask == 15]
        self.assertTrue({(0, 0), (4, 2)} <= {(s.pms, s.ams) for s in held})
        self.assertTrue(any(s.lfo_reset == 1 for s in states))
        self.assertTrue(any(any(op.am_enabled == 1 for op in s.operators) for s in held))

    def test_channel7_noise_changes_preserve_held_key(self):
        analysis = self.cases['noise_channel7'][2]
        noise = [e for e in analysis.events if e.ch == 7 and e.register == 15]
        self.assertEqual([e.data for e in noise], [0, 128, 132, 148, 159, 0])
        self.assertEqual([(e.state.noise_enabled, e.state.noise_rate) for e in noise[-4:]],
                         [(1, 4), (1, 20), (1, 31), (0, 0)])
        self.assertTrue(all(e.state.key_mask == 15 for e in noise[-3:]))

    def test_same_sample_pulse_and_redundant_key_are_not_lost(self):
        analysis = self.cases['same_sample_retrigger'][2]
        keys = [e for e in analysis.events if e.register == 8]
        # Ordinary note on/off, then on/off/on/nochange at one sample.
        pulse = keys[2:6]
        self.assertEqual([e.state.key_mask for e in pulse], [15, 0, 15, 15])
        self.assertEqual([e.ev_type for e in pulse], ['key_on', 'key_off', 'key_on', 'key_nochange'])
        self.assertEqual(len({e.vgmticks for e in pulse}), 1)
        self.assertTrue(any(s.ev_type == 'key_off' and s.duration_samples == 0 for s in analysis.segments))

    def test_operator_register_banks_keep_distinct_values(self):
        analysis = self.cases['operator_register_banks'][2]
        state = next(e.state for e in reversed(analysis.events) if e.ch == 0 and e.state.key_mask == 15)
        self.assertEqual([(op.dt1, op.mul) for op in state.operators], [(1, 1), (2, 2), (3, 3), (4, 4)])
        self.assertEqual([op.tl for op in state.operators], [11, 22, 33, 44])
        m1 = state.operators[0]
        self.assertEqual((m1.ks, m1.ar, m1.am_enabled, m1.d1r, m1.dt2, m1.d2r, m1.d1l, m1.rr),
                         (1, 31, 1, 12, 1, 5, 6, 7))

    def test_release_spans_and_nested_phrase_attack_counts(self):
        analysis = self.cases['release_retrigger'][2]
        attacks = [e for e in analysis.events if e.rising_mask]
        releases = [e for e in analysis.events if e.falling_mask]
        self.assertEqual(len(attacks), 4)
        self.assertTrue(all(off.vgmticks < on.vgmticks for off, on in zip(releases, attacks[1:])))
        self.assertTrue(any(s.ev_type == 'key_off' and s.duration_samples > 0 for s in analysis.segments))
        nested = self.cases['nested_phrase_loops'][2]
        self.assertEqual(key_counts(nested)['channel_attack_events'], 3 * 2 * 4)


if __name__ == '__main__':
    unittest.main()
