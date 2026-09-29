"""Exact shared boundaries and unchanged expanded music after annotation."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from mml_sync import analyze_mml, annotate_sync_points, sync_points, _leaves, _parse, _time


def timeline(text):
    tracks, _, _ = analyze_mml(text)
    return {ch: [(node.text, node.start, node.end) for node in _leaves(nodes)]
            for ch, nodes in tracks.items()}


def assert_valid_marks(test, text, min_gap=0):
    tracks, boundaries, _ = analyze_mml(text)
    marks = sync_points(tracks, boundaries, min_gap=min_gap)
    # Count time in each rendered prefix independently of the comment number.
    states = {ch: dict(step=0, default=48, tokens=0, rhythm=(ch == 'f' and '#opll_mode 1' in text)) for ch in tracks}
    seen = {ch: set() for ch in tracks}
    pending = {ch: [] for ch in tracks}
    macros = {m[1]: _parse(m[2]) for m in re.finditer(r'^\*(\d+)\s*=\s*\{([^}]*)\}', text, re.M)}
    for line in text.splitlines():
        music = re.match(r'^([1-9a-h])\s+(.*)$', line)
        if music and music[1] in states:
            pending[music[1]].append(music[2])
        mark = re.match(r'; ch([1-9a-h]) --- step (\d+) : (.*?) ---', line)
        if mark:
            channel, step, label = mark[1], int(mark[2]), mark[3]
            test.assertIn(step, marks)
            test.assertEqual(label, marks[step])
            test.assertNotIn(step, seen[channel])
            seen[channel].add(step)
            _time(_parse(' '.join(pending[channel]), rhythm=states[channel]['rhythm']), states[channel], macros)
            pending[channel].clear()
            actual = states[channel]['step']
            test.assertEqual(step, actual)
    for channel, nodes in tracks.items():
        _time(_parse(' '.join(pending[channel]), rhythm=states[channel]['rhythm']), states[channel], macros)
        test.assertEqual(states[channel]['step'], nodes[-1].end)
        test.assertEqual(seen[channel], {step for step in marks if step <= nodes[-1].end})


class SyncTests(unittest.TestCase):
    def test_min_gap_selects_shared_points_and_keeps_short_tail(self):
        source = '1 [c%12]120\n4 [r%12]120\n'
        tracks, bounds, _ = analyze_mml(source)
        self.assertEqual(list(sync_points(tracks, bounds, min_gap=700)),
                         [0, 1440])
        result = annotate_sync_points(source, min_gap=700)
        self.assertEqual(timeline(source), timeline(result))
        assert_valid_marks(self, result, min_gap=700)
        self.assertNotIn('step 700 ', result)
        self.assertEqual(len(sync_points(tracks, bounds, min_gap=0)), 2)
        self.assertEqual(list(sync_points(tracks, bounds, min_gap=2000)), [0, 1440])
        flat = '1 ' + 'c%12 ' * 120 + '\n4 ' + 'r%12 ' * 120 + '\n'
        flat_tracks, flat_bounds, _ = analyze_mml(flat)
        self.assertEqual(list(sync_points(flat_tracks, flat_bounds, min_gap=700)),
                         [0, 708, 1416, 1440])
        with self.assertRaises(ValueError):
            annotate_sync_points(source, min_gap=-1)

    def assert_preserved(self, source):
        result = annotate_sync_points(source)
        self.assertEqual(timeline(source), timeline(result))
        assert_valid_marks(self, result)
        self.assertNotIn('tick count:', result)
        return result

    def test_shared_boundaries_not_independent_note_counts(self):
        source = '#tempo 75\n1 c%3 d%3 e%6\n4 r%6 g%6\n9 c%4 c%4 c%4\n'
        tracks, bounds, _ = analyze_mml(source)
        self.assertEqual(sync_points(tracks, bounds), {0: 'start', 12: 'end'})
        result = self.assert_preserved(source)
        self.assertNotIn('step 3 ', result)
        self.assertNotIn('step 6 ', result)

    def test_inline_nested_repeats_and_delta_commands(self):
        source = '#tempo 75\n1 o4v10 [>[(c%3]2 <d%6]2\n4 [g%6]4\n'
        result = self.assert_preserved(source)
        self.assertNotIn('step 6 :', result)
        self.assertNotIn('step 18 :', result)
        self.assertIn('[g%6]4', result)

    def test_mixed_parts_skip_internal_loop_boundaries(self):
        source = '#opll_mode 1\n1 [c%3 d%3]4 e%6\n4 [g%6]4 a%6\n9 [c%12]2 d%6\nf [b%6]4 s%6\n'
        result = self.assert_preserved(source)
        self.assertIn('step 24 : token-boundary 4/4ch', result)
        self.assertNotIn('step 12 :', result)
        for loop in ('[c%3 d%3]4', '[g%6]4', '[c%12]2', '[b%6]4'):
            self.assertIn(loop, result)

    def test_repeat_is_kept_when_no_sync_point_inside(self):
        result = self.assert_preserved('1 [c%3]4\n4 g%12\n')
        self.assertIn('[c%3]4', result)

    def test_default_lengths_dots_and_loop_state(self):
        source = '1 l8 c. d16 [l%6 e l4 f]2\n4 r%24 r%54 r%54\n'
        result = self.assert_preserved(source)
        self.assertIn('step 156 : end', result)

    def test_ended_and_empty_tracks_do_not_block_other_tracks(self):
        source = '1 c%6\n4 g%6 a%6 b%6\n9 l64\n'
        result = self.assert_preserved(source)
        self.assertIn('; ch4 --- step 12 : token-boundary 1/1ch ---', result)
        self.assertNotIn('; ch9 ---', result)
        self.assertNotIn('; ch1 --- step 18', result)
        self.assertIn('9 l64', result)

    def test_tied_note_is_not_split_at_internal_boundary(self):
        result = self.assert_preserved('1 c%6 & c%6\n4 r%6 r%6\n')
        self.assertNotIn('step 6 ', result)

    def test_headers_macros_and_track_h_are_preserved(self):
        source = ('#opll_mode 1\n#alloc { 0=180, 1=100, h=100 }\n'
                  '@s00 = { 00 00 }\n*1 = { c%3 d%3 }\n'
                  '1 *1\nh e%3 f%3\n')
        result = self.assert_preserved(source)
        self.assertIn('@s00 = { 00 00 }', result)
        self.assertNotIn('step 3 :', result)
        self.assertIn('1 *1', result)

    def test_unknown_or_infinite_syntax_is_not_silently_miscounted(self):
        for body in ('[c%3]0', '*99', 'c%3 ! d%3'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                annotate_sync_points('1 ' + body)

    def test_supplied_giselle_sample_points(self):
        sample = ROOT / ('tests/fixtures/public/psg_scc_opll/www.mutopiaproject.org/'
                         'Classical/giselle/with_sync_mark/cpebach_fine_grained.mml')
        source = sample.read_text(encoding='utf-8')
        tracks, bounds, _ = analyze_mml(source)
        self.assertEqual(list(sync_points(tracks, bounds)), [0, 4490, 4538, 4778])
        result = self.assert_preserved(source)
        self.assertIn('; ch9 --- step 4490 : token-boundary 7/7ch ---', result)

    def test_mixed_vgm_cli_in_both_length_modes(self):
        sys.path.insert(0, str(ROOT))
        import vgm2mml
        source = ROOT / ('tests/fixtures/public/psg_scc_opll/www.mutopiaproject.org/'
                         'Classical/giselle/giselle.vgm')
        for raw, gap in ((False, 1000), (True, 1000), (False, 0), (False, 700)):
            with self.subTest(raw=raw, gap=gap), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                           '--outdir', folder, '--debug', '--dump-passes']
                if raw:
                    command.append('--raw-ticks')
                if gap != 1000:
                    command.extend(['--sync-min-gap', str(gap)])
                run = subprocess.run(command, capture_output=True, text=True,
                                     encoding='utf-8', timeout=120)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                with patch.object(vgm2mml, 'annotate_sync_points', lambda text, **kwargs: text):
                    original = vgm2mml._build_merged_mml(source.stem, folder,
                                                       True, True, True, raw_ticks=raw)
                result = (Path(folder) / f'{source.stem}.mml').read_text(encoding='utf-8')
                self.assertEqual(timeline(annotate_sync_points(original, min_gap=gap, drop_silent=True)), timeline(result))
                self.assertTrue(analyze_mml(result)[0])
                assert_valid_marks(self, result, min_gap=gap)


if __name__ == '__main__':
    unittest.main()
