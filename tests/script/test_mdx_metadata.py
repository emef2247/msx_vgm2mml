from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts')]
from audit_mdx_metadata import audit,inspect_mdx


class MdxMetadataTests(unittest.TestCase):
    def test_external_dump_metadata_is_reported_separately_from_the_score(self):
        text='title 原曲\npdxfile \nChannelStart A (0)\nSetTempo 131 BPM (219)\nNote 48 (c4) duration 11 (192 / 17)\n'
        run=subprocess.CompletedProcess(['mdxdump'],0,text.encode('cp932'),b'')
        with tempfile.TemporaryDirectory() as tmp,patch('audit_mdx_metadata.subprocess.run',return_value=run):
            folder=Path(tmp);mml=folder/'out.mml'
            mml.write_text('#title "原曲"\nA @t219 c16\n',encoding='utf-8')
            result=audit(Path('mdxdump'),folder/'reference.mdx',folder/'generated.mdx',mml,folder/'audit')
            self.assertTrue(result['compiled_title_matches_mml'])
            self.assertTrue(result['tempo_bytes_match_reference'])
            self.assertTrue(result['generated_tempo_visible_in_mml'])
            self.assertEqual(result['reference']['command_counts']['Note'],1)
            self.assertTrue((folder/'audit/reference.mdxdump.txt').exists())

    def test_external_failure_is_not_treated_as_missing_metadata(self):
        run=subprocess.CompletedProcess(['mdxdump'],1,b'partial',b'bad input')
        with tempfile.TemporaryDirectory() as tmp,patch('audit_mdx_metadata.subprocess.run',return_value=run):
            output=Path(tmp)/'dump.txt'
            with self.assertRaises(RuntimeError): inspect_mdx(Path('mdxdump'),Path('input.mdx'),output)
            self.assertEqual(output.read_bytes(),b'partial')
            self.assertEqual(output.with_suffix('.stderr.txt').read_bytes(),b'bad input')

    def test_multiline_title_and_pdx_terminator_are_metadata_not_music_commands(self):
        text='title 曲名\r\n作者\r\n\x1atones.pdx\npdxfile tones.pdx\nSetTempo 131 BPM (219)\n'
        run=subprocess.CompletedProcess(['mdxdump'],0,text.encode('cp932'),b'')
        with tempfile.TemporaryDirectory() as tmp,patch('audit_mdx_metadata.subprocess.run',return_value=run):
            result=inspect_mdx(Path('mdxdump'),Path('source.mdx'),Path(tmp)/'dump.txt')
            self.assertEqual(result['title'],'曲名\r\n作者')
            self.assertEqual(result['pdx'],'tones.pdx')
            self.assertEqual(result['command_counts'],{'SetTempo':1})
