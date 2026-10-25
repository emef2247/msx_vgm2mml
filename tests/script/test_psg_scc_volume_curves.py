"""Full attack curves must preserve original holds and operational barriers."""
import csv
from dataclasses import replace
import json
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(Path(__file__).resolve().parent)]
from psg_scc_performance import analyze
from psg_scc_volume_curves import project, dump
from pre_envelope_loops import LoopFirstEnvelopeBank
from test_psg_scc_performance import psg, scc
from test_mml_envelopes import sounding_timeline


def attack(factory, levels=(8, 10, 12, 9, 6)):
    return [factory(i * 2, volume=volume, tone_period=400) for i, volume in enumerate(levels)]


class VolumeCurveTests(unittest.TestCase):
    def test_complete_attack_is_projected_without_mutating_native_partitions(self):
        for chip, factory in (('psg', psg), ('scc', scc)):
            with self.subTest(chip=chip):
                rows = attack(factory)
                original = analyze({0: rows}, chip)
                result = project(original)
                self.assertEqual(len(dict(original.channels)[0]), 3)
                note, = dict(result.performance.channels)[0]
                self.assertEqual(note.runs, ((8, 2), (10, 2), (12, 2), (9, 2), (6, 2)))
                self.assertEqual(note.segment_indices, tuple(range(5)))
                self.assertEqual(result.summary()['joined_boundaries'], 2)
                self.assertIs(result.performance.source_segments, original.source_segments)
                self.assertIs(result.performance.controls, original.controls)
                self.assertEqual(result.performance.reconstruct_segments(), {0: rows})

    def test_same_pitch_write_preserves_rearticulation(self):
        for chip, factory, event in (('psg', psg, 'fCA'), ('scc', scc, 'f1Ctrl')):
            rows = attack(factory)
            rows[1] = replace(rows[1], ev_type=event)
            original = analyze({0: rows}, chip)
            result = project(original)
            self.assertTrue(any(d['reason'] == 'pitch_write' for d in result.decisions))
            self.assertTrue(all(not (0 in note.segment_indices and 1 in note.segment_indices)
                                for _, notes in result.performance.channels for note in notes))

    def test_zero_duration_setting_restore_is_still_a_barrier(self):
        for chip, factory in (('psg', psg), ('scc', scc)):
            rows = attack(factory)
            transient = (dict(mode=2, ev_type='mode') if chip == 'psg'
                         else dict(waveform_id=1, waveform_hex='01' * 32, ev_type='wtb'))
            rows.insert(1, factory(2, 0, **transient))
            original = analyze({0: rows}, chip)
            result = project(original)
            self.assertTrue(any(d['reason'] == 'ordered_settings_change' for d in result.decisions))
            self.assertTrue(all(not (0 in n.segment_indices and 2 in n.segment_indices)
                                for _, notes in result.performance.channels for n in notes))
            self.assertEqual(result.performance.reconstruct_segments(), {0: rows})

    def test_subtick_silence_unknown_time_and_source_gap_are_not_bridged(self):
        for kind in ('silence', 'unknown', 'gap'):
            rows = attack(scc)
            if kind == 'silence':
                rows[0] = replace(rows[0], vgmticks_end=1460)
                rows.insert(1, scc(2, 0, volume=0, vgmticks=1460, vgmticks_end=1470))
            elif kind == 'unknown':
                rows[1] = replace(rows[1], vgmticks=None)
            else:
                rows[1] = replace(rows[1], vgmticks=1471)
            result = project(analyze({0: rows}, 'scc'))
            first = dict(result.performance.channels)[0][0]
            self.assertEqual(first.segment_indices, (0,))

    def test_hardware_envelope_noise_pitch_changes_and_repeated_rises_abstain(self):
        cases = [([replace(n, envelope_enabled=1) for n in attack(psg)], 'psg'),
                 ([replace(n, mode=3) for n in attack(psg)], 'psg'),
                 (attack(scc, (8, 12, 9, 12, 6)), 'scc')]
        rows = attack(scc)
        rows[1] = replace(rows[1], tone_period=101)
        cases.append((rows, 'scc'))
        for rows, chip in cases:
            with self.subTest(chip=chip, rows=rows):
                original = analyze({0: rows}, chip)
                result = project(original)
                self.assertEqual(result.performance.channels, original.channels)

    def test_exact_shared_envelope_and_long_ties_preserve_every_render_tick(self):
        for chip, factory in (('psg', psg), ('scc', scc)):
            rows = attack(factory)
            rows[-1] = replace(rows[-1], l=300, vgmticks_end=(rows[-1].ticks+300)*735)
            original = analyze({0: rows}, chip)
            projection = project(original)
            with tempfile.TemporaryDirectory() as tmp:
                timelines = []
                for number, performance in enumerate((original, projection.performance)):
                    bank = LoopFirstEnvelopeBank(deferred=True)
                    target = Path(tmp) / f'{number}.mml'
                    bank.submit({0: rows}, chip, target, raw_ticks=True, performance=performance)
                    bank.flush()
                    timelines.append(sounding_timeline(target.read_text(), raw=True))
                    if number:
                        self.assertGreater(len(bank.curves), 1)
                        self.assertIn('&', target.read_text())
                self.assertEqual(timelines[0], timelines[1])

    def test_full_bank_and_long_curve_inline_fallback_keep_next_note_state(self):
        from mml_envelopes import EnvelopeBank, render
        for saturated in (False, True):
            rows = attack(scc)
            if not saturated:
                rows = [replace(n, ticks=i*5000, l=5000,
                                vgmticks=i*5000*735, vgmticks_end=(i+1)*5000*735)
                        for i, n in enumerate(rows)]
            end = rows[-1].ticks + rows[-1].l
            rows.append(scc(end, 2, ev_type='f1Ctrl', volume=11, tone_period=400))
            original = analyze({0: rows}, 'scc')
            projection = project(original)
            def bank():
                result = EnvelopeBank()
                if saturated:
                    for i in range(31):
                        result.register(((15, i+1), (2, 1)))
                    result.prepared = True
                return result
            before = render({0: rows}, 'scc', bank(), True, performance=original)
            after = render({0: rows}, 'scc', bank(), True, performance=projection.performance)
            self.assertEqual(sounding_timeline(before), sounding_timeline(after))
            self.assertIn('&', after)

    def test_projection_dumps_lineage_and_explicit_scope(self):
        result = project(analyze({0: attack(scc)}, 'scc'))
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / 'source.scc.volume_curves'
            dump(result, prefix, details=True)
            summary = json.loads(Path(str(prefix)+'.json').read_text())
            self.assertFalse(summary['lossy'])
            self.assertEqual(summary['maximum_volume_error'], 0)
            with Path(str(prefix)+'.candidates.csv').open() as stream:
                row, = csv.DictReader(stream)
            self.assertEqual(json.loads(row['segment_indices']), list(range(5)))
            self.assertEqual(row['action'], 'join')



