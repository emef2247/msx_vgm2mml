"""Authored native-source imports retain original clocks/evidence and isolation."""
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'py'))
from native_imports import analyze_source, inspect_source


def vgm(commands, clocks=None, fields=None):
    raw=bytearray(256);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x171)
    struct.pack_into('<I',raw,0x34,256-0x34)
    for offset,value in (clocks or {}).items():
        struct.pack_into('<I',raw,offset,value)
    for offset,value in (fields or {}).items():
        raw[offset]=value
    raw.extend(commands);raw.append(0x66)
    struct.pack_into('<I',raw,4,len(raw)-4)
    return bytes(raw)


def block(kind, payload, instance=0):
    return b'\x67\x66'+bytes((kind,))+struct.pack('<I',len(payload)|(instance<<31))+payload


class NativeImportTests(unittest.TestCase):
    def analyze(self, raw):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        return analyze_source(raw,folder,'authored'),folder

    def test_unused_clock_declarations_do_not_activate_engines(self):
        raw=vgm(bytes.fromhex('a0 08 00 62'),{0x30:4000000,0x48:8000000,
            0x0c:3579545,0x90:4000000,0x98:1000000,0x38:4000000,0xa8:8000000})
        result,_=self.analyze(raw)
        self.assertEqual(result['active_chips'],())
        self.assertTrue(all(analysis is None for analysis in result['analyses'].values()))
        self.assertEqual(result['source_end_sample'],735)

    def test_all_seven_native_domains_share_exact_source_clock(self):
        commands=bytes.fromhex('54 20 c7 54 28 4a 54 08 78 56 b0 07 56 a0 a0 '
            '56 a4 22 56 28 f0 50 85 50 08 b7 00 01 b7 01 11 b8 00 80 '
            'b8 00 10 c0 02 00 40 d4 00 05 80 77 7a 54 08 00 56 28 00')
        raw=vgm(commands,{0x30:4000000,0x48:8000000,0x0c:3579545,0x90:4000000,
                          0x98:1000000,0x38:4000000,0xa8:8000000})
        result,folder=self.analyze(raw)
        self.assertEqual(set(result['active_chips']),{'opm','opna','dcsg','msm6258','msm6295','segapcm','c140'})
        self.assertEqual(result['errors'],{})
        self.assertTrue(all(result['analyses'].values()))
        self.assertEqual(result['source_end_sample'],19)
        self.assertEqual(result['opm'].source_end_vgmticks,19)
        self.assertEqual(result['opna'].source_end_vgmticks,19)
        self.assertEqual(result['raw'],raw)
        self.assertTrue((folder/'authored.native.opm.registers.csv').is_file())
        self.assertTrue((folder/'authored.native.opna.unmodeled.csv').is_file())
        self.assertEqual(json.loads((folder/'authored.native.source.json').read_text())['source_end_sample'],19)

    def test_unwritten_opm_operator_state_is_unknown_not_filled(self):
        result,_=self.analyze(vgm(bytes.fromhex('54 28 4a 54 08 78 62'),{0x30:4000000}))
        state=next(segment.state for segment in result['opm'].segments if segment.ch==0 and segment.state.key_mask)
        self.assertTrue(any(value is None for operator in state.operators for value in asdict(operator).values()))

    def test_dual_fm_instances_and_dual_dcsg_are_not_collapsed(self):
        raw=vgm(bytes.fromhex('54 08 78 a4 08 78 56 28 f0 a6 28 f0 50 90 30 90 62'),
                {0x30:0x40000000|4000000,0x48:0x40000000|8000000,0x0c:0x40000000|3579545})
        result,_=self.analyze(raw)
        self.assertEqual(result['errors'],{})
        self.assertEqual({s.chip_instance for s in result['opm'].segments},{0,1})
        self.assertEqual({s.chip_instance for s in result['opna'].segments},{0,1})
        self.assertEqual({s.chip_instance for s in result['dcsg'].segments},{0,1})

    def test_pcm_unsupported_variant_does_not_block_fm_or_erase_commands(self):
        raw=vgm(bytes.fromhex('54 08 78 d4 00 05 80 b8 80 81 62'),
                {0x30:4000000,0xa8:8000000,0x98:0x40000000|1000000},{0x96:2})
        result,_=self.analyze(raw)
        self.assertIsNotNone(result['opm'])
        self.assertIn('unsupported_chip_type_2',result['c140'].issues)
        self.assertIn('second_msm6295_write_unsupported',result['msm6295'].issues)
        self.assertEqual(result['raw'],raw)
        self.assertTrue(result['report']['interpretation_issues']['c140'])

    def test_bad_pcm_rom_is_a_local_analysis_error_not_global_omission(self):
        raw=vgm(block(0x8b,struct.pack('<II',8,7)+b'outside')+bytes.fromhex('54 08 78 62'),
                {0x30:4000000,0x98:1000000})
        result,folder=self.analyze(raw)
        self.assertIsNotNone(result['opm'])
        self.assertIsNone(result['msm6295'])
        self.assertTrue(result['errors']['msm6295']['native_commands_retained'])
        self.assertEqual(result['raw'],raw)
        self.assertTrue((folder/'authored.native.commands.csv').is_file())

    def test_data_payload_bytes_are_not_interpreted_as_chip_commands(self):
        payload=struct.pack('<II',16,0)+bytes.fromhex('54 08 78 62 66 51 20 30')
        raw=vgm(block(0x80,payload)+block(0x8b,payload)+block(0x8d,payload),
                {0x38:4000000,0x98:1000000,0xa8:8000000})
        result,_=self.analyze(raw)
        self.assertEqual(set(result['active_chips']),{'segapcm','msm6295','c140'})
        self.assertEqual(result['source_end_sample'],0)
        self.assertEqual(result['segapcm'].rom_blocks[0].payload,payload[8:])

    def test_stream_setup_and_data_activate_only_the_declared_pcm_domain(self):
        raw=vgm(block(4,b'\x54\x66\x62')+bytes.fromhex('90 00 17 00 01 91 00 04 01 00 62'),
                {0x90:4000000})
        result,_=self.analyze(raw)
        self.assertEqual(result['active_chips'],('msm6258',))
        self.assertEqual(result['source_end_sample'],735)
        self.assertEqual(result['raw'],raw)

    def test_opna_auxiliary_registers_survive_as_unmodeled_evidence(self):
        raw=vgm(bytes.fromhex('56 00 34 56 10 01 57 00 80 62'),{0x48:8000000})
        result,_=self.analyze(raw)
        rows=result['opna'].unmodeled_writes
        self.assertEqual([(r.port,r.register,r.data) for r in rows],[(0,0,0x34),(0,0x10,1),(1,0,0x80)])

    def test_missing_fm_clock_retains_trace_and_reports_analysis_failure(self):
        result,folder=self.analyze(vgm(bytes.fromhex('54 08 78 62')))
        self.assertEqual(result['active_chips'],('opm',))
        self.assertIsNone(result['opm'])
        self.assertIn('opm',result['errors'])
        self.assertTrue((folder/'authored.native.opm.registers.csv').is_file())

    def test_same_sample_writes_keep_original_order_and_nonchanges(self):
        result,_=self.analyze(vgm(bytes.fromhex('54 08 78 54 08 78 54 08 00'),{0x30:4000000}))
        events=[e for e in result['opm'].events if e.ch==0]
        self.assertEqual([e.data for e in events],[0x78,0x78,0])
        self.assertEqual([e.vgmticks for e in events],[0,0,0])
        self.assertEqual([e.source_event_id for e in events],[0,1,2])

    def test_compressed_input_detected_by_magic_not_extension(self):
        raw=vgm(bytes.fromhex('54 08 78 62'),{0x30:4000000})
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'capture.bin';source.write_bytes(gzip.compress(raw))
            result=analyze_source(source,Path(tmp)/'out')
            self.assertEqual(result['raw'],raw)
            self.assertEqual(result['source_sha256'],hashlib.sha256(raw).hexdigest())

    def test_malformed_command_framing_is_not_silently_accepted(self):
        raw=vgm(b'')[:-1]+bytes.fromhex('54 08')
        with self.assertRaisesRegex(ValueError,'Truncated'):
            inspect_source(raw)

    def test_imported_file_hashes_match_provenance(self):
        report=json.loads((ROOT/'docs/native_import_provenance.json').read_text())
        names={row['module'] for row in report['files']}
        self.assertTrue({'opm','opna','dcsg','msm6258','msm6295','segapcm','c140'}<=names)
        for row in report['files']:
            raw=(ROOT/'py/native_imports'/(row['module']+'.py')).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['imported_sha256'])


if __name__=='__main__': unittest.main()
