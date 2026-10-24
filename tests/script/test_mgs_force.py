"""Authored source inventories exercise force without changing native input."""
import csv
import gzip
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from mgs_force import inspect_projection, MgsProjectionError


def source(commands, *, scc=0):
    header = bytearray(0x100)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 4, len(header) + len(commands) - 4)
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
    struct.pack_into('<I', header, 0x9c, scc)
    return bytes(header) + commands


class MgsForceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def inspect(self, raw, force=False):
        path = self.folder / 'authored.vgm'
        path.write_bytes(raw)
        return inspect_projection(path, self.folder, 'authored', force)

    def artifact(self, kind):
        return json.loads((self.folder / f'authored.mgs.{kind}.json').read_text())

    def test_valid_supported_writes_emit_zero_inventory(self):
        result = self.inspect(source(b'\xa0\x08\x0f\x51\x20\x10\x66'))
        self.assertEqual(result['omission_count'], 0)
        self.assertEqual(self.artifact('source')['supported_write_count'], 2)
        self.assertTrue(Path(result['csv_path']).is_file())

    def test_mixed_source_strict_blocks_and_force_reports_exact_write(self):
        raw = source(b'\xa0\x08\x0f\x62\x54\x20\xc7\x66')
        with self.assertRaises(MgsProjectionError):
            self.inspect(raw)
        self.assertEqual(self.artifact('force')['omission_count'], 0)
        result = self.inspect(raw, True)
        self.assertEqual(result['omission_count'], 1)
        row = result['omissions'][0]
        self.assertEqual((row['chip'], row['register'], row['data'], row['vgmticks']),
                         ('OPM', 0x20, 0xc7, 735))
        self.assertEqual((self.folder / 'authored.vgm').read_bytes(), raw)
        with Path(result['csv_path']).open(newline='') as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_clock_only_unsupported_declarations_do_not_block(self):
        raw = bytearray(source(b'\xa0\x08\x00\x66'))
        struct.pack_into('<I', raw, 0x30, 4000000)
        self.assertEqual(self.inspect(raw)['omission_count'], 0)

    def test_malformed_unknown_truncated_and_missing_end_always_fatal(self):
        for force in (False, True):
            for tail in (b'\x01\x66', b'\x61', b'\x62'):
                with self.subTest(force=force, tail=tail):
                    with self.assertRaises(MgsProjectionError):
                        self.inspect(source(b'\xa0\x08\x0f\x54\x20\x00' + tail), force)
                    self.assertEqual(self.artifact('force')['omission_count'], 0)
                    self.assertIsNotNone(self.artifact('source')['validation_error'])

    def test_unsupported_only_does_not_produce_silent_success(self):
        with self.assertRaisesRegex(MgsProjectionError, 'No supported'):
            self.inspect(source(b'\x54\x20\xc7\x66'), True)

    def test_scc_valid_ports_and_declared_clock(self):
        raw = source(b'\xd2\x00\x7f\x44\xd2\x01\x09\x01'
                     b'\xd2\x02\x04\x0f\xd2\x03\x00\x1f\x66', scc=3579545)
        self.assertEqual(self.inspect(raw)['omission_count'], 0)

    def test_scc_unsafe_port_address_variant_and_undeclared_are_not_forceable(self):
        for clock, port, address in ((3579545, 4, 0), (3579545, 0x80, 0),
                (3579545, 2, 5), (3579545 | 0x80000000, 0, 0)):
            for force in (False, True):
                with self.subTest(clock=clock, port=port, address=address, force=force):
                    raw = source(b'\xa0\x08\x00' + bytes([0xd2, port, address, 0, 0x66]), scc=clock)
                    with self.assertRaises(MgsProjectionError):
                        self.inspect(raw, force)

    def test_undeclared_scc_initialization_retains_legacy_reader_behavior(self):
        raw = source(b'\xa0\x08\x0f\xd2\x00\x01\x55\xd2\x02\x00\x00\x66')
        self.inspect(raw)
        self.assertEqual(self.artifact('source')['undeclared_scc_initialization_count'], 2)
        self.assertEqual(self.artifact('source')['supported_write_count'], 1)
        self.assertEqual(self.artifact('force')['omission_count'], 0)
        for force in (False, True):
            with self.assertRaisesRegex(MgsProjectionError, 'Active SCC writes'):
                self.inspect(source(b'\xa0\x08\x0f\xd2\x02\x00\x0f\x66'), force)

    def test_repeated_blockers_have_bounded_exception_and_full_inventory(self):
        raw = source(b'\xa0\x88\x0f' * 100 + b'\x66')
        with self.assertRaises(MgsProjectionError) as caught:
            self.inspect(raw, True)
        self.assertLess(len(str(caught.exception)), 1000)
        self.assertEqual(len(self.artifact('force')['blocked']), 101)

    def test_second_ay_and_opll_test_mode_cannot_be_forced(self):
        for commands in (b'\xa0\x88\x0f\x66', b'\x51\x0f\x01\x66'):
            with self.assertRaises(MgsProjectionError):
                self.inspect(source(commands), True)

    def test_pcm_commands_and_uninventoried_writes_cannot_be_forced(self):
        for command in (b'\x67\x66\x00\x00\x00\x00\x00',
                        b'\xe0\x00\x00\x00\x00', b'\x90\x00\x00\x00\x00',
                        b'\x80', b'\x52\x20\x00'):
            for force in (False, True):
                with self.subTest(command=command, force=force):
                    with self.assertRaises(MgsProjectionError):
                        self.inspect(source(b'\xa0\x08\x00' + command + b'\x66'), force)

    def test_all_whitelisted_write_layouts(self):
        commands = (b'\xa0\x08\x00\x54\x20\x01\xa4\x21\x02'
                    b'\x56\x22\x03\x57\x23\x04\xa6\x24\x05\xa7\x25\x06'
                    b'\x50\x80\x30\x81\x4f\xff\x3f\xfe\xb7\x82\x03'
                    b'\xc0\x34\x92\x07\xa1\x20\x10\x66')
        result = self.inspect(source(commands), True)
        self.assertEqual(result['omission_count'], 13)
        msm = next(r for r in result['omissions'] if r['chip'] == 'MSM6258')
        sega = next(r for r in result['omissions'] if r['chip'] == 'SegaPCM')
        self.assertEqual((msm['instance'], msm['register']), (1, 2))
        self.assertEqual((sega['instance'], sega['register']), (1, 0x1234))

    def test_invalid_header_and_gzip_always_leave_failure_reports(self):
        for raw in (b'bad', b'\x1f\x8btruncated'):
            for force in (False, True):
                with self.assertRaises(MgsProjectionError):
                    self.inspect(raw, force)
                self.assertTrue(self.artifact('force')['blocked'])
        result = self.inspect(gzip.compress(source(b'\xa0\x08\x0f\x66')))
        self.assertEqual(result['omission_count'], 0)

    def test_eof_and_loop_offsets_are_validated_before_omitting(self):
        for offset, value in ((4, 100000), (0x1c, 0x100 - 0x1c + 1)):
            raw = bytearray(source(b'\xa0\x08\x00\x54\x20\x01\x66'))
            struct.pack_into('<I', raw, offset, value)
            with self.assertRaises(MgsProjectionError):
                self.inspect(raw, True)
            self.assertEqual(self.artifact('force')['omission_count'], 0)


if __name__ == '__main__':
    unittest.main()
