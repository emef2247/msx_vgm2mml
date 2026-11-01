"""NES APU projection to SCC/PSG target VGM; authored fixtures only."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'py'), str(Path(__file__).parent)]
import struct

from test_nesapu import make_vgm, pulse_note, wait, write
from nesapu_projection import (BALANCE_GAINS, ProjectionError, has_nesapu,
                               project)
from vgm_loop import read_loop_metadata
from vgm_timing import command_times


class NesApuBalanceGainTests(unittest.TestCase):
    def test_pulse_gain_scales_target_volume(self):
        raw = make_vgm(pulse_note(control=0x98) + wait(44100))  # volume 8
        plain = project(raw)
        gained = project(raw, gains=BALANCE_GAINS)
        plain_controls = [r for r in plain.controls
                          if r['source_channel'] == 0]
        gained_controls = [r for r in gained.controls
                           if r['source_channel'] == 0]
        self.assertEqual(plain_controls[0]['target_volume'], 8)
        self.assertEqual(gained_controls[0]['target_volume'], 10)  # 8 * 1.3
        self.assertEqual(plain.summary['mapping_gains'], {})
        self.assertEqual(gained.summary['mapping_gains']['pulse'], 1.3)

    def test_triangle_gain_lowers_target_volume(self):
        note = (write(21, 4) + write(8, 0xff) + write(10, 0x7e) +
                write(11, 0xf8))
        raw = make_vgm(note + wait(7350))
        gained = project(raw, gains=BALANCE_GAINS)
        volumes = [gained.vgm[c.address + 3]
                   for c in commands_by_type(gained.vgm)[0xd2]
                   if gained.vgm[c.address + 1] == 2
                   and gained.vgm[c.address + 2] == 2]
        self.assertEqual(volumes, [11])  # 15 * 0.75

    def test_noise_gain_scales_psg_volume(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1a) + write(14, 0x03) +
                       write(15, 1 << 3) + wait(22050))  # noise volume 10
        gained = project(raw, gains=BALANCE_GAINS)
        amplitudes = [gained.vgm[c.address + 2]
                      for c in commands_by_type(gained.vgm)[0xa0]
                      if gained.vgm[c.address + 1] == 10]
        self.assertIn(8, amplitudes)  # 10 * 0.8
        self.assertNotIn(10, amplitudes)


def commands_by_type(raw):
    result = {}
    for command in command_times(raw):
        result.setdefault(command.command, []).append(command)
    return result


class NesApuProjectionTests(unittest.TestCase):
    def test_pulse_becomes_scc_with_duty_waveform(self):
        projected = project(make_vgm(pulse_note() + wait(44100)))
        by_type = commands_by_type(projected.vgm)
        self.assertIn(0xd2, by_type)
        self.assertEqual(projected.allocation[0], ('scc', 0))
        self.assertEqual(projected.summary['clamped_pitches'], 0)
        controls = [row for row in projected.controls
                    if row['source_channel'] == 0]
        self.assertTrue(controls)
        self.assertAlmostEqual(controls[0]['pitch_error_cents'], 0, delta=6)
        self.assertEqual(controls[0]['waveform'], 'duty2')
        self.assertEqual(len(projected.gates), 1)

    def test_noise_becomes_psg_noise(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1a) + write(14, 0x03) +
                       write(15, 1 << 3) + wait(22050))
        projected = project(raw)
        by_type = commands_by_type(projected.vgm)
        registers = {projected.vgm[c.address + 1] for c in by_type[0xa0]}
        self.assertIn(6, registers)   # AY noise period
        self.assertIn(10, registers)  # AY channel C amplitude
        self.assertEqual(projected.summary['noise_route'], 'psg+scc')

    def test_noise_is_omitted_not_silent_when_ay_is_present(self):
        raw = make_vgm(write(21, 8) + write(12, 0x1f) + write(14, 0x03) +
                       write(15, 1 << 3) + wait(22050))
        raw = bytearray(raw)
        # Insert an AY write ahead of the end command.
        body = bytes((0xa0, 8, 15))
        raw[-1:-1] = body
        import struct
        struct.pack_into('<I', raw, 4, len(raw) - 4)
        projected = project(bytes(raw))
        self.assertEqual(projected.summary['noise_route'],
                         'scc_only_ay_present')
        self.assertEqual(projected.summary['noise_omitted_segments'], 1)
        self.assertEqual(projected.summary['noise_scc_segments'], 0)

    def test_dpcm_omission_is_recorded(self):
        raw = make_vgm(write(18, 0x10) + write(19, 0x08) + write(16, 0x0f) +
                       write(21, 16) + wait(4410))
        projected = project(raw)
        self.assertEqual(projected.summary['dpcm_events_omitted'], 1)

    def test_dpcm_external_diverts_slices_from_the_scc_lane(self):
        import struct as st
        block = (b'\x67\x66\xc2' + st.pack('<I', 2 + 129)
                 + st.pack('<H', 0xc000) + b'\xff' * 129)
        raw = make_vgm(block + write(18, 0x00) + write(19, 0x08)
                       + write(16, 0x0f) + write(21, 16) + wait(44100))
        projected = project(raw)
        self.assertGreater(projected.summary['dpcm_slices'], 0)
        self.assertEqual(projected.summary['dpcm_events_rendered'], 1)
        self.assertNotIn('dpcm_external_pcm', projected.summary)
        external = project(raw, dpcm_external=True)
        self.assertEqual(external.summary['dpcm_slices'], 0)
        self.assertEqual(external.summary['dpcm_events_rendered'], 0)
        self.assertEqual(external.summary['dpcm_events_omitted'], 1)
        self.assertEqual(external.summary['dpcm_external_pcm'],
                         dict(events=1,
                              slices_diverted=projected.summary[
                                  'dpcm_slices']))
        self.assertFalse(any(row['source_channel'] == 4
                             for row in external.summary['allocation']))

    def test_nes_ram_block_is_recorded_not_emitted(self):
        import struct as st
        block = (b'\x67\x66\xc2' + st.pack('<I', 2 + 4)
                 + st.pack('<H', 0xc000) + b'\xaa' * 4)
        projected = project(make_vgm(block + pulse_note()))
        self.assertEqual(len(projected.summary['data_blocks_omitted']), 1)
        entry = projected.summary['data_blocks_omitted'][0]
        self.assertEqual(entry['type'], '0xc2')
        self.assertEqual(entry['start_address'], 0xc000)
        self.assertEqual(entry['data_bytes'], 4)
        self.assertNotIn(b'\x67\x66\xc2', projected.vgm[256:])

    def test_foreign_data_block_blocks(self):
        import struct as st
        block = (b'\x67\x66\x80' + st.pack('<I', 2 + 4)
                 + st.pack('<H', 0) + b'\xaa' * 4)
        with self.assertRaises(ProjectionError):
            project(make_vgm(block + pulse_note()))

    def test_repeated_triangle_note_after_rest_reemits_volume(self):
        # The gate-close write sets SCC volume 0; a later note with the
        # same pitch and volume must still emit its volume write.
        note = (write(21, 4) + write(8, 0xff) + write(10, 0x7e) +
                write(11, 0xf8))
        raw = make_vgm(note + wait(7350) + write(21, 0) + wait(7350) +
                       note + wait(7350))
        projected = project(raw)
        volumes = [projected.vgm[c.address + 3]
                   for c in commands_by_type(projected.vgm)[0xd2]
                   if projected.vgm[c.address + 1] == 2
                   and projected.vgm[c.address + 2] == 2]
        self.assertEqual(volumes[-3:], [15, 0, 15])

    def test_repeated_pulse_note_after_rest_reemits_volume(self):
        raw = make_vgm(pulse_note() + wait(7350) + write(21, 0) +
                       wait(7350) + pulse_note() + wait(7350))
        projected = project(raw)
        volumes = [projected.vgm[c.address + 3]
                   for c in commands_by_type(projected.vgm)[0xd2]
                   if projected.vgm[c.address + 1] == 2
                   and projected.vgm[c.address + 2] == 0]
        self.assertEqual(volumes[-3:], [15, 0, 15])

    def test_loop_from_start_stays_at_start(self):
        import struct
        raw = bytearray(make_vgm(pulse_note() + wait(44100)))
        struct.pack_into('<I', raw, 0x1c, 256 - 0x1c)
        struct.pack_into('<I', raw, 0x20, 44100)
        projected = project(bytes(raw))
        from vgm_loop import read_loop_metadata
        loop = read_loop_metadata(projected.vgm)
        self.assertEqual(loop['loop_start_samples'], 0)
        self.assertEqual(loop['decoded_loop_samples'], 44100)

    def test_has_nesapu(self):
        self.assertTrue(has_nesapu(make_vgm(pulse_note() + wait(735))))
        self.assertFalse(has_nesapu(make_vgm(wait(735))))


def make_looped_vgm(intro, body, loop_samples):
    raw = bytearray(make_vgm(intro + body))
    struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
    struct.pack_into('<I', raw, 0x20, loop_samples)
    return bytes(raw)


class LoopValidationTests(unittest.TestCase):
    def test_changed_waveform_is_restored_at_loop_point(self):
        intro = pulse_note(control=0x3f) + wait(4410)  # duty 0
        body = write(0, 0xbf) + wait(4410)             # duty 2
        projected = project(make_looped_vgm(intro, body, 4410))
        self.assertGreater(projected.summary['loop_restored_registers'], 0)
        self.assertTrue(projected.summary['target_loop_periodic'])
        loop = read_loop_metadata(projected.vgm)
        at_point = [c for c in command_times(projected.vgm)
                    if c.address == loop['loop_address']
                    and c.command == 0xd2]
        self.assertTrue(at_point)
        # Waveform restoration uploads the whole waveform in
        # ascending register order (the SCC segment builder's
        # wavetable assembler requires block-aligned uploads).
        registers = [projected.vgm[c.address + 2] for c in
                     command_times(projected.vgm)
                     if c.address >= loop['loop_address']
                     and c.command == 0xd2
                     and projected.vgm[c.address + 1] == 0][:32]
        self.assertEqual(registers, list(range(32)))

    def test_periodic_loop_restores_nothing(self):
        # Envelope-decay notes (control 0x80: duty 2, fastest decay)
        # end inside both the intro and the body, so every register
        # returns to its loop-point value by the end.
        intro = pulse_note(control=0x80) + wait(4410)
        body = pulse_note(control=0x80) + wait(4410)
        projected = project(make_looped_vgm(intro, body, 4410))
        self.assertEqual(projected.summary['loop_restored_registers'], 0)
        self.assertTrue(projected.summary['target_loop_periodic'])
        self.assertEqual(
            projected.summary['loop_second_traversal_differences'], [])

    def test_envelope_history_difference_is_recorded(self):
        # The envelope starts in the intro and decays through the
        # loop body without retriggering: the second traversal
        # starts from a lower gain, which the summary must name.
        intro = pulse_note(control=0x0f, length_index=1) + wait(4410)
        body = wait(44100)
        projected = project(make_looped_vgm(intro, body, 44100))
        self.assertIn(0, projected.summary[
            'loop_second_traversal_differences'])


if __name__ == '__main__':
    unittest.main()
