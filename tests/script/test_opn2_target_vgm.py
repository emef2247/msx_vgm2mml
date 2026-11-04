"""OPN2 -> OPM target VGM (S2): projection law, writer, deferred lanes."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'py'))
from native_imports import inspect_source
from native_imports.vgm_timing import command_times
from opn2_target_vgm import TARGET_CLOCK, convert, project
from native_imports.source import analyze_source


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


class Opn2TargetVgmTests(unittest.TestCase):
    def convert(self, raw):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / 'authored.vgm'
        source.write_bytes(raw)
        return convert(source, folder / 'out'), folder / 'out'

    def test_phrase_projects_to_opm_vgm_at_cartridge_clock(self):
        summary, out = self.convert(vgm(PHRASE))
        target = out / 'authored.target.vgm'
        self.assertTrue(target.is_file())
        raw = target.read_bytes()
        self.assertEqual(struct.unpack_from('<I', raw, 0x30)[0], TARGET_CLOCK)
        bundle = inspect_source(raw)
        self.assertEqual(bundle['active_chips'], ('opm',))
        self.assertGreater(bundle['command_counts']['opm'], 5)
        self.assertEqual(summary['losses'], {})
        self.assertEqual(summary['deferred'], {})
        self.assertTrue((out / 'authored.opn2_opm.writes.csv').is_file())

    def test_pitch_row_carries_source_hz_and_close_target_hz(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        bundle = analyze_source(vgm(PHRASE), Path(temporary.name), 'authored')
        rows, losses = project(bundle['analyses']['opn2'], clock_raw=7670454)
        pitch = [r for r in rows if r['target_register'] == 0x28]
        self.assertEqual(len(pitch), 1)
        # fnum 617, block 4 at 7,670,454 Hz -> 617*7670454/(144*2**17)
        self.assertAlmostEqual(pitch[0]['source_frequency_hz'], 250.71, places=1)
        self.assertLess(abs(pitch[0]['target_frequency_hz'] / pitch[0]['source_frequency_hz'] - 1), 0.01)

    def test_dac_writes_project_to_adpcm_b(self):
        # DAC enable, then an 8-byte burst at a 2-tick spacing.
        burst = bytes((0x52, 0x2b, 0x80))
        for value in (0x80, 0xA0, 0xC0, 0xE0, 0xC0, 0xA0, 0x80, 0x60):
            burst += bytes((0x52, 0x2a, value, 0x61, 0x02, 0x00))
        summary, out = self.convert(vgm(PHRASE + burst))
        self.assertNotIn('dac', summary['deferred'])
        self.assertEqual(summary['dac']['unique_samples'], 1)
        self.assertEqual(summary['dac']['playbacks'], 1)
        self.assertGreater(summary['dac_writes'], 0)
        raw = (out / 'authored.target.vgm').read_bytes()
        block = raw.find(b'\x67\x66\x81')
        self.assertGreater(block, 0)
        size = struct.unpack_from('<I', raw, block + 3)[0]
        total = struct.unpack_from('<I', raw, block + 7)[0]
        self.assertEqual(total, summary['dac']['dram_bytes'])
        self.assertEqual(size, 8 + total)
        triggers = 0
        for event in command_times(raw):
            if event.command == 0x57 and raw[event.address + 1] == 0x00 \
                    and raw[event.address + 2] == 0xA0:
                triggers += 1
        self.assertEqual(triggers, 1)
        self.assertTrue((out / 'authored.opn2_dac.csv').is_file())

    def test_dac_stream_supplies_project_to_adpcm_b(self):
        bank = bytes((0x80, 0x90, 0xB0, 0xD0, 0xB0, 0x90)) * 4
        block = bytes((0x67, 0x66, 0x00)) + struct.pack('<I', len(bank)) + bank
        stream = bytes((0xE0,)) + struct.pack('<I', 0)
        stream += bytes((0x83,)) * len(bank)  # play one byte, wait 3
        summary, _ = self.convert(vgm(PHRASE + block + stream))
        self.assertEqual(summary['dac']['stream_supplies'], len(bank))
        self.assertGreaterEqual(summary['dac']['playbacks'], 1)
        self.assertNotIn('dac', summary['deferred'])

    def test_dac_stream_start_without_setup_is_a_counted_loss(self):
        raw = vgm(PHRASE + bytes((0x93,)) + bytes(10))
        summary, _ = self.convert(raw)
        self.assertEqual(summary['losses']['dac_stream_configuration_incomplete'], 1)

    def test_adpcm_b_encoder_roundtrip_tracks_waveform(self):
        import math
        from opn2_target_vgm import _encode_adpcm_b
        wave = [round(12000 * math.sin(2 * math.pi * i / 64)) for i in range(256)]
        encoded = _encode_adpcm_b(wave)
        self.assertEqual(len(encoded), 128)
        predictor, step = 0, 127
        decoded = []
        for byte in encoded:
            for nibble in (byte >> 4, byte & 15):
                delta = ((2 * (nibble & 7) + 1) * step) // 8
                predictor = max(-32768, min(32767, predictor
                                            + (-delta if nibble & 8 else delta)))
                step = max(127, min(24576, step * (57, 57, 57, 57, 77, 102, 128, 153)[nibble & 7] // 64))
                decoded.append(predictor)
        errors = [abs(a - b) for a, b in zip(wave[16:], decoded[16:])]
        self.assertLess(sum(errors) / len(errors), 400)

    def test_test_register_write_gates_without_force(self):
        raw = vgm(PHRASE + bytes((0x52, 0x21, 0x00, 0x62)))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        bundle = analyze_source(raw, Path(temporary.name), 'authored')
        with self.assertRaises(ValueError):
            project(bundle['analyses']['opn2'], clock_raw=7670454)
        rows, losses = project(bundle['analyses']['opn2'], clock_raw=7670454, force=True)
        self.assertEqual(losses['forced_unmodeled_register_writes'], 1)


DCSG_PHRASE = bytes((
    0x50, 0x80, 0x50, 0x10,        # chip 0 tone 0 period 256
    0x50, 0x90,                    # chip 0 tone 0 attenuation 0
    0x50, 0xE1,                    # chip 0 noise control: rate 1, periodic
    0x50, 0xF2,                    # chip 0 noise attenuation 2
    0x30, 0x80, 0x30, 0x08,        # chip 1 tone 0 period 128
    0x30, 0x90,                    # chip 1 tone 0 attenuation 0
    0x61, 0x00, 0x08,              # wait 2048
    0x50, 0x95,                    # chip 0 tone 0 attenuation 5
    0x61, 0x00, 0x08,              # wait 2048
))


def dual_vgm(commands):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x0c, 3579545 | 0x40000000)  # dual SN76489
    struct.pack_into('<I', raw, 0x2c, 7670454)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    raw.extend(commands)
    raw.append(0x66)
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


class Opn2DcsgTargetTests(unittest.TestCase):
    def convert(self, raw):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / 'authored.vgm'
        source.write_bytes(raw)
        return convert(source, folder / 'out'), folder / 'out'

    def test_dcsg_projects_to_ay_and_ssg(self):
        summary, out = self.convert(dual_vgm(PHRASE + DCSG_PHRASE))
        self.assertNotIn('dcsg', summary['deferred'])
        self.assertGreater(summary['dcsg_writes'], 0)
        raw = (out / 'authored.target.vgm').read_bytes()
        self.assertEqual(struct.unpack_from('<I', raw, 0x48)[0], 8000000)
        self.assertEqual(struct.unpack_from('<I', raw, 0x74)[0], 1789773)
        self.assertEqual(raw[0x78], 0x10)
        bundle = inspect_source(raw)
        self.assertIn('opna', bundle['active_chips'])
        # native_imports has no AY domain, so the PSG lane is checked
        # on the raw command stream instead of via inspect_source.
        from native_imports.vgm_timing import command_times
        from collections import Counter
        counts = Counter(e.command for e in command_times(raw))
        self.assertEqual(counts[0xA0] + counts[0x56], summary['dcsg_writes'])
        self.assertGreater(counts[0xA0], 0)
        import csv as csv_module
        with (out / 'authored.opn2_dcsg.writes.csv').open() as stream:
            rows = list(csv_module.DictReader(stream))
        ay_period = {(int(r['target_register']), int(r['target_data']))
                     for r in rows if r['target_device'] == 'ay'
                     and r['reason'].startswith('dcsg tone period')}
        # period 256 at 3.579545 MHz -> 437 Hz -> AY TP 256 (fine 0, coarse 1)
        self.assertIn((0, 0), ay_period)
        self.assertIn((1, 1), ay_period)
        ssg_period = {(int(r['target_register']), int(r['target_data']))
                      for r in rows if r['target_device'] == 'ssg'
                      and r['reason'].startswith('dcsg tone period')}
        # period 128 -> 874 Hz -> SSG TP 286 (fine 30, coarse 1)
        self.assertIn((0, 30), ssg_period)
        self.assertIn((1, 1), ssg_period)
        ay_volumes = [int(r['target_data']) for r in rows
                      if r['target_device'] == 'ay' and int(r['target_register']) == 8]
        self.assertEqual(ay_volumes, [0, 15, 12])
        # leading 0: attenuation unknown until the first source write;
        # then attenuation 0 -> 15 and 5 -> 12 on the dB-matched table
        mixers = {int(r['target_data']) for r in rows
                  if r['target_device'] == 'ay' and int(r['target_register']) == 7}
        self.assertIn(0x18, mixers)  # noise audible on channel C
        c_volumes = {int(r['target_data']) for r in rows
                     if r['target_device'] == 'ay' and int(r['target_register']) == 10}
        self.assertIn(14, c_volumes)  # noise attenuation 2 -> 14 while audible
        # noise rate 1 = 3496 Hz shift -> AY NP 32 exceeds 31 and clamps
        self.assertEqual(summary['losses']['dcsg_noise_period_clamped_ay'], 1)
        self.assertEqual(summary['dcsg']['ay']['noise_segments'], 2)
        # initial unknown segment + the segment from the control write


if __name__ == '__main__':
    unittest.main()
