import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import vgm2mml


class BuildMergedMmlTests(unittest.TestCase):
    def test_default_uses_mgs_and_tempo_225(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = 'song'
            for chip in ('psg', 'scc', 'opll'):
                with open(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS.mml'), 'w', newline='\n') as fh:
                    fh.write(f';hdr\n#tempo 225\n#alloc 100\n{chip}_MGS\n')
                with open(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS_pct.mml'), 'w', newline='\n') as fh:
                    fh.write(f';hdr\n#tempo 75\n#alloc 100\n{chip}_PCT\n')

            merged = vgm2mml._build_merged_mml(stem, tmpdir, True, True, True)

            self.assertIn('#tempo 225', merged)
            self.assertIn('psg_MGS', merged)
            self.assertIn('scc_MGS', merged)
            self.assertIn('opll_MGS', merged)
            self.assertNotIn('psg_PCT', merged)

    def test_raw_ticks_uses_pct_and_tempo_75(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = 'song'
            for chip in ('psg', 'scc', 'opll'):
                with open(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS.mml'), 'w', newline='\n') as fh:
                    fh.write(f';hdr\n#tempo 225\n#alloc 100\n{chip}_MGS\n')
                with open(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS_pct.mml'), 'w', newline='\n') as fh:
                    fh.write(f';hdr\n#tempo 75\n#alloc 100\n{chip}_PCT\n')

            merged = vgm2mml._build_merged_mml(stem, tmpdir, True, True, True, raw_ticks=True)

            self.assertIn('#tempo 75', merged)
            self.assertIn('psg_PCT', merged)
            self.assertIn('scc_PCT', merged)
            self.assertIn('opll_PCT', merged)
            self.assertNotIn('psg_MGS', merged)


class MainCliTests(unittest.TestCase):
    def _make_parse_outputs(self, outdir, stem):
        names = [
            f'{stem}_log.psg.csv',
            f'{stem}_log.scc.csv',
            f'{stem}_trace.psg.csv',
            f'{stem}_trace.scc.csv',
            f'{stem}_log.opll.csv',
            f'{stem}_trace.opll.csv',
            f'{stem}_trace.opll_voice.csv',
            f'{stem}_trace.opll_regs.csv',
        ]
        paths = []
        for name in names:
            p = os.path.join(outdir, name)
            with open(p, 'w', newline='\n') as fh:
                fh.write('0\n')
            paths.append(p)
        return tuple(paths)

    def _fake_process(self, chip):
        def _fn(_input_path, output_dir, stem=None, **kwargs):
            stem = stem or 'song'
            mgs_path = os.path.join(output_dir, f'{stem}.{chip}.pass3.compress.MGS.mml')
            pct_path = os.path.join(output_dir, f'{stem}.{chip}.pass3.compress.MGS_pct.mml')
            with open(mgs_path, 'w', newline='\n') as fh:
                fh.write(f';hdr\n#tempo 225\n#alloc 100\n{chip}_MGS\n')
            with open(pct_path, 'w', newline='\n') as fh:
                fh.write(f';hdr\n#tempo 75\n#alloc 100\n{chip}_PCT\n')
            return pct_path if kwargs.get('raw_ticks') else mgs_path

        return _fn

    def test_help_includes_raw_ticks(self):
        out = io.StringIO()
        with patch('sys.argv', ['vgm2mml.py', '-h']), redirect_stdout(out):
            with self.assertRaises(SystemExit):
                vgm2mml.main()
        self.assertIn('--raw-ticks', out.getvalue())

    def test_main_default_uses_mgs_and_cleans_intermediates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = 'song'
            vgm_path = os.path.join(tmpdir, f'{stem}.vgm')
            with open(vgm_path, 'wb') as fh:
                fh.write(b'VGM')

            parse_outputs = self._make_parse_outputs(tmpdir, stem)
            with patch('vgm2mml.parse_vgm', return_value=parse_outputs), \
                 patch('vgm2mml.process_psg_csv', side_effect=self._fake_process('psg')), \
                 patch('vgm2mml.process_scc_csv', side_effect=self._fake_process('scc')), \
                 patch('vgm2mml.process_opll_csv', side_effect=self._fake_process('opll')), \
                 patch('sys.argv', ['vgm2mml.py', vgm_path, '--outdir', tmpdir]):
                vgm2mml.main()

            merged_path = os.path.join(tmpdir, f'{stem}.mml')
            self.assertTrue(os.path.exists(merged_path))
            with open(merged_path, 'r', newline='') as fh:
                merged = fh.read()
            self.assertIn('#tempo 225', merged)
            self.assertIn('psg_MGS', merged)
            self.assertIn('scc_MGS', merged)
            self.assertIn('opll_MGS', merged)
            self.assertNotIn('psg_PCT', merged)

            for chip in ('psg', 'scc', 'opll'):
                self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS.mml')))
                self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS_pct.mml')))

    def test_main_raw_ticks_uses_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = 'song'
            vgm_path = os.path.join(tmpdir, f'{stem}.vgm')
            with open(vgm_path, 'wb') as fh:
                fh.write(b'VGM')

            parse_outputs = self._make_parse_outputs(tmpdir, stem)
            with patch('vgm2mml.parse_vgm', return_value=parse_outputs), \
                 patch('vgm2mml.process_psg_csv', side_effect=self._fake_process('psg')), \
                 patch('vgm2mml.process_scc_csv', side_effect=self._fake_process('scc')), \
                 patch('vgm2mml.process_opll_csv', side_effect=self._fake_process('opll')), \
                 patch('sys.argv', ['vgm2mml.py', vgm_path, '--outdir', tmpdir, '--raw-ticks']):
                vgm2mml.main()

            merged_path = os.path.join(tmpdir, f'{stem}.mml')
            with open(merged_path, 'r', newline='') as fh:
                merged = fh.read()
            self.assertIn('#tempo 75', merged)
            self.assertIn('psg_PCT', merged)
            self.assertIn('scc_PCT', merged)
            self.assertIn('opll_PCT', merged)
            self.assertNotIn('psg_MGS', merged)

            for chip in ('psg', 'scc', 'opll'):
                self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS.mml')))
                self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.{chip}.pass3.compress.MGS_pct.mml')))


if __name__ == '__main__':
    unittest.main()
