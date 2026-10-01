"""Preserve all pre-refactor MML variants and PASS/trace output on public VGMs."""
import hashlib
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from vgm_test_support import with_scc_clock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vgm2mml
from test_mml_sync import timeline
from mml_sync import annotate_sync_points
from test_scc_timing import rendered_states
from mml_utils import get_octave, get_scale


class PublicConversionTests(unittest.TestCase):
    def test_public_fixtures_match_before_refactor(self):
        baseline = json.loads((ROOT / 'tests/conversion_baseline.json').read_text(encoding='utf-8'))
        for key, expected in baseline['cases'].items():
            with self.subTest(case=key), tempfile.TemporaryDirectory() as folder:
                mode, fixture = key.split('/', 1)
                source = ROOT / 'tests/fixtures/public' / fixture
                if mode.startswith('clock_'):
                    source = with_scc_clock(source, Path(folder) / 'input')
                output = Path(folder) / 'output'
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                           '--outdir', str(output), '--dump-passes', '--debug']
                if mode.endswith('raw'):
                    command.append('--raw-ticks')
                if '_log_' in mode:
                    command.extend(['--scc-input', 'log', '--psg-input', 'log'])
                run = subprocess.run(command, capture_output=True, text=True,
                                     encoding='utf-8', env={**os.environ, 'PYTHONUTF8': '1'},
                                     timeout=60)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                # The merged file now has sync comments and may expand loops.
                # Compare its music with the unannotated merge, then retain the
                # original byte baselines for all conversion stages.
                stem = source.stem
                flags = [vgm2mml._has_chip_data(str(output / f'{stem}_trace.{chip}.csv'))
                         for chip in ('psg', 'scc', 'opll')]
                with patch.object(vgm2mml, 'annotate_sync_points', lambda text, **kwargs: text):
                    unannotated = vgm2mml._build_merged_mml(stem, str(output), *flags,
                                                          raw_ticks=mode.endswith('raw'))
                annotated = (output / f'{stem}.mml').read_text(encoding='utf-8')
                self.assertEqual(timeline(annotate_sync_points(unannotated, min_gap=1000, drop_silent=True)), timeline(annotated))
                with patch.object(vgm2mml, 'annotate_sync_points', lambda text, **kwargs: text):
                    legacy = vgm2mml._build_merged_mml(stem, str(output), *flags,
                                                      raw_ticks=mode.endswith('raw'), target=False, name='psg')
                if flags[1]:
                    # The old SCC hashes encode four-channel, stale-pitch and
                    # lost-duration bugs. Check post-write states independently
                    # instead of recording those outputs as new golden files.
                    with (output / f'{stem}_trace.scc.csv').open(newline='') as fh:
                        rows = list(csv.DictReader(fh))
                    suffix = 'MGS_pct' if mode.endswith('raw') else 'MGS'
                    actual = rendered_states((output / f'{stem}.scc.pass3.compress.{suffix}.mml').read_text())
                    factor = 1 if mode.endswith('raw') else 3
                    for ch in {int(row['ch']) for row in rows}:
                        channel = [r for r in rows if int(r['ch']) == ch]
                        expected_states = []
                        for row, following in zip(channel, channel[1:]):
                            duration = int(following['ticks']) - int(row['ticks'])
                            frequency = (int(row['f1Ctrl']) + 256 * int(row['f2Ctrl'])) & 0xfff
                            volume = int(row['vCtrl']) & 15
                            pitch = get_scale(frequency) if volume and int(row['en']) else 'r'
                            expected_states.extend([(pitch, get_octave(frequency), volume)] * (duration * factor))
                        self.assertEqual([state[:3] for state in actual.get(ch, [])], expected_states)
                    continue
                if flags[2]:
                    # Old OPLL snapshots folded real same-pitch retriggers.
                    # Guard key edges independently rather than bless those hashes.
                    from opll import _build_segments
                    segments, _ = _build_segments(str(output / f'{stem}_trace.opll.csv'))
                    expected_onsets = dict.fromkeys(range(6), 0)
                    expected_edges = dict.fromkeys(range(6), 0)
                    states = dict.fromkeys(range(6), (0, 15))
                    with (output / f'{stem}_trace.opll.csv').open(newline='') as stream:
                        for row in csv.DictReader(stream):
                            ch = int(row['ch'])
                            if ch not in states or not row.get('keyon'):
                                continue
                            keyon = int(row['keyon'])
                            volume = int(row['vol'])
                            old_key, old_volume = states[ch]
                            expected_edges[ch] += bool(keyon and not old_key)
                            expected_onsets[ch] += bool(keyon and volume < 15
                                                        and (not old_key or old_volume == 15))
                            states[ch] = (keyon, volume)
                    for ch in range(6):
                        self.assertEqual(sum(s.onset for s in segments[ch]), expected_onsets[ch])
                        self.assertEqual(sum(s.key_on_edge for s in segments[ch]), expected_edges[ch])
                    continue
                artifacts = {}
                for path in output.iterdir():
                    if path.name.endswith(('.vgm.loop.csv', '.performed.units.csv', '.performed.loops.csv', '.envelope_candidates.csv', '.melody.loops.csv', '.melody.patterns.csv', '.melody.occurrences.csv', '.melody.markings.csv', '.opll.rhythm.collisions.csv', '.opll.rhythm.optimization.csv', '.opll.rhythm.groups.csv', '.opll.rhythm.patterns.csv', '.opll.rhythm.occurrences.csv', '.opll.segments.csv', '.psg.segments.csv', '.scc.segments.csv', '.scc.waveforms.csv', '.target.mml', '.target_notes.csv')):
                        continue
                    data = legacy.encode('utf-8') if path.name == f'{stem}.mml' else path.read_bytes()
                    if path.name == f'{stem}_log.scc.csv' and not flags[1]:
                        # The fifth empty SCC channel adds one blank separator.
                        data = data[:-1]
                    artifacts[path.name] = hashlib.sha256(data).hexdigest()
                payload = ''.join(f'{name}\0{digest}\n' for name, digest in sorted(artifacts.items()))
                self.assertEqual(len(artifacts), expected['file_count'])
                self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), expected['sha256'])


if __name__ == '__main__':
    unittest.main()
