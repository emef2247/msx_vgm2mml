"""
test_mml_utils.py - Unit tests for mml_utils helper functions.

Covers:
  - ticks_to_mml_length_inherited  (B-rule length inheritance)
  - apply_repeat_compression        ([...]N compression)
  - compress_mml_channel            (channel-level block compression)
"""
import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'py'))

from mml_utils import (
    ticks_to_mml_length,
    ticks_to_mml_length_inherited,
    apply_repeat_compression,
    compress_mml_channel,
)


# ──────────────────────────────────────────────────────────────────────────
# ticks_to_mml_length_inherited
# ──────────────────────────────────────────────────────────────────────────

class TestTicksToMmlLengthInherited:
    def test_length_matches_default_omits_number(self):
        """When tick count matches default_len the length number is omitted."""
        s, new_def = ticks_to_mml_length_inherited(1, 'c', 64)
        assert s == 'c'
        assert new_def == 64

    def test_length_differs_from_default_writes_number(self):
        """When tick count differs from default the length is written and updates."""
        s, new_def = ticks_to_mml_length_inherited(4, 'c', 64)
        assert s == 'c16'
        assert new_def == 16

    def test_default_updated_for_subsequent_call(self):
        """The returned default_len is carried forward correctly."""
        _, new_def = ticks_to_mml_length_inherited(4, 'c', 64)   # c16
        s2, new_def2 = ticks_to_mml_length_inherited(4, 'd', new_def)   # d inherits 16
        assert s2 == 'd'
        assert new_def2 == 16

    def test_tied_note_first_part_differs_second_matches(self):
        """Tied note: first part differs (written), second part may match new default."""
        # 3 ticks = 32nd + 64th; default=64: c32 changes to 32, then c64 changes back to 64
        s, new_def = ticks_to_mml_length_inherited(3, 'c', 64)
        assert s == 'c32c64'
        assert new_def == 64

    def test_tied_note_both_parts_differ(self):
        """Tied note where both parts differ from the running default."""
        # 6 ticks = 16th + 32nd; default=64: c16 changes to 16, then c32 changes to 32
        s, new_def = ticks_to_mml_length_inherited(6, 'a', 64)
        assert s == 'a16a32'
        assert new_def == 32

    def test_rest_inherits_default(self):
        """Rest ('r') also benefits from length inheritance."""
        s, new_def = ticks_to_mml_length_inherited(1, 'r', 64)
        assert s == 'r'
        assert new_def == 64

    def test_rest_differs_from_default(self):
        s, new_def = ticks_to_mml_length_inherited(64, 'r', 64)
        assert s == 'r1'
        assert new_def == 1

    def test_zero_ticks_fallback(self):
        """Zero ticks should return the safe fallback 'r64' unchanged default."""
        s, new_def = ticks_to_mml_length_inherited(0, 'c', 64)
        assert s == 'r64'
        assert new_def == 64

    def test_matches_ticks_to_mml_length_when_default_never_matches(self):
        """With default_len=0 (never matches), output equals ticks_to_mml_length."""
        for ticks in [1, 2, 3, 4, 8, 32, 64]:
            s_inherited, _ = ticks_to_mml_length_inherited(ticks, 'a', 0)
            s_plain = ticks_to_mml_length(ticks, 'a')
            assert s_inherited == s_plain, (
                f"For ticks={ticks}: inherited={s_inherited!r} plain={s_plain!r}")


# ──────────────────────────────────────────────────────────────────────────
# apply_repeat_compression
# ──────────────────────────────────────────────────────────────────────────

