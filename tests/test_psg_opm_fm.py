"""Check FM target selection, range disclosure and source/Key continuity."""
from dataclasses import replace
from pathlib import Path
import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT)]
from chip_segments import PsgSegment, SccAnalysis, SccSegment
from psg_opm_fm import tone_tl
from psg_scc_opm import project, opm_pitch
from scripts.psg_scc_to_mdx import convert


def row(**kwargs):
    base = PsgSegment('v', 0., 0, 0, 1, 200, 15, 4, 'c', 0, (),
                      1, 0, 0, 0, 0, 0x3e, 15, vgmticks=0, vgmticks_end=441)
    return replace(base, **kwargs)


def fm(rows, **kwargs):
    return project({0: rows}, SccAnalysis({}, ()), psg_clock=1789772,
                   scc_clock=0, end_vgmticks=rows[-1].vgmticks_end,
                   psg_model='fm', **kwargs)


class FmTargetTests(unittest.TestCase):
    def test_level_changes_leave_modulation_and_key_continuity_intact(self):
        rows = [row(), row(vgmticks=441, vgmticks_end=882, volume=7),
                row(vgmticks=882, vgmticks_end=1323, volume=0),
                row(vgmticks=1323, vgmticks_end=1764, tone_period=150)]
        before = tuple(rows)
        plan = fm(rows)
        self.assertEqual(tuple(rows), before)
        self.assertEqual(sum(w.register == 8 and bool(w.data & 0x78) for w in plan.writes), 1)
        self.assertEqual([r['target_audible'] for r in plan.rows], [True, True, False, True])
        # Volume changes affect C1, not the M1 feedback source or unused chain.
        self.assertEqual({w.data for w in plan.writes if w.register == 0x65}, {27})
        self.assertEqual({w.data for w in plan.writes if w.register == 0x6d}, {127})
        self.assertIn(8, {w.data for w in plan.writes if w.register == 0x75})
        self.assertIn(40, {w.data for w in plan.writes if w.register == 0x75})
        self.assertEqual({w.data for w in plan.writes if w.register == 0x25}, {0x3c, 0xfc})

    def test_range_limit_is_explicit_at_both_grid_phases(self):
        a = row(tone_period=0, vgmticks=582928, vgmticks_end=582930)
        b = row(tone_period=0, vgmticks=630032, vgmticks_end=630034)
        plan = fm([a, b])
        self.assertEqual(len(plan.rows), 2)
        for r in plan.rows:
            self.assertIn('clamped', r['approximation'])
            self.assertTrue(r['target_audible'])
            self.assertEqual(r['source_period'], 0)
            self.assertLess(r['target_frequency_hz'], r['frequency_hz'])
            self.assertLess(r['pitch_error_cents'], 0)
        self.assertEqual(plan.rows[0]['target_kc'], plan.rows[1]['target_kc'])
        with self.assertRaisesRegex(ValueError, 'outside OPM'):
            fm([row(tone_period=0)], pitch_policy='error')

    def test_legal_pitch_remains_accurate_and_range_limits_are_monotone(self):
        expected = 440
        self.assertLess(abs(1200 * math.log2(opm_pitch(expected)[2] / expected)), 1)
        low = opm_pitch(.1, clamp=True)
        high = opm_pitch(1e6, clamp=True)
        self.assertEqual(low[:2], (0, 0))
        self.assertEqual(high[:2], (0x7e, 252))
        self.assertLess(low[2], high[2])
        for invalid in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                opm_pitch(invalid, clamp=True)

    def test_gain_scales_carrier_not_timbre_and_bad_controls_still_fail(self):
        self.assertEqual(tone_tl(15, 1), 8)
        self.assertEqual(tone_tl(0, 1), 127)
        self.assertAlmostEqual((tone_tl(15, .5)-tone_tl(15, 1))*.75, 6, delta=.75)
        with self.assertRaises(ValueError):
            tone_tl(15, float('nan'))
        for r in (row(mode=2), row(envelope_enabled=1, volume=0)):
            with self.assertRaisesRegex(ValueError, 'not implemented'):
                fm([r])

    def test_mixed_voice_dump_does_not_fabricate_fm_spectral_components(self):
        wave = bytes(round(100*math.sin(i*math.pi/16)) & 255 for i in range(32)).hex()
        s = SccSegment('v', 0., 0, 0, 1, 200, 15, 4, 'c', 0, (),
                       200, 1, 0, 0, wave, 1, vgmticks=0, vgmticks_end=441)
        plan = project({0:[row()]}, SccAnalysis({0:[s]}, (wave,)),
                       psg_clock=1789772, scc_clock=1789772, end_vgmticks=441, psg_model='fm')
        with tempfile.TemporaryDirectory() as tmp:
            plan.dump(tmp, 'mixed')
            with (Path(tmp)/'mixed.opm_voices.csv').open(encoding='utf-8') as stream:
                voices = list(csv.DictReader(stream))
            v = next(x for x in voices if x['identity']=='psg_fm_feedback')
            self.assertEqual(v['harmonics'], '')
            self.assertEqual(v['algorithm'], '4')
            self.assertEqual(len(voices), 2)

    def test_entry_defaults_to_fm_and_additive_remains_selectable(self):
        fixture = ROOT/'tests/fixtures/public/psg/volume_sweep/volume_sweep.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            for model in ('fm', 'additive'):
                folder = Path(tmp)/model
                _, plan = convert(fixture, folder, **({'psg_model':model} if model=='additive' else {}))
                self.assertEqual(plan.settings['psg_model'], model)
                self.assertEqual(plan.settings['pitch_policy'], 'clamp' if model=='fm' else 'error')
                self.assertEqual(plan.settings['psg_gain'], 1 if model=='fm' else .125)
            # Native Segment evidence is identical for the two projections.
            self.assertEqual((Path(tmp)/'fm/volume_sweep.psg.segments.csv').read_bytes(),
                             (Path(tmp)/'additive/volume_sweep.psg.segments.csv').read_bytes())
            run = subprocess.run([sys.executable,str(ROOT/'vgm2mml.py'),str(fixture),
                                  '--target','opm','--outdir',str(Path(tmp)/'main')],
                                 capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual([p.name for p in (Path(tmp)/'main').iterdir()],['volume_sweep.mdx.mml'])
            self.assertIn('PSG model=fm', (Path(tmp)/'main/volume_sweep.mdx.mml').read_text())


if __name__ == '__main__':
    unittest.main()
