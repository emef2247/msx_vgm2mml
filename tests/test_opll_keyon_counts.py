"""Count actual key edges, never volume recovery or state-row changes."""
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
sys.path.insert(0, str(ROOT / 'scripts'))
from opll_comparison import compare_keyons
from check_opll_key_edges import extract


def edges(*channels):
    return [dict(ch=ch, keyon=1) for ch in channels]


class KeyOnCounts(unittest.TestCase):
    def test_channel_deficits_do_not_cancel_each_other(self):
        self.assertEqual(compare_keyons(edges(0, 0, 1), edges(0, 1, 1)),
                         dict(reference_keyon=3, actual_keyon=3, missing_keyon=1, extra_keyon=1))

    def test_only_keyon_edges_count_and_no_time_matching(self):
        reference = [dict(ch=0, keyon=1, time=0), dict(ch=0, keyon=0, time=1)]
        actual = [dict(ch=0, keyon=1, time=100)]
        self.assertEqual(compare_keyons(reference, actual),
                         dict(reference_keyon=1, actual_keyon=1, missing_keyon=0, extra_keyon=0))
        self.assertEqual(compare_keyons([], edges(0))['extra_keyon'], 1)
        self.assertEqual(compare_keyons(edges(0), [])['missing_keyon'], 1)

    def test_raw_edges_ignore_level_writes_volume_and_rhythm_channels(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'regs.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=('addr', 'val', 'time', 'ticks'))
                writer.writeheader()
                for i, (address, value) in enumerate([
                        (0x20, 0x10), (0x20, 0x10), (0x20, 0x11),
                        (0x30, 15), (0x30, 3), (0x20, 0), (0x20, 0x10),
                        (0x0e, 32), (0x26, 16), (0x26, 0),
                        (0x0e, 0), (0x26, 16)]):
                    writer.writerow(dict(addr=hex(address), val=value, time=i / 60, ticks=i))
            result = compare_keyons(extract(path), [])
            self.assertEqual(result['reference_keyon'], 3)
            self.assertEqual(result['missing_keyon'], 3)

    def test_pair_failure_has_blank_counts_instead_of_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            pairs = folder / 'pairs.csv'
            pairs.write_text('reference,actual\nmissing.vgm,also_missing.vgm\n', encoding='utf-8')
            out = folder / 'out'
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/check_opll_key_edges.py'),
                                   '--pairs', str(pairs), '--outdir', str(out)], capture_output=True)
            self.assertEqual(proc.returncode, 1)
            with (out / 'keyon_totals.csv').open(newline='') as stream:
                result = list(csv.DictReader(stream))
            self.assertEqual(result[0]['status'], 'error')
            self.assertEqual(result[0]['reference_keyon'], '')
            self.assertTrue(result[0]['error'])
