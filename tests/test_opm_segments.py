"""Native OPM state tests, independent of target MML and normalization."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opm import build_segments, dump_analysis, key_counts
from vgm_reader import parse_vgm
from test_opm_reader import vgm, read_rows


def write(register, data, instance=0):
    return bytes([0x54 if instance == 0 else 0xa4, register, data])


def analyze(folder, commands, clock=4000000, end_override=None):
    source = Path(folder) / 'case.vgm'
    source.write_bytes(vgm(commands, clock))
    metadata = {}
    parse_vgm(str(source), folder, opm_metadata=metadata)
    return build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks']
                          if end_override is None else end_override)


class OpmSegmentTests(unittest.TestCase):
    def test_partial_keys_operator_order_and_continuity(self):
        commands = (write(0x08, 0x08 | 3) + b'\x70' + write(0x08, 0x10 | 3)
                    + write(0x08, 0x10 | 3) + write(0x08, 0x20 | 3)
                    + write(0x08, 0x40 | 3) + write(0x08, 3) + b'\x62')
        with tempfile.TemporaryDirectory() as folder:
            result = analyze(folder, commands)
            events = result.events
            self.assertEqual([e.ch for e in events], [3] * 6)
            self.assertEqual([e.rising_mask for e in events], [1, 2, 0, 4, 8, 0])
            self.assertEqual([e.falling_mask for e in events], [0, 1, 0, 2, 4, 8])
            self.assertEqual([e.continuity_id for e in events], [1, 2, 2, 3, 4, 4])
            self.assertFalse(events[2].changed)
            self.assertEqual(key_counts(result), {'key_writes': 6, 'channel_attack_events': 4,
                                                 'operator_keyons': 4, 'operator_keyoffs': 4})
            segment_csv = Path(folder) / 'segments.csv'
            dump_analysis(result, state_csv=Path(folder) / 'state.csv', segments_csv=segment_csv)
            rows = read_rows(segment_csv)
            attacks = [r for r in rows if int(r['rising_mask'])]
            self.assertEqual([(r['m1_key_on_edge'], r['m2_key_on_edge'], r['c1_key_on_edge'], r['c2_key_on_edge'])
                              for r in attacks], [('1', '0', '0', '0'), ('0', '0', '1', '0'),
                                                  ('0', '1', '0', '0'), ('0', '0', '0', '1')])

    def test_held_note_pitch_patch_tl_and_pan_do_not_attack(self):
        commands = (write(0x20, 0xc5) + write(0x28, 0x4a) + write(0x30, 0xff)
                    + write(8, 0x78) + b'\x62' + write(0x28, 0x4e) + write(0x20, 0x52)
                    + write(0x40, 0x7f) + write(0x48, 0x12) + write(0x50, 0x23)
                    + write(0x58, 0x34) + write(0x60, 0x85) + write(0x80, 0xff)
                    + write(0xa0, 0xff) + write(0xc0, 0xff) + write(0xe0, 0xab)
                    + write(0x38, 0x73) + b'\x63')
        with tempfile.TemporaryDirectory() as folder:
            result = analyze(folder, commands)
            last = result.events[-1]
            self.assertEqual((last.state.octave, last.state.note, last.state.kf), (5, 'c', 63))
            self.assertEqual((last.state.kc_raw, last.state.kf_raw), (0x4e, 0xff))
            self.assertEqual((last.state.algorithm, last.state.feedback, last.state.left_enabled,
                              last.state.right_enabled), (2, 2, 1, 0))
            self.assertEqual((last.state.pms, last.state.ams), (7, 3))
            m1, m2, c1, c2 = last.state.operators
            self.assertEqual((m1.dt1, m1.mul, m1.tl, m1.ks, m1.ar, m1.am_enabled,
                              m1.d1r, m1.dt2, m1.d2r, m1.d1l, m1.rr),
                             (7, 15, 5, 3, 31, 1, 31, 3, 31, 10, 11))
            self.assertEqual([op.mul for op in (m1, m2, c1, c2)], [15, 2, 3, 4])
            self.assertIsNone(m2.tl)
            self.assertEqual(key_counts(result)['channel_attack_events'], 1)
            self.assertTrue(all(e.continuity_id == 1 and e.rising_mask == 0 for e in result.events[4:]))
            self.assertEqual(result.source_end_vgmticks, 735 + 882)

    def test_zero_time_key_pulse_release_tail_and_channel_isolation(self):
        commands = (write(8, 0x78) + b'\x62' + write(8, 0) + write(8, 0x78)
                    + write(8, 0x79) + b'\x70' + write(8, 1) + b'\x63')
        with tempfile.TemporaryDirectory() as folder:
            result = analyze(folder, commands)
            zero_off = [s for s in result.segments if s.ch == 0 and s.ev_type == 'key_off']
            self.assertEqual(len(zero_off), 1)
            self.assertEqual((zero_off[0].vgmticks, zero_off[0].vgmticks_end), (735, 735))
            ch1 = [s for s in result.segments if s.ch == 1]
            self.assertEqual(ch1[-1].state.key_mask, 0)
            self.assertEqual(ch1[-1].duration_samples, 882)  # Gate-off interval, not silent rest.
            self.assertEqual(key_counts(result)['channel_attack_events'], 3)
            for ch in range(8):
                channel = [s for s in result.segments if s.ch == ch]
                self.assertEqual(channel[0].vgmticks, 0)
                self.assertEqual(channel[-1].vgmticks_end, 1618)
                self.assertEqual(sum(s.duration_samples for s in channel), 1618)
                self.assertTrue(all(a.vgmticks_end == b.vgmticks for a, b in zip(channel, channel[1:])))

    def test_shared_depth_lfo_noise_csm_and_independent_instances(self):
        commands = (write(0x19, 12) + write(0x19, 0x91) + write(1, 2)
                    + write(0x0f, 0x9f) + write(0x10, 0x12) + write(0x11, 0xff)
                    + write(0x12, 0x34) + write(0x14, 0x85) + write(0x1b, 0xc3)
                    + write(0x18, 0xab) + write(0x19, 0x87, 1) + b'\x62')
        with tempfile.TemporaryDirectory() as folder:
            result = analyze(folder, commands, 0x40000000 | 4000000)
            state = [e.state for e in result.events if e.chip_instance == 0 and e.ch == 7][-1]
            self.assertEqual((state.amd, state.pmd, state.lfo_reset, state.noise_enabled,
                              state.noise_rate, state.lfo_waveform, state.ct, state.lfo_rate_raw),
                             (12, 17, 1, 1, 31, 3, 3, 0xab))
            self.assertEqual((state.timer_a_high_raw, state.timer_a_low_raw, state.timer_b_raw,
                              state.timer_control_raw, state.csm_enabled), (0x12, 0xff, 0x34, 0x85, 1))
            self.assertTrue(result.csm_observed)
            self.assertEqual(key_counts(result)['operator_keyons'], 0)  # No invented CSM simulation.
            other = [e.state for e in result.events if e.chip_instance == 1 and e.ch == 7][-1]
            self.assertIsNone(other.amd)
            self.assertEqual(other.pmd, 7)
            self.assertIsNone(other.noise_raw)

    def test_unknown_initial_parameters_noncanonical_kc_and_reserved_write(self):
        with tempfile.TemporaryDirectory() as folder:
            result = analyze(folder, write(0x28, 0xf3) + write(0x1a, 0xef) + b'\x62')
            self.assertIsNone(result.events[0].state.note)
            self.assertEqual(result.events[0].state.kc_raw, 0xf3)
            self.assertIsNone(result.events[0].state.kf_raw)
            self.assertEqual(result.events[-1].ev_type, 'uninterpreted')
            self.assertIn((0x1a, 0xef), result.events[-1].state.shared_registers)
            self.assertIsNone(result.events[-1].state.pmd)  # 1A is not a PMD shadow write.

    def test_source_end_and_order_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'source order'):
                analyze(folder, b'\x62' + write(8, 0x78), end_override=10)
            path = Path(folder) / 'case_trace.opm_regs.csv'
            rows = read_rows(path)
            rows.append(dict(rows[0]))
            with open(path, 'w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, 'source order'):
                build_segments(path, end_vgmticks=1000)


if __name__ == '__main__':
    unittest.main()
