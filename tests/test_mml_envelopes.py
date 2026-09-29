"""Compare the rendered envelope at every source tick, not just note lengths."""
import csv
from dataclasses import replace
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from chip_segments import SccSegment, PsgSegment
from mml_envelopes import EnvelopeBank, render
from mml_sync import analyze_mml, _leaves, annotate_sync_points


def sounding_timeline(text, raw=True):
    curves = {}
    for number, body in re.findall(r'@e(\d+)\s*=\s*\{([^}]+)\}', text):
        values = []
        for item in body.split(',')[2:]:
            level, *count = item.strip().split(':')
            values.extend([int(level, 16)] * (int(count[0]) if count else 1))
        curves[int(number)] = values
    result = {}
    for channel, nodes in analyze_mml(text)[0].items():
        if channel not in '12345678':
            continue
        octave, volume, wave, env, mode, noise = 4, 0, 0, 0, 1, 0
        hw, period, shape = False, 0, 0
        env_pos, tie = 0, False
        samples = []
        for node in _leaves(nodes):
            t = node.text
            if re.fullmatch(r'@e\d+', t): env = int(t[2:]); hw = False
            elif re.fullmatch(r'@\d+', t): wave = int(t[1:]); env = 0
            elif re.fullmatch(r'v\d+', t): volume = int(t[1:]); hw = False
            elif re.fullmatch(r'o\d+', t): octave = int(t[1:])
            elif t == '>': octave += 1
            elif t == '<': octave -= 1
            elif t == ')': volume = min(15, volume + 1); hw = False
            elif t == '(': volume = max(0, volume - 1); hw = False
            elif re.fullmatch(r'/\d+', t): mode = int(t[1:])
            elif re.fullmatch(r'n\d+', t): noise = int(t[1:])
            elif re.fullmatch(r'm\d+', t): period = int(t[1:])
            elif re.fullmatch(r'y11,\d+', t): period = (period & 0xff00) | int(t.split(',')[1])
            elif re.fullmatch(r'y12,\d+', t): period = (period & 255) | (int(t.split(',')[1]) << 8)
            elif re.fullmatch(r's\d+', t): shape = int(t[1:]); hw = True
            elif t == '&': tie = True
            elif node.end > node.start:
                length = node.end - node.start
                self_factor = 1 if raw else 3
                assert length % self_factor == 0
                length //= self_factor
                pitch = re.match(r'[a-gr][+#-]?', t)[0]
                if not tie:
                    env_pos = 0
                curve = curves.get(env, [15])
                for i in range(length):
                    if pitch == 'r': samples.append(None); continue
                    level = curve[min(env_pos + i, len(curve) - 1)]
                    # Generated envelopes use v15; constant F uses actual v.
                    amplitude = ('hw', period, shape) if hw else max(0, volume + level - 15)
                    config = (mode, noise if mode & 2 else 0) if channel in '123' else (wave,)
                    samples.append((pitch, octave, amplitude, config))
                env_pos += length
                tie = False
        if any(sample is not None for sample in samples):
            result[channel] = samples
    return result


def segment_timeline(folder, stem):
    result = {}
    for chip in ('psg', 'scc'):
        with (Path(folder) / f'{stem}.{chip}.segments.csv').open(newline='') as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            ch = str(int(row['ch']) + (1 if chip == 'psg' else 4))
            samples = result.setdefault(ch, [])
            start, length = int(row['ticks']), int(row['l'])
            if length <= 0: continue
            if len(samples) < start: samples.extend([None] * (start - len(samples)))
            pitch, vol = row['scale'], int(row['volume'])
            hw = chip == 'psg' and int(row['envelope_enabled'])
            enabled = int(row['mode'] if chip == 'psg' else row['enabled'])
            sample = None
            if pitch != 'r' and enabled and (vol or hw):
                amp = ('hw', int(row['envelope_period']), int(row['envelope_shape'])) if hw else vol
                config = (enabled, int(row['noise_period']) if enabled & 2 else 0) if chip == 'psg' else (int(row['waveform_id']),)
                sample = (pitch, int(row['octave']), amp, config)
            samples.extend([sample] * length)
    return {ch: samples for ch, samples in result.items() if any(s is not None for s in samples)}