class InactiveResetTests(unittest.TestCase):
    def test_constant_and_decaying_tone_reset_boundaries_coalesce_with_lineage(self):
        for volumes in ((12, 12, 12), (12, 9, 6)):
            rows = [psg(0, volume=volumes[0]), psg(2, ev_type='evS', volume=volumes[1]),
                    psg(4, ev_type='evS', volume=volumes[2])]
            original = analyze({0: rows}, 'psg')
            result = project(original)
            note, = dict(result.performance.channels)[0]
            self.assertEqual(note.length, 6)
            self.assertEqual(note.segment_indices, (0, 1, 2))
            self.assertEqual(result.summary()['inactive_reset_joins'], 2)
            self.assertEqual(result.candidates[0]['original_note_ids'], (0, 1, 2))
            self.assertIs(result.performance.controls, original.controls)
            self.assertIs(result.performance.boundaries, original.boundaries)
            self.assertEqual(result.performance.reconstruct_segments(), {0: rows})

    def test_active_reset_noise_unknown_time_and_other_boundary_reasons_protect(self):
        cases = [dict(envelope_enabled=1), dict(mode=3), dict(vgmticks=None),
                 dict(volume=14)]
        for change in cases:
            rows = [psg(**change), psg(2, ev_type='evS', **change)]
            if 'volume' in change:
                rows[0] = psg(volume=8)
            result = project(analyze({0: rows}, 'psg'))
            self.assertEqual(result.summary()['inactive_reset_joins'], 0)
            self.assertEqual(len(dict(result.performance.channels)[0]), 2)

    def test_zero_duration_hardware_enable_pitch_mixer_and_silence_are_barriers(self):
        for transient in (dict(envelope_enabled=1, ev_type='aVC'),
                          dict(ev_type='fCA'), dict(ev_type='mode'), dict(volume=0)):
            rows = [psg(), psg(2, 0, **transient), psg(2, 0, ev_type='evS'), psg(2)]
            result = project(analyze({0: rows}, 'psg'))
            self.assertEqual(result.summary()['inactive_reset_joins'], 0, transient)
            self.assertEqual(len(dict(result.performance.channels)[0]), 2)
            self.assertEqual(result.performance.reconstruct_segments(), {0: rows})

    def test_subtick_silence_and_source_gap_do_not_coalesce(self):
        for silence in (False, True):
            rows = [psg(vgmticks_end=1460), psg(2, ev_type='evS')]
            if silence:
                rows.insert(1, psg(2, 0, volume=0, vgmticks=1460, vgmticks_end=1470))
            result = project(analyze({0: rows}, 'psg'))
            self.assertEqual(result.summary()['inactive_reset_joins'], 0)

    def test_zero_duration_inactive_reset_is_retained_as_control(self):
        rows = [psg(), psg(2, 0, ev_type='evS'), psg(2)]
        original = analyze({0: rows}, 'psg')
        result = project(original)
        self.assertEqual(result.summary()['inactive_reset_joins'], 1)
        self.assertIs(result.performance.controls, original.controls)
        resets = [p for p in result.performance.controls if p.source_event == 'evS']
        self.assertTrue(resets)
        self.assertEqual(result.performance.reconstruct_segments(), {0: rows})

    def test_reset_and_attack_stages_use_original_note_ids(self):
        rows = [psg(0, volume=8), psg(2, ev_type='evS', volume=8),
                psg(4, volume=12), psg(6, volume=6)]
        result = project(analyze({0: rows}, 'psg'))
        self.assertEqual(result.summary()['inactive_reset_joins'], 1)
        self.assertEqual(result.summary()['joined_boundaries'], 2)
        self.assertEqual(result.candidates[-1]['original_note_ids'], (0, 1, 2))
        self.assertEqual(len(dict(result.performance.channels)[0]), 1)



