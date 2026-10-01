"""Check user patches against source definitions and split notes against attacks."""
import csv
from pathlib import Path
import re
import subprocess
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opll_target import decode_patch, render, target_note
from mml_utils import compact_state_token
from mml_sync import analyze_mml, _leaves
from test_rhythm_patterns import segment


class OpllTarget(unittest.TestCase):
    def test_relative_tokens_require_known_one_step_state(self):
        for prefix, value, old, expected in [
                ('o', 4, None, 'o4'), ('v', 12, None, 'v12'),
                ('o', 5, 4, '>'), ('o', 3, 4, '<'),
                ('v', 13, 12, ')'), ('v', 11, 12, '('),
                ('o', 6, 4, 'o6'), ('v', 9, 12, 'v9'),
                ('@', 17, 16, '@17')]:
            self.assertEqual(compact_state_token(prefix, value, old), expected)

    def test_relative_controls_follow_emitted_state_across_keyoff_rests(self):
        rows = [segment(0, volume=3, tick_end=4, inst=1, fnum=290, block=3),
                segment(4, volume=15, keyon=0, tick_end=8, inst=1, fnum=290, block=0),
                segment(8, volume=2, tick_end=12, inst=1, fnum=290, block=4),
                segment(12, volume=3, tick_end=16, inst=1, fnum=290, block=3)]
        text = render({0: rows}, raw_ticks=True)
        self.assertIn('v12 o4', text)
        self.assertIn(') >', text)
        self.assertIn('( <', text)
        self.assertNotIn('o1', text)

    def test_continuous_state_changes_tie_but_zero_length_key_edges_retrigger(self):
        rows = [segment(0, tick_end=4, inst=1, fnum=290, block=3, key_on_edge=1),
                segment(4, tick_end=8, inst=1, fnum=291, block=3, vol=4),
                segment(8, tick_end=8, inst=1, fnum=291, block=3, key_on_edge=1),
                segment(8, tick_end=12, inst=1, fnum=291, block=3)]
        for raw in (False, True):
            text = render({0: rows}, raw_ticks=raw)
            tokens = list(_leaves(analyze_mml(text)[0]['9']))
            self.assertEqual(sum(n.text == '&' for n in tokens), 1)
            self.assertEqual(tokens[-1].end, 12*(1 if raw else 3))
        rows[2].key_on_edge = 0
        rows[2].keyon = 0
        self.assertEqual(render({0: rows}, raw_ticks=True).count('&'), 1)

    def test_attenuation_recovery_is_not_a_key_edge(self):
        from segment_utils import pass2_compute_onsets_and_ioi
        rows = [dict({'#type': 'instVol'}, ch=0, ticks=tick, l=4,
                     keyon=key, vol=volume, fnum=290, block=3)
                for tick, key, volume in ((0, 1, 15), (4, 1, 3),
                                          (8, 1, 15), (12, 1, 4), (16, 0, 4))]
        events = pass2_compute_onsets_and_ioi(rows)
        self.assertEqual([e['onset'] for e in events], [0, 1, 0, 1, 0])
        self.assertEqual([e['key_on_edge'] for e in events], [1, 0, 0, 0, 0])
        segments = [segment(e['ticks'], volume=e['vol'], keyon=e['keyon'],
                            tick_end=e['ticks'] + e['l'], inst=1, fnum=290, block=3,
                            onset=e['onset'], key_on_edge=e['key_on_edge']) for e in events]
        for raw in (False, True):
            nodes = list(_leaves(analyze_mml(render({0: segments}, raw_ticks=raw))[0]['9']))
            notes = [n for n in nodes if n.end > n.start and not n.text.startswith('r')]
            self.assertEqual(len(notes) - sum(n.text == '&' for n in nodes), 1)
            self.assertEqual(sum(n.text == '&' for n in nodes), 3)
            self.assertIn('v0', [n.text for n in nodes])
            self.assertEqual(nodes[-1].end, 20 * (1 if raw else 3))

    def test_maximum_attenuation_keeps_register_states_and_zero_tick_key_edges(self):
        from vgm_reader import parse_vgm
        from opll import _build_segments
        from opll_segments import dump_segments
        header = bytearray(0x100)
        header[:4] = b'Vgm '
        struct.pack_into('<I', header, 8, 0x161)
        struct.pack_into('<I', header, 0x10, 3579545)
        struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
        # Key-on at attenuation 15, pitch change, zero-tick off/on, recovery.
        commands = bytes.fromhex('51 30 1f 51 10 22 51 20 17 61 7c 0b '
                                 '51 10 23 61 7c 0b 51 20 07 51 20 17 '
                                 '61 7c 0b 51 30 13 61 7c 0b 51 20 07 66')
        struct.pack_into('<I', header, 4, len(header) + len(commands) - 4)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'mute_edges.vgm'
            source.write_bytes(header + commands)
            paths = parse_vgm(str(source), folder)
            segments, _ = _build_segments(paths[5])
            rows = segments[0]
            self.assertEqual(sum(s.key_on_edge for s in rows), 2)
            self.assertTrue(any(not s.keyon and s.tick_start == s.tick_end for s in rows))
            self.assertTrue(any(s.fnum == 291 and s.vol == 15 for s in rows))
            self.assertEqual(sum(s.onset for s in rows), 1)
            dump = Path(folder) / 'segments.csv'
            dump_segments(segments, dump)
            with dump.open(newline='') as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(sum(int(r['key_on_edge']) for r in exported if r['ch'] == '0'), 2)

    def test_ys_source_retriggers_survive_segment_construction(self):
        source = ROOT / 'tests/fixtures/local_only/opll/www.smspower.org/YSSMS/YsSMS01.vgm'
        if not source.exists():
            self.skipTest('Optional local Ys fixture unavailable')
        from vgm_reader import parse_vgm
        from opll import _build_segments
        with tempfile.TemporaryDirectory() as folder:
            paths = parse_vgm(str(source), folder)
            segments, _ = _build_segments(paths[5])
            state, expected = {}, dict.fromkeys(range(6), 0)
            with open(paths[7], newline='') as stream:
                for row in csv.DictReader(stream):
                    ch = int(row['addr'], 0)-0x20
                    if ch not in expected:
                        continue
                    value = int(row['val'])
                    old = state.get(ch, 0)
                    state[ch] = value
                    expected[ch] += bool(value & 16 and not old & 16)
            for ch in range(6):
                self.assertEqual(sum(s.key_on_edge for s in segments[ch]), expected[ch])

    def test_mgs_octaves_match_driver_register_blocks(self):
        # MGSC 1.11/libkss: o4 a writes block 3; o3 a writes block 2.
        for block in range(8):
            self.assertEqual(target_note(290, block), (block + 1, 'a'))
            self.assertEqual(target_note(172, block), (block + 1, 'c'))
        self.assertEqual(target_note(0, 3), (1, 'r'))

    def test_all_rom_instruments_keep_mgs_numbering(self):
        for inst in range(1, 16):
            text = render({0: [segment(0, volume=0, tick_end=10,
                                      inst=inst, fnum=290, block=3)]})
            tokens = [n.text for n in _leaves(analyze_mml(text)[0]['9'])]
            self.assertIn('@' + str(inst - 1), tokens)
            self.assertIn('o4', tokens)

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
