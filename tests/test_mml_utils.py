"""
test_mml_utils.py - Unit tests for mml_utils helper functions.

Covers emit_volume() and emit_octave() which select the shorter of
the absolute or relative MML token for volume / octave changes.
"""
import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'py'))

from mml_utils import emit_volume, emit_octave


# ──────────────────────────────────────────────────────────────────────────
# emit_volume
# ──────────────────────────────────────────────────────────────────────────

class TestEmitVolume:
    def test_unknown_prev_always_absolute(self):
        """When v_prev is None the absolute token vN is always returned."""
        assert emit_volume(0) == 'v0'
        assert emit_volume(8) == 'v8'
        assert emit_volume(15) == 'v15'

    def test_equal_volume_returns_absolute(self):
        """When v == v_prev the absolute token is returned (no change needed)."""
        assert emit_volume(8, v_prev=8) == 'v8'

    # --- cases where relative is shorter ---

    def test_increase_saves_char(self):
        """dv=1 from v14 → ')1' (2 chars) < 'v15' (3 chars)."""
        assert emit_volume(15, v_prev=14) == ')1'

    def test_decrease_saves_char(self):
        """dv=-1 from v11 → '(1' (2 chars) < 'v10' (3 chars)."""
        assert emit_volume(10, v_prev=11) == '(1'

    def test_relative_increase_multi(self):
        """dv=5 from v5 → ')5' (2 chars) < 'v10' (3 chars)."""
        assert emit_volume(10, v_prev=5) == ')5'

    def test_relative_decrease_multi(self):
        """dv=-5 from v15 → '(5' (2 chars) < 'v10' (3 chars)."""
        assert emit_volume(10, v_prev=15) == '(5'

    # --- cases where relative is NOT shorter (equal or longer) ---

    def test_equal_length_keeps_absolute(self):
        """'v5' (2 chars) == ')5' (2 chars) → keep absolute for readability."""
        assert emit_volume(5, v_prev=0) == 'v5'

    def test_large_dv_keeps_absolute(self):
        """dv>15 is out of range → always absolute."""
        # hypothetical: v_prev=0, v=15 → dv=15, ')15' (3 chars) == 'v15' (3) → absolute
        assert emit_volume(15, v_prev=0) == 'v15'

    def test_single_digit_target_equal_length(self):
        """'v9' (2 chars) == ')9' (2 chars) → keep absolute."""
        assert emit_volume(9, v_prev=0) == 'v9'

    def test_decrease_equal_length_keeps_absolute(self):
        """'v1' (2 chars) == '(1' (2 chars) → keep absolute."""
        assert emit_volume(1, v_prev=2) == 'v1'

    def test_two_digit_dv_equal_to_two_digit_abs(self):
        """dv=10 from v0 → ')10' (3 chars) == 'v10' (3 chars) → keep absolute."""
        assert emit_volume(10, v_prev=0) == 'v10'


# ──────────────────────────────────────────────────────────────────────────
# emit_octave
# ──────────────────────────────────────────────────────────────────────────

class TestEmitOctave:
    def test_unknown_prev_always_absolute(self):
        """When o_prev is None the absolute token oN is always returned."""
        assert emit_octave(1) == 'o1'
        assert emit_octave(5) == 'o5'
        assert emit_octave(8) == 'o8'

    def test_equal_octave_returns_absolute(self):
        """When o == o_prev the absolute token is returned."""
        assert emit_octave(4, o_prev=4) == 'o4'

    # --- cases where relative is shorter ---

    def test_up_one_step(self):
        """do=+1 → '>' (1 char) < 'oN' (2 chars) → always use relative."""
        assert emit_octave(5, o_prev=4) == '>'
        assert emit_octave(2, o_prev=1) == '>'
        assert emit_octave(8, o_prev=7) == '>'

    def test_down_one_step(self):
        """do=-1 → '<' (1 char) < 'oN' (2 chars) → always use relative."""
        assert emit_octave(4, o_prev=5) == '<'
        assert emit_octave(1, o_prev=2) == '<'
        assert emit_octave(7, o_prev=8) == '<'

    # --- cases where relative is NOT shorter ---

    def test_two_steps_equal_length_keeps_absolute(self):
        """do=±2 → '>>' or '<<' (2 chars) == 'oN' (2 chars) → keep absolute."""
        assert emit_octave(6, o_prev=4) == 'o6'
        assert emit_octave(3, o_prev=5) == 'o3'

    def test_three_or_more_steps_keeps_absolute(self):
        """do=±3 or more → relative is longer → keep absolute."""
        assert emit_octave(7, o_prev=4) == 'o7'
        assert emit_octave(1, o_prev=5) == 'o1'
        assert emit_octave(8, o_prev=1) == 'o8'
