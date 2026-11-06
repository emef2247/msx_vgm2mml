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


def vgm_commands(raw):
    """(command, register, data) triples of the 3-byte writes in a target VGM."""
    stream = raw[0x100:]
    index, commands = 0, []
    while index < len(stream):
        cmd = stream[index]
        if cmd == 0x66:
            break
        if cmd in (0x54, 0x56, 0x57, 0x5c, 0xa0):
            commands.append((cmd, stream[index + 1], stream[index + 2]))
            index += 3
        elif cmd == 0x61:
            index += 3
        elif cmd in (0x62, 0x63) or 0x70 <= cmd <= 0x7f:
            index += 1
        elif cmd == 0x67:
            size = struct.unpack_from('<I', stream, index + 3)[0]
            index += 7 + size
        else:
            raise AssertionError(f'unexpected VGM command 0x{cmd:02x} at {index}')
    return commands
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

    def test_sd_layout_publishes_all_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out, '--sd-layout'), 0)
            package = out
            makoto = package / 'song' / 'makoto' / 'song.vgm'
            dac_makoto = package / 'song' / 'sfg01' / 'dac_makoto' / 'song.vgm'
            dac_y8950 = package / 'song' / 'sfg01' / 'dac_y8950' / 'song.vgm'
            layered = package / 'song' / 'layered' / 'song.vgm'
            opm4mhz = package / 'song' / 'opm4mhz' / 'song.vgm'
            for product in (makoto, dac_makoto, dac_y8950, layered, opm4mhz):
                self.assertTrue(product.is_file(), product)
            # The SD makoto variant is the tracks product's own bytes.
            self.assertEqual(makoto.read_bytes(),
                             (package / 'tracks' / 'song.target.vgm').read_bytes())
            makoto_raw = makoto.read_bytes()
            self.assertEqual(struct.unpack_from('<I', makoto_raw, 0x30)[0], 0)
            self.assertNotEqual(struct.unpack_from('<I', makoto_raw, 0x48)[0], 0)
            self.assertGreater(dac_makoto.read_bytes().find(b'\x67\x66\x81'), 0)
            y8950_raw = dac_y8950.read_bytes()
            self.assertGreater(y8950_raw.find(b'\x67\x66\x88'), 0)
            self.assertEqual(struct.unpack_from('<I', y8950_raw, 0x58)[0], 3579545)
            layered_raw = layered.read_bytes()
            self.assertNotEqual(struct.unpack_from('<I', layered_raw, 0x30)[0], 0)
            self.assertNotEqual(struct.unpack_from('<I', layered_raw, 0x48)[0], 0)
            opm4mhz_raw = opm4mhz.read_bytes()
            self.assertEqual(struct.unpack_from('<I', opm4mhz_raw, 0x30)[0], 4000000)
            self.assertNotEqual(struct.unpack_from('<I', opm4mhz_raw, 0x48)[0], 0)
            self.assertGreater(opm4mhz_raw.find(b'\x67\x66\x81'), 0)
            # opm4mhz differs from the sfg01/dac_makoto variant only in
            # the OPM pitch projection: the same command stream except
            # YM2151 KC/KF data, the same header except the YM2151 clock.
            sfg01_raw = dac_makoto.read_bytes()
            self.assertEqual(len(opm4mhz_raw), len(sfg01_raw))
            # Both clocks fit in 24 bits, so the top clock byte (0x33) is 0 in both.
            self.assertEqual([i for i in range(0x100)
                              if opm4mhz_raw[i] != sfg01_raw[i]],
                             [0x30, 0x31, 0x32])
            a, b = vgm_commands(opm4mhz_raw), vgm_commands(sfg01_raw)
            self.assertEqual(len(a), len(b))
            self.assertTrue(any(left != right for left, right in zip(a, b)))
            for left, right in zip(a, b):
                if left == right:
                    continue
                self.assertEqual(left[0], 0x54)
                self.assertEqual(left[1], right[1])
                self.assertIn(left[1],
                              tuple(range(0x28, 0x2e)) + tuple(range(0x30, 0x36)))
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            for name in ('song/makoto/song.vgm', 'song/sfg01/dac_makoto/song.vgm',
                         'song/sfg01/dac_y8950/song.vgm', 'song/layered/song.vgm',
                         'song/opm4mhz/song.vgm'):
                self.assertIn(name, published)

    def test_sd_layout_variants_removed_when_option_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(OPN2_SONG)
            out = root / 'out'
            self.assertEqual(self.run_main(source, '--outdir', out, '--sd-layout'), 0)
            self.assertTrue((out / 'song' / 'makoto' / 'song.vgm').is_file())
            self.assertTrue((out / 'song' / 'opm4mhz' / 'song.vgm').is_file())
            self.assertEqual(self.run_main(source, '--outdir', out), 0)
            self.assertFalse((out / 'song' / 'makoto' / 'song.vgm').exists())
            self.assertFalse((out / 'song' / 'layered' / 'song.vgm').exists())
            self.assertFalse((out / 'song' / 'opm4mhz' / 'song.vgm').exists())
            manifest = json.loads((out / 'listening_manifest.json').read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            self.assertNotIn('song/makoto/song.vgm', published)
            self.assertIn('tracks/song.target.vgm', published)

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
