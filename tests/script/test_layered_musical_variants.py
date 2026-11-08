"""Layered cartridge composition keeps independent FM and single shared parts."""
from dataclasses import replace
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from native_music import NativeDevice, NativeVoice, NativeUnit
from native_imports.vgm_timing import command_times
from musical_variants import _write, export_variants, project_variant
from test_musical_fm_target import performance, unit
from test_musical_variants import performance as wave_performance


class LayeredMusicalVariantTests(unittest.TestCase):
    def test_both_fm_chips_follow_gates_and_edited_pitch_with_one_psg_part(self):
        p = performance()
        psg = NativeDevice('psg:0', 'psg', 0, 1789773)
        voice = NativeVoice('psgvoice', psg.device_id, 'tone',
                            (('mode', 1), ('hardware_envelope', False)))
        tone = NativeUnit('psgunit', psg.device_id, 'tone', 0, 10, 90,
                          ((10, 220.),), ((10, 12),), ((10, voice.voice_id),))
        p = replace(p, devices=(*p.devices, psg), voices=(*p.voices, voice),
                    units=(*p.units, tone), song_loop_sample=50)
        rows, prefix, _, plan = project_variant(p, 'layered')
        commands = lambda rs, chip: [(r['sample'], r['command']) for r in rs
                                     if r['command'][0] == chip]
        self.assertEqual([(at, cmd[2]) for at, cmd in commands(rows, 0x54) if cmd[1] == 8],
                         [(10, 0x78), (90, 0)])
        self.assertEqual([(at, cmd[2]) for at, cmd in commands(rows, 0x56) if cmd[1] == 0x28],
                         [(10, 0xf0), (90, 0)])
        self.assertEqual({r['sample'] for r in rows if r['command'][:2] == bytes((0x54, 0x28))}, {10, 50})
        for at, expected in ((10, 440), (50, 880)):
            pitch = {r['command'][1]: r['command'][2] for r in rows
                     if r['sample'] == at and r['command'][0] == 0x56
                     and r['command'][1] in (0xa0, 0xa4)}
            high, low = pitch[0xa4], pitch[0xa0]
            hz = ((high & 7) * 256 + low) * 8000000 / (144 * 2 ** (21 - ((high >> 3) & 7)))
            self.assertAlmostEqual(hz, expected, delta=1)
        single, _, _, _ = project_variant(p, 'makoto')
        self.assertEqual(commands(rows, 0xa0), commands(single, 0xa0))
        self.assertEqual(set(plan['fm_layers']), {'opm', 'opna'})
        edited = replace(p, units=(replace(p.units[0], pitch_curve=((10, 220.), (50, 660.))), tone))
        altered, _, _, _ = project_variant(edited, 'layered')
        for chip, register in ((0x54, 0x28), (0x56, 0xa0)):
            before = [cmd for at, cmd in commands(rows, chip) if cmd[1] == register]
            after = [cmd for at, cmd in commands(altered, chip) if cmd[1] == register]
            self.assertNotEqual(before, after)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'layered.vgm'
            _write(p, rows, prefix, path)
            raw = path.read_bytes()
            self.assertEqual(struct.unpack_from('<I', raw, 0x30)[0], 3579545)
            self.assertEqual(struct.unpack_from('<I', raw, 0x48)[0], 8000000)
            events = tuple(command_times(raw))
            self.assertEqual(events[-1].vgmticks, p.end_sample)
            loop_address = struct.unpack_from('<I', raw, 0x1c)[0] + 0x1c
            self.assertEqual(next(event.vgmticks for event in events if event.address == loop_address), 50)

    def test_target_capacities_and_omissions_remain_separate(self):
        p = performance(chip='opm', clock=3579545)
        p = replace(p, units=tuple(unit(unit_id=str(ch), channel=ch) for ch in range(8)))
        with self.assertRaisesRegex(ValueError, 'FM target capacity exceeded'):
            project_variant(p, 'layered')
        rows, _, losses, plan = project_variant(p, 'layered', force=True)
        layers = plan['fm_layers']
        self.assertEqual(len(layers['opm']['fm_allocation']), 8)
        self.assertEqual(len(layers['opna']['fm_allocation']), 6)
        self.assertNotIn('fm_units_omitted_capacity', layers['opm']['losses'])
        self.assertEqual(layers['opna']['losses']['fm_units_omitted_capacity'], 2)
        self.assertEqual(losses['fm_units_omitted_capacity'], 2)
        self.assertEqual(len({r['unit_id'] for r in rows if r['command'][0] == 0x54 and r['unit_id']}), 8)

    def test_opna_calibration_does_not_change_sfg01_layer(self):
        p = performance()
        plain, _, _, _ = project_variant(p, 'layered')
        calibrated, _, _, _ = project_variant(p, 'layered', opna_law=True)
        commands = lambda rows, chip: [r['command'] for r in rows if r['command'][0] == chip]
        self.assertEqual(commands(plain, 0x54), commands(calibrated, 0x54))
        self.assertNotEqual(commands(plain, 0x56), commands(calibrated, 0x56))

    def test_waveform_fm_approximation_is_layered_without_a_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = export_variants(wave_performance(), tmp, 'authored', force=True)['layered']
            self.assertEqual(result['status'], 'success')
            self.assertFalse(result['source_file_consulted'])
            self.assertTrue(all(layer['waveform_allocation'] for layer in result['plan']['fm_layers'].values()))
            raw = Path(result['path']).read_bytes()
            commands = {event.command for event in command_times(raw)}
            self.assertTrue({0x54, 0x56}.issubset(commands))


if __name__ == '__main__':
    unittest.main()
