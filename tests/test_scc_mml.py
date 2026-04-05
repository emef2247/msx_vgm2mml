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
from vgm_reader import parse_vgm

# ──────────────────────────────────────────────────────────────────────────
# Paths – log (per-channel grouped) pipeline
# ──────────────────────────────────────────────────────────────────────────
INPUT_CSV = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint_log.scc.csv')

GOLDEN_MML = os.path.join(
    REPO_ROOT,
    'outputs', '02_StartingPoint_log',
    '02_StartingPoint.scc.mml')

# ──────────────────────────────────────────────────────────────────────────
# Paths – trace (chronological) pipeline
# ──────────────────────────────────────────────────────────────────────────
TRACE_CSV = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint_trace.scc.csv')

GOLDEN_TRACE_MML = os.path.join(
    REPO_ROOT,
    'outputs', '02_StartingPoint_trace',
    '02_StartingPoint.scc.mml')

VGM_FILE = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint.vgm')

# ──────────────────────────────────────────────────────────────────────────
# Paths – 01_AbovetheHorizon (ch7 tick-offset regression)
# ──────────────────────────────────────────────────────────────────────────
ABOVE_TRACE_CSV = os.path.join(
    REPO_ROOT,
    'inputs', '01_AbovetheHorizon', '01_AbovetheHorizon_trace.scc.csv')

ABOVE_LOG_CSV = os.path.join(
    REPO_ROOT,
    'inputs', '01_AbovetheHorizon', '01_AbovetheHorizon_log.scc.csv')

ABOVE_GOLDEN_TRACE_MML = os.path.join(
    REPO_ROOT,
    'outputs', '01_AbovetheHorizon_trace',
    '01_AbovetheHorizon.scc.mml')

ABOVE_GOLDEN_LOG_MML = os.path.join(
    REPO_ROOT,
    'outputs', '01_AbovetheHorizon_log',
    '01_AbovetheHorizon.scc.mml')


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
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')

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
        process_scc_csv(INPUT_CSV, out_dir, dump_passes=True,
                        stem='02_StartingPoint')

        stem = '02_StartingPoint'
        for suffix in ('pass0.csv', 'pass1.csv', 'pass2.csv', 'pass3.csv'):
            expected_file = os.path.join(out_dir, f'{stem}.scc.{suffix}')
            assert os.path.isfile(expected_file), (
                f"Expected dump file not found: {expected_file}")


def test_scc_pass3_mml_no_dump():
    """When dump_passes=False no intermediate CSV files are written."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                        stem='02_StartingPoint')

        stem = '02_StartingPoint'
        for suffix in ('pass0.csv', 'pass1.csv', 'pass2.csv', 'pass3.csv'):
            unexpected = os.path.join(out_dir, f'{stem}.scc.{suffix}')
            assert not os.path.isfile(unexpected), (
                f"Unexpected dump file found: {unexpected}")


def test_scc_mml_wavetable_header():
    """The generated MML must contain the correct @s wavetable definitions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')

        with open(mml_path) as fh:
            content = fh.read()

        assert '@s00 = {' in content, "Missing @s00 wavetable definition"
        assert ';[name=scc lpf=1]' in content, "Missing SCC header comment"
        assert '#tempo 225' in content, "Missing tempo directive"


