# OPLL key-on count comparison

Compare source VGM and a VGM exported from the generated MGS:

```sh
python scripts/check_opll_key_edges.py source.vgm exported.vgm --outdir outputs/keyon_check
```

`keyon_totals.csv` contains one row per input VGM:

- `reference_keyon`: source melodic key-on rising edges.
- `actual_keyon`: exported melodic key-on rising edges.
- `missing_keyon`: sum of per-channel count shortages.
- `extra_keyon`: sum of per-channel count excesses.

Counts cover OPLL channels 0..8, excluding 6..8 while rhythm mode is enabled.
Rhythm attacks are outside this comparison. Repeated key-high writes, pitch
updates and volume recovery do not add attacks. Terminal zero-duration key
edges are counted. There is no timing/frequency/volume metric or combined score.

Shortages and excesses are count differences, not identities of missing events.
Missing and extra attacks within the same channel can cancel. Equal counts do
not prove matching notes or sound. Segment row counts and tied MML fragments
are not musical-note counts.

For regression, supply a CSV with `reference,actual` columns and an optional
`input` label. Relative paths resolve against the CSV directory:

```sh
python scripts/check_opll_key_edges.py --pairs pairs.csv --outdir outputs/keyon_regression
```

This standalone tool reads existing VGM pairs; it does not compile or export MGS itself.
Failed/unavailable pairs have status `error` and blank counts, and later pairs
still run. Each successful pair retains register traces, native Segment dumps,
`key_edges.csv` and a JSON summary. Regression artifacts use `case_0001` etc.

`batch_vgm_to_mgs.py` now performs the MGS export and count comparison after
successful compilation by default, adding the same four count fields to its
CSV/JSON results. It reuses the compiled MGS without converting the source to
MML a second time. See [batch setup and failure states](batch_mgs.md).
