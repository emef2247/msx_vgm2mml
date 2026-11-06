"""S3: LFO bridge correction (OPN2/OPNA routes) and the OPM route.

Part A: the forward LFO bridge selects its rate table by the OPM
clock actually stamped (3,579,545 Hz for the sfg01 family, the
previous 4 MHz table only for opm4mhz) and selects PMD/AMD per
activation from the span's maximum PMS/AMS instead of the fixed
86/16 pair; selections land in the summary losses.

Part B: OPM (YM2151) sources publish the makoto variant (the
verified OPM>OPNA law), the sfg01/opm4mhz passthrough
re-emissions and the layered composition; sfg01/dac_y8950 is
recorded unavailable. Allocation losses (8 keyed channels) refuse
without force and are recorded under force. All fixtures are
byte-built synthetics.
"""
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

    def w(reg, data):
        cmds.extend((0x54, reg, data))

    for ch in range(channels):
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
    for ch in range(channels):
        w(0x08, 0x78 | ch)
    cmds.extend(b'\x61' + struct.pack('<H', 4410))
    if noise:
        w(0x0F, 0x00)
    for ch in range(channels):
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


def _variant_pass(source_dir, out, enabled, force=False):
    from types import SimpleNamespace
    args = SimpleNamespace(input=source_dir, outdir=out,
                           vgm_variants=enabled, force=force,
                           normalization_ms=8.0, fm_state_ms=24.0)
    return export_mgs._update_vgm_variants(args)


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
    def stage(self, root, name, data):
        source_dir = root / 'input'
        source_dir.mkdir()
        (source_dir / name).write_bytes(data)
        return source_dir, root / 'out'

    def test_opm_publishes_four_variants_and_records_dac_y8950(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, out = self.stage(Path(tmp), 'song.vgm', _opm_song())
            rows = _variant_pass(source_dir, out, True)
            self.assertEqual(rows[0]['status'], 'success')
            package = out / 'vgm_variants' / 'song'
            makoto = (package / 'makoto' / 'song.vgm').read_bytes()
            sfg01 = (package / 'sfg01' / 'dac_makoto' / 'song.vgm').read_bytes()
            layered = (package / 'layered' / 'song.vgm').read_bytes()
            opm4mhz = (package / 'opm4mhz' / 'song.vgm').read_bytes()
            self.assertFalse((package / 'sfg01' / 'dac_y8950' / 'song.vgm').exists())
            self.assertEqual(_stamp(makoto, 0x48), 8000000)
            self.assertEqual(_stamp(makoto, 0x30), 0)
            self.assertEqual(_stamp(sfg01, 0x30), 3579545)
            self.assertEqual(_stamp(sfg01, 0x48), 0)
            self.assertEqual(_stamp(layered, 0x30), 3579545)
            self.assertEqual(_stamp(layered, 0x48), 8000000)
            self.assertEqual(_stamp(opm4mhz, 0x30), 4000000)
            evidence = _evidence(out, 'song')
            self.assertEqual(evidence['source_route'], 'opm')
            self.assertEqual(len(evidence['published']), 4)
            unavailable = evidence['unavailable']
            self.assertEqual(list(unavailable),
                             ['vgm_variants/song/sfg01/dac_y8950/song.vgm'])
            self.assertIn('Y8950', list(unavailable.values())[0])

    def test_opm_makoto_summary_records_law_losses(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, out = self.stage(
                Path(tmp), 'song.vgm',
                _opm_song(dt2=2, lfo=True, noise=True))
            rows = _variant_pass(source_dir, out, True)
            self.assertEqual(rows[0]['status'], 'success')
            summary = _evidence(out, 'song')['summaries']['makoto']
            losses = summary['losses']
            self.assertGreaterEqual(losses['opm_dt2_dropped'], 1)
            self.assertEqual(losses['opm_pm_depth_saturated'], 1)
            self.assertEqual(losses['opm_am_depth_saturated'], 1)
            self.assertEqual(losses['opm_lfo_waveform_substituted'], 1)
            self.assertEqual(losses['opm_noise_loudness_uncalibrated'], 1)
            self.assertEqual(summary['noise_loudness'], 'calibration-pending')

    def test_opm_eight_channels_refuse_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, out = self.stage(Path(tmp), 'song.vgm',
                                         _opm_song(channels=8))
            rows = _variant_pass(source_dir, out, True)
            self.assertEqual(rows[0]['status'], 'success')
            package = out / 'vgm_variants' / 'song'
            self.assertFalse((package / 'makoto' / 'song.vgm').exists())
            self.assertFalse((package / 'layered' / 'song.vgm').exists())
            self.assertTrue((package / 'sfg01' / 'dac_makoto' / 'song.vgm').is_file())
            self.assertTrue((package / 'opm4mhz' / 'song.vgm').is_file())
            evidence = _evidence(out, 'song')
            reasons = ' '.join(evidence['unavailable'].values())
            self.assertIn('8 FM channels', reasons)

    def test_opm_eight_channels_allocate_under_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir, out = self.stage(Path(tmp), 'song.vgm',
                                         _opm_song(channels=8))
            rows = _variant_pass(source_dir, out, True, force=True)
            self.assertEqual(rows[0]['status'], 'success')
            package = out / 'vgm_variants' / 'song'
            self.assertTrue((package / 'makoto' / 'song.vgm').is_file())
            summary = _evidence(out, 'song')['summaries']['makoto']
            self.assertEqual(len(summary['allocation_omissions']), 2)
            reasons = {item['reason'] for item in summary['allocation_omissions']}
            self.assertEqual(reasons, {'opm_simultaneous_fm_capacity'})
            self.assertEqual(
                summary['losses']['allocation_opm_simultaneous_fm_capacity'], 2)
            self.assertEqual(
                summary['allocation']['peak_ordered_source_keyed_voices'], 8)


if __name__ == '__main__':
    unittest.main()
