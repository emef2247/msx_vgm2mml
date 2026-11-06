"""export_mgs.py --vgm-variants: cartridge variant VGMs beside the MGS export.

Only OPN2 (YM2612) sources have a variant route in this stage; other
sources record a route_unavailable variant row without failing the
batch. Variant products are owned through the package listening
manifest like every other product.
"""
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

VARIANT_NAMES = ('vgm_variants/song/makoto/song.vgm',
                 'vgm_variants/song/sfg01/dac_makoto/song.vgm',
                 'vgm_variants/song/sfg01/dac_y8950/song.vgm',
                 'vgm_variants/song/layered/song.vgm',
                 'vgm_variants/song/opm4mhz/song.vgm')


def combined_rows(out):
    return json.loads((out / '_diagnostics' / 'results.json').read_text(encoding='utf-8'))


def variant_rows(out):
    return [row for row in combined_rows(out) if row.get('route') == 'vgm_variants']


class ExportMgsVgmVariantsTests(unittest.TestCase):
    def run_main(self, *argv):
        return export_mgs.main([str(item) for item in argv])

    def test_opn2_publishes_all_five_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.run_main(source, '--outdir', out, '--vgm-variants', '--skip-keyon-counts')
            package = out / 'vgm_variants' / 'song'
            makoto = package / 'makoto' / 'song.vgm'
            dac_makoto = package / 'sfg01' / 'dac_makoto' / 'song.vgm'
            dac_y8950 = package / 'sfg01' / 'dac_y8950' / 'song.vgm'
            layered = package / 'layered' / 'song.vgm'
            opm4mhz = package / 'opm4mhz' / 'song.vgm'
            for product in (makoto, dac_makoto, dac_y8950, layered, opm4mhz):
                self.assertTrue(product.is_file(), product)
            makoto_raw = makoto.read_bytes()
            self.assertEqual(struct.unpack_from('<I', makoto_raw, 0x30)[0], 0)
            self.assertNotEqual(struct.unpack_from('<I', makoto_raw, 0x48)[0], 0)
            self.assertGreater(dac_makoto.read_bytes().find(b'\x67\x66\x81'), 0)
            self.assertGreater(dac_y8950.read_bytes().find(b'\x67\x66\x88'), 0)
            self.assertEqual(struct.unpack_from('<I', opm4mhz.read_bytes(), 0x30)[0],
                             4000000)
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            for name in VARIANT_NAMES:
                self.assertIn(name, published)
            rows = variant_rows(out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['status'], 'success')
            self.assertEqual(rows[0]['vgm'], 'vgm_variants/song/makoto/song.vgm')
            evidence = json.loads((out / '_diagnostics' / 'song' / 'vgm_variants.json')
                                  .read_text(encoding='utf-8'))
            self.assertEqual(evidence['status'], 'success')
            self.assertEqual(sorted(evidence['published']), sorted(VARIANT_NAMES))
            self.assertEqual(sorted(evidence['summaries']),
                             ['makoto', 'opm4mhz', 'sfg01_opna', 'sfg01_y8950'])

    def test_non_opn2_records_route_unavailable_without_failing_the_batch(self):
        fixture = ROOT / 'tests/fixtures/public/psg/scale_rom1/scale_rom1.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            # mgsexc is the bundled compiler: the batch outcome then
            # depends on the conversion alone, not on an npm setup.
            result = self.run_main(fixture, '--outdir', out, '--vgm-variants',
                                   '--skip-keyon-counts', '--compiler', 'mgsexc')
            self.assertEqual(result, 0)
            self.assertFalse((out / 'vgm_variants').exists())
            rows = variant_rows(out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['input'], 'scale_rom1.vgm')
            self.assertEqual(rows[0]['status'], 'conversion_failed')
            self.assertEqual(rows[0]['error_code'], 'route_unavailable')
            evidence = json.loads((out / '_diagnostics' / 'scale_rom1' / 'vgm_variants.json')
                                  .read_text(encoding='utf-8'))
            self.assertEqual(evidence['status'], 'route_unavailable')

    def test_rerun_without_the_flag_removes_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.run_main(source, '--outdir', out, '--vgm-variants', '--skip-keyon-counts')
            self.assertTrue((out / 'vgm_variants' / 'song' / 'makoto' / 'song.vgm').is_file())
            self.run_main(source, '--outdir', out, '--skip-keyon-counts')
            for name in VARIANT_NAMES:
                self.assertFalse((out / name).exists(), name)
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            for name in VARIANT_NAMES:
                self.assertNotIn(name, published)
            self.assertEqual(variant_rows(out), [])

    def test_hand_edited_variant_product_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.run_main(source, '--outdir', out, '--vgm-variants', '--skip-keyon-counts')
            (out / 'vgm_variants' / 'song' / 'layered' / 'song.vgm').write_bytes(b'edited')
            with self.assertRaises(SystemExit) as raised:
                self.run_main(source, '--outdir', out, '--vgm-variants',
                              '--skip-keyon-counts')
            self.assertEqual(raised.exception.code, 2)

    def test_adjacent_discovery_does_not_reingest_variant_products(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'song.vgm').write_bytes(OPN2_SONG)
            nested = root / 'vgm_variants' / 'song' / 'makoto'
            nested.mkdir(parents=True)
            (nested / 'song.vgm').write_bytes(OPN2_SONG)
            self.assertEqual(discover_inputs(root, adjacent=True), [root / 'song.vgm'])


if __name__ == '__main__':
    unittest.main()
