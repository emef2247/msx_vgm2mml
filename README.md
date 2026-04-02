# MSX VGM to MML Converter

Python port of the Tcl VGM→MGSDRV MML conversion pipeline.
Converts a VGM binary file into SCC (and PSG) log CSVs, then generates
MGSDRV-compatible MML through a multi-pass CSV pipeline.

## Requirements

- Python 3.8+
- No third-party packages required for the core pipeline
- `pytest` for running the test suite

## Quick Start

### Full pipeline (VGM → MML)

```bash
python vgm2mml.py inputs/02_StartingPoint/02_StartingPoint.vgm \
    --outdir outputs_py --dump-passes
```

This command:
1. Parses the VGM binary → `outputs_py/02_StartingPoint_log.scc.csv`
   (and `…_log.psg.csv`)
2. Runs the SCC MML pipeline → `outputs_py/02_StartingPoint_log/02_StartingPoint_log.scc.pass3.mml`

With `--dump-passes` the intermediate CSV files are also written:
- `…_log.scc.pass0.csv` – ticks recalculated, wavetable indices resolved
- `…_log.scc.pass1.csv` – note lengths, frequencies, volumes computed
- `…_log.scc.pass2.csv` – redundant rows removed, merged events
- `…_log.scc.pass3.csv` – volume envelope strings computed
- `…_log.scc.pass3.mml` – final MGSDRV MML

### SCC MML pipeline only (from an existing log CSV)

```bash
python py/scc_mml.py inputs/02_StartingPoint/02_StartingPoint_log.scc.csv \
    outputs/02_StartingPoint_log
```

## Running Tests

```bash
python -m pytest tests/ -v
```

The regression test (`tests/test_scc_mml.py`) verifies that the Python
pipeline produces a `pass3.mml` that is byte-for-byte identical to the
committed golden reference at
`outputs/02_StartingPoint_log/02_StartingPoint_log.scc.pass3.mml`.

## Repository Layout

```
py/
  vgm_reader.py   – VGM binary parser → SCC + PSG log CSVs
  scc_mml.py      – SCC log CSV → pass0…pass3 CSVs + pass3.mml  (port of scc.mml.tcl)
  psg_mml.py      – PSG log CSV → MML                            (port of psg.mml.tcl)
  mml_utils.py    – Tone-table and note/octave helpers            (port of mml_utils.tcl)
vgm2mml.py        – Top-level CLI entry point
tests/
  test_scc_mml.py – Regression tests for the SCC MML pipeline
inputs/           – Sample VGM files and Tcl-generated log CSVs
outputs/          – Committed golden MML reference outputs
```
