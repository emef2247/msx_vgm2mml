"""Real source integration for native musical cartridge variant publication."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import export_mgs
from batch_vgm_to_mgs import discover_inputs


def vgm(commands):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x0c, 3579545)
    struct.pack_into('<I', raw, 0x2c, 7670454)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    raw.extend(commands)
    raw.append(0x66)
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


PHRASE = bytes((
    0x52, 0x30, 0x71, 0x52, 0x40, 0x23, 0x52, 0xa4, 0x22,
    0x52, 0xa0, 0x69, 0x52, 0xb0, 0x37, 0x52, 0x28, 0xf0,
    0x61, 0x00, 0x10,
    0x52, 0x28, 0x00,
))
BURST = bytes((0x52, 0x2b, 0x80))
for _value in (0x80, 0xA0, 0xC0, 0xE0, 0xC0, 0xA0, 0x80, 0x60):
    BURST += bytes((0x52, 0x2a, _value, 0x61, 0x02, 0x00))
OPN2_SONG = vgm(PHRASE + BURST)

PROFILES = ('sfg01', 'makoto', 'sfg01_makoto', 'sfg01_msxaudio')
VARIANT_NAMES = tuple(f'vgm-variants/{profile}/song.vgm' for profile in PROFILES)


def combined_rows(out):
    return json.loads((out / '_diagnostics/results.json').read_text(encoding='utf-8'))


def variant_rows(out):
    return [row for row in combined_rows(out) if row.get('route') == 'vgm_variants']


def evidence(out, stem='song'):
    return json.loads((out / '_diagnostics' / stem / 'vgm_variants.json').read_text(encoding='utf-8'))


def variant_pass(source, out, enabled=True, force=False):
    argv = [str(source), '--outdir', str(out)]
    if enabled:
        argv.append('--vgm-variants')
    if force:
        argv.append('--force')
    return export_mgs._update_vgm_variants(export_mgs.build_parser().parse_args(argv))


def assert_profiles(test, out, expected, stem='song'):
    report = evidence(out, stem)
    summaries = report['summaries']
    test.assertEqual(set(summaries), set(PROFILES))
    test.assertEqual({p for p, result in summaries.items() if result['status'] == 'success'}, set(expected))
    published = {f'vgm-variants/{profile}/{stem}.vgm' for profile in expected}
    test.assertEqual(set(report['published']), published)
    manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
    owned = manifest['entries'][stem + '.vgm']['published']
    for profile in PROFILES:
        path = out / 'vgm-variants' / profile / (stem + '.vgm')
        test.assertEqual(path.is_file(), profile in expected)
        if profile in expected:
            test.assertIn(path.relative_to(out).as_posix(), owned)
            result = summaries[profile]
            test.assertEqual(result['input_representation'], 'NativePerformance')
            test.assertFalse(result['source_file_consulted'])
            csv_path = out / '_diagnostics' / stem / 'vgm_variants' / profile / (stem + '.writes.csv')
            test.assertTrue(csv_path.is_file())
            test.assertIn('unit_id', csv_path.read_text().splitlines()[0])
        else:
            test.assertEqual(summaries[profile]['status'], 'unavailable')
            test.assertTrue(summaries[profile]['reason'])
    test.assertTrue((out / '_diagnostics' / stem / 'vgm_variants/native' / (stem + '.native_music.json')).is_file())
    return report


class ExportMgsVgmVariantsTests(unittest.TestCase):
    def run_main(self, *argv):
        return export_mgs.main([str(item) for item in argv])

    def test_opn2_pcm_publishes_three_capable_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'song.vgm'; source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.run_main(source, '--outdir', out, '--vgm-variants', '--skip-keyon-counts')
            report = assert_profiles(self, out, ('makoto', 'sfg01_makoto', 'sfg01_msxaudio'))
            self.assertIn('PCM', report['summaries']['sfg01']['reason'])
            makoto = (out / 'vgm-variants/makoto/song.vgm').read_bytes()
            self.assertEqual(struct.unpack_from('<I', makoto, 0x30)[0], 0)
            self.assertEqual(struct.unpack_from('<I', makoto, 0x48)[0], 8000000)
            self.assertIn(b'\x67\x66\x81', makoto)
            self.assertIn(b'\x67\x66\x88', (out / 'vgm-variants/sfg01_msxaudio/song.vgm').read_bytes())
            self.assertEqual(variant_rows(out)[0]['status'], 'success')

    def test_public_psg_fixture_publishes_two_profiles_without_failing_mgs(self):
        fixture = ROOT / 'tests/fixtures/public/psg/scale_rom1/scale_rom1.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            result = self.run_main(fixture, '--outdir', out, '--vgm-variants', '--skip-keyon-counts', '--compiler', 'mgsexc')
            self.assertEqual(result, 0)
            assert_profiles(self, out, ('sfg01', 'makoto'), 'scale_rom1')
            self.assertEqual(variant_rows(out)[0]['status'], 'success')

    def test_rerun_without_flag_removes_products_and_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'song.vgm'; source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(variant_pass(source, out)[0]['status'], 'success')
            self.assertEqual(variant_pass(source, out, False), [])
            for name in VARIANT_NAMES:
                self.assertFalse((out / name).exists())
            self.assertEqual(json.loads((out / 'listening_manifest.json').read_text())['entries']['song.vgm']['published'], {})

    def test_hand_edited_product_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'song.vgm'; source.write_bytes(OPN2_SONG)
            out = root / 'out'; variant_pass(source, out)
            edited = out / 'vgm-variants/makoto/song.vgm'; edited.write_bytes(b'edited')
            row, = variant_pass(source, out)
            self.assertEqual(row['status'], 'publication_failed')
            self.assertIn('unowned or modified', row['detail'])
            self.assertEqual(edited.read_bytes(), b'edited')

    def test_discovery_does_not_reingest_either_variant_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'song.vgm').write_bytes(OPN2_SONG)
            for name in ('vgm_variants/song/makoto', 'vgm-variants/makoto'):
                nested = root / name; nested.mkdir(parents=True)
                (nested / 'song.vgm').write_bytes(OPN2_SONG)
            for adjacent in (False, True):
                self.assertEqual(discover_inputs(root, adjacent=adjacent), [root / 'song.vgm'])


if __name__ == '__main__':
    unittest.main()
