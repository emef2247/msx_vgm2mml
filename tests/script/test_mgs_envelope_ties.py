"""Atomic target-only envelope compensation and shared-bank constraints."""
from pathlib import Path
import csv
import shutil
import subprocess
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from mgs_envelope_ties import compensate

DEF = '@e01 = { 0, 0, 8:2, A:2, C:92, B:24, 9:20, 6:20, 3:20 }\n'


def score(notes, definition=DEF, track='1', setup='@e1 v15'):
    return definition + f'{track} {setup} o4 {notes}\n'


class EnvelopeTieCompensationTests(unittest.TestCase):
    def test_uniform_long_note_preserves_body_and_pads_exact_holds(self):
        text = score('c%255 & c%255 & c%30')
        out, report = compensate({'psg': text}, tempo=225)
        self.assertEqual(out['psg'].splitlines()[-1], text.splitlines()[-1])
        self.assertIn('C:93', out['psg'])
        self.assertIn('3:21', out['psg'])
        self.assertEqual(report['definitions'][0]['padded_holds'], 2)
        self.assertEqual(report['definitions'][0]['affected_usages'][0]['tie_frames'], [85, 170])
        self.assertEqual(text, score('c%255 & c%255 & c%30'))

    def test_shared_chip_definition_normalizes_id_and_short_prefix(self):
        psg = score('c%255 & c%255 & c%30')
        scc = score('[ *1 ]2\n4 c%255', definition=DEF.replace('@e01', '@e1') + '*1 = { c%255 & c%45 }\n', track='4')
        out, report = compensate({'psg': psg, 'scc': scc}, tempo=225)
        self.assertEqual(report['affected_usages'], 4)
        self.assertIn('C:93', out['scc'])
        self.assertIn('[ *1 ]2', out['scc'])
        self.assertEqual(out['scc'].split('}')[0].split('{')[1], out['psg'].split('}')[0].split('{')[1])

    def test_transition_at_cut_extends_next_hold(self):
        text = score('c%255 & c%45', '@e1 = { 0, 0, C:85, 6:15 }\n')
        out, _ = compensate({'psg': text}, tempo=225)
        self.assertIn('C:85, 6:16', out['psg'])

    def test_raw_tempo_has_255_frame_tie_interval(self):
        text = score('c%255 & c%45', '@e1 = { 0, 0, C:255, 6:45 }\n')
        out, report = compensate({'psg': text}, tempo=75)
        self.assertIn('C:255, 6:46', out['psg'])
        self.assertEqual(report['definitions'][0]['tie_interval_frames'], 255)

    def test_constant_and_hardware_usage_are_not_compensated(self):
        for text in (score('c%200 & c%100', '@e1 = { 0, 0, F }\n'),
                     score('c%200 & c%100', setup='@e1 v16 s9')):
            out, report = compensate({'psg': text}, tempo=75)
            self.assertEqual(out['psg'], text)
            self.assertEqual(report['compensated_definitions'], 0)

    def test_inline_constant_volume_changes_do_not_require_uniform_ties(self):
        constant = '@e0 = { 0, 0, F }\n'
        text = score('c%20 v8 & c%35 )2 & c%45 (3 & c%30', constant, setup='@e0 v10')
        out, report = compensate({'psg': text}, tempo=75)
        self.assertEqual(out['psg'], text)
        self.assertEqual(report['compensated_definitions'], 0)
        fractional = score('c%20 v8 & c%35', constant, setup='@e0 v10')
        self.assertEqual(compensate({'psg': fractional}, tempo=225)[0]['psg'], fractional)

    def test_varying_curve_relative_volume_change_rejects(self):
        for change in ('(', ')', '(2', ')3'):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'binding'):
                compensate({'psg': score('c%255 ' + change + ' & c%45', setup='@e1 v10')}, tempo=225)

    def test_hardware_constant_transitions_ignore_irrelevant_tie_schedule(self):
        constant = '@e0 = { 0, 0, F }\n'
        text = score('c%20 s9 & c%35 v12 & c%45', constant, setup='@e0 v16')
        out, report = compensate({'psg': text}, tempo=75)
        self.assertEqual(out['psg'], text)
        self.assertEqual(report['compensated_definitions'], 0)
        for start, middle in (('@e1 v16 s9', 'v15 @e1'), ('@e1 v15', 'v16 s9')):
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, 'binding'):
                compensate({'psg': score('c%255 ' + middle + ' & c%45', setup=start)}, tempo=225)

    def test_conflict_and_nonuniform_usage_reject_atomically(self):
        original = {'psg': score('c%255 & c%45'),
                    'scc': score('c%120 & c%180', track='4')}
        before = original.copy()
        with self.assertRaisesRegex(ValueError, 'Nonuniform'):
            compensate(original, tempo=225)
        self.assertEqual(original, before)
        with self.assertRaisesRegex(ValueError, 'Conflicting envelope'):
            compensate({'psg': score('c%255'), 'scc': score('c%255', DEF.replace('C:92', 'C:91'))}, tempo=225)

    def test_binding_clock_and_fractional_frames_reject(self):
        for text, tempo in ((score('c%255 & @e1 c%45'), 225),
                            (score('c%255 & c%45') + '#tempo 75\n', 225),
                            (score('c%254'), 225),
                            (score('t120 c%255'), 225),
                            (score('c%255'), 120)):
            with self.subTest(text=text, tempo=tempo), self.assertRaises(ValueError):
                compensate({'psg': text}, tempo=tempo)

    def test_padded_definition_overflow_rejects(self):
        body = ', '.join(('F:255' if i % 2 else '8:255') for i in range(34))
        with self.assertRaisesRegex(ValueError, 'length budget'):
            compensate({'psg': score('c%255 & c%45', '@e1 = { 0, 0, ' + body + ' }\n')}, tempo=225)


class ActualCompensatedEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('mgsc') or not shutil.which('node'):
            raise unittest.SkipTest('MGSC and Node are required')
        check = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'), '--check'],
                               capture_output=True, timeout=30)
        if check.returncode:
            raise unittest.SkipTest('libkss-js is required')

    def test_shared_long_definition_short_prefix_at_tie_cut_and_restart(self):
        from mml_sync import annotate_sync_points
        from vgm_reader import parse_vgm
        runs = [(8, 2), (10, 2), (12, 92), (11, 24), (9, 20), (6, 120), (3, 40)]
        expected = [volume for volume, duration in runs for _ in range(duration)]
        for chip in ('psg', 'scc'):
            for tempo in (75, 225):
                with self.subTest(chip=chip, tempo=tempo), tempfile.TemporaryDirectory() as tmp:
                    folder = Path(tmp); factor = tempo // 75; prefix = 255 // factor
                    remaining = len(expected) * factor; parts = []
                    while remaining:
                        take = min(255, remaining)
                        parts.append(('& ' if parts else '') + f'c%{take}')
                        remaining -= take
                    # Three attacks share one definition: long, exactly-at-cut
                    # prefix, then a short restart. No extra envelope selection.
                    notes = (' '.join(parts) + f' r%{6*factor} c%255 r%{6*factor}'
                             + f' c%{10*factor} r%{30*factor}')
                    definition = '@e01 = { 0, 0, ' + ', '.join(
                        f'{volume:X}:{duration}' for volume, duration in runs) + ' }\n'
                    wave = ('@s00 = {' + ''.join(f'{v:02X}' for v in range(0,256,8))
                            + '}\n') if chip == 'scc' else ''
                    body = score(notes, definition, '4' if chip == 'scc' else '1',
                                 '@0 @e1 v15' if chip == 'scc' else '@0 /1 @e1 v15')
                    rewritten, report = compensate({chip: body}, tempo=tempo)
                    self.assertEqual(report['compensated_definitions'], 1)
                    self.assertEqual(report['affected_usages'], 3)
                    self.assertEqual(report['definitions'][0]['affected_usages'][1]['duration_frames'], prefix)
                    target = folder/'score.mml'; mgs = folder/'score.mgs'; vgm = folder/'score.vgm'
                    target.write_text(annotate_sync_points(f'#opll_mode 0\n#tempo {tempo}\n'
                                      + wave + rewritten[chip]), encoding='cp932')
                    result = subprocess.run(['mgsc', str(target), str(mgs)], capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'),
                                             str(mgs), str(vgm), '11000'], capture_output=True, timeout=45)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    paths = parse_vgm(str(vgm), str(folder/'trace'), include_vgmticks=True)
                    values = {}
                    with Path(paths[2 if chip == 'psg' else 3]).open() as stream:
                        for row in csv.DictReader(stream):
                            if int(row['ch']) == 0:
                                values[round(int(row['vgmticks'])/735)] = (
                                    int(row['aVCtrl' if chip == 'psg' else 'vCtrl']) & 15) if int(row['en']) else 0
                    first = min(frame for frame, volume in values.items() if volume)
                    actual = []; level = 0
                    for frame in range(first, first+300+6+prefix+6+14):
                        level = values.get(frame, level); actual.append(level)
                    self.assertEqual(actual[:300], expected)
                    prefix_start = 306; score_restart = prefix_start + prefix + 6
                    onsets = [i for i, volume in enumerate(actual) if volume and (i == 0 or not actual[i-1])]
                    self.assertEqual(len(onsets), 3)
                    restart = onsets[2]
                    # The raw 255-step untied prefix delays the subsequent
                    # attack by one frame even without compensation. Verify
                    # against identical unmodified score bodies below.
                    self.assertEqual(restart-score_restart, 1 if tempo == 75 else 0)
                    self.assertEqual(actual[prefix_start:prefix_start+prefix], expected[:prefix])
                    self.assertEqual(actual[restart:restart+10], expected[:10])
                    # Explicitly retain the known extra ending frame as a
                    # driver observation, not a claim of source ending equality.
                    self.assertEqual(actual[300], expected[-1])
                    self.assertEqual(actual[301:306], [0]*5)
                    self.assertEqual(actual[prefix_start+prefix], expected[prefix-1])
                    prefix_overhang = 2 if tempo == 75 else 1
                    self.assertEqual(actual[prefix_start+prefix:prefix_start+prefix+prefix_overhang],
                                     [expected[prefix-1]]*prefix_overhang)
                    self.assertEqual(actual[prefix_start+prefix+prefix_overhang:restart], [0]*5)
                    self.assertEqual(actual[restart+10], expected[9])
                    self.assertEqual(actual[restart+11], 0)
                    target.write_text(annotate_sync_points(f'#opll_mode 0\n#tempo {tempo}\n'
                                      + wave + body), encoding='cp932')
                    result = subprocess.run(['mgsc', str(target), str(mgs)], capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    result = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'),
                                             str(mgs), str(vgm), '11000'], capture_output=True, timeout=45)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    paths = parse_vgm(str(vgm), str(folder/'baseline'), include_vgmticks=True)
                    baseline = {}
                    with Path(paths[2 if chip == 'psg' else 3]).open() as stream:
                        for row in csv.DictReader(stream):
                            if int(row['ch']) == 0:
                                baseline[round(int(row['vgmticks'])/735)] = (
                                    int(row['aVCtrl' if chip == 'psg' else 'vCtrl']) & 15) if int(row['en']) else 0
                    baseline_first = min(frame for frame, volume in baseline.items() if volume)
                    baseline_onsets = []; baseline_levels = []; level = 0
                    for frame in range(baseline_first, baseline_first+len(actual)):
                        volume = baseline.get(frame, level)
                        if volume and not level:
                            baseline_onsets.append(frame-baseline_first)
                        baseline_levels.append(volume)
                        level = volume
                    self.assertEqual(onsets, baseline_onsets)
                    self.assertEqual([bool(v) for v in actual], [bool(v) for v in baseline_levels])

    def test_module_preserves_every_audible_frame_on_psg_and_scc(self):
        from mml_sync import annotate_sync_points
        from vgm_reader import parse_vgm
        runs = [(8, 2), (10, 2), (12, 92), (11, 24), (9, 20), (6, 120), (3, 40)]
        expected = [volume for volume, duration in runs for _ in range(duration)]
        for chip in ('psg', 'scc'):
            for tempo in (75, 225):
                with self.subTest(chip=chip, tempo=tempo), tempfile.TemporaryDirectory() as tmp:
                    folder = Path(tmp)
                    factor = tempo // 75; remaining = len(expected) * factor; parts = []
                    while remaining:
                        take = min(255, remaining)
                        parts.append(('& ' if parts else '') + f'c%{take}')
                        remaining -= take
                    definition = '@e01 = { 0, 0, ' + ', '.join(
                        f'{volume:X}:{duration}' for volume, duration in runs) + ' }\n'
                    wave = ('@s00 = {' + ''.join(f'{v:02X}' for v in range(0,256,8))
                            + '}\n') if chip == 'scc' else ''
                    body = score(' '.join(parts) + f' r%{30*factor}', definition,
                                 '4' if chip == 'scc' else '1',
                                 '@0 @e1 v15' if chip == 'scc' else '@0 /1 @e1 v15')
                    rewritten, report = compensate({chip: body}, tempo=tempo)
                    self.assertEqual(report['compensated_definitions'], 1)
                    target = folder/'score.mml'; mgs = folder/'score.mgs'; vgm = folder/'score.vgm'
                    target.write_text(annotate_sync_points(f'#opll_mode 0\n#tempo {tempo}\n'
                                      + wave + rewritten[chip]), encoding='cp932')
                    result = subprocess.run(['mgsc', str(target), str(mgs)], capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'),
                                             str(mgs), str(vgm), '6500'], capture_output=True, timeout=45)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    paths = parse_vgm(str(vgm), str(folder/'trace'), include_vgmticks=True)
                    values = {}
                    with Path(paths[2 if chip == 'psg' else 3]).open() as stream:
                        for row in csv.DictReader(stream):
                            if int(row['ch']) == 0:
                                values[round(int(row['vgmticks'])/735)] = (
                                    int(row['aVCtrl' if chip == 'psg' else 'vCtrl']) & 15) if int(row['en']) else 0
                    first = min(frame for frame, volume in values.items() if volume)
                    actual = []; level = 0
                    for frame in range(first, first+len(expected)):
                        level = values.get(frame, level); actual.append(level)
                    self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
