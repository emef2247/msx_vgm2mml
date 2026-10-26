"""Editable score: volume holds, sounding units, provenance and safe output."""
from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from musical_plan import MusicalPlan, MusicalUnit, MusicalControl
from musical_blueprint import BlueprintError, render_blueprint, write_blueprint
from musical_blueprint import _length
from mml_sync import analyze_mml
from vgm_io import read_vgm_bytes
from vgm_timing import command_times


def note(chip='psg', channel=0, start=0, length=4410, uid='unit', volumes=((0, 15), (1470, 9), (2940, 3))):
    unit = MusicalUnit(uid, chip, channel, start, start+length, False)
    controls = [MusicalControl(start, chip, channel, 'pitch',
                              (172, 3, 0) if chip == 'opll' else (426,), unit_id=uid)]
    controls += [MusicalControl(start+t, chip, channel, 'volume', (v,), unit_id=uid)
                 for t, v in volumes if t < length]
    return unit, controls


def plan(*notes, metadata=()):
    units, controls = zip(*notes)
    end = max(u.end_sample for u in units)
    return MusicalPlan(tuple(units), tuple(c for rows in controls for c in rows), end, end,
                       (('psg', 1789773), ('scc', 1789773), ('opll', 3579545)), metadata=metadata)


class BlueprintTests(unittest.TestCase):
    def test_subframe_durations_use_valid_raw_lengths(self):
        self.assertEqual(_length('c', 1), 'c%1')
        self.assertEqual(_length('c', 2), 'c%2')
        self.assertEqual(_length('c', 3), 'c64')
        self.assertEqual(_length('c', 48), 'c4')

    def test_native_lanes_strip_definitions_and_retain_inline_volume(self):
        for chip, track in (('psg', '1'), ('scc', '4'), ('opll', '9')):
            with self.subTest(chip=chip):
                p = plan(note(chip))
                if chip == 'scc':
                    p = replace(p, controls=p.controls + (MusicalControl(0, chip, 0, 'waveform', tuple(range(32))),))
                elif chip == 'opll':
                    p = replace(p, controls=p.controls + (MusicalControl(0, chip, 0, 'instrument', (7,)),
                        MusicalControl(0, chip, None, 'patch_write', (0, 255))))
                text, report = render_blueprint(p)
                self.assertIsNone(re.search(r'^\s*@[sev]?\d+\s*=', text, re.M))
                self.assertNotRegex(text, r'@e\d+')
                self.assertTrue(all(f'v{v}' in text for v in (15, 9, 3)))
                tracks, _, _ = analyze_mml(text)
                self.assertEqual(set(tracks), {track})
                self.assertEqual(tracks[track][-1].end, 18)
                self.assertEqual(report['omitted_units'], 0)

    def test_full_units_remain_finite_loops_with_volume_holds_inside(self):
        p = plan(*(note('psg', start=i*4410, uid=f'n{i}') for i in range(4)))
        text, report = render_blueprint(p)
        self.assertRegex(text, r'\]\s*4')
        self.assertTrue(any(row['status'] == 'loop_emitted' or row.get('emitted_repeats') == 4
                            for row in report['loops']))
        tracks, _, _ = analyze_mml(text)
        self.assertEqual(tracks['1'][-1].end, 72)

    def test_pitch_change_is_tied_but_explicit_retrigger_is_not(self):
        u, controls = note('opll')
        controls += [MusicalControl(1470, 'opll', 0, 'pitch', (194, 3, 0), unit_id=u.unit_id)]
        p = plan((u, controls))
        _, report = render_blueprint(p)
        text = report['allocations'][0]['mml']
        self.assertIn('&d', text)
        controls += [MusicalControl(2940, 'opll', 0, 'gate', (0,), order=1, unit_id=u.unit_id),
                     MusicalControl(2940, 'opll', 0, 'gate', (1,), order=2, unit_id=u.unit_id)]
        _, report = render_blueprint(plan((u, controls)))
        self.assertRegex(report['allocations'][0]['mml'], r'v3 d32$')

    def test_huc_provenance_uses_free_opll_then_psg_and_keeps_volume(self):
        metadata = (('source_projection', dict(source='huc6280', allocation=[
            dict(source_channel=0, target_chip='scc', target_channel=0)])),)
        others = [note('opll', channel=ch, uid=f'o{ch}') for ch in range(9)]
        p = plan(note('scc'), *others, metadata=metadata)
        _, report = render_blueprint(p)
        row = next(r for r in report['allocations'] if r['unit_id'] == 'unit')
        self.assertEqual((row['source_chip'], row['source_channel']), ('huc6280', 0))
        self.assertEqual((row['target_chip'], row['track']), ('psg', '1'))
        _, report = render_blueprint(plan(note('scc'), note('opll', uid='native'), metadata=metadata))
        row = next(r for r in report['allocations'] if r['unit_id'] == 'unit')
        self.assertEqual((row['target_chip'], row['track']), ('opll', 'a'))
        self.assertIn('v9', row['mml'])

    def test_capacity_failure_does_not_omit_a_voice(self):
        metadata = (('source_projection', dict(source='huc6280', allocation=[
            dict(source_channel=0, target_chip='scc', target_channel=0)])),)
        p = plan(note('scc'), *(note('opll', channel=ch, uid=f'o{ch}') for ch in range(9)),
                 *(note('psg', channel=ch, uid=f'p{ch}') for ch in range(3)), metadata=metadata)
        with self.assertRaisesRegex(BlueprintError, 'No free OPLL/PSG lane'):
            render_blueprint(p)

    def test_inactive_global_envelope_writes_do_not_split_a_fixed_volume_note(self):
        p = plan(note(volumes=((0, 12),)))
        p = replace(p, controls=p.controls + tuple(MusicalControl(at, 'psg', None,
                    'psg_envelope_shape', (5,)) for at in (735, 1470, 2205)))
        _, report = render_blueprint(p)
        self.assertEqual(len(re.findall(r'c(?:%\d+|\d+)', report['allocations'][0]['mml'])), 1)

    def test_hardware_envelope_is_retained_and_not_relabelled_as_software(self):
        u, controls = note(volumes=((0, 15),))
        u = replace(u, parameters=(('mode', 1), ('hardware_envelope', True)))
        controls += [MusicalControl(0, 'psg', 0, 'psg_envelope_enable', (1,), unit_id=u.unit_id),
                     MusicalControl(0, 'psg', None, 'psg_envelope_period', (900,)),
                     MusicalControl(0, 'psg', None, 'psg_envelope_shape', (10,))]
        text, _ = render_blueprint(plan((u, controls)))
        self.assertIn('m900', text)
        self.assertIn('s10', text)
        self.assertNotIn('@e', text)

    def test_zero_time_and_rounding_losses_are_not_silently_held(self):
        p = plan(note(length=1))
        with self.assertRaisesRegex(BlueprintError, 'collapses'):
            render_blueprint(p)

    def test_edited_output_and_unowned_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = write_blueprint(plan(note()), root, 'song')
            target = Path(report['path'])
            target.write_text('hand edited score')
            result = write_blueprint(plan(note()), root, 'song')
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('edited blueprint', result['detail'])
            self.assertEqual(target.read_text(), 'hand edited score')
            result = write_blueprint(plan(note()), root, 'song')
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(target.read_text(), 'hand edited score')

    def test_failed_attempt_retains_ownership_without_claiming_latest_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = write_blueprint(plan(note()), root, 'song')
            contents = Path(good['path']).read_bytes()
            failed = write_blueprint(plan(note(length=1)), root, 'song')
            self.assertEqual(failed['status'], 'blocked')
            self.assertEqual(failed['sha256'], good['sha256'])
            self.assertEqual(Path(good['path']).read_bytes(), contents)
            self.assertEqual(write_blueprint(plan(note()), root, 'song')['status'], 'success')

    def test_rhythm_presets_remain_without_custom_voices(self):
        p = plan(note('opll'))
        p = replace(p, controls=p.controls + tuple(MusicalControl(t, 'opll', None, 'rhythm_register', v)
                    for t, v in ((0, (0x36, 5)), (0, (14, 48)), (735, (14, 32)))))
        text, report = render_blueprint(p)
        self.assertIn('#opll_mode 1', text)
        self.assertIn('vb10', text)
        self.assertEqual(report['rhythm'][0]['volumes'], {'b': 10})
        self.assertNotRegex(text, r'@\d+\s*=')

    def test_held_rhythm_volume_changes_are_not_silently_discarded(self):
        p = plan(note('opll'))
        p = replace(p, controls=p.controls + tuple(MusicalControl(t, 'opll', None, 'rhythm_register', v)
                    for t, v in ((0, (0x36, 5)), (0, (14, 48)), (735, (0x36, 10)))))
        with self.assertRaisesRegex(BlueprintError, 'Held OPLL percussion volume curve'):
            render_blueprint(p)

    def test_rhythm_volume_update_at_same_sample_release_is_not_a_held_curve(self):
        p = plan(note('opll'))
        p = replace(p, controls=p.controls + tuple(MusicalControl(t, 'opll', None, 'rhythm_register', v, order=i)
                    for i, (t, v) in enumerate(((0, (0x36, 5)), (0, (14, 48)),
                        (735, (0x36, 10)), (735, (14, 32)), (1470, (14, 48)), (2205, (14, 32))))))
        _, report = render_blueprint(p)
        self.assertEqual([row['volumes']['b'] for row in report['rhythm']], [10, 5])


