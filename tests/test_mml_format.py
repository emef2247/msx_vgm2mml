"""Final whitespace layout preserves expanded music and native MGSC bytes."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from mml_format import format_mml
from mml_sync import analyze_mml, _leaves


def timeline(text):
    tracks, _, _ = analyze_mml(text)
    return {channel: [(node.text, node.start, node.end) for node in _leaves(nodes)]
            for channel, nodes in tracks.items()}


MIXED = ('#opll_mode 1\n#title "Formatter test"\n'
         '*0={c8[d16 e16]2}\n*1={b8[s16 h16]2}\n'
         '1 o4v10[*0[g8]2]2 a4\n'
         '4 o4v10[c8 d8]2 e4\n9 o4v10[e8 f8]2 g4\n'
         'f vb10vs10vh10[*1]2 b4\n')


class MmlFormatTests(unittest.TestCase):
    def assert_preserved(self, source):
        result = format_mml(source)
        self.assertEqual(timeline(source), timeline(result))
        self.assertEqual(format_mml(result), result)
        return result

    def test_uniform_channels_and_attached_counts(self):
        for channel in '123456789abcdefgh':
            with self.subTest(channel=channel):
                source = channel + ' c4[d8 e8]12f4\n'
                expected = '\n'.join(channel + ' ' + body
                                     for body in ('c4', '[', 'd8 e8', ']12', 'f4')) + '\n'
                self.assertEqual(format_mml(source), expected)

    def test_nested_adjacent_delimiters_default_and_zero_counts(self):
        source = '1 [[c4]3[d4]]2e4\n'
        result = self.assert_preserved(source)
        self.assertEqual(result, '1 [\n1 [\n1 c4\n1 ]3\n1 [\n1 d4\n1 ]\n1 ]2\n1 e4\n')
        self.assertEqual(format_mml('1 [c4] 12 d4'), '1 [\n1 c4\n1 ]12\n1 d4')
        self.assertIn('1 ]0\n', format_mml('1 [c4]0 d4\n'))

    def test_macros_nested_and_rhythm_keep_expanded_commands(self):
        result = self.assert_preserved(MIXED)
        self.assertIn('*0={\nc8\n[\nd16 e16\n]2\n}', result)
        self.assertIn('f ]2\nf b4', result)

    def test_opaque_definitions_metadata_and_comments_unchanged(self):
        header = ('; [literal] comment\n#title "[song]; {title}"\n'
                  '#psg_tune {\n1 2 3 [4]\n}\n'
                  '@e0={\n1 2 3\n}\n@s0={\n4 5 6\n}\n'
                  '@v0={\n9 10 11\n}\n\n')
        source = header + '1 [c4]2 d4  ; keep [comment] exactly\n\n'
        result = format_mml(source)
        self.assertTrue(result.startswith(header))
        self.assertTrue(result.endswith('1 d4  ; keep [comment] exactly\n\n'))
        self.assertEqual(format_mml(result), result)
        quoted = '1 "literal [x]; {y}" [c4]2\n'
        self.assertIn('1 "literal [x]; {y}"\n1 [\n', format_mml(quoted))

    def test_commented_multiline_macro_is_preserved_in_full(self):
        source = '*0={ [c4]2 ; [comment]\n d4 }\n1 *0 [e4]2\n'
        result = format_mml(source)
        self.assertTrue(result.startswith(source.split('1 *0')[0]))
        self.assertEqual(format_mml(result), result)

    def test_multiline_macro_numeric_body_is_not_a_track(self):
        source = '*0={\nc4 [d4]3\n}\n1 *0\n'
        result = self.assert_preserved(source)
        self.assertEqual(result, '*0={\nc4\n[\nd4\n]3\n}\n1 *0\n')

    def test_width_wrap_only_at_safe_unquoted_whitespace(self):
        source = '1 ' + ' '.join(['c4', 'd8', 'e16'] * 50) + '\n'
        result = self.assert_preserved(source)
        self.assertTrue(all(len(line) <= 120 for line in result.splitlines()))
        indivisible = '1 ' + 'c4' * 100 + '\n'
        self.assertEqual(format_mml(indivisible), indivisible)
        quote = '1 "' + 'a b ' * 40 + '" [c4]2\n'
        self.assertIn('"' + 'a b ' * 40 + '"', format_mml(quote))

    def test_blank_lines_line_endings_and_no_final_newline(self):
        for source in ('\n\n1 [c4]2\n\n', '1 [c4]2', '1 [c4]2\r\n'):
            result = format_mml(source)
            self.assertEqual(result.endswith('\n'), source.endswith('\n'))
            self.assertEqual(format_mml(result), result)
        self.assertEqual(format_mml(''), '')
        self.assertEqual(format_mml('1 [c4]2\r\n'), '1 [\r\n1 c4\r\n1 ]2\r\n')

    @unittest.skipUnless(shutil.which('mgsc'), 'Native MGSC is unavailable on PATH')
    def test_native_mgsc_binary_identical_all_chips_macros_and_rhythm(self):
        with tempfile.TemporaryDirectory() as folder:
            binaries = []
            for name, text in (('before', MIXED), ('after', format_mml(MIXED))):
                source = Path(folder) / (name + '.mml')
                output = source.with_suffix('.mgs')
                source.write_text(text, encoding='ascii')
                run = subprocess.run([shutil.which('mgsc'), str(source), str(output)],
                                     capture_output=True, timeout=30)
                self.assertEqual(run.returncode, 0, (run.stdout + run.stderr).decode(errors='replace'))
                self.assertTrue(output.exists(), (run.stdout + run.stderr).decode(errors='replace'))
                binaries.append(output.read_bytes())
            self.assertEqual(*binaries)


if __name__ == '__main__':
    unittest.main()
