"""MDX target timing/order and independently generated public replay evidence."""
from dataclasses import replace
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opm import build_segments
from opm_mdx import project_segments, render
from opm_roundtrip import controls, compare
from vgm_reader import parse_vgm
from test_opm_reader import vgm


def analyze(source, outdir):
    metadata = {}
    parse_vgm(str(source), str(outdir), opm_metadata=metadata)
    return build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks'])


def wait(samples):
    return b'\x61' + samples.to_bytes(2, 'little')


def write(register, data):
    return bytes((0x54, register, data))


class OpmMdxTests(unittest.TestCase):
    def test_cli_defaults_to_mml_only_and_dump_retains_identical_music_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(write(0x28, 0x4e) + write(8, 8) + wait(101)
                                 + write(8, 0) + wait(101)))
            outputs = []
            for name, options in [('default', []), ('dump', ['--dump-passes'])]:
                folder = root / name
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/opm_to_mdx_mml.py'),
                                      str(path), '--outdir', str(folder), *options],
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                outputs.append((folder / 'source.mdx.mml').read_bytes())
                if name == 'default':
                    self.assertEqual([p.name for p in folder.iterdir()], ['source.mdx.mml'])
                else:
                    for filename in ('source_trace.opm_regs.csv', 'source_trace.opm.csv',
                                     'source.opm.segments.csv', 'source.mdx.controls.csv',
                                     'source.mdx.timing.json'):
                        self.assertTrue((folder / filename).is_file(), filename)
                    replay = build_segments(folder / 'source_trace.opm_regs.csv', end_vgmticks=202)
                    self.assertEqual(sum(bool(s.rising_mask) for s in replay.segments), 1)
                    self.assertEqual(sum(bool(s.falling_mask) for s in replay.segments), 1)
            self.assertEqual(outputs[0], outputs[1])

    def test_shared_fanout_redundancy_partial_keys_and_same_sample_order(self):
        commands = (write(0x19, 0x12) + write(0x19, 0x93)
                    + write(0x28, 0x4e) + write(0x28, 0x4e)
                    + write(8, 8) + write(8, 0) + write(8, 8) + wait(101))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(commands))
            source = analyze(path, root / 'source')
            plan = project_segments(source.segments, end_vgmticks=source.source_end_vgmticks)
            self.assertEqual([(w.register, w.data) for w in plan.writes],
                             [(0x19, 0x12), (0x19, 0x93), (0x28, 0x4e), (8, 8), (8, 0), (8, 8)])
            self.assertEqual([len(w.source_segment_ids) for w in plan.writes], [8, 8, 1, 1, 1, 1])
            self.assertEqual(plan.end_projected_vgmticks, 101)
            text = render(plan, title='test')
            self.assertEqual(re.findall(r'^A y(\d+),(\d+)', text, re.M),
                             [(str(w.register), str(w.data)) for w in plan.writes])
            self.assertEqual(re.findall(r'^A r%(\d+)$', text, re.M), ['9'])

    def test_absolute_rounding_does_not_accumulate_and_reports_collapses(self):
        commands = b''.join(wait(1) + write(0x30, i % 256) for i in range(1, 201)) + wait(500)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(commands))
            source = analyze(path, root / 'source')
            plan = project_segments(source.segments, end_vgmticks=700)
            self.assertLessEqual(plan.timing_report()['max_abs_timing_error_samples'], 6)
            self.assertGreater(plan.timing_report()['collapsed_positive_intervals'], 0)
            self.assertEqual(plan.end_mdx_tick, 62)
            self.assertEqual(plan.end_projected_vgmticks, 699)
            self.assertEqual([w.data for w in plan.writes], list(range(1, 201)))

    def test_long_time_advances_are_split_without_losing_the_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(write(8, 8) + b''.join(wait(65535) for _ in range(20))))
            source = analyze(path, root / 'source')
            plan = project_segments(source.segments, end_vgmticks=source.source_end_vgmticks)
            advances = [int(x) for x in re.findall(r'^A r%(\d+)$', render(plan), re.M)]
            self.assertGreater(len(advances), 1)
            self.assertTrue(all(1 <= n <= 65535 for n in advances))
            self.assertEqual(sum(advances), plan.end_mdx_tick)

    def test_unsupported_clock_variant_and_instances_are_explicit(self):
        for clock in (3579545, 0x80000000 | 4000000, 0x40000000 | 4000000):
            with self.subTest(clock=clock), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / 'source.vgm'
                path.write_bytes(vgm(write(8, 8) + b'\xa4\x08\x08' + wait(100), clock))
                source = analyze(path, root / 'source')
                with self.assertRaisesRegex(ValueError, 'one 4 MHz'):
                    project_segments(source.segments, end_vgmticks=source.source_end_vgmticks)

    def test_conflicting_source_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(write(0x19, 10) + wait(100)))
            source = analyze(path, root / 'source')
            altered = list(source.segments)
            pos = next(i for i, s in enumerate(altered) if s.source_event_id is not None)
            altered[pos] = replace(altered[pos], data=11)
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                project_segments(altered, end_vgmticks=100)

    def test_comparison_detects_missing_extra_pitch_timing_and_wrong_initializer(self):
        baseline = write(1, 0)
        original = write(0x28, 0x4e) + write(8, 8) + wait(100) + write(8, 0) + wait(100)
        mutations = {
            'correct': original,
            'missing_key': write(0x28, 0x4e) + wait(100) + write(8, 0) + wait(100),
            'extra_key': original + write(8, 8),
            'pitch': original.replace(write(0x28, 0x4e), write(0x28, 0x4d)),
            'timing': original.replace(wait(100), wait(110)),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(original))
            source = analyze(path, root / 'source')
            plan = project_segments(source.segments, end_vgmticks=200)
            # Independent example: @t255 tick9=101 samples; tick18=203.
            mutations['correct'] = original.replace(wait(100), wait(101), 1)
            mutations['correct'] = mutations['correct'][:-3] + wait(102)
            for name, commands in mutations.items():
                with self.subTest(case=name):
                    path.write_bytes(vgm(baseline + commands))
                    actual = analyze(path, root / name)
                    result = compare(plan, source.segments, actual, initialization=[(0, 1, 0)])
                    self.assertEqual(result['passed'], name == 'correct')
                    if name == 'missing_key':
                        self.assertEqual(result['missing_channel_attacks'], 1)
                    if name == 'extra_key':
                        self.assertEqual(result['extra_channel_attacks'], 1)
            wrong = compare(plan, source.segments, actual, initialization=[(0, 1, 2)])
            self.assertFalse(wrong['initialization_prefix_matches'])
            self.assertFalse(wrong['passed'])

    def test_known_operator_state_mismatch_is_not_hidden_by_matching_key_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'source.vgm'
            path.write_bytes(vgm(write(0x60, 15) + write(8, 8) + wait(101)))
            source = analyze(path, root / 'source')
            plan = project_segments(source.segments, end_vgmticks=101)
            corrupt = tuple(replace(s, state=replace(s.state, operators=(
                replace(s.state.operators[0], tl=16), *s.state.operators[1:])))
                if s.state.operators[0].tl is not None else s for s in source.segments)
            result = compare(plan, corrupt, source, initialization=[])
            self.assertTrue(result['control_sequence_matches'])
            self.assertEqual(result['missing_operator_keyons'], 0)
            self.assertGreater(result['known_state_mismatches'], 0)
            self.assertFalse(result['passed'])

    def test_committed_external_roundtrip_for_nine_original_patterns(self):
        fixtures = ROOT / 'tests/fixtures/public/opm'
        returned = fixtures / 'mdx_roundtrip'
        sources = sorted((fixtures / 'from_mdx').glob('*/*.vgm'))
        self.assertEqual(len(sources), 9)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initialization = controls(analyze(returned / 'initialization.vgm', root / 'init'))
            self.assertTrue(initialization)
            self.assertTrue(all(tick == 0 and register != 8 for tick, register, _ in initialization))
            for path in sources:
                with self.subTest(case=path.stem):
                    source = analyze(path, root / path.stem / 'source')
                    actual = analyze(returned / path.name, root / path.stem / 'returned')
                    plan = project_segments(source.segments, end_vgmticks=source.source_end_vgmticks)
                    result = compare(plan, source.segments, actual, initialization=initialization)
                    self.assertTrue(result['passed'], result)
                    self.assertEqual(result['max_abs_source_timing_error_samples'], 0)


if __name__ == '__main__':
    unittest.main()
