"""export_mgs.py --vgm-variants, S2 routes: OPNA and DCSG sources.

OPNA sources publish the makoto variant (register-level
passthrough at the 8.00 MHz cartridge stamp) and the sfg01
family (FM projected to OPM, SSG/rhythm/ADPCM-B staying on the
OPNA); sfg01/dac_y8950 does not apply and is recorded
unavailable. DCSG sources publish the PSG composition
(sfg01/dac_makoto) plus the layered OPM projection; makoto,
dac_y8950 and opm4mhz are recorded unavailable. NES APU sources
record route_unavailable with the port-deferral reason. All
fixtures are byte-built synthetics.
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


def _vgm(commands, *, version=0x171, total=4410, stamps=()):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, version)
    struct.pack_into('<I', raw, 0x18, total)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    for offset, value in stamps:
        struct.pack_into('<I', raw, offset, value)
    raw.extend(commands)
    raw.append(0x66)
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


def _opna_song(ch3_special=False):
    cmds = bytearray()

    def w(reg, data):
        cmds.extend((0x56, reg, data))

    w(0x00, 0x3d)
    w(0x01, 0x01)                       # SSG chA tone period
    w(0x07, 0x3e)
    w(0x08, 0x0c)                       # SSG mixer + volume
    if ch3_special:
        w(0x27, 0x40)                   # CH3 special mode (bit 6)
    w(0xb0, 0x32)
    for slot in range(4):
        w(0x30 + slot * 4, 0x32)
        w(0x40 + slot * 4, 0x20)
        w(0x50 + slot * 4, 0x14)
        w(0x60 + slot * 4, 0x0a)
        w(0x70 + slot * 4, 0x05)
        w(0x80 + slot * 4, 0x29)
    w(0xa4, 0x22)
    w(0xa0, 0x00)
    w(0x28, 0xf0)
    cmds.extend(b'\x61' + struct.pack('<H', 4410))
    w(0x28, 0x00)
    return _vgm(cmds, stamps=((0x48, 7987200),))


def _dcsg_song():
    cmds = bytearray((0x50, 0x8e, 0x50, 0x05, 0x50, 0x90))
    cmds.extend(b'\x61' + struct.pack('<H', 4410))
    cmds.extend((0x50, 0x9f))
    return _vgm(cmds, version=0x150, stamps=((0x0c, 3579545),))


def _nes_song():
    cmds = bytes((0xb4, 0x00, 0x30, 0xb4, 0x02, 0x7d, 0xb4, 0x03, 0x02,
                  0xb4, 0x15, 0x01))
    cmds += b'\x61' + struct.pack('<H', 4410)
    cmds += bytes((0xb4, 0x15, 0x00))
    return _vgm(cmds)


def _stamp(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def _variant_rows(out):
    rows = json.loads((out / '_diagnostics' / 'results.json')
                      .read_text(encoding='utf-8'))
    return [row for row in rows if row.get('route') == 'vgm_variants']


def _evidence(out, stem):
    return json.loads((out / '_diagnostics' / stem / 'vgm_variants.json')
                      .read_text(encoding='utf-8'))


class ExportMgsVgmVariantsS2Tests(unittest.TestCase):
    def run_main(self, *argv):
        return export_mgs.main([str(item) for item in argv])

    def stage(self, root, name, data):
        source = root / name
        source.write_bytes(data)
        return source, root / 'out'

    def test_opna_publishes_four_variants_and_records_dac_y8950(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = self.stage(Path(tmp), 'song.vgm', _opna_song())
            self.run_main(source, '--outdir', out, '--vgm-variants',
                          '--skip-keyon-counts')
            package = out / 'vgm_variants' / 'song'
            makoto = (package / 'makoto' / 'song.vgm').read_bytes()
            sfg01 = (package / 'sfg01' / 'dac_makoto' / 'song.vgm').read_bytes()
            layered = (package / 'layered' / 'song.vgm').read_bytes()
            opm4mhz = (package / 'opm4mhz' / 'song.vgm').read_bytes()
            self.assertFalse((package / 'sfg01' / 'dac_y8950' / 'song.vgm').exists())
            self.assertEqual(_stamp(makoto, 0x48), 8000000)
            self.assertEqual(_stamp(makoto, 0x30), 0)
            self.assertEqual(_stamp(sfg01, 0x48), 8000000)
            self.assertEqual(_stamp(sfg01, 0x30), 3579545)
            self.assertEqual(_stamp(layered, 0x30), 3579545)
            self.assertEqual(_stamp(opm4mhz, 0x30), 4000000)
            rows = _variant_rows(out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['status'], 'success')
            self.assertEqual(rows[0]['vgm'],
                             'vgm_variants/song/makoto/song.vgm')
            evidence = _evidence(out, 'song')
            self.assertEqual(evidence['source_route'], 'opna')
            self.assertEqual(len(evidence['published']), 4)
            unavailable = evidence['unavailable']
            self.assertEqual(list(unavailable),
                             ['vgm_variants/song/sfg01/dac_y8950/song.vgm'])
            self.assertIn('Y8950', list(unavailable.values())[0])
            manifest = json.loads((out / 'listening_manifest.json')
                                  .read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            self.assertNotIn('vgm_variants/song/sfg01/dac_y8950/song.vgm',
                             published)

    def test_opna_ch3_special_publishes_only_makoto(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = self.stage(Path(tmp), 'song.vgm',
                                     _opna_song(ch3_special=True))
            self.run_main(source, '--outdir', out, '--vgm-variants',
                          '--skip-keyon-counts')
            package = out / 'vgm_variants' / 'song'
            self.assertTrue((package / 'makoto' / 'song.vgm').is_file())
            for name in ('sfg01/dac_makoto', 'layered', 'opm4mhz'):
                self.assertFalse((package / name / 'song.vgm').exists(), name)
            evidence = _evidence(out, 'song')
            self.assertEqual(evidence['published'],
                             ['vgm_variants/song/makoto/song.vgm'])
            reasons = ' '.join(evidence['unavailable'].values())
            self.assertIn('CH3 special', reasons)
            rows = _variant_rows(out)
            self.assertEqual(rows[0]['status'], 'success')

    def test_dcsg_publishes_psg_composition_and_layered(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = self.stage(Path(tmp), 'song.vgm', _dcsg_song())
            self.run_main(source, '--outdir', out, '--vgm-variants',
                          '--skip-keyon-counts')
            package = out / 'vgm_variants' / 'song'
            sfg01 = (package / 'sfg01' / 'dac_makoto' / 'song.vgm').read_bytes()
            layered = (package / 'layered' / 'song.vgm').read_bytes()
            self.assertEqual(_stamp(sfg01, 0x30), 0)
            self.assertEqual(_stamp(sfg01, 0x74), 1789773)
            self.assertEqual(_stamp(layered, 0x30), 3579545)
            self.assertIn(b'\x54', layered)
            evidence = _evidence(out, 'song')
            self.assertEqual(evidence['source_route'], 'dcsg')
            self.assertEqual(len(evidence['published']), 2)
            self.assertEqual(len(evidence['unavailable']), 3)
            reasons = ' '.join(evidence['unavailable'].values())
            self.assertIn('mucom88-side stage (S3)', reasons)
            self.assertIn('no DAC-class lane', reasons)
            rows = _variant_rows(out)
            self.assertEqual(rows[0]['status'], 'success')

    def test_nes_records_route_unavailable_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = self.stage(Path(tmp), 'song.vgm', _nes_song())
            self.run_main(source, '--outdir', out, '--vgm-variants',
                          '--skip-keyon-counts')
            self.assertFalse((out / 'vgm_variants').exists())
            rows = _variant_rows(out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['error_code'], 'route_unavailable')
            self.assertIn('NES APU/FDS', rows[0]['detail'])
            evidence = _evidence(out, 'song')
            self.assertEqual(evidence['status'], 'route_unavailable')
            self.assertEqual(evidence['source_route'], 'nesapu')

    def test_opna_rerun_without_the_flag_removes_published_subset(self):
        # Drives the variant pass directly: a full main() rerun of
        # an OPNA source trips a pre-existing manifest quirk in
        # the MGS batch (blueprint/ndp republish, present at the
        # S1 commit), which is not what this test is about.
        from types import SimpleNamespace

        def variant_pass(source_dir, out, enabled):
            args = SimpleNamespace(input=source_dir, outdir=out,
                                   vgm_variants=enabled, force=False,
                                   normalization_ms=8.0, fm_state_ms=24.0)
            return export_mgs._update_vgm_variants(args)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / 'input'
            source_dir.mkdir()
            (source_dir / 'song.vgm').write_bytes(_opna_song())
            out = root / 'out'
            rows = variant_pass(source_dir, out, True)
            self.assertEqual(rows[0]['status'], 'success')
            self.assertTrue((out / 'vgm_variants' / 'song' / 'makoto'
                             / 'song.vgm').is_file())
            self.assertEqual(variant_pass(source_dir, out, False), [])
            for name in ('makoto', 'sfg01/dac_makoto', 'layered', 'opm4mhz'):
                self.assertFalse((out / 'vgm_variants' / 'song' / name
                                  / 'song.vgm').exists(), name)
            manifest = json.loads((out / 'listening_manifest.json')
                                  .read_text(encoding='utf-8'))
            published = manifest['entries']['song.vgm']['published']
            self.assertFalse([name for name in published
                              if name.startswith('vgm_variants/')])


if __name__ == '__main__':
    unittest.main()
