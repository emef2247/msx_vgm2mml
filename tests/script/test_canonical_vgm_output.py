"""Canonical direct-output branch consumes shared plans without text capacity."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'py')]
import vgm2mml


def authored_psg(path):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    struct.pack_into('<I', raw, 0x74, 1789773)
    commands = bytes.fromhex('a0 07 3e a0 08 0f a0 00 ac a0 01 01 61 be 05 '
                             'a0 08 0c 61 be 05 a0 08 00 61 df 02 66')
    raw.extend(commands)
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    struct.pack_into('<I', raw, 0x18, 3675)
    path.write_bytes(raw)
    return bytes(raw)


class CanonicalVgmTests(unittest.TestCase):
    def test_inherited_sustain_loss_is_reported_without_losing_direct_control(self):
        from test_opll_execution import raw_vgm
        from vgm_timing import command_times
        raw=raw_vgm(bytes.fromhex('51 30 10 51 10 ac 51 20 36 61 be 05 51 20 26'))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'sustain.vgm';source.write_bytes(raw)
            self.invoke(source,root/'out','--output-format','both')
            report=json.loads((root/'out/sustain.conversion.json').read_text())
            self.assertEqual(report['backend_losses'][0]['kind'],'opll_sustain_not_encoded_by_mgs_lowering')
            self.assertTrue(report['backend_losses'][0]['retained_in_shared_plan'])
            output=(root/'out/tracks/sustain.vgm').read_bytes()
            highs=[output[e.address+2] for e in command_times(output)
                   if e.command==0x51 and output[e.address+1]==0x20]
            self.assertTrue(any(value&0x30==0x30 for value in highs))

    def invoke(self, source, output, *options):
        argv = ['vgm2mml.py', str(source), '--outdir', str(output), '--dump-passes', *options]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
            return vgm2mml.main()

    def test_vgm_only_skips_all_mml_lowering_and_preserves_old_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'authored.vgm', root / 'out'
            original = authored_psg(source)
            output.mkdir()
            existing = output / 'authored.mml'
            existing.write_text('user existing text')
            with patch.object(vgm2mml, '_convert_mgs', side_effect=AssertionError('MML is forbidden')):
                self.invoke(source, output, '--output-format', 'vgm')
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(existing.read_text(), 'user existing text')
            self.assertTrue((output / 'tracks/authored.vgm').stat().st_size)
            self.assertTrue((output / 'blueprint/authored.mml').is_file())
            report = json.loads((output / 'authored.conversion.json').read_text())
            self.assertEqual(report['status'], 'success')
            self.assertFalse(report['mml_generated'])
            self.assertFalse(report['compiler_invoked'])

    def test_both_keeps_direct_output_when_mml_backend_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'authored.vgm', root / 'out'
            authored_psg(source)
            with patch.object(vgm2mml, '_convert_mgs', side_effect=ValueError('simulated text capacity')):
                with self.assertRaisesRegex(ValueError, 'text capacity'):
                    self.invoke(source, output, '--output-format', 'both')
            self.assertTrue((output / 'tracks/authored.vgm').stat().st_size)
            report = json.loads((output / 'authored.conversion.json').read_text())
            self.assertEqual(report['status'], 'conversion_failed')
            self.assertTrue(report['direct_vgm']['vgm_sha256'])
            self.assertEqual(report['blueprint']['status'], 'success')
            self.assertTrue((output / 'blueprint/authored.mml').is_file())

    def test_unowned_direct_target_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'authored.vgm', root / 'out'
            authored_psg(source)
            target = output / 'tracks/authored.vgm'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'foreign file')
            with self.assertRaisesRegex(ValueError, 'unowned or modified'):
                self.invoke(source, output, '--output-format', 'vgm')
            self.assertEqual(target.read_bytes(), b'foreign file')

    def test_owned_direct_target_can_be_regenerated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'authored.vgm', root / 'out'
            authored_psg(source)
            self.invoke(source, output, '--output-format', 'vgm')
            first = (output / 'tracks/authored.vgm').read_bytes()
            self.invoke(source, output, '--output-format', 'vgm')
            self.assertEqual((output / 'tracks/authored.vgm').read_bytes(), first)

    def test_mml_renderer_receives_the_same_accepted_performance_objects(self):
        import musical_conversion
        import pre_envelope_loops
        captured, rendered = {}, []
        original_build, original_render = musical_conversion.build_plan, pre_envelope_loops.render

        def build(*args, **kwargs):
            result = original_build(*args, **kwargs)
            captured.update(kwargs['decision_sink'])
            return result

        def render(*args, **kwargs):
            rendered.append(kwargs['performance'])
            return original_render(*args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'authored.vgm', root / 'out'
            authored_psg(source)
            with patch.object(musical_conversion, 'build_plan', side_effect=build), patch.object(
                    pre_envelope_loops, 'render', side_effect=render):
                self.invoke(source, output, '--software-volume-curves')
            accepted = {id(p) for p in captured['performances']}
            self.assertTrue(rendered)
            self.assertTrue(all(id(p) in accepted for p in rendered))
            self.assertTrue((output / 'authored.mml').stat().st_size)

    def test_backend_partition_fallback_preserves_shared_curve_semantics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'authored.vgm', root / 'out'
            authored_psg(source)
            with patch('mgs_envelope_ties.compensate', side_effect=ValueError('authored backend limitation')):
                self.invoke(source, output, '--output-format', 'both', '--software-volume-curves')
            report = json.loads((output / 'authored.volume_curves.target.json').read_text())
            self.assertTrue(report['backend_partition_fallback'])
            self.assertTrue(report['semantic_volume_timeline_unchanged'])
            self.assertTrue(report['shared_clock_preserved'])
            self.assertTrue(report['source_unit_mapping'])
            self.assertTrue((output / 'authored.mml').stat().st_size)
            self.assertTrue((output / 'tracks/authored.vgm').stat().st_size)


if __name__ == '__main__':
    unittest.main()
