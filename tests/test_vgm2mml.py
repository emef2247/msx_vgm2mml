"""
test_vgm2mml.py - CLI-level tests for vgm2mml.py output directory behaviour.

Validates that:
  1. Default (no --debug): only a single merged <stem>.mml is produced.
  2. With --debug: merged MML plus all chip-specific variants and CSV files.
  3. With --dump-passes: pass CSVs are produced alongside the merged MML.
  4. --outdir <dir> → all outputs land under <dir>/<vgm_stem>/
  5. No --outdir    → all outputs land under <repo_root>/outputs/<vgm_stem>/
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
# Default behaviour (no --debug): single merged MML, no extra files
# ──────────────────────────────────────────────────────────────────────────

def test_default_produces_single_merged_mml():
    """Default mode must produce exactly one .mml file: <stem>.mml."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        stem_dir = os.path.join(tmp, VGM_STEM)
        mml_files = [f for f in os.listdir(stem_dir) if f.endswith('.mml')]
        assert mml_files == [f'{VGM_STEM}.mml'], (
            f"Expected only '{VGM_STEM}.mml', got {mml_files}")


def test_default_no_csv_files():
    """Default mode must not produce any CSV files."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        stem_dir = os.path.join(tmp, VGM_STEM)
        csv_files = [f for f in os.listdir(stem_dir) if f.endswith('.csv')]
        assert csv_files == [], (
            f"Default mode must not write CSV files, got {csv_files}")


def test_default_merged_mml_header():
    """The merged MML must start with the required global header."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        with open(merged) as fh:
            content = fh.read()
        assert content.startswith(';[name=psg lpf=1]\n'), (
            "Merged MML must start with ';[name=psg lpf=1]'")
        assert '#opll_mode 1\n' in content, "Merged MML must contain '#opll_mode 1'"
        assert '#tempo 75\n' in content, "Merged MML must contain '#tempo 75'"
        assert f'#title {{ "{VGM_STEM}"}}' in content, (
            "Merged MML must contain '#title { \"<stem>\"}'")


def test_default_merged_mml_psg_part():
    """The merged MML must contain the PSG part separator and content."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        with open(merged) as fh:
            content = fh.read()
        assert ';-----------------------  psg part' in content, (
            "Merged MML must contain PSG part separator")
        assert '#alloc 1=' in content, "Merged MML must contain PSG #alloc lines"


def test_default_merged_mml_scc_part():
    """The merged MML must contain the SCC part separator for this VGM."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        with open(merged) as fh:
            content = fh.read()
        assert ';-----------------------  scc part' in content, (
            "Merged MML must contain SCC part separator")


def test_default_merged_mml_no_opll_part():
    """For this VGM (no OPLL), the merged MML must NOT contain the OPLL part."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        with open(merged) as fh:
            content = fh.read()
        assert ';-----------------------  OPLL part' not in content, (
            "Merged MML must not contain OPLL part for a PSG+SCC-only VGM")


def test_default_merged_mml_parts_start_with_alloc():
    """Each chip part in the merged MML must start at #alloc (no chip header)."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        with open(merged) as fh:
            content = fh.read()
        # After the PSG separator line, the next non-empty line must be #alloc
        separator = ';-----------------------  psg part'
        idx = content.find(separator)
        assert idx != -1
        # Skip past the full separator line (including trailing dashes and newline)
        newline_idx = content.find('\n', idx)
        after = content[newline_idx + 1:]
        for line in after.splitlines():
            stripped = line.strip()
            if stripped:
                assert stripped.startswith('#alloc'), (
                    f"First non-empty line after PSG separator must be #alloc, "
                    f"got: {stripped!r}")
                break


def test_default_merged_mml_ends_with_newline():
    """Merged MML must end with a newline."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp)
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        with open(merged, 'rb') as fh:
            data = fh.read()
        assert data.endswith(b'\n'), "Merged MML must end with a newline"


def test_default_stdout_reports_merged_path():
    """Default mode stdout must report the merged MML path."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_cli('--outdir', tmp)
        merged_path = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        assert merged_path in result.stdout, (
            f"stdout must mention merged MML path {merged_path!r};\n"
            f"got:\n{result.stdout}")


