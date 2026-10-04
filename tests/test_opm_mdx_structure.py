"""Hybrid notes must preserve gates/state; loops must remain reversible."""
from dataclasses import replace
from pathlib import Path
import csv
import json
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'py'), str(ROOT/'scripts')]
from opm_mdx_structure import build_structure, compare_hybrid, note_spelling
from opm_mdx import mdx_tick, projected_samples, project_segments
from opm_to_mdx_mml import convert
from source_loop_plan import expanded_tokens
from test_opm_mdx import analyze, wait, write
from test_opm_reader import vgm


class OpmMdxStructureTests(unittest.TestCase):
    fixture = ROOT/'tests/fixtures/public/opm/from_mdx/nested_phrase_loops/nested_phrase_loops.vgm'

    def build(self, root, source=None, loops=True):
        analysis = analyze(source or self.fixture, root/'trace')
        projection = project_segments(analysis.segments, end_vgmticks=analysis.source_end_vgmticks)
        return analysis, projection, build_structure(projection, analysis.segments, loops=loops)

    def test_native_loop_fixture_has_notes_voices_nested_reversible_loops_and_no_long_plain_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, plan, structure = self.build(Path(tmp))
            self.assertEqual(structure.summary()['note_units'], 24)
            self.assertGreaterEqual(structure.summary()['max_loop_depth'], 2)
            # Native export merges the final phrase rest and song tail. Without
            # rewriting that source interval, emit two outer passes plus the
            # remaining inner repeat, rather than inventing a third outer pass.
            self.assertEqual(structure.summary()['emitted_loop_commands'], 3)
            self.assertLess(len(structure.text), len(structure.plain_text))
            for track, units in structure.units.items():
                text, _ = structure.plans[track].render([u.command for u in units])
                self.assertEqual(expanded_tokens(text), expanded_tokens(' '.join(u.command for u in units)))
            self.assertIn(' & ', structure.text)
            self.assertTrue(all(int(n) <= 256 for n in re.findall(r'[cdefgab]\+?%(\d+)', structure.text)))
            self.assertTrue(all(units[-1].end_tick == plan.end_mdx_tick for units in structure.units.values()))
            # Native banks are M1,M2,C1,C2; MDX text rows are M1,C1,M2,C2.
            ops = structure.voices[0][0]
            self.assertIn(','.join(map(str, ops[2]))+',', structure.text)

    def test_partial_and_same_time_keys_do_not_become_notes(self):
        commands = write(0x28, 0x4e)+write(8, 8)+write(8, 0)+write(8, 8)+wait(101)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'source.vgm'; path.write_bytes(vgm(commands))
            source, _, structure = self.build(root, path)
            self.assertEqual(structure.summary()['note_units'], 0)
            tokens = expanded_tokens(' '.join(u.command for u in structure.units['A']))
            self.assertEqual([token for token in tokens if token.startswith('y8,')], ['y8,8','y8,0','y8,8'])
            self.assertEqual(sum(bool(e.rising_mask) for e in source.events), 2)

    def test_tempo_track_with_no_channel_zero_controls_keeps_common_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'channel1.vgm'
            path.write_bytes(vgm(write(0x29, 0x4e)+write(8, 9)+wait(101)))
            source, plan, structure = self.build(root, path)
            self.assertEqual(set(structure.units), {'A', 'B'})
            self.assertEqual(structure.units['A'][0].end_tick, plan.end_mdx_tick)
            self.assertTrue(any(line.startswith('B ') and 'y8,9' in line for line in structure.text.splitlines()))

    def test_unknown_tones_and_unreleased_tails_are_preserved_as_raw_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'source.vgm'
            path.write_bytes(vgm(write(0x28, 0x4e)+write(8, 120)+wait(101)))
            source, plan, structure = self.build(root, path)
            self.assertEqual(structure.summary()['note_units'], 0)
            self.assertIn('y8,120', structure.text)
            self.assertNotIn('y8,0', structure.text)
            self.assertEqual(structure.units['A'][-1].end_tick, plan.end_mdx_tick)

    def test_isolated_carrier_only_notes_keep_their_original_operator_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'carrier.vgm'
            path.write_bytes(self.fixture.read_bytes().replace(write(8, 120), write(8, 64)))
            source, _, structure = self.build(root, path)
            self.assertEqual(structure.summary()['note_units'], 24)
            self.assertTrue(all(voice[-1] == 8 for voice in structure.voices))
            self.assertEqual(sum(e.rising_mask.bit_count() for e in source.events), 24)

    def test_held_parameter_changes_stay_in_the_raw_control_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ROOT/'tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm'
            source, _, structure = self.build(root, fixture)
            attack = next(e for e in source.events if e.rising_mask)
            unit = next(u for u in structure.units[chr(65+attack.ch)]
                        if attack.source_event_id in u.source_event_ids)
            self.assertEqual(unit.kind, 'controls')
            ids = {eid for units in structure.units.values() for u in units for eid in u.source_event_ids}
            retained = {s.source_event_id for s in source.segments if s.source_event_id is not None}
            self.assertEqual(ids, retained)

    def test_reserved_key_bits_are_not_discarded_by_note_notation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'reserved.vgm'
            path.write_bytes(self.fixture.read_bytes().replace(write(8, 120), write(8, 248)))
            source, _, structure = self.build(root, path)
            self.assertEqual(structure.summary()['note_units'], 0)
            tokens = expanded_tokens(' '.join(u.command for u in structure.units['A']))
            self.assertEqual(tokens.count('y8,248'), 24)
            self.assertEqual(sum(bool(e.rising_mask) for e in source.events), 24)

    def test_note_pitch_inverse_uses_target_kc_table_and_kf_without_rounding(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _, _ = self.build(Path(tmp))
            state = next(s.state for s in source.segments if s.rising_mask == 15)
            self.assertEqual(note_spelling(state), (4, 'c', 0))
            self.assertEqual(note_spelling(replace(state, kf_raw=0)), (4, 'c', -5))
            self.assertIsNone(note_spelling(replace(state, kf_raw=21)))
            self.assertIsNone(note_spelling(replace(state, kc_raw=0x3f)))

    def test_dump_preserves_segment_cells_and_adds_unit_and_loop_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, source, projection = convert(self.fixture, root/'out', dump_passes=True)
            segment_path = root/'out/nested_phrase_loops.opm.segments.csv'
            with segment_path.open(encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(any(json.loads(row['mdx_loop_path']) for row in rows))
            self.assertEqual({int(r['segment_id']): (int(r['ch']), int(r['vgmticks']), int(r['vgmticks_end'])) for r in rows},
                             {s.segment_id: (s.ch, s.vgmticks, s.vgmticks_end) for s in source.segments})
            self.assertTrue((root/'out/nested_phrase_loops.mdx.structure.voices.csv').is_file())
            self.assertTrue(any(json.loads(row['opm_source_loop_path']) for row in rows))
            self.assertFalse((root/'out/nested_phrase_loops.mdx.structure.A.loops.csv').exists())

    def test_hybrid_comparison_rejects_wrong_pitch_keys_and_end_even_with_equal_key_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, plan, _ = self.build(Path(tmp))
            actual = replace(source, events=tuple(replace(e, vgmticks=projected_samples(mdx_tick(e.vgmticks)))
                                                 for e in source.events),
                             source_end_vgmticks=plan.end_projected_vgmticks)
            self.assertTrue(compare_hybrid(plan, source, actual, initialization=[])['passed'])
            pitch = replace(actual, events=tuple(replace(e, state=replace(e.state, kc_raw=0x4e))
                                                 if e.state.key_mask else e for e in actual.events))
            result = compare_hybrid(plan, source, pitch, initialization=[])
            self.assertEqual(result['source_channel_attacks'], result['returned_channel_attacks'])
            self.assertFalse(result['passed']); self.assertGreater(result['known_state_mismatches'], 0)
            key = replace(actual, events=tuple(replace(e, vgmticks=e.vgmticks+1)
                                               if e.rising_mask else e for e in actual.events))
            self.assertFalse(compare_hybrid(plan, source, key, initialization=[])['key_edge_sequence_matches'])
            end = replace(actual, source_end_vgmticks=actual.source_end_vgmticks+1)
            self.assertFalse(compare_hybrid(plan, source, end, initialization=[])['passed'])


if __name__ == '__main__':
    unittest.main()
