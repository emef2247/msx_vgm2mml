"""Authored driver probe: tied continuations advance software envelopes."""
import csv
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from mml_sync import annotate_sync_points
from vgm_reader import parse_vgm


class TiedEnvelopePlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('mgsc') or not shutil.which('node'):
            raise unittest.SkipTest('MGSC and Node are required')
        check = subprocess.run(['node', str(ROOT / 'scripts/mgs_to_vgm.mjs'), '--check'],
                               capture_output=True, timeout=30)
        if check.returncode:
            raise unittest.SkipTest('libkss-js is required')

    def test_tied_continuation_extra_updates_and_hold_compensation(self):
        # Includes attack, long sustain and transitions exactly at tie boundaries.
        runs = [(8, 2), (10, 2), (12, 56), (11, 25), (9, 11), (6, 24), (3, 60)]
        expected = [volume for volume, frames in runs for _ in range(frames)]
        for chip in ('psg', 'scc'):
            for tempo in (75, 225):
                for lengths in ([85, 85, 10], [60, 60, 60]):
                    for compensate in (False, True):
                        with self.subTest(chip=chip, tempo=tempo, lengths=lengths,
                                          compensate=compensate), tempfile.TemporaryDirectory() as tmp:
                            folder = Path(tmp)
                            cuts = []; cursor = 0
                            for length in lengths[:-1]:
                                cursor += length; cuts.append(cursor)
                            adjusted = []; cursor = 0
                            for volume, duration in runs:
                                extra = sum(cursor <= cut < cursor + duration for cut in cuts)
                                adjusted.append((volume, duration + (extra if compensate else 0)))
                                cursor += duration
                            envelope = '@e01 = { 0, 0, ' + ', '.join(
                                f'{volume:X}:{duration}' for volume, duration in adjusted) + ' }\n'
                            wave = ('@s00 = {' + ''.join(f'{v:02X}' for v in range(0, 256, 8))
                                    + '}\n') if chip == 'scc' else ''
                            factor = tempo // 75
                            notes = ' '.join(('& ' if i else '') + f'c%{length * factor}'
                                             for i, length in enumerate(lengths))
                            track, mode = ('4', '@0') if chip == 'scc' else ('1', '@0 /1')
                            text = (f'#opll_mode 0\n#tempo {tempo}\n' + wave + envelope
                                    + f'{track} {mode} o4 @e1 v15 {notes} r%{30 * factor}\n')
                            mml, mgs, vgm = (folder / ('score.' + ext) for ext in ('mml', 'mgs', 'vgm'))
                            mml.write_text(annotate_sync_points(text), encoding='cp932')
                            compile_result = subprocess.run(['mgsc', str(mml), str(mgs)],
                                                            capture_output=True, timeout=30)
                            self.assertEqual(compile_result.returncode, 0,
                                             compile_result.stdout + compile_result.stderr)
                            replay = subprocess.run(['node', str(ROOT / 'scripts/mgs_to_vgm.mjs'),
                                                     str(mgs), str(vgm), '4000'],
                                                    capture_output=True, timeout=45)
                            self.assertEqual(replay.returncode, 0, replay.stderr)
                            paths = parse_vgm(str(vgm), str(folder / 'trace'), include_vgmticks=True)
                            values = {}
                            with Path(paths[2 if chip == 'psg' else 3]).open() as stream:
                                for row in csv.DictReader(stream):
                                    if int(row['ch']) == 0:
                                        level = int(row['aVCtrl' if chip == 'psg' else 'vCtrl']) & 15
                                        values[round(int(row['vgmticks']) / 735)] = level if int(row['en']) else 0
                            first = min(frame for frame, volume in values.items() if volume)
                            actual = []; level = 0
                            for frame in range(first, first + 182):
                                level = values.get(frame, level); actual.append(level)
                            if compensate:
                                self.assertEqual(actual[:180], expected)
                            else:
                                self.assertNotEqual(actual[:180], expected)
                                transition = 95 if lengths[0] == 85 else 84
                                self.assertNotEqual(actual[transition], expected[transition])
                            # This probe's release is one frame late independently of ties.
                            self.assertEqual(actual[180], 3)
                            self.assertEqual(actual[181], 0)


if __name__ == '__main__':
    unittest.main()
