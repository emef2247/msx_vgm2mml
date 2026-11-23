"""PSG layered profiles: native AY lanes plus FM doublings, PSG-only sources."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_music import NativeDevice, NativeVoice, NativeUnit, NativePerformance
from musical_variants import project_variant, export_variants
from musical_wave_target import project_waves

TONE = (('mode', 1), ('hardware_envelope', False), ('envelope_shape', None))
NOISE = (('mode', 2), ('hardware_envelope', False), ('envelope_shape', None))


def performance(chip='psg', voice=TONE, voice_curve=None, end=4410):
    d = NativeDevice(chip + ':0', chip, 0, 1789773)
    v = NativeVoice('voice', d.device_id, 'tone', voice)
    u = NativeUnit('unit', d.device_id, 'tone', 0, 0, end,
                   ((0, 440.),), ((0, 15),), voice_curve or ((0, 'voice'),))
    return NativePerformance((d,), (u,), (), (v,), (), (), end, '', '')


class PsgLayeredProfileTests(unittest.TestCase):
    def test_profiles_stack_native_ay_with_fm_doubling(self):
        p = performance()
        commands = {}
        for profile in ('psg_layered', 'sfg01'):
            rows, _, losses, plan = project_variant(p, profile, force=True)
            commands[profile] = {row['command'][0] for row in rows}
        self.assertTrue({0xa0, 0x54, 0x56} <= commands['psg_layered'])
        # The base profile keeps the PSG native-only: no FM doubling.
        self.assertIn(0xa0, commands['sfg01'])
        self.assertNotIn(0x54, commands['sfg01'])
        _, _, _, plan = project_variant(p, 'psg_layered', force=True)
        self.assertTrue(plan['psg_fm_doubling'])

    def test_profiles_require_a_psg_only_source(self):
        psg = performance()
        d = NativeDevice('scc:0', 'scc', 0, 1789773)
        v = NativeVoice('sccvoice', d.device_id, 'tone',
                        (('waveform_hex', '7f' * 16 + '80' * 16),))
        u = NativeUnit('sccunit', d.device_id, 'tone', 0, 0, 4410,
                       ((0, 440.),), ((0, 15),), ((0, 'sccvoice'),))
        mixed = NativePerformance((*psg.devices, d), (*psg.units, u), (),
                                  (*psg.voices, v), (), (), 4410, '', '')
        with self.assertRaisesRegex(ValueError, 'PSG-only'):
            project_variant(mixed, 'psg_layered', force=True)
        scc_only = NativePerformance((d,), (u,), (), (v,), (), (), 4410, '', '')
        with self.assertRaisesRegex(ValueError, 'No sounding PSG units'):
            project_variant(scc_only, 'psg_layered', force=True)

    def test_export_reports_psg_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = export_variants(performance(), tmp, 'authored', force=True)
            self.assertEqual(result['psg_layered']['status'], 'success')
            result = export_variants(performance(chip='scc'), tmp, 'authored',
                                     force=True)
            self.assertEqual(result['psg_layered']['status'], 'unavailable')
            self.assertIn('No sounding PSG units', result['psg_layered']['reason'])

    def test_noise_intervals_rest_the_fm_layer(self):
        d = NativeDevice('psg:0', 'psg', 0, 1789773)
        tone = NativeVoice('tone', d.device_id, 'tone', TONE)
        noise = NativeVoice('noise', d.device_id, 'tone', NOISE)
        u = NativeUnit('unit', d.device_id, 'tone', 0, 0, 3000,
                       ((0, 440.),), ((0, 15),),
                       ((0, 'tone'), (1000, 'noise'), (2000, 'tone')))
        p = NativePerformance((d,), (u,), (), (tone, noise), (), (), 3000, '', '')
        rows, losses, _ = project_waves(p, 'opm', 3579545, force=True,
                                        include_psg=True)
        starts = [r for r in rows if r['reason'] == 'musical gate start']
        self.assertEqual(len(starts), 2)
        self.assertEqual(losses['psg_noise_only_intervals_not_doubled'], 1)
        # Without the opt-in the PSG unit is not a wave source at all.
        rows, _, _ = project_waves(p, 'opm', 3579545, force=True)
        self.assertEqual(rows, [])


if __name__ == '__main__':
    unittest.main()