@unittest.skipUnless(shutil.which('mgsc') and shutil.which('node'), 'MGSC/Node required')
class BlueprintPlaybackTests(unittest.TestCase):
    def test_subframe_score_is_blocked_without_publishing_invalid_mml(self):
        p=plan(*(note(start=245*i, length=245, uid=f'n{i}', volumes=((0, 10),)) for i in range(3)))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=write_blueprint(p,root,'short')
            self.assertEqual(report['status'],'blocked')
            self.assertEqual(report['projection_detail']['minimum_steps'],3)
            self.assertEqual(report['projection_detail']['unit_id'],'n0')
            self.assertFalse((root/'blueprint/short.mml').exists())

    def test_long_duration_split_has_no_subframe_remainder(self):
        from mml_sync import annotate_sync_points
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'long.mml'
            source.write_text(annotate_sync_points('#opll_mode 0\n#tempo 225\n1 @0 q8 o4 v12 '+
                _length('c',256,minimum=3)+'\n'))
            result=subprocess.run(['mgsc',str(source),str(root/'long.mgs')],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout)

    def test_actual_mgs_keeps_volume_holds_and_full_gate_length(self):
        check = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'), '--check'], capture_output=True)
        if check.returncode:
            self.skipTest('libkss required')
        p = plan(note(length=44100, volumes=((0, 15), (14700, 9), (29400, 3))))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = write_blueprint(p, root, 'probe')
            result = subprocess.run(['mgsc', report['path'], str(root/'probe.mgs')], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout)
            result = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'), str(root/'probe.mgs'),
                str(root/'probe.vgm'), '2000'], capture_output=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = read_vgm_bytes(root/'probe.vgm')
            actual = [(e.vgmticks, raw[e.address+2]) for e in command_times(raw)
                      if e.command == 0xa0 and raw[e.address+1] == 8]
            self.assertEqual([v for _, v in actual], [0, 15, 9, 3, 0])
            levels = [(t, v) for t, v in actual if v]
            self.assertTrue(all(abs(b[0]-a[0]-14700) < 735 for a, b in zip(levels, levels[1:])))
            self.assertLess(abs(actual[-1][0]-levels[0][0]-44100), 735)


if __name__ == '__main__':
    unittest.main()
