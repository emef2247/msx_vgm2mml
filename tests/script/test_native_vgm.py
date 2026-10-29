"""Native source -> musical units -> independently encoded multi-chip VGM."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/script')]
from native_source_music import build_native_performance
from native_vgm import write_native_vgm, scheduled_native_writes
from native_imports.vgm_timing import command_times
from musical_conversion import build_plan
from musical_vgm import write_vgm
from test_native_imports import vgm, block


def signature(raw):
    events=tuple(command_times(raw))
    return [(event.vgmticks,raw[event.address:events[i+1].address])
            for i,event in enumerate(events[:-1])
            if event.command not in (0x61,0x62,0x63,0x64) and not 0x70<=event.command<=0x7f]


class NativeVgmTests(unittest.TestCase):
    def build(self,raw,folder):
        source=folder/'source.vgm';source.write_bytes(raw)
        performance=build_native_performance(source,folder/'source_passes','source')
        return source,performance

    def test_all_seven_chips_preserve_source_clock_and_complete_write_sequence(self):
        commands=bytes.fromhex('54 20 c7 54 28 4a 54 30 04 54 08 78 56 b0 07 '
            '56 a4 22 56 a0 a0 56 28 f0 50 85 50 08 50 90 b7 00 01 b7 01 11 '
            'b8 00 80 b8 00 10 c0 02 00 40 d4 00 05 80 77 7a 54 08 00 56 28 00')
        raw=vgm(commands,{0x30:4000000,0x48:8000000,0x0c:3579545,0x90:4000000,
                         0x98:1000000,0x38:4000000,0xa8:8000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,performance=self.build(raw,root)
            source.unlink()
            rows=write_native_vgm(performance,root/'rebuilt.vgm',mapping_path=root/'writes.csv')
            output=(root/'rebuilt.vgm').read_bytes()
            self.assertEqual(signature(output),signature(raw))
            self.assertEqual(tuple(command_times(output))[-1].vgmticks,19)
            self.assertEqual({d.chip for d in performance.devices},
                {'opm','opna','dcsg','msm6258','msm6295','segapcm','c140'})
            self.assertTrue(any(row['preserved_pcm'] for row in rows))
            self.assertTrue(any(not row['preserved_pcm'] for row in rows))

    def test_native_control_and_clock_are_the_output_authority(self):
        raw=vgm(bytes.fromhex('54 28 4a 54 30 00 54 08 78 62 54 08 00'),{0x30:4000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,performance=self.build(raw,root)
            controls=[]
            for control in performance.controls:
                if control.kind=='opm_pitch_note':
                    values=dict(control.parameters);values['octave']=5
                    control=replace(control,parameters=tuple(values.items()))
                controls.append(control)
            devices=tuple(replace(d,clock_hz=3579545) if d.chip=='opm' else d for d in performance.devices)
            changed=replace(performance,controls=tuple(controls),devices=devices)
            write_native_vgm(changed,root/'changed.vgm')
            output=(root/'changed.vgm').read_bytes()
            self.assertEqual(int.from_bytes(output[0x30:0x34],'little')&0x3fffffff,3579545)
            writes=[data for _,data in signature(output)]
            self.assertIn(bytes.fromhex('54 28 5a'),writes)
            self.assertNotIn(bytes.fromhex('54 28 4a'),writes)

    def test_partial_operators_retriggers_and_release_tail_writes_survive(self):
        raw=vgm(bytes.fromhex('54 28 4a 54 08 78 62 54 08 70 54 08 78 62 '
            '54 08 00 54 08 78 62 54 08 00 54 60 35 62'),{0x30:4000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,performance=self.build(raw,root)
            self.assertEqual(len([u for u in performance.units if u.section=='fm']),2)
            write_native_vgm(performance,root/'out.vgm')
            self.assertEqual(signature(raw),signature((root/'out.vgm').read_bytes()))
            self.assertTrue(any(c.sample==2205 and c.kind=='fm_operator_level' for c in performance.controls))

    def test_pcm_blocks_streams_and_same_sample_dependencies_survive(self):
        data=block(4,b'\x12\x34\x56\x78')
        setup=bytes.fromhex('90 00 17 00 01 91 00 04 01 00 92 00 44 ac 00 00 '
                            '93 00 00 00 00 00 01 04 00 00 00')
        raw=vgm(bytes.fromhex('54 28 4a 54 08 78')+data+setup+
                bytes.fromhex('62 94 00 54 08 00'),{0x30:4000000,0x90:4000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,performance=self.build(raw,root)
            self.assertGreaterEqual(len(performance.pcm_packets),6)
            write_native_vgm(performance,root/'out.vgm')
            self.assertEqual(signature(raw),signature((root/'out.vgm').read_bytes()))

    def test_native_profile_never_merges_retimed_legacy_controls_with_pcm(self):
        raw=vgm(bytes.fromhex('54 28 4a 54 08 78 a0 00 ac a0 01 01 a0 07 3e '
            'a0 08 0f b7 00 02 61 73 01 a0 08 09 b7 01 12 62 54 08 00 a0 08 00'),
            {0x30:4000000,0x74:1789773,0x90:4000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.vgm';source.write_bytes(raw)
            plan,report=build_plan(source,root/'passes',normalize_lengths=True,normalization_ms=8,fm_state_ms=24)
            self.assertEqual(report['target_profile'],'native')
            write_vgm(plan,root/'out.vgm')
            self.assertEqual(signature(raw),signature((root/'out.vgm').read_bytes()))
            self.assertEqual(plan.source_performance.end_sample,1106)
            self.assertTrue((root/'passes/source.native_music.units.csv').is_file())
            saved=json.loads((root/'passes/source.native_music.json').read_text())
            self.assertFalse(saved['projection_applied'])

    def test_same_sample_loop_boundary_keeps_source_order(self):
        raw=bytearray(vgm(bytes.fromhex('54 28 4a 54 08 78 54 30 00 62 54 08 00'),{0x30:4000000}))
        address=256+6
        struct.pack_into('<I',raw,0x1c,address-0x1c)
        struct.pack_into('<I',raw,0x20,735)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,performance=self.build(bytes(raw),root)
            write_native_vgm(performance,root/'out.vgm',source_loop=True)
            output=(root/'out.vgm').read_bytes();loop=0x1c+int.from_bytes(output[0x1c:0x20],'little')
            self.assertEqual(output[loop:loop+3],bytes.fromhex('54 30 00'))
            self.assertEqual(signature(raw),signature(output))

    def test_dual_opm_and_dcsg_identities_and_headers_survive(self):
        raw=vgm(bytes.fromhex('54 28 4a a4 28 5a 54 08 78 a4 08 78 '
                             '50 80 50 10 30 81 30 11 62 54 08 00 a4 08 00'),
                {0x30:4000000|0x40000000,0x0c:3579545|0x40000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,performance=self.build(raw,root)
            self.assertTrue({'opm:0','opm:1','dcsg:0','dcsg:1'} <= {d.device_id for d in performance.devices})
            write_native_vgm(performance,root/'out.vgm')
            output=(root/'out.vgm').read_bytes()
            self.assertEqual(output[0x30:0x34],raw[0x30:0x34])
            self.assertEqual(output[0x0c:0x10],raw[0x0c:0x10])
            self.assertEqual(signature(raw),signature(output))

    def test_opll_and_opna_rhythm_have_shared_events_and_explicit_stops(self):
        raw=vgm(bytes.fromhex('51 36 05 51 0e 30 56 11 00 56 18 c4 56 10 01 '
                             '62 51 0e 20 56 10 81 62'),{0x10:3579545,0x48:8000000})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,performance=self.build(raw,root)
            percussion=performance.percussion
            self.assertTrue(any(p.device_id=='opll:0' and p.observed for p in percussion))
            self.assertTrue(any(p.device_id=='opna:0' and p.observed for p in percussion))
            self.assertTrue(all(p.stop_sample==735 for p in percussion))
            write_native_vgm(performance,root/'out.vgm')
            self.assertEqual(signature(raw),signature((root/'out.vgm').read_bytes()))


if __name__=='__main__':unittest.main()
