"""Target state and compiler duration boundaries, independent of any song."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from mdx_compaction import compact, tokens
from source_loop_plan import expanded_tokens


class MdxCompactionTests(unittest.TestCase):
    def test_repeated_note_settings_are_reused_but_first_settings_remain(self):
        setup = '@2 @v127 p3 q8 D-5 o4'
        text, report = compact(f'{setup} c%12 {setup} d%12', 'A')
        self.assertEqual(text, f'{setup} c%12 d%12')
        self.assertEqual(len(report), 6)

    def test_raw_operator_or_algorithm_write_requires_same_voice_reload(self):
        for register in (0x20, 0x40, 0x60, 0xe0):
            text, _ = compact(f'@1 @v127 p3 q8 D0 o4 c%12 y{register},5 '
                              '@1 @v127 p3 q8 D0 o4 d%12', 'A')
            self.assertIn(f'y{register},5 @1 @v127 p3 d%12', text)

    def test_raw_pitch_and_keys_are_not_removed_and_do_not_modify_target_detune(self):
        text, _ = compact('D0 o4 c%12 y40,78 y8,120 r%1 y8,0 D0 o4 d%12', 'A')
        self.assertEqual(text, 'D0 o4 c%12 y40,78 y8,120 r%1 y8,0 d%12')

    def test_loop_entry_keeps_setters_needed_after_back_edge(self):
        text, _ = compact('D0 o4 [D0 o4 c%12 D1 o5 d%12]3 D1 o5 e%12', 'A')
        self.assertEqual(text, 'D0 o4 [ D0 o4 c%12 D1 o5 d%12 ]3 e%12')

    def test_nested_loops_keep_their_first_voice_and_note_settings(self):
        text, _ = compact('@1 p3 [@1 p3 c%4 [@1 p3 d%4 @1 p3 e%4]2 @2 p1 f%4]3', 'A')
        self.assertEqual(text.count('@1'), 3)
        self.assertEqual(text.count('p3'), 3)
        self.assertIn('@2 p1', text)

    def test_rest_compaction_preserves_encoded_chunk_sequence(self):
        def rest_chunks(text):
            result = []
            for token in expanded_tokens(text):
                ticks = int(token[2:])
                result.extend([128]*(ticks//128))
                if ticks % 128:
                    result.append(ticks % 128)
            return result
        for duration in (1, 127, 128, 1023, 1024, 1025, 32640, 65535):
            original = f'r%{duration}'
            result, _ = compact(original, 'A')
            self.assertEqual(rest_chunks(original), rest_chunks(result))
        self.assertEqual(compact('r%1024', 'A')[0], '[r%128]8')
        self.assertEqual(compact('r%896', 'A')[0], 'r%896')

    def test_tied_chunks_expand_exactly_with_tie_inside_loop(self):
        for count in (1, 3, 4, 255, 256, 520):
            original = 'c+%256 & ' * count + 'c+%17'
            result, _ = compact(original, 'A')
            self.assertEqual(expanded_tokens(original), expanded_tokens(result))
            if count >= 4:
                self.assertIn('&]', result)

    def test_different_pitches_or_raw_controls_stop_duration_run(self):
        original = 'c%256 & d%256 & y40,78 c%256 & c%256'
        self.assertEqual(tokens(compact(original, 'A')[0]), tokens(original))

    def test_equal_notes_without_ties_are_distinct_attacks(self):
        original = 'c%256 '*10
        self.assertEqual(tokens(compact(original, 'A')[0]), tokens(original))
        self.assertNotIn('[', compact(original, 'A')[0])

    def test_keyoff_then_keyon_is_retained_inside_a_source_loop(self):
        original = '[y8,120 r%8 y8,0 r%1]4'
        self.assertEqual(expanded_tokens(compact(original, 'A')[0]), expanded_tokens(original))

    def test_disabled_duration_compaction_emits_no_new_loops(self):
        original = 'r%8192 ' + 'c%256 & '*8 + 'c%3'
        self.assertNotIn('[', compact(original, 'A', durations=False)[0])

    def test_new_duration_loops_do_not_exceed_target_compiler_depth(self):
        original = '['*64 + 'r%2048 ' + 'c%256 & '*4 + 'c%3' + ']2'*64
        result, _ = compact(original, 'A')
        self.assertEqual(tokens(result), tokens(original))


if __name__ == '__main__':
    unittest.main()