class UnchangedPsgPeriodTests(unittest.TestCase):
    def test_unchanged_period_release_tail_remains_one_observed_curve(self):
        for event in ('fCA', 'fCB'):
            rows = [psg(0, 16, volume=8), psg(16, 0, ev_type=event, volume=8),
                    psg(16, 2, volume=7), psg(18, 2, volume=5),
                    psg(20, 0, ev_type=event, volume=5), psg(20, 2, volume=14)]
            original = analyze({0: rows}, 'psg');result = project(original)
            notes = dict(result.performance.channels)[0]
            self.assertEqual((notes[0].start, notes[0].length), (0, 20))
            self.assertEqual(notes[0].runs, ((8, 16), (7, 2), (5, 2)))
            self.assertEqual(notes[1].start, 20)
            self.assertIn('volume_rise', notes[1].boundary_reasons)
            self.assertEqual(result.summary()['unchanged_period_joins'], 1)
            self.assertIs(result.performance.controls, original.controls)
            self.assertIs(result.performance.boundaries, original.boundaries)
            self.assertEqual(result.performance.reconstruct_segments(), {0: rows})

    def test_intermediate_pitch_excursion_even_at_zero_duration_is_protected(self):
        rows = [psg(), psg(2, 0, ev_type='fCA', tone_period=101),
                psg(2, 0, ev_type='fCB', tone_period=100), psg(2, volume=9)]
        result = project(analyze({0: rows}, 'psg'))
        self.assertEqual(result.summary()['unchanged_period_joins'], 0)
        self.assertTrue(any(d['reason'] == 'ordered_settings_change' for d in result.decisions))

    def test_transient_volume_rise_and_hardware_mixer_controls_are_protected(self):
        for extra in (dict(volume=14, ev_type='aVC'),
                      dict(envelope_enabled=1, ev_type='aVC'), dict(ev_type='mode'),
                      dict(ev_type='unknown')):
            rows = [psg(volume=12), psg(2, 0, **extra),
                    psg(2, 0, ev_type='fCB', volume=12), psg(2, volume=9)]
            result = project(analyze({0: rows}, 'psg'))
            self.assertEqual(result.summary()['unchanged_period_joins'], 0, extra)

    def test_silence_noise_unknown_time_and_real_pitch_change_are_protected(self):
        cases = [[psg(volume=0), psg(2, ev_type='fCB')],
                 [psg(mode=3), psg(2, ev_type='fCB', mode=3)],
                 [psg(vgmticks_end=None), psg(2, ev_type='fCB')],
                 [psg(), psg(2, ev_type='fCB', tone_period=101)]]
        for rows in cases:
            self.assertEqual(project(analyze({0: rows}, 'psg')).summary()['unchanged_period_joins'], 0)

    def test_inactive_noise_and_envelope_period_writes_preserve_complete_units(self):
        for event in ('wNC', 'ePL', 'evM'):
            rows = [psg(volume=12), psg(2, 0, ev_type=event, noise_period=9,
                                       envelope_period=99),
                    psg(2, 0, ev_type='fCB', volume=12, noise_period=9, envelope_period=99),
                    psg(2, volume=9, noise_period=9, envelope_period=99)]
            original = analyze({0: rows}, 'psg');result = project(original)
            self.assertEqual(result.summary()['unchanged_period_joins'], 1)
            self.assertIs(result.performance.controls, original.controls)
            self.assertEqual(result.performance.reconstruct_segments(), {0: rows})
            for transient in (dict(mode=3), dict(envelope_enabled=1)):
                changed = list(rows)
                changed[1] = replace(rows[1], **transient)
                guarded = project(analyze({0: changed}, 'psg'))
                self.assertEqual(guarded.summary()['unchanged_period_joins'], 0)

    def test_scc_identical_frequency_write_remains_protected(self):
        rows = [scc(), scc(2, 0, ev_type='f1Ctrl'), scc(2, volume=9)]
        original = analyze({0: rows}, 'scc');result = project(original)
        self.assertEqual(result.performance.channels, original.channels)
        self.assertEqual(result.summary()['unchanged_period_joins'], 0)


