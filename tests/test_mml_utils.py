"""
test_mml_utils.py - Unit tests for mml_utils helper functions.

Covers emit_volume, emit_octave, and rle_compress_tokens introduced to
support relative-notation and RLE compression in MML generation.
"""
import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'py'))

from mml_utils import emit_volume, emit_octave, rle_compress_tokens


# ──────────────────────────────────────────────────────────────────────────
# emit_volume
# ──────────────────────────────────────────────────────────────────────────

class TestEmitVolume:
    """emit_volume: return shorter of relative ')'/('  vs absolute 'vN'."""

    def test_no_change_returns_empty(self):
        assert emit_volume(10, 10) == ''
        assert emit_volume(0, 0) == ''
        assert emit_volume(15, 15) == ''

    def test_decrease_by_1_relative_wins(self):
        # ')' (1 char) < 'v9' (2 chars)
        assert emit_volume(9, 10) == ')'

    def test_decrease_by_1_single_digit_target(self):
        # ')' (1) < 'v5' (2) – relative always wins for diff=1 to single-digit target
        assert emit_volume(5, 6) == ')'

    def test_decrease_by_2_from_two_digit_relative_wins(self):
        # '))' (2) < 'v12' (3)
        assert emit_volume(12, 14) == '))'

    def test_decrease_by_2_single_digit_target_absolute_wins(self):
        # '))' (2) == 'v8' (2) – tie goes to absolute
        assert emit_volume(8, 10) == 'v8'

    def test_decrease_by_3_absolute_wins(self):
        # ')))' (3) > 'v7' (2) – absolute shorter for single-digit
        assert emit_volume(7, 10) == 'v7'
        # ')))' (3) == 'v12' (3) – tie goes to absolute
        assert emit_volume(12, 15) == 'v12'

    def test_increase_by_1_relative_wins(self):
        # '(' (1) < 'v14' (3)
        assert emit_volume(14, 13) == '('

    def test_increase_to_single_digit_relative_wins(self):
        # '(' (1) < 'v8' (2)
        assert emit_volume(8, 7) == '('

    def test_increase_by_2_single_digit_absolute_wins(self):
        # '((' (2) == 'v9' (2) – tie goes to absolute
        assert emit_volume(9, 7) == 'v9'

    def test_increase_by_2_two_digit_relative_wins(self):
        # '((' (2) < 'v14' (3)
        assert emit_volume(14, 12) == '(('

    def test_large_diff_always_absolute(self):
        # '))))))))))))))))' (15) >> 'v0' (2)
        assert emit_volume(0, 15) == 'v0'
        assert emit_volume(15, 0) == 'v15'


# ──────────────────────────────────────────────────────────────────────────
# emit_octave
# ──────────────────────────────────────────────────────────────────────────

class TestEmitOctave:
    """emit_octave: return shorter of relative '>'/'<' vs absolute 'oN'."""

    def test_no_change_returns_empty(self):
        assert emit_octave(4, 4) == ''
        assert emit_octave(1, 1) == ''

    def test_increase_by_1_relative_wins(self):
        # '>' (1) < 'o5' (2)
        assert emit_octave(5, 4) == '>'

    def test_decrease_by_1_relative_wins(self):
        # '<' (1) < 'o3' (2)
        assert emit_octave(3, 4) == '<'

    def test_diff_2_tie_goes_to_absolute(self):
        # '>>' (2) == 'o6' (2) – tie → absolute
        assert emit_octave(6, 4) == 'o6'
        # '<<' (2) == 'o2' (2) – tie → absolute
        assert emit_octave(2, 4) == 'o2'

    def test_large_diff_absolute_wins(self):
        assert emit_octave(1, 8) == 'o1'
        assert emit_octave(8, 1) == 'o8'


# ──────────────────────────────────────────────────────────────────────────
# rle_compress_tokens
# ──────────────────────────────────────────────────────────────────────────

class TestRleCompressTokens:
    """rle_compress_tokens: replace N identical consecutive tokens with N[tok]."""

    def test_empty_list(self):
        assert rle_compress_tokens([]) == []

    def test_single_token_unchanged(self):
        assert rle_compress_tokens(['e%4']) == ['e%4']

    def test_two_identical_tokens_compressed(self):
        # '2[e%4]' (6) < 'e%4 e%4' (7)
        assert rle_compress_tokens(['e%4', 'e%4']) == ['2[e%4]']

    def test_two_single_char_tokens_not_compressed(self):
        # '2[a]' (4) > 'a a' (3) – original shorter
        assert rle_compress_tokens(['a', 'a']) == ['a', 'a']

    def test_seven_decrease_tokens_compressed(self):
        tokens = [')e%1'] * 7
        result = rle_compress_tokens(tokens)
        assert result == ['7[)e%1]']

    def test_mixed_run_only_run_compressed(self):
        tokens = ['e%2', ')e%1', ')e%1', ')e%1']
        result = rle_compress_tokens(tokens)
        # 'e%2' is unique, ')e%1' x3 -> '3[)e%1]'
        # '3[)e%1]' (8) < ')e%1 )e%1 )e%1' (17)
        assert result == ['e%2', '3[)e%1]']

    def test_two_different_runs(self):
        tokens = [')e%1', ')e%1', ')f%1', ')f%1', ')f%1']
        result = rle_compress_tokens(tokens)
        assert result == ['2[)e%1]', '3[)f%1]']

    def test_compression_saves_characters(self):
        """Verify that compression never makes output longer."""
        tokens = [')e%1'] * 7
        compressed = rle_compress_tokens(tokens)
        original_len = sum(len(t) for t in tokens) + (len(tokens) - 1)
        compressed_len = sum(len(t) for t in compressed) + max(0, len(compressed) - 1)
        assert compressed_len < original_len

    def test_no_compression_when_not_shorter(self):
        """Single-char repeated twice: '2[a]'=4 vs 'a a'=3 – keep original."""
        assert rle_compress_tokens(['a', 'a']) == ['a', 'a']
        # 3 repetitions of single char DO compress: '3[b]'=4 < 'b b b'=5
        assert rle_compress_tokens(['b', 'b', 'b']) == ['3[b]']

    def test_whole_group_rle_matches_problem_example(self):
        """The exact scenario from the problem statement.

        Original: v10 o2 e%2  v9 e%1  v8 e%1 ...  v3 e%1  (8 notes)
        After relative conversion the grp_tokens are:
            ['e%2', ')e%1', ')e%1', ')e%1', ')e%1', ')e%1', ')e%1', ')e%1']
        After RLE: ['e%2', '7[)e%1]']
        """
        tokens = ['e%2'] + [')e%1'] * 7
        result = rle_compress_tokens(tokens)
        assert result == ['e%2', '7[)e%1]']
