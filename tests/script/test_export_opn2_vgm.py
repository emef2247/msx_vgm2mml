"""export_opn2_vgm.py: export_mgs layout with the OPN2 target VGM route."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import export_opn2_vgm


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
PLAIN_SONG = vgm(bytes((0x4f, 0x03, 0x61, 0x10, 0x00)))  # PSG only, no OPN2


class ExportOpn2VgmTests(unittest.TestCase):
    def run_main(self, *argv):
        return export_opn2_vgm.main([str(item) for item in argv])

    def test_opn2_publishes_target_vgm_in_export_mgs_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out), 0)
            self.assertTrue((out / 'tracks' / 'song.target.vgm').is_file())
            # No conversion evidence beside the product.
            self.assertEqual([p.name for p in (out / 'tracks').iterdir()],
                             ['song.target.vgm'])
            folder = out / '_diagnostics' / 'song'
            self.assertTrue((folder / 'song.opn2_opm.json').is_file())
            self.assertTrue((folder / 'song.opn2_dac.csv').is_file())
            self.assertTrue((folder / 'report.json').is_file())
            self.assertTrue((folder / 'report.txt').is_file())
            self.assertTrue((out / '_source_inputs' / 'song.vgm').is_file())
            results = (out / 'results.csv').read_text(encoding='utf-8')
            self.assertIn('song.vgm', results)
            self.assertIn('success', results)
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            self.assertIn('tracks/song.target.vgm', published)
            combined = json.loads((out / '_diagnostics' / 'results.json').read_text(encoding='utf-8'))
            self.assertEqual([row['status'] for row in combined], ['success'])

    def test_layered_and_dac_correction_through_the_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out,
                                           '--layered', '--dac', 'y8950'), 0)
            self.assertTrue((out / 'tracks' / 'song.layer.target.vgm').is_file())
            summary = json.loads((out / '_diagnostics' / 'song' / 'song.opn2_opm.json')
                                 .read_text(encoding='utf-8'))
            self.assertEqual(summary['dac_target'], 'opna')
            self.assertEqual(summary['dac_corrected_from'], 'y8950')
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            self.assertIn('tracks/song.layer.target.vgm', published)

    def test_plain_rerun_removes_stale_layer_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out, '--layered'), 0)
            self.assertTrue((out / 'tracks' / 'song.layer.target.vgm').is_file())
            self.assertEqual(self.run_main(source, '--outdir', out), 0)
            self.assertFalse((out / 'tracks' / 'song.layer.target.vgm').exists())
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            self.assertNotIn('tracks/song.layer.target.vgm', published)

    def test_hand_edited_target_product_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out), 0)
            (out / 'tracks' / 'song.target.vgm').write_bytes(b'edited')
            with self.assertRaises(SystemExit) as raised:
                self.run_main(source, '--outdir', out)
            self.assertEqual(raised.exception.code, 2)

    def test_opn2_with_msx_music_scc_target_is_a_failure_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out,
                                           '--target', 'msx-music-scc'), 1)
            self.assertFalse((out / 'tracks' / 'song.target.vgm').exists())
            combined = json.loads((out / '_diagnostics' / 'results.json').read_text(encoding='utf-8'))
            self.assertEqual(combined[0]['error_code'], 'route_unavailable')

    @patch('export_opn2_vgm.run_batch',
           return_value=[dict(status='success', vgm_status='success', keyon_status='disabled')])
    def test_non_opn2_delegates_to_run_batch_once(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'plain.vgm'
            source.write_bytes(PLAIN_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out), 0)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args, (source, out))
            self.assertEqual(run.call_args.kwargs['macro_mode'], 'v110')
            self.assertEqual(run.call_args.kwargs['loop_mode'], 'v110')

    @patch('export_opn2_vgm.run_batch',
           return_value=[dict(status='success', vgm_status='success', keyon_status='disabled')])
    def test_cartridge_target_for_non_opn2_is_a_failure_row(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'plain.vgm'
            source.write_bytes(PLAIN_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out, '--target', 'makoto'), 1)
            self.assertEqual(run.call_count, 0)
            combined = json.loads((out / '_diagnostics' / 'results.json').read_text(encoding='utf-8'))
            self.assertEqual(combined[0]['error_code'], 'route_unavailable')


if __name__ == '__main__':
    unittest.main()
