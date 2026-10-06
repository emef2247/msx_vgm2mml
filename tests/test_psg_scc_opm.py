"""Independent additive target checks, without private fixture expectations."""
from dataclasses import replace
import math
import struct
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT)]
from scripts.psg_scc_to_mdx import source_facts
from chip_segments import PsgSegment, SccAnalysis, SccSegment
from psg_scc_opm import waveform_voice, square_voice, source_frequency, opm_pitch, project, verify_writes
from opm_mdx import projected_samples


def psg(**kwargs):
    row = PsgSegment('v', 0., 0, 0, 1, 200, 15, 4, 'c', 0, (),
                     1, 0, 0, 0, 0, 0x3e, 15, vgmticks=0, vgmticks_end=441)
    return replace(row, **kwargs)


class AdditiveTargetTests(unittest.TestCase):
    def test_sine_wave_selects_fundamental_and_preserves_amplitude(self):
        def wave(scale):
            return bytes(round(scale * math.sin(2 * math.pi * i / 32)) & 255 for i in range(32)).hex()
        full, half = waveform_voice(wave(120)), waveform_voice(wave(60))
        i = full.harmonics.index(1)
        self.assertAlmostEqual(full.amplitudes[i], 120 / 128, delta=.004)
        self.assertAlmostEqual(half.amplitudes[half.harmonics.index(1)] / full.amplitudes[i], .5, delta=.01)
        self.assertGreater(full.retained_ac_fraction, .999)
        self.assertAlmostEqual(waveform_voice('40' * 32).retained_ac_fraction, 0)

    def test_square_ratios_and_clock_pitch(self):
        voice = square_voice()
        self.assertEqual(voice.harmonics, (1, 3, 5, 7))
        self.assertAlmostEqual(voice.amplitudes[1] / voice.amplitudes[0], 1 / 3)
        self.assertEqual(source_frequency('psg', 1789772, 213), source_frequency('scc', 1789772, 212))
        self.assertEqual(opm_pitch(440, 3579545)[:2], (0x4a, 0))
        kc, kf, frequency = opm_pitch(440)
        self.assertNotEqual(kc, 0x4a)
        self.assertLess(abs(1200 * math.log2(frequency / 440)), 1)

    def test_held_changes_mute_and_unmute_do_not_retrigger(self):
        rows = [psg(), psg(vgmticks=441, vgmticks_end=882, volume=12, tone_period=190),
                psg(vgmticks=882, vgmticks_end=1323, volume=0),
                psg(vgmticks=1323, vgmticks_end=1764)]
        before = tuple(rows)
        plan = project({0: rows}, SccAnalysis({}, ()), psg_clock=1789772, scc_clock=0, end_vgmticks=1764)
        self.assertEqual(tuple(rows), before)
        keys = [w for w in plan.writes if w.register == 8 and w.data & 0x78]
        self.assertEqual(len(keys), 1)
        self.assertTrue(all(w.target_ch == 5 for w in plan.writes))
        self.assertEqual(len(plan.rows), 4)
        self.assertIn('F y37,7', plan.render('test'))
        self.assertEqual([r['target_audible'] for r in plan.rows], [True, True, False, True])
        actual = [(projected_samples(w.mdx_tick), w.register, w.data) for w in plan.scheduled_writes()]
        self.assertTrue(verify_writes(plan, actual, [], projected_samples(plan.end_tick))['passed'])
        actual[-1] = (actual[-1][0], actual[-1][1], 127)
        self.assertFalse(verify_writes(plan, actual, [], projected_samples(plan.end_tick))['passed'])

    def test_out_of_range_transient_is_reported_but_sustained_pitch_fails(self):
        row = psg(tone_period=0, vgmticks=0, vgmticks_end=2)
        plan = project({0: [row]}, SccAnalysis({}, ()), psg_clock=1789772,
                       scc_clock=0, end_vgmticks=2)
        self.assertIn('zero target duration', plan.rows[0]['approximation'])
        self.assertEqual(plan.rows[0]['source_period'], 0)
        with self.assertRaisesRegex(ValueError, 'outside OPM'):
            project({0: [replace(row, vgmticks_end=441)]}, SccAnalysis({}, ()),
                    psg_clock=1789772, scc_clock=0, end_vgmticks=441)

    def test_scc_wave_changes_keep_amplitude_and_continuity(self):
        wave = bytes(round(120 * math.sin(2 * math.pi * i / 32)) & 255 for i in range(32)).hex()
        half = bytes(round(60 * math.sin(2 * math.pi * i / 32)) & 255 for i in range(32)).hex()
        first = SccSegment('v', 0., 0, 0, 1, 200, 15, 4, 'c', 0, (),
                           200, 1, 0, 0, wave, 1, vgmticks=0, vgmticks_end=441)
        second = replace(first, waveform_hex=half, waveform_id=1, vgmticks=441, vgmticks_end=882)
        plan = project({}, SccAnalysis({0: [first, second]}, (wave, half)),
                       psg_clock=0, scc_clock=1789772, end_vgmticks=882)
        import json
        a, b = [json.loads(r['carrier_tl'])[0] for r in plan.rows]
        self.assertAlmostEqual((b-a)*.75, 6, delta=.75)
        self.assertEqual(sum(w.register == 8 and bool(w.data & 0x78) for w in plan.writes), 1)
        self.assertEqual([r['source_waveform_id'] for r in plan.rows], [0, 1])
        self.assertEqual(first.waveform_hex, wave)

    def test_v151_psg_legacy_output_is_supported(self):
        raw=bytearray(0x80)
        raw[:4]=b'Vgm '
        struct.pack_into('<I', raw, 8, 0x151)
        struct.pack_into('<I', raw, 0x34, 0x80-0x34)
        struct.pack_into('<I', raw, 0x74, 1789772)
        raw[0x79]=1
        raw += bytes([0xa0,8,0,0x66])
        facts=source_facts(raw)
        self.assertEqual(facts['psg_clock'],1789772)
        self.assertEqual(facts['scc_clock'],0)
        self.assertEqual(facts['ay_flags'],1)

    def test_preflight_distinguishes_initialization_from_playing_chips(self):
        def data(commands):
            raw = bytearray(0x100)
            raw[:4] = b'Vgm '
            struct.pack_into('<I', raw, 8, 0x171)
            struct.pack_into('<I', raw, 0x34, 0x100-0x34)
            struct.pack_into('<I', raw, 0x74, 1789772)
            return raw + bytes(commands) + b'\x66'
        facts = source_facts(data([0x51, 0x0e, 0x20, 0x51, 0x20, 0,
                                  0xd2, 3, 0, 31, 0xd2, 2, 0, 0]))
        self.assertEqual(facts['silent_opll_writes'], 2)
        self.assertEqual(facts['absent_scc_writes'], 2)
        for commands in ([0x51, 0x20, 0x10], [0x51, 0x0e, 0x21], [0xd2, 2, 0, 1]):
            with self.assertRaises(ValueError):
                source_facts(data(commands))

    def test_main_target_only_leaves_mml_and_default_mgs_is_unchanged(self):
        fixture = ROOT / 'tests/fixtures/public/scc/redundant_fnum_writes/redundant_fnum_writes.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'mdx'
            run = subprocess.run([sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                                  '--target', 'opm-additive', '--outdir', str(target)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual([p.name for p in target.iterdir()], ['redundant_fnum_writes.mdx.mml'])
            default = Path(tmp) / 'mgs'
            run = subprocess.run([sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                                  '--outdir', str(default)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('#opll_mode', (default / 'redundant_fnum_writes.mml').read_text(encoding='cp932'))

    def test_unsupported_controls_fail_instead_of_silent_omission(self):
        for row in [psg(mode=3), psg(envelope_enabled=1, volume=0)]:
            with self.assertRaisesRegex(ValueError, 'not implemented'):
                project({0: [row]}, SccAnalysis({}, ()), psg_clock=1789772, scc_clock=0, end_vgmticks=441)
        with self.assertRaisesRegex(ValueError, 'boundaries'):
            project({0: [psg(vgmticks=None)]}, SccAnalysis({}, ()), psg_clock=1789772, scc_clock=0, end_vgmticks=441)


if __name__ == '__main__':
    unittest.main()
