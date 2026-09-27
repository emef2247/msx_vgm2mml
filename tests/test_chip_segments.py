import csv
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from chip_segments import PsgSegment, SccAnalysis
from psg import build_segments as build_psg_segments
from psg_mml import write_psg_mml, _update_and_optimize_cnt_psg
from scc import build_segments as build_scc_segments
from scc_mml import write_scc_mml
from vgm_reader import parse_vgm


class SegmentTests(unittest.TestCase):
    def test_psg_preserves_noise_envelope_and_zero_length_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.csv'
            rows = []
            for event, time, shape in [('evS', '0.1', '9'), ('wNC', '0.1', '10'), ('aVC', '0.2', '10')]:
                row = [''] * 34
                row[0:3] = [event, time, '0']
                row[12] = '3'
                row[24:32] = ['85', '1', '17', '0', '16', '52', '18', shape]
                rows.append(row)
            path.write_text('\n'.join(','.join(row) for row in rows), encoding='utf-8')
            segments = build_psg_segments(path, folder, stem='sample')
            first, second, last = segments[0]
            self.assertIsInstance(first, PsgSegment)
            self.assertEqual([s.ev_type for s in segments[0]], ['evS', 'wNC', 'aVC'])
            self.assertEqual(first.l, 0)
            self.assertEqual(first.envelope_shape, 9)
            self.assertEqual(second.envelope_shape, 10)
            self.assertEqual(second.envelope_period, 0x1234)
            self.assertEqual(second.envelope_enabled, 1)
            self.assertEqual(second.noise_period, 17)
            self.assertEqual(second.tone_period, 0x155)
            self.assertNotEqual(second.scale, 'r')  # envelope makes volume=0 audible
            self.assertEqual(second.time, 0.1)
            self.assertEqual(second.tick_start, 6)
            self.assertEqual(second.tick_end, 12)
            self.assertEqual(last.l, 0)
            with (Path(folder) / 'sample.psg.segments.csv').open(encoding='utf-8', newline='') as fh:
                dumped = list(csv.DictReader(fh))
            self.assertEqual(json.loads(dumped[1]['pass3_row']), list(second.pass3_row))
            self.assertEqual(dumped[1]['envelope_period'], '4660')
            with self.assertRaises(FrozenInstanceError):
                second.l = 99

    def test_renderers_consume_segments_without_legacy_rows(self):
        for chip, build, render in [('psg', build_psg_segments, write_psg_mml),
                                    ('scc', build_scc_segments, write_scc_mml)]:
            with self.subTest(chip=chip), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                fixture = ROOT / f'tests/fixtures/public/{chip}/patch_change_midnote/patch_change_midnote.vgm'
                paths = parse_vgm(str(fixture), str(root / 'events'))
                trace = paths[2 if chip == 'psg' else 3]
                analysis = build(trace, str(root / 'passes'), stem='test')
                segments = analysis if chip == 'psg' else analysis.segments
                stripped = {ch: [replace(seg, pass3_row=()) for seg in channel]
                            for ch, channel in segments.items()}
                render_input = stripped if chip == 'psg' else SccAnalysis(stripped, analysis.waveforms)
                self.assertTrue(any(seg.l > 0 for channel in segments.values() for seg in channel))
                for raw in (False, True):
                    original = Path(render(analysis, root / 'original', 'test', debug=False, raw_ticks=raw))
                    independent = Path(render(render_input, root / 'independent', 'test', debug=False, raw_ticks=raw))
                    self.assertEqual(original.read_bytes(), independent.read_bytes())
                self.assertTrue(all(seg.pass3_row for channel in segments.values() for seg in channel))
                if chip == 'scc':
                    self.assertTrue(analysis.waveforms)
                    self.assertTrue(all(len(wave) == 64 for wave in analysis.waveforms))
                    for channel in segments.values():
                        for seg in channel:
                            self.assertEqual(seg.waveform_hex, analysis.waveforms[seg.waveform_id])

    def test_repeat_projection_does_not_mutate_segments(self):
        segment = PsgSegment('fCA', 0.1, 0, 6, 3, 85, 10, 6, 'e', 0, (),
                             1, 0, 0, 0, 0, 0, 10)
        repeated = replace(segment, time=0.15, ticks=9)
        source = {0: [segment, repeated]}
        self.assertEqual(_update_and_optimize_cnt_psg(source), {0: [(segment, 2)]})
        self.assertEqual(source, {0: [segment, repeated]})
        self.assertEqual(repeated.tick_start, 9)

    def test_dump_passes_keeps_source_and_segment_csv_without_debug(self):
        fixture = ROOT / 'tests/fixtures/public/psg/retrigger/retrigger.vgm'
        for dump in (False, True):
            with self.subTest(dump=dump), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture), '--outdir', folder]
                if dump:
                    command.append('--dump-passes')
                run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                     env={**os.environ, 'PYTHONUTF8': '1'}, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                for name in ('retrigger_trace.psg.csv', 'retrigger.psg.pass3.csv',
                             'retrigger.psg.segments.csv', 'retrigger.scc.waveforms.csv'):
                    self.assertEqual((Path(folder) / name).exists(), dump, name)
                self.assertTrue((Path(folder) / 'retrigger.mml').exists())


if __name__ == '__main__':
    unittest.main()
