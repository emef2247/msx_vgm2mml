import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import vgm2mml
import psg_mml
import scc_mml
from mml_utils import (build_section_group_map, is_enable_off_transition,
                       register_section_break)


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

    def test_skips_absent_chip_parts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = 'song'
            with open(os.path.join(tmpdir, f'{stem}.psg.pass3.compress.MGS.mml'), 'w', newline='\n') as fh:
                fh.write(';hdr\n#tempo 225\n#alloc 100\npsg_MGS\n')
            with open(os.path.join(tmpdir, f'{stem}.psg.pass3.compress.MGS_pct.mml'), 'w', newline='\n') as fh:
                fh.write(';hdr\n#tempo 75\n#alloc 100\npsg_PCT\n')

            merged = vgm2mml._build_merged_mml(stem, tmpdir, True, False, False)

            self.assertIn('psg_MGS', merged)
            self.assertNotIn('scc part', merged)
            self.assertNotIn('OPLL part', merged)


class MainCliTests(unittest.TestCase):
    def _make_parse_outputs(self, outdir, stem, has_psg=True, has_scc=True, has_opll=True):
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
        data_flags = [has_psg, has_scc, has_psg, has_scc, has_opll, has_opll, has_opll, has_opll]
        for name, has_data in zip(names, data_flags):
            p = os.path.join(outdir, name)
            with open(p, 'w', newline='\n') as fh:
                fh.write('0\n' if has_data else '# empty\n')
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

    def test_main_cleanup_only_detected_chips(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = 'song'
            vgm_path = os.path.join(tmpdir, f'{stem}.vgm')
            with open(vgm_path, 'wb') as fh:
                fh.write(b'VGM')

            parse_outputs = self._make_parse_outputs(tmpdir, stem, has_psg=True, has_scc=False, has_opll=False)
            def _absent_chip_process(_input_path, output_dir, stem=None, **_kwargs):
                stem = stem or 'song'
                return os.path.join(output_dir, f'{stem}.absent.mml')

            with patch('vgm2mml.parse_vgm', return_value=parse_outputs), \
                 patch('vgm2mml.process_psg_csv', side_effect=self._fake_process('psg')), \
                 patch('vgm2mml.process_scc_csv', side_effect=_absent_chip_process), \
                 patch('vgm2mml.process_opll_csv', side_effect=_absent_chip_process), \
                 patch('sys.argv', ['vgm2mml.py', vgm_path, '--outdir', tmpdir]):
                vgm2mml.main()

            merged_path = os.path.join(tmpdir, f'{stem}.mml')
            with open(merged_path, 'r', newline='') as fh:
                merged = fh.read()
            self.assertIn('psg_MGS', merged)
            self.assertNotIn('scc_MGS', merged)
            self.assertNotIn('opll_MGS', merged)

            self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.psg.pass3.compress.MGS.mml')))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.psg.pass3.compress.MGS_pct.mml')))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.scc.pass3.compress.MGS.mml')))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.scc.pass3.compress.MGS_pct.mml')))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.opll.pass3.compress.MGS.mml')))
            self.assertFalse(os.path.exists(os.path.join(tmpdir, f'{stem}.opll.pass3.compress.MGS_pct.mml')))


