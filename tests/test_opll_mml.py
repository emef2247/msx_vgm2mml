"""
test_opll_mml.py - Smoke tests for the OPLL MML pipeline.

Validates that:
  1. parse_vgm writes the OPLL trace and log CSVs.
  2. process_opll_csv generates a .opll.mml file with the correct structure.
  3. Tick-based final-state evaluation handles the KeyOn-before-INST quirk.
  4. The generated MML header contains required MGSDRV directives.
  5. The generated MML assigns OPLL channels to MGSDRV tracks 9-14.
"""
import os
import re
import sys
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'py'))

from vgm_reader import parse_vgm
from opll_mml import process_opll_csv

# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────

VGM_FILE = os.path.join(
    REPO_ROOT,
    'inputs', 'ym2413_patch_change_midnote',
    'ym2413_patch_change_midnote.vgm')

VGM_STEM = 'ym2413_patch_change_midnote'

GOLDEN_OPLL_MML = os.path.join(
    REPO_ROOT,
    'outputs', VGM_STEM,
    f'{VGM_STEM}.opll.mml')

GOLDEN_OPLL_TRACE = os.path.join(
    REPO_ROOT,
    'outputs', VGM_STEM,
    f'{VGM_STEM}_trace.opll.csv')


def _read(path):
    with open(path, 'r', newline='') as fh:
        return fh.read()


# ──────────────────────────────────────────────────────────────────────────
# Fixture existence
# ──────────────────────────────────────────────────────────────────────────

def test_opll_vgm_fixture_exists():
    """The OPLL test fixture VGM must exist."""
    assert os.path.isfile(VGM_FILE), (
        f"OPLL test fixture not found: {VGM_FILE}")


def test_golden_opll_mml_exists():
    """The committed golden OPLL MML must exist."""
    assert os.path.isfile(GOLDEN_OPLL_MML), (
        f"Golden OPLL MML not found: {GOLDEN_OPLL_MML}")


def test_golden_opll_trace_csv_exists():
    """The committed golden OPLL trace CSV must exist."""
    assert os.path.isfile(GOLDEN_OPLL_TRACE), (
        f"Golden OPLL trace CSV not found: {GOLDEN_OPLL_TRACE}")


# ──────────────────────────────────────────────────────────────────────────
# parse_vgm → OPLL CSVs
# ──────────────────────────────────────────────────────────────────────────

def test_parse_vgm_writes_opll_trace_csv():
    """parse_vgm must write the OPLL trace CSV."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        assert len(results) == 6, (
            f"parse_vgm should return 6 paths (psg_log, scc_log, psg_trace, "
            f"scc_trace, opll_log, opll_trace), got {len(results)}")
        opll_trace = results[5]
        assert os.path.isfile(opll_trace), (
            f"OPLL trace CSV not written: {opll_trace}")


def test_parse_vgm_writes_opll_log_csv():
    """parse_vgm must write the OPLL log CSV."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_log = results[4]
        assert os.path.isfile(opll_log), (
            f"OPLL log CSV not written: {opll_log}")


def test_opll_trace_csv_has_expected_columns():
    """OPLL trace CSV header must list all 9 required columns."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        with open(opll_trace) as fh:
            header = fh.readline().strip()
        expected_cols = ['type', 'time', 'ch', 'ticks', 'keyon',
                         'fnum', 'block', 'inst', 'vol']
        for col in expected_cols:
            assert col in header, (
                f"Column '{col}' missing from OPLL trace CSV header: {header}")


def test_opll_trace_csv_contains_keyon_events():
    """OPLL trace CSV must contain keyBlk events (KeyOn writes)."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        content = _read(opll_trace)
        assert 'keyBlk' in content, (
            "OPLL trace CSV contains no keyBlk events; VGM parsing may be broken")


def test_opll_trace_csv_channels_in_range():
    """All OPLL trace events must be on channels 0-5."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        with open(opll_trace) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                ch = int(parts[2])
                assert 0 <= ch <= 5, (
                    f"Channel {ch} is outside melody range 0-5: {line}")


# ──────────────────────────────────────────────────────────────────────────
# process_opll_csv → MML
# ──────────────────────────────────────────────────────────────────────────

def test_opll_mml_is_generated():
    """process_opll_csv must produce a .opll.mml file."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        assert os.path.isfile(mml_path), (
            f"OPLL MML not generated: {mml_path}")


def test_opll_mml_header_has_opll_mode():
    """Generated OPLL MML must contain '#opll_mode 1'."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        assert '#opll_mode 1' in content, (
            f"OPLL MML missing '#opll_mode 1':\n{content[:500]}")


def test_opll_mml_header_has_tempo():
    """Generated OPLL MML must contain '#tempo 225'."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        assert '#tempo 225' in content, (
            f"OPLL MML missing '#tempo 225':\n{content[:500]}")


def test_opll_mml_header_has_title():
    """Generated OPLL MML must contain the correct '#title' with the stem."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        assert f'#title' in content, "OPLL MML missing '#title'"
        assert VGM_STEM in content, (
            f"OPLL MML #title does not contain stem '{VGM_STEM}'")


def test_opll_mml_has_tracks_9_to_14():
    """Generated OPLL MML must reference MGSDRV tracks 9-e (single-char IDs)."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        # Tracks 9-14 in MGSDRV single-char notation: 9, a, b, c, d, e
        expected_track_ids = ['9', 'a', 'b', 'c', 'd', 'e']
        for tid in expected_track_ids:
            assert f'#alloc {tid}=' in content, (
                f"OPLL MML missing '#alloc {tid}=': {mml_path}")


