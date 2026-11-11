"""Native musical OPM profiles and retained standalone LFO bridge checks."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'py'))
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


def _opm_song(channels=2, *, clock=3579545, dt2=0, lfo=False, noise=False):
    cmds = bytearray()
    channel_ids=list(range(channels))
    if noise and 7 not in channel_ids:channel_ids[-1]=7

    def w(reg, data):
        cmds.extend((0x54, reg, data))

    for ch in channel_ids:
        w(0x20 + ch, 0xC2)
        for bank in range(4):
            w(0x40 + bank * 8 + ch, 0x32)
            w(0x60 + bank * 8 + ch, 0x20)
            w(0x80 + bank * 8 + ch, 0x14)
            w(0xA0 + bank * 8 + ch, 0x0A)
            w(0xC0 + bank * 8 + ch, (dt2 << 6) | 0x05)
            w(0xE0 + bank * 8 + ch, 0x29)
        w(0x28 + ch, 0x4A)
        w(0x30 + ch, 0x00)
    if lfo:
        w(0x38, 0x52)                   # ch0 PMS 5, AMS 2
        w(0x19, 0x80 | 127)             # PMD 127: PM depth saturates OPNA
        w(0x19, 100)                    # AMD 100: AM depth saturates OPNA
        w(0x1B, 0x00)                   # sawtooth: substituted by triangle
        w(0x18, 0xC8)                   # ~5.1 Hz at the MSX clock
    if noise:
        w(0x0F, 0x80 | 20)              # noise on, NFREQ 20
    for ch in channel_ids:
        w(0x08, 0x78 | ch)
    cmds.extend(b'\x61' + struct.pack('<H', 4410))
    if noise:
        w(0x0F, 0x00)
    for ch in channel_ids:
        w(0x08, ch)
    return _vgm(cmds, stamps=((0x30, clock),))


def _opna_lfo_song():
    cmds = bytearray()

    def w(reg, data):
        cmds.extend((0x56, reg, data))

    w(0x22, 0x0B)                       # LFO on, rate 3
    w(0xB0, 0x32)
    for slot in range(4):
        w(0x30 + slot * 4, 0x32)
        w(0x40 + slot * 4, 0x20)
        w(0x50 + slot * 4, 0x14)
        w(0x60 + slot * 4, 0x0A)
        w(0x70 + slot * 4, 0x05)
        w(0x80 + slot * 4, 0x29)
    w(0xA4, 0x22)
    w(0xA0, 0x00)
    w(0xB4, 0xC0 | (1 << 4) | 2)        # AMS 1, PMS 2 -> PMD 83, AMD 8
    w(0x28, 0xF0)
    cmds.extend(b'\x61' + struct.pack('<H', 4410))
    w(0xB4, 0xC0 | (1 << 4) | 6)        # PMS 6 -> reselect PMD 15
    cmds.extend(b'\x61' + struct.pack('<H', 4410))
    w(0x22, 0x03)                       # LFO off: span ends
    w(0x28, 0x00)
    return _vgm(cmds, stamps=((0x48, 7987200),))


def _stamp(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def _opm_writes(raw):
    """(register, data) of every YM2151 write in a variant VGM."""
    writes = []
    index = 256
    while index < len(raw):
        command = raw[index]
        if command == 0x54:
            writes.append((raw[index + 1], raw[index + 2]))
            index += 3
        elif command == 0x61:
            index += 3
        elif command in (0x62, 0x63) or 0x70 <= command <= 0x7F:
            index += 1
        elif command == 0x66:
            break
        else:
            raise AssertionError(f'unexpected command {command:#x}')
    return writes


from test_export_mgs_variants import assert_profiles, variant_pass as _variant_pass


def _evidence(out, stem):
    return json.loads((out / '_diagnostics' / stem / 'vgm_variants.json')
                      .read_text(encoding='utf-8'))


class LfoBridgeCorrectionTests(unittest.TestCase):
    def test_opna_bridge_selects_depths_per_activation(self):
        from opna_target_vgm import convert
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(_opna_lfo_song())
            out = root / 'out'
            summary = convert(source, out, force=True, target='sfg01')
            losses = summary['losses']
            self.assertEqual(losses['lfo_depths_bridged'], 1)
            self.assertEqual(losses['lfo_bridge_pmd_83'], 1)
            self.assertEqual(losses['lfo_bridge_pmd_15'], 1)
            self.assertEqual(losses['lfo_bridge_amd_8'], 2)
            self.assertEqual(losses['lfo_bridge_depths_reselected'], 1)
            writes = _opm_writes((out / summary['target_vgm']).read_bytes())
            # Corrected 3,579,545 Hz table: index 0 and rate 3.
            self.assertEqual(writes[0], (0x18, 0xC3))
            self.assertIn((0x18, 0xCE), writes)
            depths = [data for reg, data in writes if reg == 0x19]
            self.assertEqual(depths, [0x80 | 83, 8, 0x80 | 15, 8, 0x80, 0])

    def test_opna_bridge_opm4mhz_keeps_the_4mhz_table(self):
        from opna_target_vgm import convert
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'song.vgm'
            source.write_bytes(_opna_lfo_song())
            out = root / 'out'
            summary = convert(source, out, force=True, target='opm4mhz')
            writes = _opm_writes((out / summary['target_vgm']).read_bytes())
            self.assertEqual(writes[0], (0x18, 0xC1))
            self.assertIn((0x18, 0xCB), writes)
            depths = [data for reg, data in writes if reg == 0x19]
            self.assertEqual(depths, [0x80 | 83, 8, 0x80 | 15, 8, 0x80, 0])


class ExportMgsOpmVariantsTests(unittest.TestCase):
    def render(self, data, check, force=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'song.vgm'; source.write_bytes(data)
            out = root / 'out'; rows = _variant_pass(source, out, force=force)
            self.assertEqual(rows[0]['status'], 'success', rows)
            check(out, _evidence(out, 'song'))

    def test_opm_publishes_base_profiles_without_redundant_auxiliaries(self):
        def check(out, report):
            assert_profiles(self, out, ('sfg01', 'makoto', 'layered'))
            makoto = (out / 'vgm-variants/makoto/song.vgm').read_bytes()
            sfg01 = (out / 'vgm-variants/sfg01/song.vgm').read_bytes()
            self.assertEqual(_stamp(makoto, 0x48), 8000000)
            self.assertEqual(_stamp(makoto, 0x30), 0)
            self.assertEqual(_stamp(sfg01, 0x30), 3579545)
            self.assertEqual(_stamp(sfg01, 0x48), 0)
        self.render(_opm_song(), check)

    def test_opm_cross_chip_timbre_losses_are_reported(self):
        def check(out, report):
            losses = report['summaries']['makoto']['losses']
            self.assertGreater(losses['fm_opm_dt2_unavailable_on_opn'], 0)
            self.assertGreater(losses['fm_lfo_cross_chip_approximation'], 0)
            self.assertGreater(losses['fm_opm_lfo_waveform_approximated'], 0)
            self.assertGreater(losses['fm_native_noise_register_not_projected'],0)
        self.render(_opm_song(dt2=2, lfo=True, noise=True), check)

    def test_opm_eight_channels_keep_sfg_and_refuse_makoto_capacity_loss(self):
        def check(out, report):
            assert_profiles(self, out, ('sfg01',))
            self.assertIn('capacity', report['summaries']['makoto']['reason'])
        self.render(_opm_song(channels=8), check)

    def test_opm_eight_channels_record_omissions_under_force(self):
        def check(out, report):
            assert_profiles(self, out, ('sfg01', 'makoto', 'layered'))
            self.assertEqual(report['summaries']['makoto']['losses']['fm_units_omitted_capacity'], 2)
        self.render(_opm_song(channels=8), check, force=True)


if __name__ == '__main__':
    unittest.main()
