"""Check user patches against source definitions and split notes against attacks."""
import csv
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opll_target import decode_patch, render
from mml_sync import analyze_mml, _leaves
from test_rhythm_patterns import segment


class OpllTarget(unittest.TestCase):
    def test_register_layout_and_waveforms(self):
        self.assertEqual(decode_patch(bytes.fromhex('71611e17d0780017')),
                         (30, 7, 13,0,0,0,0,1,0,1,1,1,0,
                          7,8,1,7,0,1,0,1,1,0,1))

    def test_long_note_has_one_attack_and_presets_do_not_collide(self):
        seg = segment(0, volume=0, tick_end=600, inst=1, fnum=172, block=3)
        for raw in (False, True):
            text = render({0: [seg]}, raw_ticks=raw)
            nodes = list(_leaves(analyze_mml(text)[0]['9']))
            self.assertIn('@0', [n.text for n in nodes])
            self.assertIn('&', [n.text for n in nodes])
            self.assertEqual(nodes[-1].end, 600 * (1 if raw else 3))
            self.assertEqual(sum(n.end > n.start for n in nodes)
                             - sum(n.text == '&' for n in nodes), 1)

    def test_custom_fixture_definitions_and_voice_selection(self):
        fixture = ROOT / 'tests/fixtures/public/opll/custom_voice/custom_voice.vgm'
        if not fixture.exists():
            self.skipTest('Optional custom voice fixture unavailable')
        reference = fixture.parent / 'reference/custom_voice.mml'
        def definitions(text):
            text = re.sub(r';[^\n]*', '', text)
            return {int(m[1]): tuple(map(int, re.findall(r'\d+', m[2])))
                    for m in re.finditer(r'@(\d+)\s*=\s*\{([^}]+)\}', text)}
        expected = definitions(reference.read_text(encoding='utf-8-sig'))
        for raw in (False, True):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(fixture),
                           '--outdir', folder, '--dump-passes']
                if raw:
                    command.append('--raw-ticks')
                run = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                text = (Path(folder) / 'custom_voice.mml').read_text()
                self.assertEqual(definitions(text), expected)
                tokens = [n.text for n in _leaves(analyze_mml(text)[0]['9'])]
                voices = [t for t in tokens if re.fullmatch(r'@\d+', t)]
                self.assertEqual(voices, [v for i in range(15) for v in (f'@{i}', f'@{i+16}')])
                self.assertNotIn('@v', text)
                with (Path(folder) / 'custom_voice.opll.target_notes.csv').open(newline='') as stream:
                    notes = list(csv.DictReader(stream))
                # Count attacks after length splitting: tied continuations are not attacks.
                nodes = list(_leaves(analyze_mml(text)[0]['9']))
                attack_count = sum(n.end > n.start and not n.text.startswith('r') for n in nodes)
                attack_count -= sum(n.text == '&' for n in nodes)
                self.assertEqual(attack_count, len(notes))
