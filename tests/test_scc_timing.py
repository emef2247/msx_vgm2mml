"""SCC post-write intervals and five-channel output, checked against event states."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from vgm_reader import _SccState
from scc import build_segments
from scc_mml import write_scc_mml, _update_and_optimize_cnt_scc
from mml_sync import analyze_mml, _leaves, annotate_sync_points, proportional_allocations


def rendered_states(text):
    result = {}
    for ch, nodes in analyze_mml(text)[0].items():
        octave, volume, wave = 4, 8, 0
        states = []
        for node in _leaves(nodes):
            token = node.text
            if re.fullmatch(r'o\d+', token): octave = int(token[1:])
            elif re.fullmatch(r'v\d+', token): volume = int(token[1:])
            elif re.fullmatch(r'@\d+', token): wave = int(token[1:])
            elif token == '>': octave += 1
            elif token == '<': octave -= 1
            elif token == '(': volume -= 1
            elif token == ')': volume += 1
            elif node.end > node.start:
                pitch = re.match(r'[a-gr][+#-]?', token)[0]
                states.extend([(pitch, octave, volume, wave)] * (node.end - node.start))
        result[int(ch) - 4] = states
    return result


class SccTimingTests(unittest.TestCase):
    def test_enable_bits_and_shared_fifth_wave(self):
        state = _SccState()
        for ch in range(5):
            state.write_scc(0, 0x988f, 1 << ch)
            self.assertEqual(state.enBit, [int(i == ch) for i in range(5)])
        for offset in range(32):
            state.write_scc(0, 0x9860 + offset, offset)
        state.write_scc(0, 0x9888, 0x51)
        state.write_scc(0, 0x9889, 1)
        state.write_scc(0, 0x988e, 7)
        self.assertEqual(state.f1Ctrl[4] + 256 * state.f2Ctrl[4], 337)
        self.assertEqual(state.vCtrl[4], 7)
        self.assertEqual(state.wtbl_index[3], state.wtbl_index[4])
        self.assertEqual(sum(r.startswith('wtb') for r in state.log_buf[4]), 32)

    def test_event_intervals_survive_wave_setup_pitch_and_repeat_changes(self):
        state = _SccState()
        state.write_scc(0, 0x988f, 31)
        for ch in range(5):
            for offset in range(32):
                if ch < 4:
                    state.write_scc(0, 0x9800 + ch * 32 + offset, offset + ch)
            state.write_scc(0, 0x9880 + ch * 2, 0xe0)
            state.write_scc(0, 0x9881 + ch * 2, 5)
            state.write_scc(0, 0x988a + ch, 10)
        # Set the time origin before nonzero timestamps (legacy reader clock).
        state._start_time = -1
        for tick, volume, low in ((10, 9, 0x40), (20, 8, 0x40), (30, 8, 0xe0), (40, 0, 0xe0)):
            for ch in range(5):
                state.write_scc(tick / 60 - 1, 0x9880 + ch * 2, low)
                state.write_scc(tick / 60 - 1, 0x988a + ch, volume)
        with tempfile.TemporaryDirectory() as folder:
            trace = Path(folder) / 'trace.csv'
            state.output_trace_csv(trace)
            analysis = build_segments(trace, folder, stem='scc')
            self.assertEqual(set(analysis.segments), set(range(5)))
            compressed = _update_and_optimize_cnt_scc(analysis.segments, list(range(5)))
            for ch, segments in analysis.segments.items():
                self.assertEqual(sum(s.l for s in segments), 40)
                self.assertEqual(sum(s.l * n for s, n in compressed[ch]), 40)
                self.assertEqual([(s.ticks, s.scale) for s in segments if s.l > 0],
                                 [(0, 'd'), (10, 'e'), (20, 'e'), (30, 'd')])
            for raw in (True, False):
                path = write_scc_mml(analysis, folder, 'scc', debug=False, raw_ticks=raw)
                actual = rendered_states(Path(path).read_text())
                factor = 1 if raw else 3
                for ch, segments in analysis.segments.items():
                    expected = []
                    for s in segments:
                        expected.extend([(s.scale, s.octave, s.volume, s.waveform_id)] * (s.l * factor))
                    self.assertEqual(actual[ch], expected)

    def test_allocation_pool_and_unused_tracks(self):
        self.assertEqual(proportional_allocations({'1': 1, '2': 2, '3': 0}),
                         {'1': 5000, '2': 10000})
        self.assertEqual(sum(proportional_allocations({'1': 7, '2': 11, '3': 13}).values()), 15000)
        text = annotate_sync_points('#alloc { 1=96, 2=96, 3=96 }\n1 v10 c%10\n2 r%10\n3 v0 c%10\n')
        self.assertIn('#alloc { 1=15000 }', text)
        self.assertNotIn('2=96', text)
        self.assertNotIn('#alloc', annotate_sync_points('1 r%10\n'))


if __name__ == '__main__':
    unittest.main()
