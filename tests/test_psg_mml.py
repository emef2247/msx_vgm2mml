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
# Inheritance and [...]N compression feature tests
# ──────────────────────────────────────────────────────────────────────────

def test_psg_mml_length_inheritance():
    """Generated PSG MML must use B-rule length inheritance on content lines."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        content = _read(mml_path)

    # After an 'lN' declaration, subsequent notes of the same length should
    # have no explicit length suffix.  Check that the MML contains bare note
    # tokens (letter only, no following digit).
    content_lines = [ln for ln in content.splitlines()
                     if not ln.strip().startswith(';') and ln.strip()]
    for line in content_lines:
        if re.search(r'\bl\d+\b', line):
            # Bare note: a note letter (with optional '+') not followed by a digit
            bare = re.findall(r'(?<![a-z@/\d])([a-gr]\+?)(?!\d)(?=\s|$)', line)
            if bare:
                return  # Found at least one inherited bare note

    pytest.fail(
        "No bare (length-omitted) notes found in PSG MML. "
        "Length inheritance does not appear to be active.")


def test_psg_mml_sync_after_comment():
    """After every ;tick count: comment, audible PSG groups must declare v, o, l."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        content = _read(mml_path)

    lines = content.splitlines()
    violations = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ';tick count:' in line:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                next_content = lines[j].strip()
                if next_content and not next_content.startswith(';'):
                    # For mute mode (/0), only v is required
                    is_mute = '/0' in next_content
                    if not is_mute:
                        # Audible mode must have v, o, l
                        if not re.search(r'\bv\d+\b', next_content):
                            violations.append(f"line {j+1}: missing v: {next_content!r}")
                        if not re.search(r'\bo\d+\b', next_content):
                            violations.append(f"line {j+1}: missing o: {next_content!r}")
                        if not re.search(r'\bl\d+\b', next_content):
                            violations.append(f"line {j+1}: missing l: {next_content!r}")
                    else:
                        if not re.search(r'\bv\d+\b', next_content):
                            violations.append(f"line {j+1}: missing v in mute: {next_content!r}")
        i += 1

    assert not violations, (
        "PSG group headers after ;tick count: comments missing declarations:\n"
        + '\n'.join(violations[:10]))


def test_psg_mml_bracket_compression_grammar():
    """Any [...]N compression in PSG MML must use [...]N grammar (not N[...])."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, PSG_STEM)
        mml_path = process_psg_csv(PSG_LOG_CSV, out_dir, stem=PSG_STEM,
                                   dump_passes=False)
        content = _read(mml_path)

    wrong = re.findall(r'\d+\[', content)
    assert not wrong, (
        f"Found N[...] (wrong) repeat syntax in PSG MML: {wrong}")

    brackets = re.findall(r'\[([^\]]+)\](\d+)', content)
    for inner, count in brackets:
        assert int(count) >= 2, (
            f"Repeat count {count} < 2 in [...]N construct: [{inner}]{count}")