class EnvelopeTests(unittest.TestCase):
    def test_global_selection_is_order_independent_and_prefers_long_curves(self):
        from collections import Counter
        short = [((15, n + 1), (10, 1), (5, 1)) for n in range(35)]
        long = ((14, 100), (9, 100), (2, 100))
        a, b = EnvelopeBank(), EnvelopeBank()
        a.select(Counter(dict([(c, 1000) for c in short] + [(long, 1)])))
        b.select(Counter(dict([(long, 1)] + [(c, 1000) for c in reversed(short)])))
        self.assertEqual(a.curves, b.curves)
        self.assertEqual(a.curves[long], 1)
        self.assertLessEqual(len(a.curves), 32)

    def test_prefix_sharing_checks_release_and_every_observed_tick(self):
        from collections import Counter
        from mml_envelopes import curve_prefix
        long = ((12, 4), (8, 4), (3, 4))
        short = ((12, 4), (8, 2))
        release = ((12, 4), (7, 2))
        self.assertTrue(curve_prefix(short, long))
        self.assertFalse(curve_prefix(release, long))
        bank = EnvelopeBank()
        bank.select(Counter({long: 1, short: 1, release: 1}))
        self.assertEqual(bank.aliases[short], bank.curves[long])
        self.assertNotIn(release, bank.aliases)
        base = SccSegment('vCtrl', 0, 0, 0, 4, 400, 12, 4, 'c', 0, (), 400, 1, 1, 0, '', 1)
        bank.prepared = True
        text = render({0: [base, replace(base, ticks=4, l=2, volume=8)]}, 'scc', bank, True)
        self.assertEqual([x[2] for x in sounding_timeline(text)['4']], [12]*4 + [8]*2)


    def test_segment_dump_records_actual_envelope_selection(self):
        from chip_segments import dump_segments
        base = SccSegment('vCtrl', 0, 0, 0, 2, 400, 10, 4, 'c', 0, (), 400, 1, 1, 0, '', 1)
        rows = [base, replace(base, ticks=2, volume=8), replace(base, ticks=4, volume=6),
                replace(base, ticks=6, l=0), replace(base, ticks=6, volume=0, scale='r'),
                replace(base, ticks=8, volume=12)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.scc.segments.csv'
            target = Path(folder) / 'test.scc.target_notes.csv'
            for full in (False, True):
                bank = EnvelopeBank()
                if full:
                    for n in range(31): bank.register(((15, n + 1), (3, 1)))
                dump_segments(path, {0: rows}, SccSegment)
                with path.open(newline='') as stream: original = list(csv.DictReader(stream))
                text = render({0: rows}, 'scc', bank, dump_path=target)
                with path.open(newline='') as stream: actual = list(csv.DictReader(stream))
                for before, after in zip(original, actual):
                    self.assertEqual(before, {k: after[k] for k in before})
                expected = ('0', 'inline') if full else ('1', 'software')
                self.assertEqual([(r['envelope_id'], r['envelope_kind']) for r in actual],
                                 [expected] * 3 + [('', 'zero_length'), ('', 'rest'), ('0', 'constant')])
                self.assertIn('@e' + expected[0], text)
                first = path.read_bytes()
                render({0: rows}, 'scc', bank, dump_path=target)
                self.assertEqual(path.read_bytes(), first)

    def test_hardware_and_silent_channel_have_no_software_id(self):
        from chip_segments import dump_segments
        hw = PsgSegment('evS', 0, 0, 0, 3, 400, 0, 4, 'c', 0, (), 1, 0, 1, 100, 9, 0, 16)
        rows = {0: [hw], 1: [replace(hw, ch=1, envelope_enabled=0, scale='r')]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.psg.segments.csv'
            dump_segments(path, rows, PsgSegment)
            render(rows, 'psg', EnvelopeBank(), dump_path=Path(folder) / 'test.psg.target_notes.csv')
            with path.open(newline='') as stream: actual = list(csv.DictReader(stream))
            self.assertEqual([(r['envelope_id'], r['envelope_kind']) for r in actual],
                             [('', 'hardware'), ('', 'rest')])

    def test_rest_settings_deferred_and_curve_exact(self):
        base = SccSegment('vCtrl', 0, 0, 0, 2, 400, 10, 4, 'c', 0, (), 400, 1, 1, 0, '', 1)
        segments = {0: [base, replace(base, ticks=2, volume=8), replace(base, ticks=4, volume=6),
                        replace(base, ticks=6, scale='r', volume=0, waveform_id=1),
                        replace(base, ticks=8, scale='r', volume=0, waveform_id=2),
                        replace(base, ticks=10, volume=9, waveform_id=2)]}
        for raw in (True, False):
            text = render(segments, 'scc', EnvelopeBank(), raw)
            states = sounding_timeline(text, raw)['4']
            self.assertEqual([s[2] if s else None for s in states], [10, 10, 8, 8, 6, 6, None, None, None, None, 9, 9])
            self.assertNotIn('@1 ', text)
            self.assertIn('A:2, 8:2, 6:2', text)
            self.assertEqual(states[-1][-1], (2,))

    def test_silent_track_removed_from_body_alloc_and_sync(self):
        text = annotate_sync_points('1 v0 c%100\n2 v9 c%6\n3 r%200\n', drop_silent=True)
        self.assertNotRegex(text, r'(?m)^[13] ')
        self.assertNotIn('ch1 ---', text)
        self.assertIn('#alloc { 2=15000 }', text)
        self.assertIn('step 6 : end', text)

    def test_bank_limit_has_lossless_fallback(self):
        bank = EnvelopeBank()
        for n in range(40): bank.register(((15, n + 1), (3, 1)))
        self.assertEqual(len(bank.curves), 32)
        self.assertIsNone(bank.register(((14, 999), (1, 2))))

    def test_retrigger_and_hardware_envelope_are_not_absorbed(self):
        base = SccSegment('vCtrl', 0, 0, 0, 2, 400, 10, 4, 'c', 0, (), 400, 1, 1, 0, '', 1)
        from mml_envelopes import extract_notes
        notes = extract_notes({0: [base, replace(base, ev_type='f1Ctrl', ticks=2, l=0),
                                  replace(base, ticks=2, volume=8)]}, 'scc')[0]
        self.assertEqual([n.length for n in notes], [2, 2])
        hw = PsgSegment('evS', 0, 0, 0, 3, 400, 0, 4, 'c', 0, (), 1, 0, 1, 100, 9, 0, 16)
        text = render({0: [hw, replace(hw, ticks=3, ev_type='aVC', envelope_enabled=0, volume=8)]},
                      'psg', EnvelopeBank(), True)
        states = sounding_timeline(text)['1']
        self.assertEqual(states[0][2], ('hw', 100, 9))
        self.assertEqual(states[3][2], 8)

    def test_definition_overflow_falls_back_to_tied_volume_changes(self):
        bank = EnvelopeBank()
        for n in range(31): bank.register(((15, n + 1), (3, 1)))
        base = SccSegment('vCtrl', 0, 0, 0, 2, 400, 10, 4, 'c', 0, (), 400, 1, 1, 0, '', 1)
        text = render({0: [base, replace(base, ticks=2, volume=8), replace(base, ticks=4, volume=6)]},
                      'scc', bank, True)
        self.assertIn('&c%2', text)
        self.assertEqual([s[2] for s in sounding_timeline(text)['4']], [10, 10, 8, 8, 6, 6])

    def test_user_fixtures_match_segment_volume_at_every_tick(self):
        for number in ('001', '002'):
            source = ROOT / f'tests/fixtures/public/psg_scc/{number}/psg_scc_{number}.vgm'
            if not source.exists():
                self.skipTest('Optional mixed PSG/SCC fixtures are not installed')
            for raw in (False, True):
                with self.subTest(fixture=number, raw=raw), tempfile.TemporaryDirectory() as folder:
                    command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(source), '--outdir', folder, '--dump-passes']
                    if raw: command.append('--raw-ticks')
                    run = subprocess.run(command, capture_output=True, timeout=120)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    text = (Path(folder) / f'{source.stem}.mml').read_text()
                    self.assertEqual(sounding_timeline(text, raw), segment_timeline(folder, source.stem))
                    self.assertRegex(text, r'@e0[1-9] =')


if __name__ == '__main__':
    unittest.main()
