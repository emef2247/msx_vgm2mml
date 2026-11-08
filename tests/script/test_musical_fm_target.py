"""Source-independent FM projection checks with authored native performances."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))
from native_music import NativeDevice, NativeVoice, NativeUnit, NativeControl, NativePerformance
from musical_fm_target import project_fm


def voice(identity='v', algorithm=7, tl=0, **extra):
    operators = tuple(tuple(dict(dt=0, dt1=0, mul=1, tl=tl, ks=0, ar=31,
        am_enabled=0, d1r=5, d2r=2, sl=0, d1l=0, rr=7).items()) for _ in range(4))
    values = dict(algorithm=algorithm, feedback=0, operators=operators, ams=0, pms=0)
    values.update(extra)
    return NativeVoice(identity, 'source', 'fm', tuple(values.items()))


def unit(**changes):
    base = NativeUnit('u', 'source', 'fm', 0, 10, 90,
        ((10, 440.), (50, 880.)), ((10, 10), (60, 20)), ((10, 'v'),), source_indices=(3, 4))
    return replace(base, **changes)


def performance(u=None, controls=(), voices=None, chip='opn2', clock=7670454):
    return NativePerformance((NativeDevice('source', chip, 0, clock),),
        (unit() if u is None else u,), tuple(controls), (voice(),) if voices is None else tuple(voices),
        (), (), 120, '', '')


def control(kind, sample, order, channel=0, section='fm', **parameters):
    return NativeControl(str(order), 'source', section, channel, sample, order,
        kind, tuple(parameters.items()))


class MusicalFMProjectionTests(unittest.TestCase):
    def test_authored_curves_without_source_or_events(self):
        rows, losses, mapping = project_fm(performance(), 'opm', 3579545)
        self.assertEqual(mapping, {('source', 0): 0})
        self.assertEqual([r['sample'] for r in rows if r['command'][1] == 0x28], [10, 50])
        self.assertEqual([r['command'][2] for r in rows if r['command'][1] == 0x60], [10, 20])
        self.assertTrue(all(r['source_indices'] == (3, 4) for r in rows))
        self.assertEqual([(r['sample'], r['command'][2]) for r in rows if r['command'][1] == 8], [(10, 120), (90, 0)])

    def test_edits_override_redundant_pitch_voice_and_level_evidence(self):
        evidence = [control('opna_frequency_low', 50, 5, register=0xa0, port=0, fnum_low=1),
            control('fm_operator_level', 60, 6, register=0x40, port=0, total_level=127)]
        edited = unit(pitch_curve=((10, 220.), (50, 660.)), volume_curve=((10, 2), (60, 3)),
            voice_curve=((10, 'v'), (55, 'w')))
        rows, _, _ = project_fm(performance(edited, evidence, (voice(), voice('w', tl=7))), 'opna', 8000000)
        self.assertEqual([r['command'][2] for r in rows if r['command'][1] == 0x40], [2, 9, 10])
        self.assertEqual([r['sample'] for r in rows if r['command'][1] == 0xb0], [10, 55])
        self.assertFalse(any(r['command'] == bytes((0x56, 0x40, 127)) for r in rows))

    def test_atomic_pitch_high_low_pairs_retained(self):
        rows, _, _ = project_fm(performance(), 'opna', 8000000)
        pitch = [r for r in rows if r['command'][1] in (0xa0, 0xa4)]
        self.assertEqual([(r['sample'], r['command'][1]) for r in pitch], [(10, 0xa4), (10, 0xa0), (50, 0xa4), (50, 0xa0)])

    def test_only_carriers_receive_curve_attenuation(self):
        rows, _, _ = project_fm(performance(voices=(voice(algorithm=0, tl=3),)), 'opm', 3579545)
        onset = {r['command'][1]: r['command'][2] for r in rows if r['sample'] == 10}
        self.assertEqual([onset[0x60+i*8] for i in range(4)], [3, 3, 3, 13])

    def test_partial_keys_and_same_sample_retrigger_order(self):
        keys = [control('opna_key', at, order, key_mask=mask) for at, order, mask in
            [(10, 1, 1), (10, 2, 3), (30, 3, 1), (40, 4, 0), (40, 5, 7), (90, 6, 0)]]
        rows, _, _ = project_fm(performance(controls=keys), 'opm', 3579545)
        actual = [(r['sample'], r['command'][2] >> 3) for r in rows if r['command'][1] == 8]
        self.assertEqual(actual, [(10, 1), (10, 3), (30, 1), (40, 0), (40, 7), (90, 0)])

    def test_moved_onset_restores_observed_partial_mask(self):
        keys = [control('opna_key', 10, 1, key_mask=1), control('opna_key', 90, 2, key_mask=0)]
        rows, _, _ = project_fm(performance(unit(start_sample=5, pitch_curve=((5, 440.),)), keys), 'opm', 3579545)
        onset = next(r for r in rows if r['command'][1] == 8)
        self.assertEqual((onset['sample'], onset['command'][2] >> 3), (5, 1))

    def test_unit_gate_edit_supersedes_old_full_off(self):
        keys = [control('opna_key', 10, 1, key_mask=15), control('opna_key', 90, 2, key_mask=0)]
        rows, losses, _ = project_fm(performance(unit(end_sample=110), keys), 'opm', 3579545)
        self.assertEqual([r['sample'] for r in rows if r['command'][1] == 8], [10, 110])
        self.assertEqual(losses['fm_observed_key_off_superseded_by_unit_gate'], 1)

    def test_same_chip_shared_lfo_and_timer_retained(self):
        cs = [control('opm_lfo_rate', 0, 1, None, 'shared', register=0x18, port=0, rate=0xaa),
              control('opm_timer_a_high', 0, 2, None, 'shared', register=0x10, port=0, timer_a_high=23)]
        rows, losses, _ = project_fm(performance(controls=cs, chip='opm', clock=3579545), 'opm', 3579545)
        self.assertIn(bytes((0x54, 0x18, 0xaa)), [r['command'] for r in rows])
        self.assertIn(bytes((0x54, 0x10, 23)), [r['command'] for r in rows])
        self.assertFalse(losses)

    def test_cross_lfo_approximation_and_unsupported_mode_reported(self):
        cs = [control('opna_lfo', 0, 1, None, 'shared', register=0x22, port=0, rate=4, enabled=1),
              control('opna_mode', 0, 2, None, 'shared', register=0x27, port=0, timer_flags=0, channel3_special=1, csm=1)]
        rows, losses, _ = project_fm(performance(controls=cs), 'opm', 3579545)
        self.assertTrue(any(r['command'][1] == 0x18 for r in rows))
        self.assertEqual(losses['fm_lfo_cross_chip_approximation'], 1)
        self.assertEqual(losses['fm_shared_opna_mode_unsupported_on_opm'], 1)

    def test_native_channel3_special_frequencies_rescaled_atomically(self):
        cs = [control('opna_frequency_high', 20, 1, 2, register=0xac, port=0, fnum_high=3, block=4),
              control('opna_frequency_low', 20, 2, 2, register=0xa8, port=0, fnum_low=20)]
        rows, _, allocation = project_fm(performance(unit(channel=2), cs, chip='opna', clock=8000000), 'opna', 8000000)
        self.assertEqual(allocation[('source', 2)], 2)
        special = [r['command'][1] for r in rows if 'channel3 special' in r['reason']]
        self.assertEqual(special, [0xac, 0xa8])

    def test_lfo_depth_tracks_measured_active_voice_maximum(self):
        cs = [control('opna_lfo', 0, 1, None, 'shared', register=0x22, port=0, rate=4, enabled=1)]
        u = unit(voice_curve=((10, 'v'), (55, 'w')))
        rows, _, _ = project_fm(performance(u, cs,
            (voice(pms=1, ams=1), voice('w', pms=7, ams=3))), 'opm', 3579545)
        depths = [(r['sample'], r['command'][2]) for r in rows if r['command'][1] == 0x19]
        self.assertIn((10, 0x80 | 85), depths)
        self.assertIn((10, 8), depths)
        self.assertIn((55, 0x80 | 15), depths)
        self.assertIn((55, 16), depths)

    def test_opm_shared_depth_changes_reproject_channel_sensitivity(self):
        from opm_target_vgm import _opna_pms, _opna_ams, _OPM_PMS_FULL_CENTS, _OPM_AMS_FULL_DB
        cs = [control('opm_modulation_depth', 0, 1, None, 'shared', register=0x19, port=0,
                      phase_modulation=1, depth=10),
              control('opm_modulation_depth', 40, 2, None, 'shared', register=0x19, port=0,
                      phase_modulation=1, depth=127),
              control('opm_modulation_depth', 45, 3, None, 'shared', register=0x19, port=0,
                      phase_modulation=0, depth=127)]
        rows, _, _ = project_fm(performance(controls=cs, voices=(voice(pms=7, ams=3),),
            chip='opm', clock=3579545), 'opna', 8000000)
        sensitivities = {r['sample']: r['command'][2] for r in rows if r['command'][1] == 0xb4}
        self.assertEqual(sensitivities[10] & 7, _opna_pms(_OPM_PMS_FULL_CENTS[7]*10/127))
        self.assertEqual(sensitivities[40] & 7, _opna_pms(_OPM_PMS_FULL_CENTS[7]))
        self.assertEqual((sensitivities[45] >> 4) & 3, _opna_ams(_OPM_AMS_FULL_DB[3]))

    def test_unknown_pitch_is_explicitly_muted(self):
        rows, losses, _ = project_fm(performance(unit(pitch_curve=((10, None),))), 'opm', 3579545)
        self.assertFalse(rows)
        self.assertEqual(losses['fm_unknown_pitch_units_muted'], 1)

    def test_observation_end_does_not_invent_loop_key_off(self):
        u = unit(end_sample=120, parameters=(('termination', 'source_observation_end'),))
        p = replace(performance(u), song_loop_sample=20)
        rows, _, _ = project_fm(p, 'opm', 3579545)
        self.assertEqual([r['sample'] for r in rows if r['command'][1] == 8], [10])

    def test_capacity_omission_explicit(self):
        p = performance()
        p = replace(p, units=tuple(replace(unit(), unit_id=str(ch), channel=ch) for ch in range(8)))
        with self.assertRaisesRegex(ValueError, 'capacity'):
            project_fm(p, 'opna', 8000000)
        _, losses, allocation = project_fm(p, 'opna', 8000000, force=True)
        self.assertEqual(len(allocation), 6)
        self.assertEqual(losses['fm_units_omitted_capacity'], 2)


if __name__ == '__main__':
    unittest.main()


class ZeroWidthFMTests(unittest.TestCase):
    def test_authored_zero_width_gate_ends_after_onset(self):
        p=performance(u=unit(end_sample=10,pitch_curve=((10,440.),),volume_curve=((10,10),)))
        rows,_,_=project_fm(p,'opm',3579545)
        keys=[r['command'][2] for r in rows if r['command'][1]==8]
        self.assertEqual(keys,[0x78,0])
