"""Native musical variant publication, independent of the MGS projection."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'py')]
import export_mgs
import batch_vgm_to_mgs as batch


class MusicalVariantPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source' / 'song.vgm'
        self.source.parent.mkdir()
        self.source.write_bytes(b'Vgm ')
        self.output = self.root / 'output'
        self.args = export_mgs.build_parser().parse_args(
            [str(self.source), '--outdir', str(self.output), '--vgm-variants'])
        self.performance = object()  # Renderer receives no path or raw source.
        self.build = patch('native_source_music.build_native_performance', return_value=self.performance).start()
        self.render = patch('musical_variants.export_variants', side_effect=self.results).start()
        self.addCleanup(patch.stopall)

    def results(self, performance, stage, stem, **options):
        self.assertIs(performance, self.performance)
        result = {}
        for profile in export_mgs.VARIANT_PROFILES:
            path = stage / profile / (stem + '.vgm')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('new-' + profile).encode())
            result[profile] = dict(status='success', path=str(path))
        return result

    def update(self):
        return export_mgs._update_song_variants(self.source, Path('song.vgm'),
                                               self.output, self.output, self.args)

    def own(self, name, data=b'previous'):
        path = self.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        state = batch.package_manifest(self.output)
        state['entries'].setdefault('song.vgm', dict(input='song.vgm', published={}))['published'][name] = batch.file_digest(path)
        batch.save_json(self.output / 'listening_manifest.json', state)
        return path

    def test_all_paths_and_single_native_construction(self):
        row, = self.update()
        self.assertEqual(row['status'], 'success')
        self.build.assert_called_once_with(self.source, self.output / '_diagnostics/song/vgm_variants/native', 'song')
        self.render.assert_called_once_with(self.performance, self.output / '_diagnostics/song/vgm_variants',
                                            'song', force=False, dcsg_gain=.5, opna_law=False)
        products = batch.package_manifest(self.output)['entries']['song.vgm']['published']
        self.assertEqual(set(products), {f'vgm-variants/{p}/song.vgm' for p in export_mgs.VARIANT_PROFILES})
        for name in products:
            self.assertTrue((self.output / name).is_file())
        batch.publication_targets([self.source], self.source.parent, self.output, 'all')

    def test_mgs_failure_does_not_block_variant_publication(self):
        with patch('export_mgs.run_batch', return_value=[dict(input='song.vgm', status='conversion_failed', keyon_status='disabled')]):
            self.assertEqual(export_mgs.main([str(self.source), '--outdir', str(self.output), '--vgm-variants']), 1)
        self.assertTrue((self.output / 'vgm-variants/sfg01/song.vgm').is_file())
        diagnostic = json.loads((self.output / '_diagnostics/results.json').read_text())
        self.assertEqual([r['status'] for r in diagnostic], ['conversion_failed', 'success'])
        self.assertEqual(json.loads((self.output / 'results.json').read_text())[0]['route'], 'vgm_variants')

    def test_legacy_migration_and_failed_profile_cleanup(self):
        legacy = self.own('vgm_variants/song/makoto/song.vgm')
        failed = self.own('vgm-variants/makoto/song.vgm')
        def partial(*args, **kwargs):
            result = self.results(*args, **kwargs)
            result['makoto'] = dict(status='failed', reason='projection failed')
            return result
        self.render.side_effect = partial
        row, = self.update()
        self.assertEqual(row['status'], 'conversion_failed')
        self.assertFalse(legacy.exists())
        self.assertFalse(failed.exists())
        products = batch.package_manifest(self.output)['entries']['song.vgm']['published']
        self.assertNotIn('vgm-variants/makoto/song.vgm', products)
        self.assertTrue((self.output / 'vgm-variants/sfg01/song.vgm').exists())

    def test_build_failure_removes_stale_owned_products(self):
        stale = self.own('vgm-variants/sfg01/song.vgm')
        self.build.side_effect = ValueError('source unavailable')
        row, = self.update()
        self.assertEqual(row['status'], 'conversion_failed')
        self.assertFalse(stale.exists())
        self.render.assert_not_called()

    def test_disabled_cleans_both_generations_without_building(self):
        old = self.own('vgm_variants/song/layered/song.vgm')
        new = self.own('vgm-variants/sfg01/song.vgm')
        self.args.vgm_variants = False
        self.assertEqual(self.update(), [])
        self.assertFalse(old.exists()); self.assertFalse(new.exists())
        self.build.assert_not_called()

    def test_user_edited_product_is_protected(self):
        path = self.own('vgm-variants/sfg01/song.vgm')
        path.write_bytes(b'user edit')
        self.args.vgm_variants = False
        with self.assertRaisesRegex(ValueError, 'unowned or modified'):
            self.update()
        self.assertEqual(path.read_bytes(), b'user edit')
        self.build.assert_not_called()

    def test_atomic_failure_restores_products_and_manifest(self):
        old = self.own('vgm_variants/song/makoto/song.vgm')
        previous = (self.output / 'listening_manifest.json').read_bytes()
        real_replace = batch.replace_product
        failed = False
        def replace(source, target, **kwargs):
            nonlocal failed
            if not failed and target == self.output / 'vgm-variants/makoto/song.vgm':
                failed = True
                raise OSError('injected publication failure')
            return real_replace(source, target, **kwargs)
        with patch('batch_vgm_to_mgs.replace_product', side_effect=replace):
            row, = self.update()
        self.assertEqual(row['status'], 'publication_failed')
        self.assertEqual(old.read_bytes(), b'previous')
        self.assertEqual((self.output / 'listening_manifest.json').read_bytes(), previous)
        self.assertFalse((self.output / 'vgm-variants/sfg01/song.vgm').exists())

    def test_discovery_excludes_both_variant_generations(self):
        for tree in ('vgm_variants/song/makoto', 'vgm-variants/sfg01'):
            path = self.source.parent / tree / 'song.vgm'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'Vgm ')
        for adjacent in (False, True):
            self.assertEqual(batch.discover_inputs(self.source.parent, adjacent=adjacent), [self.source])


if __name__ == '__main__':
    unittest.main()