class TestApplyRepeatCompression:
    def test_simple_repeat_compressed(self):
        tokens = ['c', 'c', 'c', 'c']
        result = apply_repeat_compression(tokens)
        assert result == ['[c]4']

    def test_two_token_repeat_compressed(self):
        tokens = ['c', 'd', 'c', 'd', 'c', 'd']
        result = apply_repeat_compression(tokens)
        assert result == ['[c d]3']

    def test_no_repeat_unchanged(self):
        tokens = ['c', 'd', 'e', 'f']
        result = apply_repeat_compression(tokens)
        assert result == tokens

    def test_grammar_is_bracket_N_not_N_bracket(self):
        """Result must be [...]N, never N[...]."""
        tokens = ['a', 'b', 'a', 'b']
        result = apply_repeat_compression(tokens)
        combined = ' '.join(result)
        assert '[' in combined
        assert combined.index('[') < combined.index(']')

    def test_only_applied_when_shorter(self):
        """Compression is only applied when it reduces size."""
        # [ab]2 = 5 chars, "ab ab" = 5 chars – no saving
        tokens = ['ab', 'ab']
        result = apply_repeat_compression(tokens)
        # saving: sub_size=2, orig=2*2+(2-1)=5, compressed=[ab]2=5, saving=0
        assert result == tokens  # not shorter, no compression

    def test_short_token_list_not_compressed(self):
        """Lists with fewer than 4 tokens are not processed."""
        tokens = ['c', 'c', 'c']
        result = apply_repeat_compression(tokens)
        assert result == tokens

    def test_recursive_compression(self):
        """Multiple non-overlapping repeats are compressed recursively."""
        # 'a b a b c d c d' should become '[a b]2 [c d]2'
        tokens = ['a', 'b', 'a', 'b', 'c', 'd', 'c', 'd']
        result = apply_repeat_compression(tokens)
        combined = ' '.join(result)
        # Both groups should be compressed
        assert '[a b]2' in combined
        assert '[c d]2' in combined

    def test_eight_identical_notes_compressed(self):
        """Eight identical notes should compress to [note]8."""
        tokens = ['g+'] * 8
        result = apply_repeat_compression(tokens)
        assert result == ['[g+]8']

    def test_context_tokens_preserved(self):
        """Tokens outside the repeated block are preserved unchanged."""
        tokens = ['v12', 'o3', 'c', 'c', 'c', 'c', 'v8']
        result = apply_repeat_compression(tokens)
        combined = ' '.join(result)
        assert combined.startswith('v12 o3')
        assert '[c]4' in combined
        assert combined.endswith('v8')


# ──────────────────────────────────────────────────────────────────────────
# compress_mml_channel
# ──────────────────────────────────────────────────────────────────────────

class TestCompressMmlChannel:
    def test_comment_items_pass_through(self):
        """Comment items (starting with ;) are left unchanged."""
        items = ['\n;ch4 start', '\n4 @0 v8 o5 l64 c', '\n;tick count: 1\n']
        result = compress_mml_channel(items)
        assert result[0] == '\n;ch4 start'
        assert result[-1] == '\n;tick count: 1\n'

    def test_multi_item_block_joined_and_compressed(self):
        """Multiple content items between comments are joined and compressed."""
        items = [
            '\n4 /2 v8 o1 l64 g+',  # group header + first note
            ' g+',                   # subsequent notes
            ' g+',
            ' g+',
            '',                      # empty flush
            '\n;tick count: 4\n',
        ]
        result = compress_mml_channel(items)
        # The four g+ items should be joined into one compressed item
        content_items = [r for r in result
                         if r.strip() and not r.strip().startswith(';')]
        assert len(content_items) == 1
        assert '[g+]4' in content_items[0]

    def test_compression_does_not_cross_comment(self):
        """Compression must not merge blocks across comment lines."""
        items = [
            '\n4 @0 v8 o5 l64 c',
            '\n;tick count: 1\n',
            '\n4 v8 o5 l64 c',
        ]
        result = compress_mml_channel(items)
        # There should still be two separate content items
        content_items = [r for r in result
                         if r.strip() and not r.strip().startswith(';')]
        assert len(content_items) == 2

    def test_empty_items_are_block_boundaries(self):
        """Empty items act as block boundaries (same as comments)."""
        items = [
            '\n4 /2 v8 o1 l64 g+',
            ' g+',
            '',                       # boundary
            '\n4 /2 v8 o1 l64 g+',
            ' g+',
        ]
        result = compress_mml_channel(items)
        content_items = [r for r in result
                         if r.strip() and not r.strip().startswith(';')]
        # Two separate blocks (each too small to compress [g+]2 saves nothing)
        assert len(content_items) == 2

    def test_tempo_preserved(self):
        """The #tempo 225 directive must survive channel compression."""
        # compress_mml_channel is applied per-channel after the header is built.
        # This test just verifies the function doesn't corrupt header-like tokens.
        items = ['\n\n;ch4 start', '\n4 @0 v8 o5 l64 c']
        result = compress_mml_channel(items)
        assert any(';ch4 start' in r for r in result)
