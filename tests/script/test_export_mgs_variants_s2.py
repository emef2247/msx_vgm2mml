"""OPNA, DCSG, NES and mixed-source musical variant integration."""
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
    cmds = bytes((0xb4, 0x15, 0x01, 0xb4, 0x00, 0x3f, 0xb4, 0x02, 0x7d, 0xb4, 0x03, 0x02))
    cmds += b'\x61' + struct.pack('<H', 4410)
    cmds += bytes((0xb4, 0x15, 0x00))
    return _vgm(cmds, stamps=((0x84, 1789773),))


def _stamp(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def _variant_rows(out):
    rows = json.loads((out / '_diagnostics' / 'results.json')
                      .read_text(encoding='utf-8'))
    return [row for row in rows if row.get('route') == 'vgm_variants']


def _evidence(out, stem):
    return json.loads((out / '_diagnostics' / stem / 'vgm_variants.json')
                      .read_text(encoding='utf-8'))


from test_export_mgs_variants import assert_profiles, variant_pass


class ExportMgsVgmVariantsS2Tests(unittest.TestCase):
    def render(self, data, check, force=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'song.vgm'; source.write_bytes(data)
            out = root / 'out'
            rows = variant_pass(source, out, force=force)
            self.assertEqual(rows[0]['status'], 'success', rows)
            check(out, assert_profiles(self, out, ('sfg01', 'makoto', 'layered')))

    def test_opna_fm_and_ssg_publish_both_base_profiles(self):
        def check(out, report):
            makoto = (out / 'vgm-variants/makoto/song.vgm').read_bytes()
            sfg01 = (out / 'vgm-variants/sfg01/song.vgm').read_bytes()
            self.assertEqual(_stamp(makoto, 0x48), 8000000)
            self.assertEqual(_stamp(makoto, 0x30), 0)
            self.assertEqual(_stamp(sfg01, 0x30), 3579545)
            self.assertEqual(_stamp(sfg01, 0x74), 1789773)
        self.render(_opna_song(), check)

    def test_opna_special_mode_is_retained_with_explicit_cross_chip_loss(self):
        def check(out, report):
            loss = report['summaries']['sfg01']['losses']
            self.assertGreater(loss.get('fm_channel3_special_observed_not_exactly_projected', 0), 0)
        self.render(_opna_song(ch3_special=True), check)

    def test_dcsg_publishes_auxiliary_psg_in_both_base_profiles(self):
        def check(out, report):
            self.assertEqual(_stamp((out / 'vgm-variants/sfg01/song.vgm').read_bytes(), 0x74), 1789773)
            self.assertEqual(_stamp((out / 'vgm-variants/makoto/song.vgm').read_bytes(), 0x74), 1789773)
            self.assertEqual(_stamp((out / 'vgm-variants/makoto/song.vgm').read_bytes(), 0x48), 0)
        self.render(_dcsg_song(), check)

    def test_nes_pulse_has_musical_profiles_instead_of_deferred_route(self):
        def check(out, report):
            self.assertGreater(report['summaries']['sfg01']['writes'], 0)
            self.assertEqual(_stamp((out / 'vgm-variants/sfg01/song.vgm').read_bytes(), 0x30), 3579545)
        self.render(_nes_song(), check)

    def test_mixed_opna_dcsg_source_uses_one_shared_native_projection(self):
        # Keep both source devices active in the same authored VGM timeline.
        raw = _opna_song()
        commands = raw[256:-1] + _dcsg_song()[256:-1]
        mixed = _vgm(commands, total=8820, stamps=((0x48, 7987200), (0x0c, 3579545)))
        def check(out, report):
            self.assertEqual(report['summaries']['sfg01']['input_representation'], 'NativePerformance')
        self.render(mixed, check)

    def test_opna_disable_removes_published_subset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'song.vgm'; source.write_bytes(_opna_song())
            out = root / 'out'; variant_pass(source, out)
            self.assertEqual(variant_pass(source, out, False), [])
            self.assertFalse(list((out / 'vgm-variants').rglob('*.vgm')))


if __name__ == '__main__':
    unittest.main()