class SectionBreakTrackingTests(unittest.TestCase):
    def test_enable_off_transition_requires_actual_enabled_to_disabled_edge(self):
        self.assertFalse(is_enable_off_transition(None, 0))
        self.assertFalse(is_enable_off_transition(0, 0))
        self.assertFalse(is_enable_off_transition(0, 1))
        self.assertFalse(is_enable_off_transition(1, 1))
        self.assertFalse(is_enable_off_transition(3, 2))
        self.assertTrue(is_enable_off_transition(1, 0))
        self.assertTrue(is_enable_off_transition(3, 0))

    def test_psg_group_comment_waits_for_all_channels_and_uses_section_deltas(self):
        group_map = build_section_group_map(psg_mml.PSG_SECTION_TRACK_GROUPS)
        self.assertEqual('', register_section_break(group_map, 1, 4))
        self.assertEqual('', register_section_break(group_map, 2, 5))
        self.assertEqual(
            '\n; Total length count: ch1-ch2-ch3: 4-5-6\n',
            register_section_break(group_map, 3, 6),
        )
        self.assertEqual('', register_section_break(group_map, 1, 10))
        self.assertEqual('', register_section_break(group_map, 2, 11))
        self.assertEqual(
            '\n; Total length count: ch1-ch2-ch3: 6-6-6\n',
            register_section_break(group_map, 3, 12),
        )

    def test_scc_group_comment_waits_for_all_channels_and_uses_section_deltas(self):
        group_map = build_section_group_map(scc_mml.SCC_SECTION_TRACK_GROUPS)
        self.assertEqual('', register_section_break(group_map, 4, 7))
        self.assertEqual('', register_section_break(group_map, 5, 8))
        self.assertEqual('', register_section_break(group_map, 6, 9))
        self.assertEqual(
            '\n; Total length count: ch4-ch5-ch6-ch7: 7-8-9-10\n',
            register_section_break(group_map, 7, 10),
        )
        self.assertEqual('', register_section_break(group_map, 4, 11))
        self.assertEqual('', register_section_break(group_map, 5, 14))
        self.assertEqual('', register_section_break(group_map, 6, 17))
        self.assertEqual(
            '\n; Total length count: ch4-ch5-ch6-ch7: 4-6-8-10\n',
            register_section_break(group_map, 7, 20),
        )


