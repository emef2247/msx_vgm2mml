"""
test_vgm2mml.py - Integration tests for the vgm2mml CLI.

Validates the output directory structure produced by the top-level CLI.
"""
import os
import sys
import subprocess
import tempfile
import pytest

# Locate repository root (one level up from tests/)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VGM_FILE = os.path.join(
    REPO_ROOT,
    'inputs', '02_StartingPoint', '02_StartingPoint.vgm')

BASE_NAME = '02_StartingPoint'


def _run_cli(*args):
    """Run vgm2mml.py as a subprocess and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, 'vgm2mml.py')] + list(args),
        capture_output=True, text=True)


# ──────────────────────────────────────────────────────────────────────────
# A) Output directory restructuring: --outdir creates <outdir>/<base_name>/
# ──────────────────────────────────────────────────────────────────────────

def test_outdir_creates_per_song_subdirectory():
    """With --outdir, initial CSVs go into <outdir>/<base_name>/, not <outdir>/."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_cli(VGM_FILE, '--outdir', tmp_dir)
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

        song_dir = os.path.join(tmp_dir, BASE_NAME)
        assert os.path.isdir(song_dir), (
            f"Expected per-song subdirectory {song_dir!r} was not created")


def test_outdir_initial_csvs_inside_song_subdir():
    """The four initial parse_vgm CSVs must be inside <outdir>/<base_name>/."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_cli(VGM_FILE, '--outdir', tmp_dir)
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

        song_dir = os.path.join(tmp_dir, BASE_NAME)
        for csv_name in (
            f'{BASE_NAME}_log.psg.csv',
            f'{BASE_NAME}_log.scc.csv',
            f'{BASE_NAME}_trace.psg.csv',
            f'{BASE_NAME}_trace.scc.csv',
        ):
            expected = os.path.join(song_dir, csv_name)
            assert os.path.isfile(expected), (
                f"Expected CSV not found inside song subdir: {expected}")


def test_outdir_no_csvs_at_outdir_root():
    """No initial CSVs should appear directly at <outdir>/."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_cli(VGM_FILE, '--outdir', tmp_dir)
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

        for entry in os.listdir(tmp_dir):
            path = os.path.join(tmp_dir, entry)
            # Only the per-song subdirectory should exist at the root level
            assert os.path.isdir(path), (
                f"Unexpected file at --outdir root (expected only a subdir): {path}")


def test_outdir_dump_passes_inside_song_subdir():
    """With --dump-passes, pass files must be nested inside <outdir>/<base_name>/."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_cli(VGM_FILE, '--outdir', tmp_dir, '--dump-passes')
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

        song_dir = os.path.join(tmp_dir, BASE_NAME)
        # SCC pass files live in <song_dir>/<base_name>_trace/
        scc_subdir = os.path.join(song_dir, f'{BASE_NAME}_trace')
        assert os.path.isdir(scc_subdir), (
            f"SCC pass subdir not found: {scc_subdir}")

        # PSG pass files live in <song_dir>/<base_name>_psg_trace/
        psg_subdir = os.path.join(song_dir, f'{BASE_NAME}_psg_trace')
        assert os.path.isdir(psg_subdir), (
            f"PSG pass subdir not found: {psg_subdir}")


def test_no_outdir_uses_legacy_default():
    """Without --outdir, outputs go to <vgm_dir>/<base_name>_log/ (legacy)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Copy the VGM into a temp dir so we control where the default output lands
        import shutil
        vgm_copy = os.path.join(tmp_dir, f'{BASE_NAME}.vgm')
        shutil.copy(VGM_FILE, vgm_copy)

        result = _run_cli(vgm_copy)
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"

        legacy_dir = os.path.join(tmp_dir, f'{BASE_NAME}_log')
        assert os.path.isdir(legacy_dir), (
            f"Expected legacy output dir {legacy_dir!r} was not created")
