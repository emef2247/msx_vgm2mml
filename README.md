# MSX VGM to MML Converter

Python port of the Tcl VGM→MGSDRV MML conversion pipeline.
Converts a VGM binary file into SCC (and PSG) intermediate CSVs, then
generates MGSDRV-compatible MML through a multi-pass CSV pipeline.

## Pipeline Overview

```
VGM binary  ──►  *_trace.scc.csv  ──►  pass0…pass3.csv  ──►  pass3.mml
               (chronological)        (MML pipeline)
               *_log.scc.csv          (per-channel grouped,
               (per-channel)           alternative input)
```

**VGM is the true input.**  The primary SCC intermediate format is
`*_trace.scc.csv` (events in VGM-stream order, all channels interleaved).
This matches the Tcl pipeline's `*_trace.scc.csv` convention and is the
default when running `vgm2mml.py`.

The `*_log.scc.csv` format (events grouped per channel) is also produced
and can be used as input to the MML pipeline via `--scc-input log`.

## Requirements

- Python 3.8+
- No third-party packages required for the core pipeline
- `pytest` for running the test suite

## Quick Start

### Full pipeline (VGM → trace → MML)  *(default)*

```bash
python vgm2mml.py inputs/02_StartingPoint/02_StartingPoint.vgm \
    --outdir outputs_py --dump-passes
```

This command:
1. Parses the VGM binary and writes both CSV variants:
   - `outputs_py/02_StartingPoint_trace.scc.csv` (chronological trace, primary)
   - `outputs_py/02_StartingPoint_log.scc.csv`   (per-channel log, secondary)
   - `outputs_py/02_StartingPoint_log.psg.csv`   (PSG log)
2. Runs the SCC MML pipeline from the trace CSV →
   `outputs_py/02_StartingPoint_trace/02_StartingPoint_trace.scc.pass3.mml`

With `--dump-passes` the intermediate CSV files are also written:
- `…_trace.scc.pass0.csv` – ticks recalculated, wavetable indices resolved
- `…_trace.scc.pass1.csv` – note lengths, frequencies, volumes computed
- `…_trace.scc.pass2.csv` – redundant rows removed, merged events
- `…_trace.scc.pass3.csv` – volume envelope strings computed

### Full pipeline using log CSV as intermediate

```bash
python vgm2mml.py inputs/02_StartingPoint/02_StartingPoint.vgm \
    --outdir outputs_py --scc-input log
```

Output: `outputs_py/02_StartingPoint_log/02_StartingPoint_log.scc.pass3.mml`

### SCC MML pipeline only (from an existing trace or log CSV)

```bash
# From trace CSV (default convention)
python py/scc_mml.py inputs/02_StartingPoint/02_StartingPoint_trace.scc.csv \
    outputs/02_StartingPoint_trace

# From log CSV
python py/scc_mml.py inputs/02_StartingPoint/02_StartingPoint_log.scc.csv \
    outputs/02_StartingPoint_log
```

## Running Tests

```bash
python -m pytest tests/ -v
```

The regression tests (`tests/test_scc_mml.py`) verify:
- Log CSV → MML matches the golden reference at
  `outputs/02_StartingPoint_log/02_StartingPoint_log.scc.pass3.mml`
- Trace CSV → MML matches the golden reference at
  `outputs/02_StartingPoint_trace/02_StartingPoint_trace.scc.pass3.mml`
- Python-generated trace CSV is byte-for-byte identical to the Tcl-generated
  `inputs/02_StartingPoint/02_StartingPoint_trace.scc.csv`
- Full VGM → trace → MML pipeline matches the golden trace MML

## Repository Layout

```
py/
  vgm_reader.py   – VGM binary parser → SCC + PSG log/trace CSVs
  scc_mml.py      – SCC CSV → pass0…pass3 CSVs + pass3.mml  (port of scc.mml.tcl)
  psg_mml.py      – PSG log CSV → MML                        (port of psg.mml.tcl)
  mml_utils.py    – Tone-table and note/octave helpers        (port of mml_utils.tcl)
vgm2mml.py        – Top-level CLI entry point
tests/
  test_scc_mml.py – Regression tests for the SCC MML pipeline
inputs/           – Sample VGM files and Tcl-generated log/trace CSVs
outputs/          – Committed golden MML reference outputs
```

## Tcl Compatibility Note

The Python VGM reader intentionally replicates a Tcl `vgm_read.tcl` quirk:
VGM wait commands `0x77` (8 samples) and `0x7a` (11 samples) are treated as
zero-sample waits. This matches the Tcl reference output and ensures the
Python-generated trace CSV is identical to the Tcl-generated trace CSV.

