# Initial OPM Segment / MDX MML roundtrip

## Scope and implementation

The user requested native OPM VGM -> Segment and Segment -> MDX MML, first
reaching a verifiable roundtrip. The initial renderer emits ordered decimal
register controls on conductor A. It consumes the actual immutable Segments,
deduplicates shared-write fanout, and retains source event/Segment identifiers
in target CSV. It does not bypass Segments by copying the raw VGM stream.

Ordinary MDX notes, voice definitions, musical loops/compression and PCM output
remain future work. Only one 4 MHz YM2151 is accepted by this target. Other
clocks/variants/instances are explicitly unsupported at output, while the
native reader can still inspect them. Existing MGS conversion is unchanged.

External compilation/playback uses the separate Rust helper with pinned mmlx
0.2.0 and soundlog 0.15.0. These are development-only dependencies. The Python
Segment engine does not import them or require Rust. No mml2vgm source is used.

## Public verification on 2026-10-04

Command from the repository root, after building the external helper:

```bash
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm \
  --outdir outputs/opm/mdx_roundtrip/public_all \
  --generator /path/to/mdx-fixture-generator
```

The full path was VGM -> native Segment -> MDX MML -> MDX -> VGM -> native
Segment. All38 current input cases passed:

| Set | Cases | Channel attacks | Operator KeyOns | Operator KeyOffs | Retained controls | Collapsed positive intervals | Maximum timing error (samples) |
|---|---:|---:|---:|---:|---:|---:|---:|
| from_fm | 16 | 249 | 996 | 996 | 5373 | 291 | 6 |
| from_mdx | 9 | 56 | 212 | 212 | 868 | 0 | 0 |
| from_psg | 13 | 52 | 169 | 0 | 2331 | 72 | 6 |
| Total | 38 | 357 | 1377 | 1208 | 8572 | 363 | 6 |

Source and returned totals match in each row. Missing/extra attacks, operator
KeyOns and operator KeyOffs are all0, counted per channel before summation.
The from_psg source set itself contains no falling Key edges; this is not an
output omission. All retained register/data sequences and source-known channel,
operator and shared states match. Returned times match the target projection
exactly. Aggregate CSV/JSON and per-case native/target CSVs are retained in the
ignored `outputs/opm/mdx_roundtrip/public_all/` directory.

The nine original from_mdx cases have committed external replay evidence under
`tests/fixtures/public/opm/mdx_roundtrip/`, including an independently generated
compiler initializer. OPM automated checks pass:30 tests. Negative cases detect
missing/extra Key edges, wrong pitch, changed operator state, wrong timing,
invalid source evidence and mismatching initialization. These tests use the
committed public evidence without needing an external compiler installation.
The existing PSG/SCC/OPLL public conversion baseline check also passed (one
aggregate test,72.379 seconds). Git diff whitespace checks passed.

## Timing, initialization and limits

MDX @t255 advances256 microseconds per tick, or7056/625 VGM samples. Absolute
positions are rounded rather than each gap, bounding source differences to
six integer samples without cumulative drift. The collapsed interval count
means distinct source timestamps share a target timestamp, not discarded
writes: order and all Key edges are preserved, including zero-duration pulses.
The original MDX fixtures use times exactly representable on this finer clock,
so they have zero error and zero collapsed positive intervals.

The external compiler/player adds twelve zero-time controls: PMS/AMS on eight
channels, test, noise, AMD and PMD initialization. A minimal independent MML
produces this baseline, and its entire control prefix must match before being
excluded. No Key writes are permitted in that baseline. Source controls are
never stripped; extra defaults in source-unknown fields are not invented source
expectations. Matching control/state does not assert matching envelope phase,
noise/LFO phase or acoustic waveform. CSM-generated attacks remain unmodeled.

An initial38-case run passed37 cases; from_fm/custom_voice hit soundlog's default
100000-tick limit. At @t255 that is only25.6 seconds. The helper now accepts an
explicit positive `--max-ticks`, and the verifier derives it from source end
plus a completion tick. The full rerun passed38/38 without clipping or weakening
comparison criteria.

Three user-approved, unconverted from_fm/rhythm_only_test0* inputs were removed.
All13 from_psg inputs were retained as explicitly requested. No private/game
VGM catalog was converted in this validation; the new local game patterns are
for the next stage, after reviewing the MDX target. VGM song loops are not yet
translated to target musical loops; this check covers the first traversal.

## Next work

Use this control replay as an inspectable baseline for a readable MDX note/voice
renderer. Preserve partial operator keys, mid-note register changes and shared
state when deciding which controls can be represented musically. Add private
game checks after that representation is agreed, rather than claiming these
synthetic state checks establish acoustic equivalence for arbitrary games.

Usage and exact comparison rules: [docs/opm_mdx.md](../docs/opm_mdx.md).

## Output packaging after user review

The OPM feature is presented as OPM VGM input -> MDX MML output. Normal
conversion now leaves only <stem>.mdx.mml in a fresh output directory.
--dump-passes preserves raw/state/Segment CSVs, target controls and timing JSON.
Internal Segment construction is unchanged; default traces use a temporary
directory. The roundtrip verifier explicitly retains all intermediate evidence.
CLI checks confirm both modes emit byte-identical MML, and all31 OPM tests pass.
Existing dumps are not deleted automatically. README lists the MDX output
command separately from MGSDRV conversion, preserving the target distinction.
