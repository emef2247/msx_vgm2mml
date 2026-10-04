# OPM Segment to MDX MML and roundtrip validation

This initial target consumes native `OpmSegment` objects and writes MDX-dialect
MML. It preserves register controls with decimal `y<register>,<data>` commands
on one conductor track A. It is a control replay target: ordinary note/voice
notation, musical loops, compression and PCM/PDX output are not implemented.
MGSDRV conversion remains a separate PSG/SCC/OPLL path.

## Generate MDX MML

```bash
python scripts/opm_to_mdx_mml.py \
  tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm \
  --outdir outputs/opm/mdx/held_controls
```

By default, this leaves only `<stem>.mdx.mml` in a fresh output directory.
The converter still builds native Segments; its internal trace files are kept
in a temporary directory and removed after reading. Existing files from an
earlier dump run are not deleted.

To retain inspectable raw/state/Segment CSVs and the target projection, add
`--dump-passes`:

```bash
python scripts/opm_to_mdx_mml.py \
  tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm \
  --outdir outputs/opm/mdx/held_controls --dump-passes
```

This keeps the native raw/state/Segment CSVs plus:

| File | Contents |
|---|---|
| `<stem>.mdx.mml` | UTF-8 MDX MML register controls |
| `<stem>.mdx.controls.csv` | Source event/Segment IDs, source samples, target tick, projected samples, timing error and register/data |
| `<stem>.mdx.timing.json` | Timing projection, collapsed intervals and nonchanging source-write counts |

The renderer consumes Segments, not a raw VGM command copy. Shared-register
writes affecting eight channels are deduplicated by their source event ID;
all associated Segment IDs remain in the controls CSV. Source order, partial
operator keys, same-time off/on and held-note parameter changes are preserved.
Unchanged writes omitted by Segment construction cannot be recovered by this
target; they remain available in the raw/state CSVs. Retained test/timer writes
are not removed merely because their register value repeats.

The first target accepts one **4 MHz YM2151**. Different clocks, YM2164 and dual
instances are explicitly rejected rather than silently changing pitch or
merging channels. This does not restrict the native reader's wider analysis.

## Time projection

Source `vgmticks` remain absolute integer 44100 Hz sample positions. MDX output
uses `@t255`: one playback tick is 256 microseconds, or 7056/625 VGM samples.
Each absolute source position is rounded to the nearest target tick; individual
gap errors do not accumulate. `r%N` advances conductor time and does not imply
that all physical channels are acoustically silent.

The current external playback represents each resulting sample position by
integer truncation. The source-to-target difference is at most six samples.
Positive source intervals may collapse to one target tick; their write order
and Key edges remain intact, and the timing JSON reports the number of such
intervals. Zero-duration events are never discarded. Final time is projected
from the real VGM end, preserving a trailing sustained/released interval.

## External compilation and replay

The compiler/player is a development-only helper using mmlx 0.2.0 and soundlog
0.15.0. It is not required by the Python engine or committed-fixture tests.

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm \
  --outdir outputs/opm/mdx_roundtrip/public_all
```

Use `--generator /path/to/mdx-fixture-generator` for a binary built elsewhere.
A single input VGM can replace the input directory. Directory scans include
`.vgm`/`.vgz` case-insensitively and exclude `reference/` and `mdx_roundtrip/`
expected replay material. Header preflight classifies unsupported source clocks,
variants and dual chips as `unsupported_target` before building large traces;
it does not retune or rewrite source evidence.

The tool writes generated
MML, MDX, returned VGM, both native analyses, compile logs, per-case comparison
JSON and aggregate `results.csv`/`results.json`. Both aggregate files are updated
after each input, and successful artifacts have absolute MML/MDX/VGM paths in
the results. Failed inputs retain `conversion.log`; compiler stdout/stderr and
timeout output are retained in `returned.compile.log`. A compiled MDX is saved
before replay so it survives a later player failure. Compilation can fail when
an uncompressed conductor track exceeds MDX's 16-bit offset capacity; no events
are clipped or dropped to make it fit.

This validation tool always
retains intermediate evidence; the regular conversion command saves it only
with `--dump-passes`. Neither tool overwrites inputs.
Source files containing a VGM loop are inspected through their first traversal;
recovering a target song loop is separate work.

The external player's tick budget is derived from the projected source end.
At this fine clock, a fixed 100000-tick default covers only 25.6 seconds and
would reject longer cases. The budget permits completion without clipping the
source or relaxing comparison. Compiler timeout/failure is reported with logs.

Comparison requires:

- Exact register/data sequence for every retained Segment control.
- No missing/extra channel attack, operator KeyOn or operator KeyOff, counted
  per channel before summing so opposing channel errors cannot cancel.
- Matching source-known raw and decoded state at each retained control, including
  KC/KF, operators, pan, modulation, noise and timer controls. Unwritten source
  parameters stay unknown and are not treated as default-value expectations.
- Exact projected target times and end; source timing differences at most six
  samples, separately reported rather than hidden in a score.

The external player inserts initialization controls. A separate minimal MML
is compiled to identify that initializer, which must contain only zero-time
non-Key controls and exactly match the returned VGM prefix before exclusion.
Source controls are never stripped. This explicitly tolerates additional known
compiler defaults where the source state is unknown; it is not a blanket
exemption for any mismatch at time zero.

These checks verify control/state preservation, not waveform equality. Native
Segments do not simulate envelope phase, acoustic level, timer expiry or
CSM-generated attacks; preserved controls do not prove these sound identical.

## Committed regression evidence

Nine newly authored public fixtures have externally generated replay VGMs in
`tests/fixtures/public/opm/mdx_roundtrip/`. Unit tests compare these returned
Segments without requiring Rust, including negative cases for missing/extra
keys, wrong pitch, timing, operator state and compiler initialization.

```bash
python -m unittest discover -s tests -p 'test_opm*.py' -v
```

For current measurements and limits, see
[the roundtrip record](../field_notes/2026-10-04_opm_mdx_roundtrip.md).

## Local listening validation (2026-10-04)

The user-requested catalog run and listening files are under
`outputs/opm/mdx_roundtrip/listening_20261004/`. `public/` and `local_only/`
contain per-case evidence and independent result indexes. `listen/` contains
copies of successful MML/MDX/VGM with the original stem as filename, grouped
by the source directory, for manual listening. These generated files and all
private source/returned content remain outside git.

See [the catalog validation record](../field_notes/2026-10-04_opm_catalog_roundtrip.md)
for counts and remaining limits. Clock-incompatible sources have diagnostics,
not misleading playable conversions. VGM song loops still cover one traversal;
MDX replay preserves the OPM controls, not other chips or external PCM samples.
