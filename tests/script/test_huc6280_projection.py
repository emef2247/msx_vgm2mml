"""Authored source/target boundaries and actual MGSDRV bridge checks."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(Path(__file__).parent)]
from test_huc6280 import make_vgm, wave, wait, write
from huc6280 import analyze
from huc6280_projection import project, prepare, ProjectionError
from vgm_io import read_vgm_header
from vgm_loop import read_loop_metadata
from vgm_timing import command_times

SQUARE = (31,) * 16 + (1,) * 16


class ProjectionTests(unittest.TestCase):
    def test_six_compatible_voices_share_scc_and_spill_to_psg(self):
        raw = make_vgm(write(1, 255) + b''.join(wave(ch, SQUARE, period=428)
                       for ch in range(6)) + wait(735))
        projection = project(raw)
        self.assertEqual(projection.summary['scc_channels'], 5)
        self.assertEqual(projection.summary['psg_channels'], 1)
        header = read_vgm_header(projection.vgm)
        self.assertEqual(header['huc6280_clock_raw'], 0)
        self.assertEqual(header['scc_clock_raw'], 1789773)
        controls = [row for row in projection.controls if row['enabled']]
        self.assertEqual({row['target_period'] for row in controls if row['target_chip'] == 'scc'}, {427})
        self.assertEqual({row['target_period'] for row in controls if row['target_chip'] == 'psg'}, {428})
        self.assertTrue(all(abs(row['pitch_error_cents']) < .001 for row in controls))
        self.assertEqual(list(command_times(projection.vgm))[-1].vgmticks, 735)
        uploaded = [row for row in projection.writes if row['command_hex'].startswith('d200')]
        self.assertEqual(len(uploaded), 128)  # Four memories, not five.

    def test_four_distinct_waves_and_two_squares_fit_without_corrupting_shared_ram(self):
        complex_waves = [tuple((n * factor) % 32 for n in range(32)) for factor in (1, 3, 5, 7)]
        raw = make_vgm(write(1, 255) + b''.join(wave(ch, values) for ch, values in
                       enumerate(complex_waves + [SQUARE, tuple(reversed(SQUARE))])) + wait(735))
        projection = project(raw)
        self.assertEqual(projection.summary['scc_channels'], 4)
        self.assertEqual(projection.summary['psg_channels'], 2)
        self.assertEqual({ch for ch, (chip, _) in projection.allocation.items() if chip == 'psg'}, {4, 5})

    def test_six_complex_waves_are_not_silently_omitted(self):
        raw = make_vgm(write(1, 255) + b''.join(wave(ch, tuple((n * (2 * ch + 1)) % 32
                       for n in range(32))) for ch in range(6)) + wait(735))
        projection = project(raw)
        self.assertEqual(projection.summary['scc_channels'], 4)
        self.assertEqual(projection.summary['opll_channels'], 2)
        self.assertTrue(projection.summary['waveform_fits'])

    def test_no_future_wave_preload_and_blocked_native_dumps_survive(self):
        raw = make_vgm(write(1, 255) + write(5, 255) + write(4, 159) + wait(10) +
                       wave(values=SQUARE) + wait(735))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.vgm'
            source.write_bytes(raw)
            with self.assertRaisesRegex(ProjectionError, 'not fully observed'):
                prepare(source, root, 'source')
            self.assertTrue((root / 'source.huc6280.segments.csv').is_file())
            self.assertEqual(json.loads((root / 'source.huc6280.projection.json').read_text())['status'], 'blocked')
            self.assertFalse((root / '_huc6280_target/source.vgm').exists())
            self.assertEqual(source.read_bytes(), raw)

    def test_gate_edges_and_internal_controls_are_distinct(self):
        raw = make_vgm(write(1, 255) + wave(values=SQUARE) + wait(100) +
                       write(4, 145) + wait(100) + write(4, 0) + write(4, 159) + wait(100))
        projection = project(raw)
        self.assertEqual([(r['start_vgmticks'], r['end_vgmticks']) for r in projection.gates],
                         [(0, 200), (200, 300)])
        self.assertTrue(any(r['vgmticks'] == 100 for r in projection.controls))
        zero_edges = [row for row in projection.writes if row['vgmticks'] == 200
                      and row['command_hex'].startswith('d203')]
        self.assertEqual([row['command_hex'] for row in zero_edges], ['d2030000', 'd2030001'])

    def test_volume_updates_do_not_rewrite_frequency_or_reload_shared_ram(self):
        raw = make_vgm(write(1, 255) + wave(values=SQUARE) + wait(100) +
                       write(4, 145) + wait(100))
        projection = project(raw)
        at_volume = [row['command_hex'] for row in projection.writes if row['vgmticks'] == 100]
        self.assertTrue(at_volume)
        self.assertFalse(any(command.startswith(('d200', 'd201')) for command in at_volume))

    def test_repeated_loop_restores_pitch_and_gain_without_resetting_held_voice(self):
        intro = (write(1, 255) + wave(0, SQUARE, period=428) + wave(1, SQUARE, period=600) +
                 write(0, 0) + wait(100))
        body = write(2, 428 & 255) + write(4, 159) + wait(100) + write(2, 500 & 255) + write(4, 145) + wait(100)
        raw = bytearray(make_vgm(intro + body))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        projection = project(raw)
        restored = [r['command_hex'] for r in projection.writes if r['vgmticks'] == 100]
        self.assertIn('d20100ab', restored)  # low byte of SCC427 restored every loop.
        self.assertIn('d202000f', restored)  # full volume restored every loop.
        self.assertFalse(any(c.startswith(('d20102', 'd20103', 'd20201')) for c in restored))
        commands = list(command_times(projection.vgm))
        loop = read_loop_metadata(projection.vgm)
        regs, levels, periods = [0] * 10, [0] * 5, []
        # Inspect actual target commands across two iterations.
        loop_commands = [c for c in commands if c.address >= loop['loop_address']]
        for c in commands + loop_commands:
            b = projection.vgm[c.address:c.address + 4]
            if b[0] == 0xd2 and b[1] == 1:
                regs[b[2]] = b[3]
            if b[0] == 0xd2 and b[1] == 2:
                levels[b[2]] = b[3]
            if c.wait_samples and c.address >= loop['loop_address']:
                periods.append((regs[0] + 256 * regs[1], levels[0], regs[2] + 256 * regs[3]))
        self.assertEqual(periods, [(427, 15, 599), (499, 1, 599)] * 2)

    def test_nonperiodic_loop_wave_pointer_is_not_guessed(self):
        intro = write(1, 255) + wave(values=SQUARE) + wait(100)
        raw = bytearray(make_vgm(intro + write(2, 428 & 255) + wait(100) + write(3, 2) + wait(100)))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        with self.assertRaisesRegex(ProjectionError, 'second traversal'):
            project(raw)

    def test_loop_activation_restores_pitch_changed_while_muted(self):
        intro = write(1, 255) + wave(values=SQUARE, period=428) + wait(100)
        body = (write(4, 159) + wait(100) + write(2, 500 & 255) + wait(100) +
                write(4, 0) + write(2, 428 & 255))
        raw = bytearray(make_vgm(intro + body))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        projection = project(raw)
        at_entry = [r['command_hex'] for r in projection.writes if r['vgmticks'] == 100]
        self.assertIn('d20100ab', at_entry)
        # project() also independently checks audible target register states
        # on two traversals, including latent pitch after muted source writes.
        self.assertEqual(read_loop_metadata(projection.vgm)['status'], 'valid')

    def test_loop_wave_upload_retains_native_pointer_dependency(self):
        # A disabled upload without a DDA falling-edge reset inherits the
        # playback index from EOF. A first-traversal wave is not enough proof.
        intro = write(1, 255) + write(5, 255)
        body = (write(4, 0) + b''.join(write(6, n) for n in range(32)) +
                write(2, 255) + write(3, 0) + write(4, 159) + wait(100))
        raw = bytearray(make_vgm(intro + body))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        with self.assertRaisesRegex(ProjectionError, 'loop waveform write'):
            project(raw)

    def test_phase_dependent_wave_can_change_only_on_third_loop(self):
        values = tuple(31 if n == 12 else 0 for n in range(32))
        intro = write(1, 255) + wave(values=values, period=428)
        body = write(6, 0) + wait(32)
        repeated = analyze(make_vgm(intro + body * 3))
        observed = [segment.waveform for segment in repeated.segments if segment.channel == 0 and segment.active]
        self.assertEqual(observed[0], observed[1])
        self.assertNotEqual(observed[1], observed[2])
        raw = bytearray(make_vgm(intro + body))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        with self.assertRaisesRegex(ProjectionError, 'loop waveform write'):
            project(raw)

    def test_disabled_loop_upload_with_explicit_reset_is_supported(self):
        intro = write(1, 255)
        raw = bytearray(make_vgm(intro + wave(values=SQUARE) + wait(100)))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        self.assertEqual(project(raw).summary['scc_channels'], 1)

    def test_dda_lfo_and_mixed_remain_explicit(self):
        cases = [write(1, 255) + wave(values=SQUARE) + write(4, 223) + wait(10),
                 write(1, 255) + wave(values=SQUARE) + write(9, 1) + wait(10),
                 write(1, 255) + wave(values=SQUARE) + b'\xa0\x08\x0f' + wait(10)]
        for commands in cases:
            with self.subTest(commands=hashlib.sha256(commands).hexdigest()[:8]):
                with self.assertRaises(ProjectionError):
                    project(make_vgm(commands))

    def test_loop_duration_gd3_and_safe_owned_replacement(self):
        intro = write(1, 255) + wave(values=SQUARE) + wait(100)
        raw = bytearray(make_vgm(intro + write(4, 140) + wait(200)))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        gd3 = b'Gd3 ' + struct.pack('<II', 0x100, 4) + b'X\0\0\0'
        struct.pack_into('<I', raw, 0x14, len(raw) - 0x14)
        raw.extend(gd3)
        struct.pack_into('<I', raw, 4, len(raw) - 4)
        projected = project(bytes(raw))
        loop = read_loop_metadata(projected.vgm)
        self.assertEqual((loop['status'], loop['loop_start_samples'], loop['decoded_loop_samples']),
                         ('valid', 100, 200))
        self.assertTrue(projected.vgm.endswith(gd3))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'song.vgm'
            source.write_bytes(raw)
            path, _ = prepare(source, root, 'song')
            original = path.read_bytes()
            self.assertEqual(prepare(source, root, 'song')[0].read_bytes(), original)
            path.write_bytes(b'user owned edit')
            with self.assertRaisesRegex(ProjectionError, 'unowned'):
                prepare(source, root, 'song')
            self.assertEqual(path.read_bytes(), b'user owned edit')


class ActualBridgeTests(unittest.TestCase):
    def test_six_voice_source_compiles_and_plays_on_real_target(self):
        if not shutil.which('mgsc') or not shutil.which('node'):
            self.skipTest('MGSC and Node required for real playback')
        check = subprocess.run(['node', str(ROOT / 'scripts/mgs_to_vgm.mjs'), '--check'], capture_output=True)
        if check.returncode:
            self.skipTest('libkss-js required for real playback')
        raw = bytearray(make_vgm(write(1, 255) + b''.join(wave(ch, SQUARE, period=428 + ch * 20)
                       for ch in range(6)) + wait(44100) + b''.join(write(0, ch) + write(4, 0)
                       for ch in range(6)) + wait(735)))
        struct.pack_into('<I', raw, 0x18, 44835)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'authored.vgm'
            source.write_bytes(raw)
            out = root / 'export'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/export_mgs.py'),
                                     str(source), '--outdir', str(out)], capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode(errors='replace'))
            diag = out / '_diagnostics/authored'
            report = json.loads((diag / 'report.json').read_text())
            self.assertEqual(report['result']['keyon_status'], 'projected_source')
            self.assertTrue((out / 'tracks/authored.mgs').stat().st_size)
            actual = (diag / 'authored.roundtrip.vgm').read_bytes()
            header = read_vgm_header(actual)
            self.assertEqual(header['ay_clock_raw'] & 0x3fffffff, 1789773)
            self.assertEqual(header['scc_clock_raw'] & 0x3fffffff, 1789773)
            periods, levels, enabled, ay, heard = [0] * 10, [0] * 5, 0, [0] * 16, set()
            for event in command_times(actual):
                b = actual[event.address:event.address + 4]
                if b[0] == 0xd2:
                    if b[1] == 1:
                        periods[b[2]] = b[3]
                    elif b[1] == 2:
                        levels[b[2]] = b[3]
                    elif b[1] == 3:
                        enabled = b[3]
                elif b[0] == 0xa0:
                    ay[b[1]] = b[2]
                if event.wait_samples:
                    for dest in range(5):
                        if enabled & (1 << dest) and levels[dest]:
                            heard.add(('scc', dest, periods[2 * dest] + 256 * periods[2 * dest + 1]))
                    for dest in range(3):
                        if not ay[7] & (1 << dest) and ay[8 + dest]:
                            heard.add(('psg', dest, ay[2 * dest] + 256 * ay[2 * dest + 1]))
            expected = {(row['target_chip'], row['target_channel'], row['target_period'])
                        for row in project(bytes(raw)).controls if row['enabled']}
            self.assertTrue(expected <= heard, (expected, heard))
            stats = root / 'audio.json'
            played = subprocess.run(['node', str(ROOT / 'scripts/probe_mgs_audio.mjs'),
                                     str(out / 'tracks/authored.mgs'), str(stats), '1500'],
                                    capture_output=True, timeout=45)
            self.assertEqual(played.returncode, 0, played.stderr)
            self.assertGreater(json.loads(stats.read_text())['nonzero_samples'], 0)


if __name__ == '__main__':
    unittest.main()