def test_opll_mml_track_ids_are_single_char():
    """OPLL MML track designators must be single characters (9,a,b,c,d,e).

    Decimal two-digit track numbers like '10', '11', etc. must not appear
    as line-leading track designators.
    """
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        # No line should start with a two-digit decimal track number (10-17)
        for track_num in range(10, 18):
            bad_pattern = re.compile(rf'^{track_num}\s', re.MULTILINE)
            assert not bad_pattern.search(content), (
                f"Decimal track number '{track_num}' found as line-leading "
                f"track designator in OPLL MML – must use single-char ID")
        # #alloc must also not contain decimal track numbers 10-17
        for track_num in range(10, 18):
            assert f'#alloc {track_num}=' not in content, (
                f"'#alloc {track_num}=' found in OPLL MML header – "
                f"must use single-char ID")


def test_opll_mml_ends_with_newline():
    """Generated OPLL MML must end with a newline character."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        assert content.endswith('\n'), (
            "OPLL MML does not end with a newline")


def test_opll_mml_has_note_on_channel_9():
    """Generated OPLL MML must contain at least one note on MGSDRV track 9."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        # Match lines starting with "9 " (track 9 MML data)
        track9_lines = [ln for ln in content.splitlines()
                        if re.match(r'^9\s+@', ln)]
        assert len(track9_lines) > 0, (
            f"No notes on MGSDRV track 9 in OPLL MML:\n{content}")


# ──────────────────────────────────────────────────────────────────────────
# Tick-based final-state evaluation (KeyOn-before-INST quirk)
# ──────────────────────────────────────────────────────────────────────────

def test_opll_keyon_before_inst_quirk():
    """Tick-based evaluation: INST written after KeyOn within same tick is applied.

    The test VGM writes KeyOn to ch0 before INST=1 at the same tick.
    The MML must start ch0 with the correct instrument (not 0/uninitialised).
    """
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        # First note on track 9 must have an explicit @N with N != 0 is not
        # mandated (INST=0 is user patch), but it MUST have an @N token.
        track9_line = next(
            (ln for ln in content.splitlines() if re.match(r'^9\s+@', ln)),
            None)
        assert track9_line is not None, (
            "No track-9 line with @N found – instrument not emitted")
        assert '@' in track9_line, (
            f"Track 9 MML line missing @ instrument token: {track9_line!r}")


def test_opll_patch_change_mid_note():
    """Patch change mid-note (different tick): two segments with different @N.

    The test VGM writes INST=1 at tick 0 then INST=2 at tick 60 on ch0.
    The MML must contain two different @N tokens on track 9.
    """
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        content = _read(mml_path)
        # Find all @N occurrences on lines that start with "9 "
        all_insts = []
        for ln in content.splitlines():
            if re.match(r'^9\s+', ln):
                all_insts += re.findall(r'@(\d+)', ln)
        assert len(all_insts) >= 2, (
            f"Expected at least two @N tokens on track 9 (instrument change "
            f"mid-note), got: {all_insts}\nMML content:\n{content}")
        # The two instruments must differ (INST=1 first, then INST=2)
        assert len(set(all_insts)) >= 2, (
            f"Expected two different instruments on track 9, got: {all_insts}")


# ──────────────────────────────────────────────────────────────────────────
# dump_passes
# ──────────────────────────────────────────────────────────────────────────

def test_opll_dump_passes_creates_segment_csv():
    """With dump_passes=True, process_opll_csv must write a pass0 segment CSV."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        process_opll_csv(opll_trace, out_dir, stem=VGM_STEM, dump_passes=True)
        pass0 = os.path.join(out_dir, f'{VGM_STEM}.opll.pass0.csv')
        assert os.path.isfile(pass0), (
            f"dump_passes=True but pass0 CSV not found: {pass0}")


def test_opll_no_dump_no_pass_csv():
    """With dump_passes=False (default), no pass CSV must be written."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        process_opll_csv(opll_trace, out_dir, stem=VGM_STEM, dump_passes=False)
        pass_csvs = [f for f in os.listdir(out_dir) if 'pass' in f]
        assert pass_csvs == [], (
            f"Unexpected pass CSV files with dump_passes=False: {pass_csvs}")


# ──────────────────────────────────────────────────────────────────────────
# Golden reference comparison
# ──────────────────────────────────────────────────────────────────────────

def test_opll_mml_matches_golden():
    """Generated OPLL MML must match the committed golden reference."""
    with tempfile.TemporaryDirectory() as tmp:
        results = parse_vgm(VGM_FILE, tmp)
        opll_trace = results[5]
        out_dir = os.path.join(tmp, VGM_STEM)
        mml_path = process_opll_csv(opll_trace, out_dir, stem=VGM_STEM)
        got      = _read(mml_path)
        expected = _read(GOLDEN_OPLL_MML)
        assert got == expected, (
            f"OPLL MML differs from golden reference.\n"
            f"Expected:\n{expected[:500]}\n\nGot:\n{got[:500]}")
