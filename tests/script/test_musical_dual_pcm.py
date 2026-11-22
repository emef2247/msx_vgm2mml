"""Authored dual-PCM-cartridge checks: makoto/msxaudio and the
two-MSX-AUDIO composition split overlapping decoded PCM assets
across two cartridge PCM units, each with its own budget."""
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py')]
from native_music import NativeDevice, NativePCM, NativePerformance
from musical_variants import export_variants, project_variant


def asset(asset_id, start, end, seed):
    return NativePCM(asset_id, 'segapcm:0', start, end, 16000,
                     tuple(round(10000 * math.sin(j * math.tau * seed / 32))
                           for j in range(64)), (seed,), ())


def performance(assets, end=6000):
    device = NativeDevice('segapcm:0', 'segapcm', 0, 16000000)
    return NativePerformance((device,), (), (), (), (), (), end, '', '',
                             pcm_assets=tuple(assets))


class DualPcmVariantTests(unittest.TestCase):
    def test_makoto_msxaudio_splits_overlapping_assets(self):
        perf = performance([asset('a', 0, 4000, 1), asset('b', 1000, 5000, 2)])
        rows, prefix, losses, plan = project_variant(perf, 'makoto_msxaudio')
        commands = {row['command'][0] for row in rows}
        self.assertIn(0x57, commands)  # Makoto ADPCM-B lane
        self.assertIn(0x5c, commands)  # MSX-AUDIO Delta-T lane
        lanes = plan['pcm']['lanes']
        self.assertEqual(len(lanes), 2)
        self.assertTrue(all(lanes))
        self.assertEqual(losses['pcm_assets_on_second_unit'], 1)
        # One RAM block per unit in the prefix (OPNA 0x81, Y8950 0x88).
        self.assertEqual(prefix.count(bytes((0x67, 0x66))), 2)

    def test_msxaudio_pair_uses_dual_chip_encoding(self):
        perf = performance([asset('a', 0, 4000, 1), asset('b', 1000, 5000, 2)])
        rows, prefix, losses, plan = project_variant(perf, 'msxaudio_msxaudio')
        commands = {row['command'][0] for row in rows}
        self.assertIn(0x5c, commands)  # first Y8950
        self.assertIn(0xac, commands)  # second Y8950 (dual-chip form)
        self.assertEqual(losses['pcm_assets_on_second_unit'], 1)
        # The second unit's RAM block carries the size top-bit flag.
        sizes = []
        pos = 0
        while True:
            pos = prefix.find(bytes((0x67, 0x66, 0x88)), pos)
            if pos < 0:
                break
            sizes.append(struct.unpack_from('<I', prefix, pos + 3)[0])
            pos += 1
        self.assertEqual(len(sizes), 2)
        self.assertEqual(sum(1 for s in sizes if s & 0x80000000), 1)

    def test_dual_header_flag_is_written(self):
        perf = performance([asset('a', 0, 4000, 1), asset('b', 1000, 5000, 2)])
        with tempfile.TemporaryDirectory() as td:
            results = export_variants(perf, Path(td), 'song')
            self.assertEqual(results['msxaudio_msxaudio']['status'], 'success')
            self.assertEqual(results['makoto_msxaudio']['status'], 'success')
            raw = (Path(td) / 'msxaudio' / 'msxaudio' / 'song.vgm').read_bytes()
            clock = struct.unpack_from('<I', raw, 0x58)[0]
            self.assertTrue(clock & 0x40000000)
            self.assertTrue((Path(td) / 'makoto' / 'msxaudio' / 'song.vgm').is_file())

    def test_single_asset_stays_on_the_first_unit(self):
        perf = performance([asset('a', 0, 4000, 1)])
        rows, prefix, losses, plan = project_variant(perf, 'makoto_msxaudio')
        self.assertIsNone(plan['pcm']['lanes'][1])
        self.assertNotIn(0x5c, {row['command'][0] for row in rows})

    def test_triple_stack_uses_three_units(self):
        perf = performance([asset('a', 0, 4000, 1), asset('b', 1000, 5000, 2),
                            asset('c', 2000, 6000, 3)])
        rows, prefix, losses, plan = project_variant(
            perf, 'makoto_msxaudio_msxaudio')
        commands = {row['command'][0] for row in rows}
        self.assertIn(0x57, commands)  # Makoto ADPCM-B lane
        self.assertIn(0x5c, commands)  # first MSX-AUDIO Delta-T lane
        self.assertIn(0xac, commands)  # second MSX-AUDIO (dual-chip form)
        lanes = plan['pcm']['lanes']
        self.assertEqual(len(lanes), 3)
        self.assertTrue(all(lanes))
        self.assertEqual(losses['pcm_assets_on_second_unit'], 1)
        self.assertEqual(losses['pcm_assets_on_third_unit'], 1)
        with tempfile.TemporaryDirectory() as td:
            results = export_variants(perf, Path(td), 'song')
            self.assertEqual(results['makoto_msxaudio_msxaudio']['status'], 'success')
            self.assertTrue(
                (Path(td) / 'makoto' / 'msxaudio' / 'msxaudio' / 'song.vgm').is_file())


if __name__ == '__main__':
    unittest.main()
