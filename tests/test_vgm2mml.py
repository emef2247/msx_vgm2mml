"""
test_vgm2mml.py - CLI-level tests for vgm2mml.py output directory behaviour.

Validates that:
  1. --outdir <dir>  → all outputs land under <dir>/<vgm_stem>/
  2. No --outdir     → all outputs land under <vgm_dir>/<vgm_stem>_log/
"""
import os
import sys
import subprocess
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VGMCLI   = os.path.join(REPO_ROOT, 'vgm2mml.py')
VGM_FILE = os.path.join(REPO_ROOT, 'inputs', '02_StartingPoint',
                         '02_StartingPoint.vgm')
VGM_STEM = '02_StartingPoint'


def _run_cli(*extra_args):
    """Run vgm2mml.py with the test VGM and optional extra arguments."""
    cmd = [sys.executable, VGMCLI, VGM_FILE] + list(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"CLI exited {result.returncode}\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}")
    return result


# ──────────────────────────────────────────────────────────────────────────
# --outdir: all outputs must land under <outdir>/<vgm_stem>/
# ──────────────────────────────────────────────────────────────────────────

def test_outdir_creates_stem_subdirectory():
    """With --outdir, a <vgm_stem>/ subdirectory must be created inside it."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        stem_dir = os.path.join(tmp, VGM_STEM)
        assert os.path.isdir(stem_dir), (
            f"Expected <outdir>/{VGM_STEM}/ to exist, but it does not.\n"
            f"Contents of {tmp}: {os.listdir(tmp)}")


def test_outdir_csv_files_inside_stem():
    """With --outdir, all CSV files must be inside <outdir>/<vgm_stem>/."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        stem_dir = os.path.join(tmp, VGM_STEM)
        # Gather all files directly in tmp (not in subdirs) – should be none
        direct_files = [f for f in os.listdir(tmp)
                        if os.path.isfile(os.path.join(tmp, f))]
        assert direct_files == [], (
            f"Found unexpected files directly in <outdir>/: {direct_files}\n"
            f"All outputs should be under <outdir>/{VGM_STEM}/")

        # CSV files must exist inside the stem dir
        csv_files = [f for f in os.listdir(stem_dir) if f.endswith('.csv')]
        assert len(csv_files) >= 4, (
            f"Expected at least 4 CSV files in {stem_dir}, got {csv_files}")


def test_outdir_mml_files_inside_stem():
    """With --outdir, all MML files must be inside <outdir>/<vgm_stem>/."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        stem_dir = os.path.join(tmp, VGM_STEM)
        # Walk the entire output tree and collect .mml files
        mml_files = []
        for dirpath, _dirs, files in os.walk(tmp):
            for fname in files:
                if fname.endswith('.mml'):
                    mml_files.append(os.path.join(dirpath, fname))

        assert len(mml_files) >= 2, (
            f"Expected at least 2 MML files in output tree, got {mml_files}")

        for mml in mml_files:
            assert mml.startswith(stem_dir + os.sep), (
                f"MML file {mml!r} is outside {stem_dir!r}")


def test_outdir_no_files_outside_stem():
    """With --outdir, nothing must be created directly in <outdir>/."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        direct_entries = os.listdir(tmp)
        # The only entry should be the stem subdirectory itself
        assert direct_entries == [VGM_STEM], (
            f"<outdir>/ should contain only '{VGM_STEM}/', "
            f"but found: {direct_entries}")


def test_outdir_stdout_reports_stem_paths():
    """CLI stdout paths must all reference <outdir>/<vgm_stem>/."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_cli('--outdir', tmp)
        for line in result.stdout.splitlines():
            if ':' not in line:
                continue
            path_part = line.split(':', 1)[1].strip()
            expected_prefix = os.path.join(tmp, VGM_STEM)
            assert path_part.startswith(expected_prefix), (
                f"Output path {path_part!r} does not start with "
                f"{expected_prefix!r}")


# ──────────────────────────────────────────────────────────────────────────
# No --outdir: all outputs must land under <vgm_dir>/<vgm_stem>_log/
# ──────────────────────────────────────────────────────────────────────────

def test_no_outdir_uses_outputs_dir_in_repo_root():
    """Without --outdir, outputs land in <repo_root>/outputs/<vgm_stem>/."""
    expected_dir = os.path.join(REPO_ROOT, 'outputs', VGM_STEM)
    _run_cli()
    assert os.path.isdir(expected_dir), (
        f"Expected {expected_dir!r} to exist\n"
        f"Contents of outputs/: {os.listdir(os.path.join(REPO_ROOT, 'outputs'))}")

    # MML files must be directly in expected_dir (no sub-directories)
    mml_files = [f for f in os.listdir(expected_dir) if f.endswith('.mml')]
    assert len(mml_files) >= 2, (
        f"Expected at least 2 MML files in {expected_dir}, got {mml_files}")
