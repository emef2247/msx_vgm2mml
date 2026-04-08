"""
test_psg_mml.py - Smoke tests for the PSG MML pipeline.

Validates that process_psg_csv generates a .psg.mml file from the
committed golden input CSV, and checks basic properties of the output.
"""
import os
import sys
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'py'))

from psg_mml import process_psg_csv
from vgm_reader import parse_vgm

# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────
PSG_LOG_CSV = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint_log.psg.csv')

GOLDEN_PSG_MML = os.path.join(
    REPO_ROOT,
    'outputs', '02_StartingPoint_psg_log',
    '02_StartingPoint.psg.mml')

VGM_FILE = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint.vgm')

PSG_STEM = '02_StartingPoint'


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _read(path):
    with open(path, 'r', newline='') as fh:
        return fh.read()


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

def test_psg_log_csv_exists():
    """The committed golden PSG log CSV must exist."""
    assert os.path.isfile(PSG_LOG_CSV), (
        f"PSG log CSV not found: {PSG_LOG_CSV}")


def test_golden_psg_mml_exists():
    """The committed golden PSG MML must exist."""
    assert os.path.isfile(GOLDEN_PSG_MML), (
        f"Golden PSG MML not found: {GOLDEN_PSG_MML}")


def test_psg_mml_file_is_generated():
    """process_psg_csv must produce a .psg.mml file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        assert os.path.isfile(mml_path), (
            f"PSG MML file not generated: {mml_path}")


def test_psg_mml_ends_with_newline():
    """The generated PSG MML file must end with a newline (POSIX convention)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        with open(mml_path, 'rb') as fh:
            data = fh.read()
        assert data.endswith(b'\n'), "PSG MML file does not end with newline"


def test_psg_mml_contains_header():
    """The generated PSG MML must contain the standard PSG header."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        content = _read(mml_path)
        assert ';[name=psg lpf=1]' in content, "Missing PSG header comment"
        assert '#tempo 225' in content, "Missing tempo directive"


def test_psg_mml_dump_passes():
    """When dump_passes=True all four intermediate CSV files are written."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                        dump_passes=True)
        for suffix in ('pass0.csv', 'pass1.csv', 'pass2.csv', 'pass3.csv'):
            expected_file = os.path.join(out_dir, f'{PSG_STEM}.psg.{suffix}')
            assert os.path.isfile(expected_file), (
                f"Expected dump file not found: {expected_file}")


def test_psg_mml_no_dump():
    """When dump_passes=False no intermediate CSV files are written."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                        dump_passes=False)
        for suffix in ('pass0.csv', 'pass1.csv', 'pass2.csv', 'pass3.csv'):
            unexpected = os.path.join(out_dir, f'{PSG_STEM}.psg.{suffix}')
            assert not os.path.isfile(unexpected), (
                f"Unexpected dump file found: {unexpected}")


def test_psg_mml_matches_golden():
    """Generated PSG MML must be byte-for-byte identical to the golden."""
    import difflib
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        got = _read(mml_path)
        expected = _read(GOLDEN_PSG_MML)

        if got != expected:
            diff = ''.join(difflib.unified_diff(
                expected.splitlines(keepends=True),
                got.splitlines(keepends=True),
                fromfile=GOLDEN_PSG_MML,
                tofile=mml_path,
            ))
            pytest.fail(
                "Generated PSG MML differs from the golden reference.\n"
                "--- diff (expected vs got) ---\n" + diff)


def test_psg_mml_has_notes_not_only_rests():
    """PSG MML must contain actual note names (not only rests) after the fix."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        content = _read(mml_path)
        # Look for note letters a-g (with optional sharp) followed by a valid MML
        # length number (1, 2, 4, 8, 16, 32, 64) - e.g. "a16", "c+8", "b4"
        note_pattern = re.compile(r'\b[a-g]\+?(?:1|2|4|8|16|32|64)\b')
        notes = note_pattern.findall(content)
        assert len(notes) > 0, (
            "PSG MML contains only rests (no actual notes found). "
            "This likely means the frequency→scale mapping is broken.")


