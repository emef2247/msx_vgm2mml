"""
test_scc_mml.py - Regression tests for the SCC MML pipeline.

Runs the Python SCC MML processor against the committed golden inputs
and compares the generated pass3.mml to the committed golden reference.
"""
import os
import sys
import difflib
import tempfile
import pytest

# Locate repository root (one level up from tests/)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'py'))

from scc_mml import process_scc_csv

# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────
INPUT_CSV = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint_log.scc.csv')

GOLDEN_MML = os.path.join(
    REPO_ROOT,
    'outputs', '02_StartingPoint_log',
    '02_StartingPoint_log.scc.pass3.mml')


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _read(path):
    with open(path, 'r', newline='') as fh:
        return fh.read()


def _unified_diff(got, expected, got_label='got', exp_label='expected'):
    return ''.join(difflib.unified_diff(
        expected.splitlines(keepends=True),
        got.splitlines(keepends=True),
        fromfile=exp_label,
        tofile=got_label,
    ))


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

def test_input_csv_exists():
    """The committed golden input CSV must exist."""
    assert os.path.isfile(INPUT_CSV), (
        f"Golden input CSV not found: {INPUT_CSV}\n"
        "Run 'tclsh scc.tcl ...' to regenerate it.")


def test_golden_mml_exists():
    """The committed golden pass3.mml must exist."""
    assert os.path.isfile(GOLDEN_MML), (
        f"Golden MML not found: {GOLDEN_MML}")


def test_scc_pass3_mml_matches_golden():
    """Generated pass3.mml must be byte-for-byte identical to the golden."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False)

        got      = _read(mml_path)
        expected = _read(GOLDEN_MML)

        if got != expected:
            diff = _unified_diff(got, expected,
                                 got_label=mml_path,
                                 exp_label=GOLDEN_MML)
            pytest.fail(
                "Generated pass3.mml differs from the golden reference.\n"
                "--- diff (expected vs got) ---\n" + diff)


def test_scc_pass3_mml_dump_passes():
    """When dump_passes=True all four intermediate CSV files are written."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        process_scc_csv(INPUT_CSV, out_dir, dump_passes=True)

        stem = '02_StartingPoint_log'
        for suffix in ('pass0.csv', 'pass1.csv', 'pass2.csv', 'pass3.csv'):
            expected_file = os.path.join(out_dir, f'{stem}.scc.{suffix}')
            assert os.path.isfile(expected_file), (
                f"Expected dump file not found: {expected_file}")


def test_scc_pass3_mml_no_dump():
    """When dump_passes=False no intermediate CSV files are written."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        process_scc_csv(INPUT_CSV, out_dir, dump_passes=False)

        stem = '02_StartingPoint_log'
        for suffix in ('pass0.csv', 'pass1.csv', 'pass2.csv', 'pass3.csv'):
            unexpected = os.path.join(out_dir, f'{stem}.scc.{suffix}')
            assert not os.path.isfile(unexpected), (
                f"Unexpected dump file found: {unexpected}")


def test_scc_mml_wavetable_header():
    """The generated MML must contain the correct @s wavetable definitions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False)

        with open(mml_path) as fh:
            content = fh.read()

        assert '@s00 = {' in content, "Missing @s00 wavetable definition"
        assert ';[name=scc lpf=1]' in content, "Missing SCC header comment"
        assert '#tempo 75' in content, "Missing tempo directive"


def test_scc_mml_ends_with_newline():
    """The generated MML file must end with a newline (POSIX convention)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False)

        with open(mml_path, 'rb') as fh:
            data = fh.read()

        assert data.endswith(b'\n'), "MML file does not end with newline"
