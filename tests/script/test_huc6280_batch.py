"""Cross-chip source verification retains playback without claiming register equality."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import batch_vgm_to_mgs as batch
import export_mgs


def vgm(commands=b'\x62', *, huc_clock=0):
    header = bytearray(256)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x34, 256 - 0x34)
    struct.pack_into('<I', header, 0x18, 735)
    struct.pack_into('<I', header, 0xa4, huc_clock)
    raw = header + commands + b'\x66'
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


class Huc6280BatchTests(unittest.TestCase):
    def test_generated_target_vgm_is_not_rediscovered_as_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'authored.vgm'
            source.write_bytes(vgm(b'\xb9\x01\xff\x62'))
            target = root / '_huc6280_target/authored.vgm'
            target.parent.mkdir()
            target.write_bytes(vgm())
            self.assertEqual(batch.discover_inputs(root), [source])
            self.assertEqual(batch.discover_inputs(root, adjacent=True), [source])

    def check(self, raw, *, export_fail=False):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        source = root / 'authored.vgm'
        source.write_bytes(raw)
        mgs = root / 'authored.mgs'
        mgs.write_bytes(b'authored placeholder')
        def playback(command, **kwargs):
            if not export_fail:
                Path(command[3]).write_bytes(vgm())
            return subprocess.CompletedProcess(command, int(export_fail), b'', b'')
        with patch.object(batch.subprocess, 'run', side_effect=playback) as run, patch.object(
                batch, 'compare_files', return_value=dict(reference_keyon=0, actual_keyon=0,
                missing_keyon=0, extra_keyon=0)) as compare:
            result = batch.check_keyons(source, mgs, root, 'node', None, 30)
        self.assertEqual(run.call_count, 1)
        self.assertTrue((root / 'authored.roundtrip.vgm').is_file())
        return result, compare.call_count

    def test_actual_huc_write_marks_projected_after_playback(self):
        result, comparisons = self.check(vgm(b'\xb9\x00\x00\x62'))
        self.assertEqual(result['keyon_status'], 'projected_source')
        self.assertIn('exported', result['keyon_error'])
        self.assertIn('not applicable', result['keyon_error'])
        self.assertNotIn('reference_keyon', result)
        self.assertEqual(comparisons, 0)

    def test_header_only_huc_clock_keeps_existing_comparison(self):
        result, comparisons = self.check(vgm(huc_clock=3579545))
        self.assertEqual(result['reference_keyon'], 0)
        self.assertEqual(comparisons, 1)

    def test_payload_huc_byte_is_not_a_register_command(self):
        block = b'\x67\x66\x00' + struct.pack('<I', 3) + b'\xb9\x00\x00'
        result, comparisons = self.check(vgm(block + b'\x62'))
        self.assertEqual(result['reference_keyon'], 0)
        self.assertEqual(comparisons, 1)

    def test_projection_does_not_hide_playback_failure(self):
        with self.assertRaisesRegex(ValueError, 'no VGM'):
            self.check(vgm(b'\xb9\x00\x00\x62'), export_fail=True)

    def test_export_accepts_successful_projected_playback(self):
        with patch.object(export_mgs, 'run_batch', return_value=[dict(
                status='success', keyon_status='projected_source')]):
            self.assertEqual(export_mgs.main(['authored.vgm']), 0)

    def test_batch_records_projected_status_with_empty_count_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'authored.vgm'
            source.write_bytes(vgm(b'\xb9\x00\x00\x62'))
            def execute(command, **kwargs):
                if str(command[1]).endswith('vgm2mml.py'):
                    (Path(command[4]) / 'authored.mml').write_text('authored')
                elif command[0] == 'fake-mgsc':
                    Path(command[2]).write_bytes(b'authored')
                elif str(command[1]).endswith('mgs_to_vgm.mjs') and '--check' not in command:
                    Path(command[3]).write_bytes(vgm())
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch.object(batch.shutil, 'which', return_value='fake-mgsc'), patch.object(
                    batch.subprocess, 'run', side_effect=execute), patch.object(batch, 'compare_files') as compare:
                rows = batch.run_batch(source, root / 'out')
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row['status'], 'success')
            self.assertEqual(row['keyon_status'], 'projected_source')
            self.assertTrue(all(row[name] == '' for name in batch.KEYON_FIELDS))
            compare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
