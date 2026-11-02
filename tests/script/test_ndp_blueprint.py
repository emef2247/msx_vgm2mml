"""NDP blueprint pages: PSG lanes, melody fold-in, noise as rhythm voices."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from musical_plan import MusicalPlan, MusicalUnit, MusicalControl
from musical_blueprint import write_blueprint
import batch_vgm_to_mgs as batch


def tone(chip, channel, start, length, uid, period=426):
    unit = MusicalUnit(uid, chip, channel, start, start + length, False)
    controls = [MusicalControl(start, chip, channel, 'pitch',
                               (172, 3, 0) if chip == 'opll' else (period,), unit_id=uid),
                MusicalControl(start, chip, channel, 'volume', (15,), unit_id=uid)]
    return unit, controls


def noise(start, length, uid, period=8):
    unit = MusicalUnit(uid, 'psg', 0, start, start + length, False,
                       parameters=(('mode', 2),))
    controls = [MusicalControl(start, 'psg', 0, 'pitch', (period,), unit_id=uid),
                MusicalControl(start, 'psg', 0, 'volume', (12,), unit_id=uid)]
    return unit, controls


def plan(*notes):
    units, controls = zip(*notes)
    end = max(u.end_sample for u in units)
    return MusicalPlan(tuple(units), tuple(c for rows in controls for c in rows), end, end,
                       (('psg', 1789773), ('scc', 1789773), ('opll', 3579545)), metadata=())


def music_lines(text):
    return [line for line in text.splitlines() if line and not line.startswith(';')]


class NdpBlueprintTests(unittest.TestCase):
    def convert(self, p, stem='song'):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        report = write_blueprint(p, root, stem)
        page = root / 'blueprint' / 'ndp' / f'{stem}.mml'
        return report, page

    def test_psg_lanes_tracks_and_noise_rhythm(self):
        p = plan(tone('psg', 0, 0, 44100, 'a'), tone('psg', 1, 0, 44100, 'b'),
                 noise(0, 7350, 'n'))
        report, page = self.convert(p)
        self.assertEqual(report['status'], 'success')
        self.assertTrue(page.is_file())
        self.assertEqual(len(report['ndp_files']), 1)
        self.assertEqual(report['ndp']['status'], 'success')
        text = page.read_text(encoding='utf-8')
        lines = music_lines(text)
        self.assertIn('#TEMPO 75', lines)
        self.assertIn('#TIMEBASE 48', lines)
        tracks = {line.split(' ', 1)[0]: line for line in lines if re.match(r'^[123R] ', line)}
        self.assertEqual(set(tracks), {'1', '2', 'R'})
        self.assertIn('o4 c', tracks['1'])
        rhythm_defs = [line for line in lines if line.startswith('@R:')]
        self.assertEqual(len(rhythm_defs), 1)
        self.assertTrue(rhythm_defs[0].startswith('@R:a=*2 N8 V12'))
        self.assertEqual(report['ndp']['rhythm_hits'], 1)

    def test_opll_melody_folds_into_free_track(self):
        p = plan(tone('psg', 0, 0, 44100, 'a'),
                 tone('opll', 0, 0, 44100, 'lead'), tone('opll', 1, 0, 44100, 'sub'))
        report, page = self.convert(p)
        text = page.read_text(encoding='utf-8')
        tracks = {line.split(' ', 1)[0] for line in music_lines(text) if re.match(r'^[123R] ', line)}
        self.assertEqual(tracks, {'1', '2', '3'})
        self.assertTrue(report['ndp']['tracks']['2']['folded'])
        self.assertTrue(report['ndp']['tracks']['3']['folded'])
        self.assertEqual(len(report['ndp']['omitted_lanes']), 0)

    def test_edited_ndp_page_blocks_republication(self):
        p = plan(tone('psg', 0, 0, 44100, 'a'))
        report, page = self.convert(p)
        self.assertEqual(report['status'], 'success')
        page.write_text(page.read_text(encoding='utf-8') + '; hand edit\n', encoding='utf-8')
        root = page.parents[2]
        report2 = write_blueprint(p, root, 'song')
        self.assertEqual(report2['status'], 'blocked')
        self.assertIn('hand edit', page.read_text(encoding='utf-8'))

    def test_no_renderable_lanes_writes_no_ndp_page(self):
        p = plan(tone('opll', 0, 0, 44100, 'a'), tone('opll', 1, 0, 44100, 'b'),
                 tone('opll', 2, 0, 44100, 'c'), tone('opll', 3, 0, 44100, 'd'))
        report, page = self.convert(p)
        # Four OPLL lanes: three fold in, so a page still exists.
        self.assertTrue(page.is_file())
        self.assertEqual(len(report['ndp']['omitted_lanes']), 1)

    def test_batch_publishes_ndp_page_beside_score_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); diag = root / 'diag'; package = root / 'package'
            package.mkdir()
            p = plan(tone('psg', 0, 0, 44100, 'a'))
            report = dict(blueprint=write_blueprint(p, diag, 'score'))
            pubs, deletes, products, status, _, _ = batch.prepare_blueprints(
                report, diag, 'score', package, {})
            self.assertEqual(status, 'success')
            self.assertIn('blueprint/ndp/score.mml', products)
            manifest = package / 'listening_manifest.json'
            state = dict(schema_version=1, entries={'score.vgm': dict(published=products)})
            batch.publish_bundle(pubs, manifest, state, diag, deletions=deletes)
            published = package / 'blueprint' / 'ndp' / 'score.mml'
            self.assertTrue(published.is_file())
            self.assertEqual(published.read_bytes(),
                             (diag / 'blueprint' / 'ndp' / 'score.mml').read_bytes())
            published.write_text(published.read_text(encoding='utf-8') + '; edit\n',
                                 encoding='utf-8')
            pubs, deletes, _, status, _, _ = batch.prepare_blueprints(
                report, diag, 'score', package, products)
            self.assertEqual(status, 'blocked')
            self.assertEqual((pubs, deletes), ([], []))


if __name__ == '__main__':
    unittest.main()