class CurveCliTests(unittest.TestCase):
    def test_public_cli_is_independent_and_removes_stale_optional_evidence(self):
        source = ROOT/'tests/fixtures/public/psg/scale_rom1/scale_rom1.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            command = [sys.executable, str(ROOT/'vgm2mml.py'), str(source), '--outdir', tmp, '--dump-passes']
            run = subprocess.run([*command, '--software-volume-curves'], capture_output=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            summary = json.loads((Path(tmp)/'scale_rom1.psg.volume_curves.json').read_text())
            self.assertTrue(summary['source_segments_unchanged'])
            report = json.loads((Path(tmp)/'scale_rom1.conversion.json').read_text())
            self.assertTrue(report['options']['software_volume_curves'])
            self.assertFalse(report['options']['normalization_enabled'])
            self.assertTrue(list(Path(tmp).glob('scale_rom1.psg.performance.*')))
            run = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertFalse(list(Path(tmp).glob('*.volume_curves.*')))

    def test_public_accepted_normalization_with_curve_projection(self):
        source = ROOT/'tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run([sys.executable, str(ROOT/'vgm2mml.py'), str(source),
                '--outdir', tmp, '--dump-passes', '--software-volume-curves',
                '--normalization-ms', '16.666666666666668'], capture_output=True, timeout=90)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            normalization = json.loads((Path(tmp)/'sample.normalization.json').read_text())
            self.assertEqual(normalization['status'], 'applied', normalization['reason'])
            self.assertEqual(normalization['timing']['tempo'], 120)
            projection = json.loads((Path(tmp)/'sample.psg.volume_curves.json').read_text())
            self.assertFalse(projection['lossy'])
            self.assertFalse(projection['applied'])
            self.assertEqual(projection['joined_boundaries'], 0)
            target = json.loads((Path(tmp)/'sample.volume_curves.target.json').read_text())
            self.assertEqual(target['status'], 'fallback')
            self.assertIn('normalized', target['reason'])
            conversion = json.loads((Path(tmp)/'sample.conversion.json').read_text())
            self.assertTrue(conversion['options']['software_volume_curves'])
            self.assertFalse(conversion['volume_curve_target']['applied'])
            # The entire fallback recomputes clock acceptance from the ordinary
            # partitions; final target files must still share one accepted clock.
            for chip in ('psg', 'scc', 'opll'):
                text = (Path(tmp)/f'sample.{chip}.target.mml').read_text()
                import re
                if re.search(r'^[1-9a-h]\s+', text, re.M):
                    self.assertIn('#tempo 120', text)


class ActualCurvePlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('mgsc') or not shutil.which('node'):
            raise unittest.SkipTest('MGSC and Node are required')
        check = subprocess.run(['node', str(ROOT/'scripts/mgs_to_vgm.mjs'), '--check'], capture_output=True)
        if check.returncode:
            raise unittest.SkipTest('libkss-js is required')

    def test_actual_psg_and_scc_attack_levels_and_next_restart(self):
        from mml_sync import annotate_sync_points
        from vgm_reader import parse_vgm
        for chip, factory, event, mode in [(c, f, e, m) for c, f, e in (('psg', psg, 'fCA'), ('scc', scc, 'f1Ctrl'))
                                          for m in ('shared', 'inline', 'normalized')]:
            rows = [replace(n, tone_period=400) for n in attack(factory)]
            rows.append(factory(10, volume=0, scale='r', tone_period=400))
            rows.extend(replace(n, ticks=n.ticks+12, vgmticks=n.vgmticks+12*735,
                                vgmticks_end=n.vgmticks_end+12*735, tone_period=400,
                                ev_type=event if i == 0 else n.ev_type)
                        for i, n in enumerate(attack(factory)))
            expected = [8,8,10,10,12,12,9,9,6,6,0,0]*2
            expected = expected[:-2]
            original = analyze({0: rows}, chip)
            projection = project(original)
            with self.subTest(chip=chip, mode=mode), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                replayed = []
                for number, performance in enumerate((original, projection.performance)):
                    output = folder/str(number); output.mkdir()
                    target = output/'score.mml'
                    bank = LoopFirstEnvelopeBank(deferred=True)
                    if mode == 'inline':
                        for i in range(31):
                            bank.register(((15, i+1), (2, 1)))
                    bank.submit({0: rows}, chip, target, raw_ticks=mode != 'normalized',
                                waveforms=(''.join(f'{v:02X}' for v in range(0,256,8)),) if chip == 'scc' else (), performance=performance)
                    bank.flush()
                    score = target.read_text()
                    if mode == 'normalized':
                        from note_normalization import retime_controls, TimingPlan
                        score = retime_controls(score, TimingPlan(75, 12, 8820, 0, 1, 0), {0: rows})
                    target.write_text(annotate_sync_points('#opll_mode 0\n'+score), encoding='cp932')
                    mgs=output/'score.mgs';vgm=output/'score.vgm'
                    run=subprocess.run(['mgsc',str(target),str(mgs)],capture_output=True,timeout=30)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    run=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'1500'],
                                       capture_output=True,timeout=45)
                    self.assertEqual(run.returncode,0,run.stderr)
                    paths=parse_vgm(str(vgm),str(output/'trace'),include_vgmticks=True)
                    path=paths[2 if chip=='psg' else 3]
                    values={}
                    with Path(path).open() as stream:
                        for r in csv.DictReader(stream):
                            if int(r['ch'])==0:
                                values[round(int(r['vgmticks']) / 735)]=(int(r['aVCtrl' if chip=='psg' else 'vCtrl']) & 15) if int(r['en']) else 0
                    first=min(t for t,v in values.items() if v)
                    actual=[];current=0
                    for tick in range(first,first+len(expected)):
                        current=values.get(tick,current);actual.append(current)
                    replayed.append(actual)
                self.assertEqual(replayed[0], replayed[1], 'Projection changed real driver output')
                self.assertEqual(replayed[1][:10], expected[:10])
                self.assertEqual(replayed[1][12:], expected[12:])
                self.assertEqual(replayed[1][11], 0)
                # Both baseline and projected effective states retain one extra
                # ending frame in this probe. This test does not certify source
                # ending equality; full before/after comparison includes that frame.
                self.assertEqual(replayed[0][10], 6)


if __name__ == '__main__':
    unittest.main()
