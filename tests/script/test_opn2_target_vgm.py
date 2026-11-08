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
from opn2_target_vgm import (OPM4MHZ_CLOCK, TARGET_CLOCK, convert,
                            project_opm_from_analysis)
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
    def convert(self, raw, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / 'authored.vgm'
        source.write_bytes(raw)
        return convert(source, folder / 'out', **kwargs), folder / 'out'

    def test_phrase_projects_to_opm_vgm_at_cartridge_clock(self):
        summary, out = self.convert(vgm(PHRASE), target='sfg01')
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

    def test_opm4mhz_variant_uses_4mhz_opm_clock(self):
        summary, out = self.convert(vgm(PHRASE), target='opm4mhz')
        raw = (out / 'authored.target.vgm').read_bytes()
        self.assertEqual(summary['target_cartridge'], 'opm4mhz')
        self.assertEqual(summary['target_clock_hz'], OPM4MHZ_CLOCK)
        self.assertEqual(struct.unpack_from('<I', raw, 0x30)[0], OPM4MHZ_CLOCK)
        self.assertGreater(summary['opm_writes'], 0)
        bundle = inspect_source(raw)
        self.assertEqual(bundle['active_chips'], ('opm',))

    def test_pitch_row_carries_source_hz_and_close_target_hz(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        bundle = analyze_source(vgm(PHRASE), Path(temporary.name), 'authored')
        rows, losses = project_opm_from_analysis(bundle['analyses']['opn2'], clock_raw=7670454)
        pitch = [r for r in rows if r['target_register'] == 0x28]
        self.assertEqual(len(pitch), 1)
        # fnum 617, block 4 at 7,670,454 Hz -> 617*7670454/(144*2**17)
        self.assertAlmostEqual(pitch[0]['source_frequency_hz'], 250.71, places=1)
        self.assertLess(abs(pitch[0]['target_frequency_hz'] / pitch[0]['source_frequency_hz'] - 1), 0.01)

    def test_opm_control_reevaluated_when_dac_context_changes(self):
        # Channel 6's OPM control byte gates its output while the
        # DAC owns the channel. The gate is context, not a write
        # to the channel's own registers: enabling and disabling
        # the DAC (register 0x2B) must re-emit the control byte
        # from the segment state at the toggle ticks.
        commands = bytes((
            0x53, 0xb6, 0xc0,              # ch6 pan L+R
            0x53, 0xb2, 0x07,              # ch6 FB 0, ALG 7
            0x53, 0xa6, 0x22, 0x53, 0xa2, 0x69,
            0x52, 0x28, 0xf6,              # key on ch6
            0x61, 0x10, 0x00,
            0x52, 0x2b, 0x80,              # DAC enable: gate shut
            0x61, 0x10, 0x00,
            0x52, 0x2b, 0x00,              # DAC disable: gate restored
            0x52, 0x28, 0x06,              # key off ch6
        ))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        bundle = analyze_source(vgm(commands), Path(temporary.name), 'authored')
        rows, losses = project_opm_from_analysis(
            bundle['analyses']['opn2'], clock_raw=7670454)
        control = [r['target_data'] for r in rows
                   if r['target_register'] == 0x25]
        self.assertEqual(control, [0xc0, 0xc7, 0x07, 0xc7])

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

    def test_dac_y8950_variant(self):
        # Same DAC burst as the ADPCM-B test, rerouted to a Y8950.
        burst = bytes((0x52, 0x2b, 0x80))
        for value in (0x80, 0xA0, 0xC0, 0xE0, 0xC0, 0xA0, 0x80, 0x60):
            burst += bytes((0x52, 0x2a, value, 0x61, 0x02, 0x00))
        summary, out = self.convert(vgm(PHRASE + burst), dac='y8950')
        self.assertEqual(summary['dac_target'], 'y8950')
        self.assertEqual(summary['dac']['unique_samples'], 1)
        self.assertEqual(summary['dac']['playbacks'], 1)
        raw = (out / 'authored.target.vgm').read_bytes()
        block = raw.find(b'\x67\x66\x88')
        self.assertGreater(block, 0)
        self.assertEqual(raw.find(b'\x67\x66\x81'), -1)
        size = struct.unpack_from('<I', raw, block + 3)[0]
        total = struct.unpack_from('<I', raw, block + 7)[0]
        self.assertEqual(total, summary['dac']['dram_bytes'])
        self.assertEqual(size, 8 + total)
        self.assertEqual(struct.unpack_from('<I', raw, 0x58)[0], 3579545)
        events = list(command_times(raw))
        self.assertFalse(any(e.command == 0x57 for e in events))
        starts = [e for e in events if e.command == 0x5C
                  and raw[e.address + 1] == 0x07
                  and raw[e.address + 2] == 0x80]
        self.assertEqual(len(starts), 1)
        # The burst's 2-tick hold is a 22050 Hz natural rate; the
        # Y8950 rate law is clock * delta-N / (72 * 65536).
        expected_delta_n = round(22050 * 72 * 65536 / 3579545)
        delta_l = [e for e in events if e.command == 0x5C
                   and raw[e.address + 1] == 0x10]
        self.assertEqual(len(delta_l), 1)
        self.assertEqual(raw[delta_l[0].address + 2], expected_delta_n & 0xFF)
        delta_h = [e for e in events if e.command == 0x5C
                   and raw[e.address + 1] == 0x11]
        self.assertEqual(raw[delta_h[0].address + 2], expected_delta_n >> 8)
        import csv as csv_module
        with (out / 'authored.opn2_dac.csv').open() as stream:
            rows = list(csv_module.DictReader(stream))
        self.assertEqual(int(rows[0]['delta_n']), expected_delta_n)

    def test_layered_corrects_y8950_dac_to_opna(self):
        # The layered composition is the dual-cartridge one, so a
        # y8950 DAC request is corrected to the OPNA's ADPCM-B.
        burst = bytes((0x52, 0x2b, 0x80))
        for value in (0x80, 0xA0, 0xC0, 0xE0, 0xC0, 0xA0, 0x80, 0x60):
            burst += bytes((0x52, 0x2a, value, 0x61, 0x02, 0x00))
        summary, out = self.convert(vgm(PHRASE + burst),
                                    dac='y8950', layered=True)
        self.assertEqual(summary['dac_target'], 'opna')
        self.assertEqual(summary['dac_corrected_from'], 'y8950')
        for name in ('authored.target.vgm', 'authored.layer.target.vgm'):
            raw = (out / name).read_bytes()
            self.assertGreater(raw.find(b'\x67\x66\x81'), 0)
            self.assertEqual(raw.find(b'\x67\x66\x88'), -1)
            self.assertEqual(struct.unpack_from('<I', raw, 0x58)[0], 0)
            events = list(command_times(raw))
            self.assertFalse(any(e.command == 0x5C for e in events))
            self.assertTrue(any(e.command == 0x57 for e in events))
        plain, _ = self.convert(vgm(PHRASE + burst), dac='y8950')
        self.assertNotIn('dac_corrected_from', plain)

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
            project_opm_from_analysis(bundle['analyses']['opn2'], clock_raw=7670454)
        rows, losses = project_opm_from_analysis(bundle['analyses']['opn2'], clock_raw=7670454, force=True)
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
    def convert(self, raw, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / 'authored.vgm'
        source.write_bytes(raw)
        return convert(source, folder / 'out', **kwargs), folder / 'out'

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
        events = list(command_times(raw))
        from collections import Counter
        counts = Counter(e.command for e in events)
        # Port 0 also carries the OPNA FM lane under the makoto
        # target; only its SSG registers (0x00-0x0F) are DCSG rows.
        ssg_writes = sum(1 for e in events if e.command == 0x56
                         and raw[e.address + 1] < 0x10)
        self.assertEqual(counts[0xA0] + ssg_writes, summary['dcsg_writes'])
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
        self.assertEqual(ay_volumes, [0, 13, 10])
        # leading 0: attenuation unknown until the first source write;
        # then attenuation 0 -> 13 and 5 -> 10 on the dB-matched
        # table at the default gain 0.5 (-6.02 dB, settled by
        # real-hardware listening 2026-11-07)
        self.assertEqual(summary['dcsg_gain'], 0.5)
        mixers = {int(r['target_data']) for r in rows
                  if r['target_device'] == 'ay' and int(r['target_register']) == 7}
        self.assertIn(0x18, mixers)  # noise audible on channel C
        c_volumes = {int(r['target_data']) for r in rows
                     if r['target_device'] == 'ay' and int(r['target_register']) == 10}
        self.assertIn(12, c_volumes)  # noise attenuation 2 -> 12 while audible
        # The same source with an explicit lane gain of 0.036 (the
        # x68k PCM balance) shifts every DCSG volume down the ladder.
        gained, gained_out = self.convert(dual_vgm(PHRASE + DCSG_PHRASE),
                                          dcsg_gain=0.036)
        self.assertEqual(gained['dcsg_gain'], 0.036)
        with (gained_out / 'authored.opn2_dcsg.writes.csv').open() as stream:
            gained_rows = list(csv_module.DictReader(stream))
        gained_volumes = [int(r['target_data']) for r in gained_rows
                          if r['target_device'] == 'ay'
                          and int(r['target_register']) == 8]
        self.assertEqual(gained_volumes, [0, 6, 3])
        gained_c = {int(r['target_data']) for r in gained_rows
                    if r['target_device'] == 'ay'
                    and int(r['target_register']) == 10}
        self.assertIn(5, gained_c)  # noise attenuation 2 -> 5 with the gain
        # noise rate 1 = 3496 Hz shift -> AY NP 32 exceeds 31 and clamps
        self.assertEqual(summary['losses']['dcsg_noise_period_clamped_ay'], 1)
        self.assertEqual(summary['dcsg']['ay']['noise_segments'], 2)
        # initial unknown segment + the segment from the control write

    def convert_layered(self, raw, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / 'authored.vgm'
        source.write_bytes(raw)
        return convert(source, folder / 'out', layered=True, **kwargs), folder / 'out'

    def test_layered_not_emitted_by_default(self):
        _summary, out = self.convert(vgm(PHRASE))
        self.assertFalse((out / 'authored.layer.target.vgm').exists())

    def test_layered_combines_fm_lanes_and_keeps_plain_target(self):
        plain_summary, plain_out = self.convert(vgm(PHRASE))
        summary, out = self.convert_layered(vgm(PHRASE))
        self.assertTrue(summary['layered'])
        self.assertGreater(summary['layer_writes'], 0)
        self.assertEqual(summary['layer_target_vgm'], 'authored.layer.target.vgm')
        self.assertTrue((out / 'authored.opn2_opna_fm.writes.csv').is_file())
        # The plain target is byte-identical with and without --layered.
        self.assertEqual((out / 'authored.target.vgm').read_bytes(),
                         (plain_out / 'authored.target.vgm').read_bytes())
        self.assertEqual(plain_summary['target_writes'], summary['target_writes'])
        raw = (out / 'authored.layer.target.vgm').read_bytes()
        bundle = inspect_source(raw)
        self.assertIn('opm', bundle['active_chips'])
        self.assertIn('opna', bundle['active_chips'])
        # The YM2608 clock is stamped because its FM commands appear.
        self.assertEqual(struct.unpack_from('<I', raw, 0x48)[0], 8000000)

    def test_layered_fnum_rescaled_to_opna_clock(self):
        _summary, out = self.convert_layered(vgm(PHRASE))
        raw = (out / 'authored.layer.target.vgm').read_bytes()
        writes = [(raw[e.address + 1], raw[e.address + 2])
                  for e in command_times(raw) if e.command == 0x56]
        # Operator parameters and key on/off pass through verbatim.
        self.assertIn((0x30, 0x71), writes)
        self.assertIn((0x28, 0xf0), writes)
        # fnum 617 (block 4) at 7,670,454 Hz -> 592 at 8 MHz: the
        # corrected high byte (block 4, fnum bits 8-10 = 2) precedes
        # the low byte 592 & 0xff = 0x50 at the same position.
        pair = [(0xa4, 0x22), (0xa0, 0x50)]
        positions = [i for i in range(len(writes) - 1)
                     if writes[i:i + 2] == pair]
        self.assertEqual(len(positions), 1)

    def test_default_target_is_makoto_opna_only(self):
        summary, out = self.convert(vgm(PHRASE))
        self.assertEqual(summary['target_cartridge'], 'makoto')
        self.assertEqual(summary['opm_writes'], 0)
        self.assertGreater(summary['opna_fm_writes'], 0)
        raw = (out / 'authored.target.vgm').read_bytes()
        commands = [e.command for e in command_times(raw)]
        self.assertNotIn(0x54, commands)
        self.assertIn(0x56, commands)
        # No YM2151 clock is stamped when no OPM writes are present.
        self.assertEqual(struct.unpack_from('<I', raw, 0x30)[0], 0)
        self.assertEqual(struct.unpack_from('<I', raw, 0x48)[0], 8000000)
        bundle = inspect_source(raw)
        self.assertNotIn('opm', bundle['active_chips'])
        self.assertIn('opna', bundle['active_chips'])
        self.assertTrue((out / 'authored.opn2_opna_fm.writes.csv').is_file())

    def test_sfg01_target_keeps_opm_composition(self):
        summary, out = self.convert(vgm(PHRASE), target='sfg01')
        self.assertEqual(summary['target_cartridge'], 'sfg01')
        self.assertGreater(summary['opm_writes'], 0)
        self.assertEqual(summary['opna_fm_writes'], 0)
        self.assertFalse((out / 'authored.opn2_opna_fm.writes.csv').exists())
        raw = (out / 'authored.target.vgm').read_bytes()
        self.assertEqual(struct.unpack_from('<I', raw, 0x30)[0], TARGET_CLOCK)

    def test_layered_under_makoto_adds_opm_lane(self):
        summary, out = self.convert_layered(vgm(PHRASE))
        raw = (out / 'authored.layer.target.vgm').read_bytes()
        commands = [e.command for e in command_times(raw)]
        self.assertIn(0x54, commands)
        self.assertIn(0x56, commands)
        self.assertGreater(summary['layer_writes'], 0)
        # The plain makoto target still carries no OPM writes.
        plain = (out / 'authored.target.vgm').read_bytes()
        self.assertNotIn(0x54, [e.command for e in command_times(plain)])

    def test_unknown_target_rejected(self):
        with self.assertRaises(ValueError):
            self.convert(vgm(PHRASE), target='bogus')


# Voice setup exercising the OPN2>OPNA law: ch1 ALG7 (all slots
# are carriers), ch1 slot2 with key scale 2, ch2 ALG0 (only OP4
# is a carrier, OP1 is a modulator).
LAW_PHRASE = bytes((
    0x52, 0xb0, 0x07,   # ch1 algorithm 7
    0x52, 0x4c, 0x40,   # ch1 OP4 TL 64 (carrier)
    0x52, 0x40, 0x60,   # ch1 OP1 TL 96 (carrier under ALG7)
    0x52, 0x5c, 0x1f,   # ch1 OP4 AR 31, KS 0
    0x52, 0x6c, 0x0a,   # ch1 OP4 DR 10
    0x52, 0x7c, 0x05,   # ch1 OP4 SR 5
    0x52, 0x58, 0x9f,   # ch1 OP2 AR 31, KS 2
    0x52, 0x68, 0x0a,   # ch1 OP2 DR 10 (KS 2: not corrected)
    0x52, 0xb1, 0x00,   # ch2 algorithm 0
    0x52, 0x4d, 0x40,   # ch2 OP4 TL 64 (carrier)
    0x52, 0x41, 0x40,   # ch2 OP1 TL 64 (modulator: verbatim)
    0x52, 0xa4, 0x22, 0x52, 0xa0, 0x69, 0x52, 0x28, 0xf0,
    0x61, 0x00, 0x10,
    0x52, 0x28, 0x00,
))


class Opn2OpnaLawTests(unittest.TestCase):
    def convert(self, raw, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / 'authored.vgm'
        source.write_bytes(raw)
        return convert(source, folder / 'out', **kwargs), folder / 'out'

    def opna_writes(self, out):
        raw = (out / 'authored.target.vgm').read_bytes()
        return [(raw[e.address + 1], raw[e.address + 2])
                for e in command_times(raw) if e.command == 0x56]

    def test_law_off_by_default_keeps_state_values(self):
        summary, out = self.convert(vgm(LAW_PHRASE))
        self.assertFalse(summary['opna_law'])
        self.assertNotIn('law_tl_carrier_writes', summary['layer'])
        writes = self.opna_writes(out)
        self.assertIn((0x4c, 0x40), writes)
        self.assertIn((0x6c, 0x0a), writes)

    def test_law_remaps_carrier_tl_and_corrects_decay(self):
        summary, out = self.convert(vgm(LAW_PHRASE), opna_law=True)
        self.assertTrue(summary['opna_law'])
        writes = self.opna_writes(out)
        # Carrier TLs follow the measured effective-level map:
        # 64 -> 45, 96 -> 47, on both channels' carrier slots.
        self.assertIn((0x4c, 45), writes)
        self.assertIn((0x40, 47), writes)
        self.assertIn((0x4d, 45), writes)
        self.assertNotIn((0x4c, 0x40), writes)
        # The ch2 OP1 is a modulator under ALG0: TL passes through.
        self.assertIn((0x41, 0x40), writes)
        # Decay rates of the KS 0 slot: DR 10 -> 9, SR 5 -> 4.
        self.assertIn((0x6c, 9), writes)
        self.assertIn((0x7c, 4), writes)
        # The KS 2 slot keeps its decay rate.
        self.assertIn((0x68, 0x0a), writes)
        self.assertEqual(summary['layer']['law_tl_carrier_writes'], 3)
        self.assertEqual(summary['layer']['law_decay_rate_writes'], 2)

    def test_law_reevaluates_tl_when_algorithm_context_changes(self):
        # OP2 TL 20 is a carrier under ALG4 (mapped to 19). The
        # algorithm then changes to ALG3, where OP2 is a
        # modulator, without any TL rewrite: the law value must
        # be re-evaluated from the state and re-emitted as 20
        # before the next key-on.
        phrase = bytes((
            0x52, 0xb0, 0x04,
            0x52, 0x48, 0x14,
            0x52, 0xa4, 0x22, 0x52, 0xa0, 0x69,
            0x52, 0x28, 0xf0,
            0x61, 0x00, 0x10,
            0x52, 0x28, 0x00,
            0x52, 0xb0, 0x03,
            0x52, 0x28, 0xf0,
            0x61, 0x00, 0x10,
            0x52, 0x28, 0x00,
        ))
        summary, out = self.convert(vgm(phrase), opna_law=True)
        writes = self.opna_writes(out)
        tl_writes = [data for reg, data in writes if reg == 0x48]
        self.assertEqual(tl_writes, [19, 20])
        summary, out = self.convert(vgm(phrase))
        writes = self.opna_writes(out)
        tl_writes = [data for reg, data in writes if reg == 0x48]
        self.assertEqual(tl_writes, [20])

    def test_law_reeval_uses_channel_port_on_shared_events(self):
        # A port-0 F-number latch fans out to segments of every
        # channel. Re-evaluating ch4 (port 1) from such a segment
        # must still address port 1: its mapped TL belongs to the
        # 0x57 stream only, never to ch1's 0x48 on port 0.
        phrase = bytes((
            0x53, 0xb0, 0x04,   # ch4 algorithm 4
            0x53, 0x48, 0x1e,   # ch4 OP2 TL 30 (carrier -> 28)
            0x52, 0xb0, 0x04,   # ch1 algorithm 4
            0x52, 0x48, 0x14,   # ch1 OP2 TL 20 (carrier -> 19)
            0x52, 0xb0, 0x03,   # ch1 algorithm 3: OP2 modulator
            0x52, 0xa4, 0x22,   # ch1 F-number latch (shared event)
            0x52, 0xa0, 0x69,
            0x52, 0x28, 0xf0,
            0x61, 0x00, 0x10,
            0x52, 0x28, 0x00,
        ))
        summary, out = self.convert(vgm(phrase), opna_law=True)
        raw = (out / 'authored.target.vgm').read_bytes()
        by_command = {0x56: [], 0x57: []}
        for e in command_times(raw):
            if e.command in by_command:
                by_command[e.command].append(
                    (raw[e.address + 1], raw[e.address + 2]))
        port0_tl = [d for r, d in by_command[0x56] if r == 0x48]
        port1_tl = [d for r, d in by_command[0x57] if r == 0x48]
        self.assertEqual(port0_tl, [19, 20])
        self.assertEqual(port1_tl, [28])

    def test_pitch_pair_is_atomic_under_shared_latch(self):
        # The F-number high byte feeds a latch shared by all
        # channels and the low write commits whatever it holds
        # (ymfm's register model). ch1 takes an octave step with
        # the SAME low byte after ch2's pitch write overwrote the
        # latch: the projected pair must be re-emitted in full -
        # high byte first, then the committing low byte - or the
        # target commit would carry ch2's block.
        phrase = bytes((
            0x52, 0xa4, 0x13, 0x52, 0xa0, 0x64,   # ch1 fnum 868 block 2
            0x52, 0xa5, 0x29, 0x52, 0xa1, 0x0a,   # ch2 fnum 266 block 5
            0x52, 0xa4, 0x1b, 0x52, 0xa0, 0x64,   # ch1 fnum 868 block 3
            0x52, 0x28, 0xf0,
            0x61, 0x00, 0x10,
            0x52, 0x28, 0x00,
        ))
        summary, out = self.convert(vgm(phrase))
        writes = self.opna_writes(out)
        ch1_pair = [(r, d) for r, d in writes if r in (0xa4, 0xa0)]
        self.assertEqual(ch1_pair, [(0xa4, 0x13), (0xa0, 64),
                                    (0xa4, 0x1b), (0xa0, 64)])
        ch2_pair = [(r, d) for r, d in writes if r in (0xa5, 0xa1)]
        self.assertEqual(ch2_pair, [(0xa5, 0x28), (0xa1, 255)])


if __name__ == '__main__':
    unittest.main()
