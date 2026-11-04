"""OPN2 (YM2612) native source analysis: inventory, segments, MGS gate."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'py'))
from native_imports import analyze_source, inspect_source
from native_imports.opn2_music import build_opn2_gates
from mgs_force import inspect_projection, MgsProjectionError
from native_source_music import build_native_performance


def vgm(commands):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x0c, 3579545)
    struct.pack_into('<I', raw, 0x2c, 7670454)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    raw.extend(commands)
    raw.append(0x66)
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


FM_PHRASE = bytes((
    0x52, 0x30, 0x71, 0x52, 0x40, 0x23, 0x52, 0xa4, 0x22,
    0x52, 0xa0, 0x69, 0x52, 0xb0, 0x37, 0x52, 0x28, 0xf0,
    0x61, 0x00, 0x10,
    0x52, 0x28, 0x00,
    0x53, 0xa0, 0x6b, 0x53, 0xa4, 0x23, 0x52, 0x28, 0xf4,
    0x62,
    0x52, 0x28, 0x04,
))
DAC_WRITES = bytes((0x52, 0x2b, 0x80, 0x52, 0x2a, 0x80))


class Opn2NativeTests(unittest.TestCase):
    def analyze(self, raw):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        return analyze_source(raw, folder, 'authored'), folder

    def test_inspect_recognizes_opn2_and_dcsg(self):
        bundle = inspect_source(vgm(FM_PHRASE + bytes((0x50, 0x9f))))
        self.assertEqual(bundle['active_chips'], ('dcsg', 'opn2'))
        self.assertEqual(bundle['command_counts']['opn2'], 11)
        self.assertEqual(bundle['header']['opn2_clock_raw'], 7670454)

    def test_segments_key_edges_and_dac_state(self):
        result, folder = self.analyze(vgm(FM_PHRASE + DAC_WRITES))
        analysis = result['analyses']['opn2']
        self.assertIsNotNone(analysis)
        self.assertEqual(result['errors'], {})
        keyed = [s for s in analysis.segments if s.ch == 0 and s.rising_mask]
        self.assertEqual(len(keyed), 1)
        self.assertEqual((keyed[0].vgmticks, keyed[0].vgmticks_end,
                          keyed[0].rising_mask), (0, 4096, 15))
        ported = [s for s in analysis.segments if s.ch == 3 and s.rising_mask]
        self.assertEqual(len(ported), 1)
        pitch = [e for e in analysis.events if e.register == 0xa0 and e.port == 1]
        self.assertEqual([(e.ch, e.port) for e in pitch], [(3, 1)])
        self.assertIn(1, {s.state.dac_enabled for s in analysis.segments})
        self.assertEqual([(u.register, u.data) for u in analysis.unmodeled_writes],
                         [(0x2a, 0x80)])
        self.assertTrue(any('dac_data' in issue for issue in analysis.issues))
        for suffix in ('registers', 'states', 'segments', 'unmodeled'):
            self.assertTrue((folder/f'authored.native.opn2.{suffix}.csv').is_file())
        self.assertTrue(result['report']['analysis_available']['opn2'])

    def test_gates_use_mucom_part_letters(self):
        result, _ = self.analyze(vgm(FM_PHRASE))
        gates = build_opn2_gates(result['analyses']['opn2'])
        self.assertTrue(gates['A'])
        self.assertEqual((gates['A'][0].start, gates['A'][0].end), (0, 4096))


class Opn2PerformanceTests(unittest.TestCase):
    def test_builder_records_pending_projection_instead_of_crashing(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        performance = build_native_performance(vgm(FM_PHRASE), Path(temporary.name), 'authored')
        devices = {d.device_id: d for d in performance.devices}
        self.assertIn('opn2:0', devices)
        self.assertEqual(devices['opn2:0'].clock_hz, 7670454)
        self.assertIn(('opn2_projection_not_implemented', 'opn2:0'), performance.decisions)
        self.assertFalse([c for c in performance.controls if c.device_id == 'opn2:0'])
        self.assertFalse([p for p in performance.pcm_packets if p.chip == 'opn2'])


class Opn2MgsGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def inspect(self, raw, force=False):
        path = self.folder / 'authored.vgm'
        path.write_bytes(raw)
        return inspect_projection(path, self.folder, 'authored', force)

    def test_pure_opn2_blocked_even_with_force(self):
        raw = vgm(FM_PHRASE)
        with self.assertRaises(MgsProjectionError):
            self.inspect(raw)
        with self.assertRaises(MgsProjectionError) as caught:
            self.inspect(raw, force=True)
        self.assertIn('No supported AY, OPLL or SCC writes', str(caught.exception))

    def test_opn2_writes_inventoried_under_force(self):
        raw = vgm(bytes((0xa0, 7, 0x3f, 0xa0, 8, 0x0f)) + FM_PHRASE)
        with self.assertRaises(MgsProjectionError) as caught:
            self.inspect(raw)
        self.assertIn('unsupported source register writes', str(caught.exception))
        summary = self.inspect(raw, force=True)
        self.assertEqual(summary['omission_count'], 11)
        self.assertTrue(all(row['chip'] == 'OPN2' for row in summary['omissions']))
        ports = {row['port'] for row in summary['omissions']}
        self.assertEqual(ports, {0, 1})
        force_json = json.loads((self.folder/'authored.mgs.force.json').read_text())
        self.assertEqual(force_json['omission_count'], 11)


if __name__ == '__main__':
    unittest.main()
