"""Authored resource conflicts and evidence for extended HuC lowering."""
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts'), str(Path(__file__).parent)]
from test_huc6280 import make_vgm, wave, wait, write
from huc6280_projection import project, ProjectionError
from huc6280_extended import noise_pitch, fit_preset
from musical_vgm_reference import render_vgm
from batch_vgm_to_mgs import discover_inputs
from vgm_timing import command_times


def noise(channel, rate):
    return write(0, channel) + write(5, 255) + write(7, 128 | rate) + write(4, 159)


class ExtendedTests(unittest.TestCase):
    def test_noise_rate_uses_pinned_shift_clock_and_reports_error(self):
        period, source, target = noise_pitch(3579545, 31)
        self.assertEqual(source, 3579545 / 64)
        self.assertEqual(period, 2)
        projection = project(make_vgm(write(1, 255) + noise(5, 31) + wait(735)))
        self.assertEqual(projection.summary['psg_channels'], 1)
        self.assertTrue(any(c['source_mode'] == 'noise' and c['source_hz'] == source
                            and c['target_hz'] == target for c in projection.controls))

    def test_shared_noise_conflict_prefers_first_audible_channel(self):
        base = write(1, 255) + noise(4, 0) + noise(5, 31)
        projection = project(make_vgm(base + wait(735)))
        # Both channels sound; the shared generator carries the first
        # channel's period, and the conflict window is recorded.
        writes = [w['command_hex'] for w in projection.writes if w['vgmticks'] == 0]
        self.assertEqual([w for w in writes if w.startswith('a006')][-1],
                         bytes((0xa0, 6, noise_pitch(3579545, 0)[0])).hex())
        self.assertEqual({c['source_channel'] for c in projection.controls
                          if c['source_mode'] == 'noise'}, {4, 5})
        conflicts = projection.summary['noise_rate_conflicts']
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['owner_channel'], 4)
        self.assertEqual(conflicts[0]['chosen_period'], noise_pitch(3579545, 0)[0])
        self.assertEqual(conflicts[0]['end_vgmticks'], 735)
        # Both rates settle before the next sample. No audible conflict.
        settled = project(make_vgm(base + write(7, 128) + wait(735)))
        self.assertTrue(settled.vgm)
        self.assertEqual(settled.summary['noise_rate_conflicts'], [])

    def test_shared_noise_rate_follows_surviving_channel(self):
        raw = make_vgm(write(1, 255) + noise(4, 0) + noise(5, 31) + wait(735) +
            write(0, 4) + write(4, 0) + wait(735))
        projection = project(raw)
        writes = [w['command_hex'] for w in projection.writes if w['vgmticks'] == 735]
        self.assertEqual([w for w in writes if w.startswith('a006')][-1],
                         bytes((0xa0, 6, noise_pitch(3579545, 31)[0])).hex())
        conflicts = projection.summary['noise_rate_conflicts']
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['end_vgmticks'], 735)

    def test_disabled_dynamic_wave_is_not_preloaded_from_the_future(self):
        first = tuple(range(32));second = tuple(reversed(first))
        projection = project(make_vgm(write(1, 255) + wave(0, first) + wait(735) +
            write(4, 0) + wave(0, second) + wait(735)))
        uploads = [w for w in projection.writes if w['command_hex'].startswith('d200')]
        self.assertEqual(len(uploads), 64)
        self.assertEqual([w['vgmticks'] for w in uploads], [0] * 32 + [735] * 32)

    def test_transient_noise_owner_does_not_leave_its_rate_on_a_held_owner(self):
        raw = make_vgm(write(1, 255) + noise(4, 0) + noise(5, 0) + wait(735) +
            write(4, 0) + wait(735) + noise(5, 31) + write(4, 0) + wait(735))
        projection = project(raw)
        writes = [w['command_hex'] for w in projection.writes if w['vgmticks'] == 1470]
        self.assertEqual([w for w in writes if w.startswith('a006')][-1],
                         bytes((0xa0, 6, noise_pitch(3579545, 0)[0])).hex())
        self.assertGreater(projection.summary['shared_resource_restorations'], 0)

    def test_transient_shared_wave_owner_does_not_corrupt_a_held_owner(self):
        # Five waveform routes with disjoint A/B intervals permit shared RAM.
        # Briefly enable B's different complete RAM at the same timestamp.
        a = tuple(range(32));b = tuple(reversed(a))
        intro = write(1, 255) + b''.join(wave(ch, tuple((i * (2 * ch + 3)) % 32
            for i in range(32))) for ch in range(3)) + wave(3, a) + wave(4, a) + wait(735)
        body = write(4, 0) + wave(4, b) + write(4, 0) + wait(735) + write(0, 3) + write(4, 0) + write(0, 4) + write(4, 159) + wait(735)
        projection = project(make_vgm(intro + body))
        self.assertEqual(projection.summary['scc_channels'], 5)
        self.assertGreater(projection.summary['shared_resource_restorations'], 0)
        memory = {}
        for row in projection.writes:
            if row['vgmticks'] > 735:break
            command = bytes.fromhex(row['command_hex'])
            if command[:2] == b'\xd2\x00':memory[command[2]] = command[3]
        self.assertEqual([memory[96 + i] for i in range(32)], [((x - 16) * 8) & 255 for x in a])

    def test_switch_silences_old_route_before_activating_new_route(self):
        projection = project(make_vgm(write(1, 255) + wave(5) + wait(735) +
            write(7, 159) + wait(735) + write(7, 0) + wait(735)))
        rows = [w['command_hex'] for w in projection.writes if w['vgmticks'] == 735]
        scc_off = rows.index('d2020000')
        noise_on = next(i for i, w in enumerate(rows) if w.startswith('a008') and w != 'a00800')
        self.assertLess(scc_off, noise_on)
        self.assertEqual({(a['source_channel'], a['source_mode']) for a in projection.summary['allocation']},
                         {(5, 'wave'), (5, 'noise')})

    def test_six_complex_waveforms_get_real_opll_registers_and_sound(self):
        raw = make_vgm(write(1, 255) + b''.join(wave(ch,
            tuple((i * (2 * ch + 1)) % 32 for i in range(32)), period=255)
            for ch in range(6)) + wait(44100))
        projection = project(raw)
        rows = [c for c in projection.controls if c['target_chip'] == 'opll' and c['enabled']]
        self.assertEqual({r['target_channel'] for r in rows}, {0, 1})
        self.assertTrue(all(1 <= r['opll_preset'] <= 15 and abs(r['pitch_error_cents']) < 4 for r in rows))
        if not (ROOT / '.tools/musical-vgm-reference/opll.so').exists():
            self.skipTest('Optional pinned reference core not built')
        rendered = render_vgm(projection.vgm)
        self.assertGreater(max(map(abs, rendered['chips']['opll']['left'])), 0)
        self.assertGreater(max(map(abs, rendered['chips']['scc']['left'])), 0)

    def test_wave_changes_remain_periodic_at_the_loop_seam(self):
        a, b = tuple(range(32)), tuple(reversed(range(32)))
        intro = write(1, 255)
        body = wave(0, a) + wait(735) + write(4, 0) + wave(0, b) + wait(735) + write(4, 0)
        raw = bytearray(make_vgm(intro + body))
        struct.pack_into('<I', raw, 0x1c, 256 + len(intro) - 0x1c)
        projection = project(bytes(raw))
        self.assertEqual(projection.summary['loop_validation'], 'source and target repeated traversal')

    def test_opll_key_off_preserves_the_pitch_of_the_release_tail(self):
        intro = write(1, 255) + b''.join(wave(ch,
            tuple((i * (2 * ch + 1)) % 32 for i in range(32)), period=170)
            for ch in range(6)) + wait(735)
        projection = project(make_vgm(intro + write(0, 4) + write(4, 0) + wait(735) +
            write(5, 0) + wait(735)))
        dest = next(a['target_channel'] for a in projection.summary['allocation']
                    if a['source_channel'] == 4 and a['target_chip'] == 'opll')
        values = [bytes.fromhex(w['command_hex'])[2] for w in projection.writes
                  if bytes.fromhex(w['command_hex'])[:2] == bytes((0x51, 0x20 + dest))]
        on = next(v for v in reversed(values) if v & 16)
        self.assertEqual(values[-1], on & ~16)

    def test_enabled_muted_ram_changes_are_not_a_disabled_upload(self):
        raw = make_vgm(write(1, 255) + wave() + wait(735) + write(4, 128) +
            write(6, 31) + write(4, 159) + wait(735))
        with self.assertRaisesRegex(ProjectionError, 'enabled waveform'):
            project(raw)

    def test_extensionless_vgm_is_discovered_without_renaming(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root / 'track01vgm'
            source.write_bytes(make_vgm(write(1, 255) + wave() + wait(735)))
            (root / 'not_music.txt').write_text('ordinary text')
            self.assertEqual(discover_inputs(source), [source])
            self.assertEqual(discover_inputs(root), [source])
            self.assertEqual(discover_inputs(root, adjacent=True), [source])

    @unittest.skipUnless(shutil.which('mgsc') and shutil.which('node'), 'MGSC and Node required')
    def test_real_mgs_playback_contains_opll_presets_and_psg_noise(self):
        check = subprocess.run(['node', str(ROOT / 'scripts/mgs_to_vgm.mjs'), '--check'], capture_output=True)
        if check.returncode:self.skipTest('Optional libkss-js unavailable')
        intro = write(1, 255) + b''.join(wave(ch,
            tuple((i * (2 * ch + 1)) % 32 for i in range(32)), period=428 + ch * 20)
            for ch in range(6)) + wait(22050)
        ending = write(0, 5) + write(7, 159) + wait(22050) + b''.join(
            write(0, ch) + write(4, 0) for ch in range(6)) + wait(735)
        raw = bytearray(make_vgm(intro + ending))
        struct.pack_into('<I', raw, 0x18, 44835)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root / 'authored.vgm';source.write_bytes(raw)
            out = root / 'out'
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/export_mgs.py'), str(source),
                '--outdir', str(out)], capture_output=True, timeout=120)
            self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr).decode(errors='replace'))
            report = json.loads((out / '_diagnostics/authored/authored.conversion.json').read_text())
            for loss in report['backend_losses']:
                self.assertTrue(loss['retained_in_projected_execution'])
                self.assertFalse(loss['retained_in_direct_vgm'])
            actual = (out / '_diagnostics/authored/authored.roundtrip.vgm').read_bytes()
            ay, fm, instruments, noise_heard = [0] * 16, [0] * 64, set(), False
            for event in command_times(actual):
                b = actual[event.address:event.address + 4]
                if b[0] == 0xa0:ay[b[1]] = b[2]
                elif b[0] == 0x51:fm[b[1]] = b[2]
                if event.wait_samples:
                    instruments.update(fm[0x30 + ch] >> 4 for ch in range(9) if fm[0x20 + ch] & 16)
                    noise_heard |= any(ay[8 + ch] and not ay[7] & (1 << (ch + 3)) for ch in range(3))
            self.assertTrue(instruments and all(1 <= n <= 15 for n in instruments))
            self.assertTrue(noise_heard)


if __name__ == '__main__':unittest.main()