def test_scc_mml_ends_with_newline():
    """The generated MML file must end with a newline (POSIX convention)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')

        with open(mml_path, 'rb') as fh:
            data = fh.read()

        assert data.endswith(b'\n'), "MML file does not end with newline"


# ──────────────────────────────────────────────────────────────────────────
# Trace CSV pipeline tests
# ──────────────────────────────────────────────────────────────────────────

def test_trace_csv_exists():
    """The committed Tcl-generated trace CSV must exist."""
    assert os.path.isfile(TRACE_CSV), (
        f"Trace CSV not found: {TRACE_CSV}\n"
        "Run 'tclsh scc.tcl ...' to regenerate it.")


def test_golden_trace_mml_exists():
    """The committed golden trace pass3.mml must exist."""
    assert os.path.isfile(GOLDEN_TRACE_MML), (
        f"Golden trace MML not found: {GOLDEN_TRACE_MML}")


def test_trace_csv_pass3_mml_matches_golden():
    """MML generated from Tcl trace CSV must match the committed golden."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_trace')
        mml_path = process_scc_csv(TRACE_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')

        got      = _read(mml_path)
        expected = _read(GOLDEN_TRACE_MML)

        if got != expected:
            diff = _unified_diff(got, expected,
                                 got_label=mml_path,
                                 exp_label=GOLDEN_TRACE_MML)
            pytest.fail(
                "Trace-based pass3.mml differs from the golden reference.\n"
                "--- diff (expected vs got) ---\n" + diff)


def test_vgm_to_trace_mml_matches_golden():
    """Full pipeline: VGM → trace CSV → MML must match the committed golden."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 1: parse VGM → trace CSV
        _psg_log, _scc_log, _psg_trace, scc_trace, *_ = parse_vgm(VGM_FILE, tmp_dir)

        # Step 2: trace CSV → MML
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_trace')
        mml_path = process_scc_csv(scc_trace, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')

        got      = _read(mml_path)
        expected = _read(GOLDEN_TRACE_MML)

        if got != expected:
            diff = _unified_diff(got, expected,
                                 got_label=mml_path,
                                 exp_label=GOLDEN_TRACE_MML)
            pytest.fail(
                "VGM→trace→MML differs from the golden reference.\n"
                "--- diff (expected vs got) ---\n" + diff)


def test_python_trace_csv_matches_tcl_trace_csv():
    """Python-generated trace CSV must be identical to the Tcl-generated one."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        _psg_log, _scc_log, _psg_trace, scc_trace, *_ = parse_vgm(VGM_FILE, tmp_dir)

        got      = _read(scc_trace)
        expected = _read(TRACE_CSV)

        if got != expected:
            diff = _unified_diff(got, expected,
                                 got_label=scc_trace,
                                 exp_label=TRACE_CSV)
            pytest.fail(
                "Python-generated trace CSV differs from the Tcl reference.\n"
                "--- diff (expected vs got) ---\n" + diff)


# ──────────────────────────────────────────────────────────────────────────
# 01_AbovetheHorizon: ch7 timing regression tests
# ──────────────────────────────────────────────────────────────────────────

def _extract_end_ticks(mml_text):
    """Return {ch_num: tick_count} for all 'chN end: tick count:' comments."""
    import re
    result = {}
    for m in re.finditer(r';ch(\d+) end: tick count: (\d+)', mml_text):
        result[int(m.group(1))] = int(m.group(2))
    return result


def test_above_horizon_ch7_tick_count_trace():
    """ch7 tick count must match ch4-6 when processing 01_AbovetheHorizon trace CSV.

    Regression test for the bug where wtbNew/wtbLast rows were dropped in pass2
    without propagating their l values, causing ch7 (internal ch3) to be 32
    ticks short because its waveform initialisation occupies the first 32 ticks.
    """
    if not os.path.isfile(ABOVE_TRACE_CSV):
        pytest.skip(f"01_AbovetheHorizon trace CSV not found: {ABOVE_TRACE_CSV}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '01_AbovetheHorizon_trace')
        mml_path = process_scc_csv(ABOVE_TRACE_CSV, out_dir, dump_passes=False)
        ticks = _extract_end_ticks(_read(mml_path))

    assert ticks, "No end-tick comments found in generated MML"
    expected = ticks[4]  # ch4 (SCC ch0) is the reference
    for ch in (5, 6, 7):
        assert ticks.get(ch) == expected, (
            f"ch{ch} tick count {ticks.get(ch)} != ch4 tick count {expected}; "
            f"all channels must have equal total length")


def test_above_horizon_ch7_tick_count_log():
    """Same regression test using the log (per-channel) CSV variant."""
    if not os.path.isfile(ABOVE_LOG_CSV):
        pytest.skip(f"01_AbovetheHorizon log CSV not found: {ABOVE_LOG_CSV}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '01_AbovetheHorizon_log')
        mml_path = process_scc_csv(ABOVE_LOG_CSV, out_dir, dump_passes=False)
        ticks = _extract_end_ticks(_read(mml_path))

    assert ticks, "No end-tick comments found in generated MML"
    expected = ticks[4]
    for ch in (5, 6, 7):
        assert ticks.get(ch) == expected, (
            f"ch{ch} tick count {ticks.get(ch)} != ch4 tick count {expected}; "
            f"all channels must have equal total length")


def test_above_horizon_trace_mml_matches_golden():
    """Generated MML for 01_AbovetheHorizon trace must match the committed golden."""
    if not os.path.isfile(ABOVE_TRACE_CSV):
        pytest.skip(f"01_AbovetheHorizon trace CSV not found: {ABOVE_TRACE_CSV}")
    if not os.path.isfile(ABOVE_GOLDEN_TRACE_MML):
        pytest.skip(f"01_AbovetheHorizon trace golden MML not found: {ABOVE_GOLDEN_TRACE_MML}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '01_AbovetheHorizon_trace')
        mml_path = process_scc_csv(ABOVE_TRACE_CSV, out_dir, dump_passes=False,
                                   stem='01_AbovetheHorizon')

        got      = _read(mml_path)
        expected = _read(ABOVE_GOLDEN_TRACE_MML)

        if got != expected:
            diff = _unified_diff(got, expected,
                                 got_label=mml_path,
                                 exp_label=ABOVE_GOLDEN_TRACE_MML)
            pytest.fail(
                "01_AbovetheHorizon trace pass3.mml differs from golden.\n"
                "--- diff (expected vs got) ---\n" + diff)


# ──────────────────────────────────────────────────────────────────────────
# Inheritance and [...]N compression feature tests
# ──────────────────────────────────────────────────────────────────────────

def test_scc_mml_length_inheritance():
    """Generated SCC MML must use B-rule length inheritance (omit repeated lengths)."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')
        content = _read(mml_path)

    # After 'l64' declaration, a note that uses the default length should
    # appear without an explicit length number (e.g., just 'c', not 'c64').
    # Find a line that declares l64 and check that not ALL notes on it have
    # explicit length suffixes (the inheritance should suppress many of them).
    content_lines = [ln for ln in content.splitlines()
                     if not ln.strip().startswith(';') and ln.strip()]
    for line in content_lines:
        if 'l64' in line:
            # A note token looks like a letter (optionally with +) followed by
            # a digit, e.g. c64, e16.  Also plain letters like 'c', 'e' are notes.
            note_with_len = re.findall(r'\b[a-gr]\+?(?:1|2|4|8|16|32|64)\b', line)
            note_bare = re.findall(r'(?<![a-z@/\d])([a-gr]\+?)(?!\d)(?=\s|$)', line)
            if note_bare:
                # At least one inherited (bare) note on an l64 line – test passes
                return

    pytest.fail(
        "No bare (length-omitted) notes found on any 'l64' line in SCC MML.\n"
        "Length inheritance (B-rule) does not appear to be active.")


def test_scc_mml_sync_after_comment():
    """After every ;tick count: comment, the next group must declare v, o, and l."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')
        content = _read(mml_path)

    lines = content.splitlines()
    violations = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ';tick count:' in line:
            # Skip blank lines after the comment
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                next_content = lines[j].strip()
                if next_content and not next_content.startswith(';'):
                    # This is the group header after a sync point.
                    # It must contain v, o, and l declarations.
                    if not re.search(r'\bv\d+\b', next_content):
                        violations.append(f"line {j+1}: missing v declaration: {next_content!r}")
                    if not re.search(r'\bo\d+\b', next_content):
                        violations.append(f"line {j+1}: missing o declaration: {next_content!r}")
                    if not re.search(r'\bl\d+\b', next_content):
                        violations.append(f"line {j+1}: missing l declaration: {next_content!r}")
        i += 1

    assert not violations, (
        "Group headers after ;tick count: comments missing v/o/l declarations:\n"
        + '\n'.join(violations[:10]))


def test_scc_mml_bracket_compression_grammar():
    """Any [...]N compression in SCC MML must use [...]N grammar (not N[...])."""
    import re
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = os.path.join(tmp_dir, '02_StartingPoint_log')
        mml_path = process_scc_csv(INPUT_CSV, out_dir, dump_passes=False,
                                   stem='02_StartingPoint')
        content = _read(mml_path)

    # N[...] pattern must NOT appear (wrong grammar)
    wrong = re.findall(r'\d+\[', content)
    assert not wrong, (
        f"Found N[...] (wrong) repeat syntax in SCC MML: {wrong}")

    # [...] must be followed immediately by a digit
    # Allow for any bracket constructs that do appear
    brackets = re.findall(r'\[([^\]]+)\](\d+)', content)
    for inner, count in brackets:
        assert int(count) >= 2, (
            f"Repeat count {count} < 2 in [...]N construct: [{inner}]{count}")