def test_psg_trace_csv_is_written():
    """parse_vgm must write the PSG trace CSV (chronological order)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        _psg_log, _scc_log, psg_trace, _scc_trace, *_ = parse_vgm(VGM_FILE, tmp_dir)
        assert os.path.isfile(psg_trace), (
            f"PSG trace CSV not written: {psg_trace}")
        # Must have more than just the header line
        with open(psg_trace) as fh:
            lines = [l for l in fh if not l.startswith('#') and l.strip()]
        assert len(lines) > 10, "PSG trace CSV appears empty"


def test_vgm_to_psg_mml_is_generated():
    """Full pipeline: VGM → PSG log CSV → PSG MML must produce a file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        psg_log, _scc_log, _psg_trace, _scc_trace, *_ = parse_vgm(VGM_FILE, tmp_dir)

        stem = '02_StartingPoint'
        out_dir = os.path.join(tmp_dir, stem)
        mml_path = process_psg_csv(psg_log, out_dir, stem=stem,
                                   dump_passes=False)
        assert os.path.isfile(mml_path), (
            f"PSG MML not generated from VGM pipeline: {mml_path}")


def test_vgm_to_psg_trace_mml_has_notes():
    """Full pipeline using trace CSV: PSG MML must contain notes, not just rests."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        _psg_log, _scc_log, psg_trace, _scc_trace, *_ = parse_vgm(VGM_FILE, tmp_dir)

        stem = '02_StartingPoint'
        out_dir = os.path.join(tmp_dir, stem)
        mml_path = process_psg_csv(psg_trace, out_dir, stem=stem,
                                   dump_passes=False)
        content = _read(mml_path)
        note_pattern = re.compile(r'\b[a-g]\+?(?:1|2|4|8|16|32|64)\b')
        notes = note_pattern.findall(content)
        assert len(notes) > 0, (
            "Trace-based PSG MML contains only rests - frequency mapping broken.")


# ──────────────────────────────────────────────────────────────────────────
# MGS-format variant tests
# ──────────────────────────────────────────────────────────────────────────

def test_psg_mgs_variants_are_generated():
    """process_psg_csv must produce all three pass3 MML variants."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM, dump_passes=False)
        for suffix in ('pass3.simple.mml',
                       'pass3.simple.MGS.mml',
                       'pass3.compress.MGS.mml'):
            expected = os.path.join(out_dir, f'{PSG_STEM}.psg.{suffix}')
            assert os.path.isfile(expected), (
                f"Missing PSG MGS variant: {expected}")


def test_psg_simple_mml_matches_main_mml():
    """pass3.simple.mml must be byte-for-byte identical to the main .psg.mml."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM, dump_passes=False)
        main_mml = _read(os.path.join(out_dir, f'{PSG_STEM}.psg.mml'))
        simple = _read(os.path.join(out_dir, f'{PSG_STEM}.psg.pass3.simple.mml'))
        assert main_mml == simple, (
            "pass3.simple.mml content differs from .psg.mml")


def test_psg_mgs_simple_has_header():
    """pass3.simple.MGS.mml must contain the standard PSG header."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM, dump_passes=False)
        content = _read(os.path.join(out_dir,
                                     f'{PSG_STEM}.psg.pass3.simple.MGS.mml'))
        assert ';[name=psg lpf=1]' in content
        assert '#tempo 225' in content


def test_psg_mgs_compress_smaller_than_simple():
    """pass3.compress.MGS.mml must be no larger than pass3.simple.MGS.mml."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM, dump_passes=False)
        simple_size = os.path.getsize(
            os.path.join(out_dir, f'{PSG_STEM}.psg.pass3.simple.MGS.mml'))
        compress_size = os.path.getsize(
            os.path.join(out_dir, f'{PSG_STEM}.psg.pass3.compress.MGS.mml'))
        assert compress_size <= simple_size, (
            f"compress ({compress_size}B) should be <= simple ({simple_size}B)")


def test_psg_mgs_simple_ends_with_newline():
    """pass3.simple.MGS.mml must end with a newline (POSIX convention)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM, dump_passes=False)
        with open(os.path.join(out_dir,
                               f'{PSG_STEM}.psg.pass3.simple.MGS.mml'), 'rb') as fh:
            data = fh.read()
        assert data.endswith(b'\n')
