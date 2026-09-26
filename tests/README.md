# Tests

Run from the repository root with Python 3.10 or newer; no third-party packages
are required:

```sh
python -m unittest discover -s tests -v
```

`test_chip_segments.py` checks Segment semantics and independent MML rendering.
`test_conversion_regression.py` compares existing MML and intermediate-file
hashes with the pre-refactor revision plus the isolated SCC header correction
recorded in `conversion_baseline.json`. Expectations come from the old
non-Segment pipeline, not from the refactored code.
The manifest covers 134 conversion scenarios and intentionally excludes the
three new diagnostic files, which are checked separately.

Twelve of the 13 public SCC fixtures already have a valid clock at 0x9C.
The original parser mistakenly read 0xCC (ES5503); earlier documentation and
test helper code repeated that mistake. `clock_*` profiles now explicitly set
the correct 0x9C field in temporary copies; `clock_log_*` uses log input.
`test_scc_header.py` checks the specified offsets and verifies actual SCC note
output from an unmodified public fixture. See `docs/psg_scc_segments.md`.

Reference MML files are human reference material, not regenerated expectations.
Tests never modify fixtures or require private game data.