class PsgSectionCommentOutputTests(unittest.TestCase):
    def _make_psg_row(self, type_, time_s, ch, en, volume=10, freq_a=85, freq_b=0):
        row = [''] * 34
        row[psg_mml.COL_TYPE] = type_
        row[psg_mml.COL_TIME] = str(time_s)
        row[psg_mml.COL_CH] = str(ch)
        row[psg_mml.COL_EN] = str(en)
        row[psg_mml.COL_FCTRLA] = str(freq_a)
        row[psg_mml.COL_FCTRLB] = str(freq_b)
        row[psg_mml.COL_AVCTRL] = str(volume)
        row[psg_mml.COL_VVCTRL] = '0'
        row[psg_mml.COL_ENVPCTRL_L] = '11'
        row[psg_mml.COL_ENVPCTRL_M] = '0'
        row[psg_mml.COL_ENVSHAPE] = '0'
        return ','.join(row)

    def test_process_psg_csv_emits_group_comments_only_on_en_off_transitions(self):
        rows = []
        rows.extend([
            self._make_psg_row('fCA', 0.0, 0, 1, volume=10),
            self._make_psg_row('mode', 0.10, 0, 0, volume=10),
            self._make_psg_row('fCA', 0.10, 0, 1, volume=10),
            self._make_psg_row('mode', 0.30, 0, 0, volume=10),
        ])
        rows.extend([
            self._make_psg_row('fCA', 0.0, 1, 1, volume=11),
            self._make_psg_row('aVC', 0.05, 1, 1, volume=0),
            self._make_psg_row('mode', 0.20, 1, 0, volume=0),
            self._make_psg_row('fCA', 0.20, 1, 1, volume=11),
            self._make_psg_row('aVC', 0.25, 1, 1, volume=0),
            self._make_psg_row('mode', 0.40, 1, 0, volume=0),
        ])
        rows.extend([
            self._make_psg_row('fCA', 0.0, 2, 1, volume=12),
            self._make_psg_row('mode', 0.15, 2, 0, volume=12),
            self._make_psg_row('fCA', 0.15, 2, 1, volume=12),
            self._make_psg_row('mode', 0.25, 2, 0, volume=12),
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, 'song_log.psg.csv')
            with open(input_path, 'w', newline='\n') as fh:
                fh.write('#type,time,ch,ticks,l,fL,v,fV,f,fF,o,scale,en,fEn,vDiff,vCnt,oDiff,envlp,envlpIndex,nE,nF,offset,data,wtbIndex,fCtrlA,fCtrlB,wNCtrl,vVCtrl,aVCtrl,envPCtrlL,envPCtrlM,envShape,ioParallel1,ioParallel2\n')
                for row in rows:
                    fh.write(row + '\n')

            output_path = psg_mml.process_psg_csv(
                input_path,
                tmpdir,
                stem='song',
                dump_passes=False,
                debug=True,
            )

            with open(output_path, 'r', newline='') as fh:
                text = fh.read()

        self.assertNotIn(';tick count:', text)
        self.assertNotIn('end: tick count', text)
        self.assertEqual(1, text.count('; Total length count: ch1-ch2-ch3: 6-12-9'))
        self.assertEqual(1, text.count('; Total length count: ch1-ch2-ch3: 12-12-6'))


class SccSectionCommentOutputTests(unittest.TestCase):
    class _DummyWtbTracker:
        def __init__(self):
            self.bytes_list = []

    def _make_scc_row(self, type_, length, volume, en, scale='c', octave=4, wtb_index=0):
        row = ['{}'] * scc_mml.NUM_COLS
        row[scc_mml.COL_TYPE] = type_
        row[scc_mml.COL_L] = str(length)
        row[scc_mml.COL_O] = str(octave)
        row[scc_mml.COL_SCALE] = scale
        row[scc_mml.COL_EN] = str(en)
        row[scc_mml.COL_WTBINDEX] = str(wtb_index)
        row[scc_mml.COL_VCTRL] = str(volume)
        row[scc_mml.COL_VDIFF] = '0'
        row[scc_mml.COL_VCNT] = '1'
        return row

    def _make_scc_buffers(self):
        return {
            0: [
                self._make_scc_row('f1Ctrl', 4, 8, 1),
                self._make_scc_row('f1Ctrl', 0, 8, 0),
                self._make_scc_row('f1Ctrl', 9, 8, 1),
                self._make_scc_row('f1Ctrl', 0, 8, 0),
            ],
            1: [
                self._make_scc_row('f1Ctrl', 4, 7, 1),
                self._make_scc_row('vCtrl', 2, 0, 1),
                self._make_scc_row('enBit', 0, 0, 0),
                self._make_scc_row('f1Ctrl', 3, 7, 1),
                self._make_scc_row('vCtrl', 1, 0, 1),
                self._make_scc_row('enBit', 0, 0, 0),
            ],
            2: [
                self._make_scc_row('f1Ctrl', 6, 6, 1),
                self._make_scc_row('enBit', 0, 6, 0),
                self._make_scc_row('f1Ctrl', 4, 6, 1),
                self._make_scc_row('enBit', 0, 6, 0),
            ],
            3: [
                self._make_scc_row('f1Ctrl', 5, 5, 1),
                self._make_scc_row('enBit', 0, 5, 0),
                self._make_scc_row('f1Ctrl', 7, 5, 1),
                self._make_scc_row('enBit', 0, 5, 0),
            ],
        }

    def test_generate_mml_emits_only_group_total_length_comments(self):
        text = scc_mml._generate_mml(
            self._make_scc_buffers(),
            [0, 1, 2, 3],
            'song',
            self._DummyWtbTracker(),
        )

        self.assertNotIn(';tick count:', text)
        self.assertNotIn('end: tick count', text)
        self.assertEqual(1, text.count('; Total length count: ch4-ch5-ch6-ch7: 4-6-6-5'))
        self.assertEqual(1, text.count('; Total length count: ch4-ch5-ch6-ch7: 9-4-4-7'))

    def test_generate_mml_mgs_emits_only_group_total_length_comments(self):
        text = scc_mml._generate_mml_mgs(
            self._make_scc_buffers(),
            [0, 1, 2, 3],
            'song',
            self._DummyWtbTracker(),
            use_cnt=False,
            use_pct=True,
        )

        self.assertNotIn(';tick count:', text)
        self.assertNotIn('end: tick count', text)
        self.assertEqual(1, text.count('; Total length count: ch4-ch5-ch6-ch7: 4-6-6-5'))
        self.assertEqual(1, text.count('; Total length count: ch4-ch5-ch6-ch7: 9-4-4-7'))


if __name__ == '__main__':
    unittest.main()