# ──────────────────────────────────────────────────────────────────────────
# --debug mode: merged MML plus all legacy files
# ──────────────────────────────────────────────────────────────────────────

def test_debug_produces_merged_mml():
    """With --debug, the merged <stem>.mml must still be produced."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp, '--debug')
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        assert os.path.isfile(merged), f"Merged MML not found in debug mode: {merged}"


def test_debug_produces_chip_mml_variants():
    """With --debug, chip-specific MML variant files must be produced."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp, '--debug')
        stem_dir = os.path.join(tmp, VGM_STEM)
        mml_files = [f for f in os.listdir(stem_dir) if f.endswith('.mml')]
        assert len(mml_files) > 1, (
            f"--debug must produce multiple MML files, got {mml_files}")
        # Check that the legacy per-chip files are present
        assert f'{VGM_STEM}.psg.mml' in mml_files, (
            "Debug mode must produce .psg.mml")
        assert f'{VGM_STEM}.scc.mml' in mml_files, (
            "Debug mode must produce .scc.mml")


def test_debug_produces_csv_files():
    """With --debug, log/trace CSV files must be produced."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp, '--debug')
        stem_dir = os.path.join(tmp, VGM_STEM)
        csv_files = [f for f in os.listdir(stem_dir) if f.endswith('.csv')]
        assert len(csv_files) >= 4, (
            f"--debug must produce at least 4 CSV files, got {csv_files}")


# ──────────────────────────────────────────────────────────────────────────
# --dump-passes: pass CSVs alongside merged MML (no debug extra files)
# ──────────────────────────────────────────────────────────────────────────

def test_dump_passes_produces_pass_csvs():
    """--dump-passes must write pass0-3 CSV files."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp, '--dump-passes')
        stem_dir = os.path.join(tmp, VGM_STEM)
        csv_files = [f for f in os.listdir(stem_dir) if f.endswith('.csv')]
        assert len(csv_files) >= 1, (
            f"--dump-passes must produce CSV files, got {csv_files}")
        # Must include at least one pass3.csv
        pass3_files = [f for f in csv_files if 'pass3' in f]
        assert len(pass3_files) >= 1, (
            f"--dump-passes must write pass3.csv files, got {csv_files}")


def test_dump_passes_still_produces_merged_mml():
    """--dump-passes must still produce the merged <stem>.mml."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp, '--dump-passes')
        merged = os.path.join(tmp, VGM_STEM, f'{VGM_STEM}.mml')
        assert os.path.isfile(merged), (
            f"--dump-passes must still produce merged MML: {merged}")


def test_dump_passes_no_log_csv_files():
    """--dump-passes without --debug must not produce log/trace CSV files."""
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli('--outdir', tmp, '--dump-passes')
        stem_dir = os.path.join(tmp, VGM_STEM)
        csv_files = [f for f in os.listdir(stem_dir) if f.endswith('.csv')]
        # log/trace CSVs have '_log.' or '_trace.' in their names
        log_trace = [f for f in csv_files
                     if '_log.' in f or '_trace.' in f]
        assert log_trace == [], (
            f"--dump-passes without --debug must not produce log/trace CSVs, "
            f"got {log_trace}")


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
# No --outdir: all outputs must land under <repo_root>/outputs/<vgm_stem>/
# ──────────────────────────────────────────────────────────────────────────

def test_no_outdir_uses_outputs_dir_in_repo_root():
    """Without --outdir, outputs land in <repo_root>/outputs/<vgm_stem>/."""
    expected_dir = os.path.join(REPO_ROOT, 'outputs', VGM_STEM)
    _run_cli()
    assert os.path.isdir(expected_dir), (
        f"Expected {expected_dir!r} to exist\n"
        f"Contents of outputs/: {os.listdir(os.path.join(REPO_ROOT, 'outputs'))}")

    # Merged MML must exist
    merged = os.path.join(expected_dir, f'{VGM_STEM}.mml')
    assert os.path.isfile(merged), (
        f"Expected merged MML at {merged}")
