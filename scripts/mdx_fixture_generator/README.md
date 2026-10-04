# External MDX fixture generator

This development-only Rust utility compiles newly authored UTF-8 MDX MML
with mmlx 0.2.0 and plays its MDX into VGM with soundlog 0.15.0. It is separate
from the Python VGM/Segment engine. No third-party compiler source is copied
here. Dependencies are pinned by Cargo.lock.

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
scripts/mdx_fixture_generator/target/release/mdx-fixture-generator input.mml output.mdx output.vgm
```

The MML compilation mode requires three positional paths. All playback modes reject PDX/PCM use, write a
4 MHz OPM VGM, and emits the intro plus one song traversal. Finite nested
repeat counts remain effective. Errors are printed to stderr with a nonzero
exit status; the Python batch regeneration script reports them. Generated
outputs are explicitly overwritten, so use dedicated output paths.

Public cases and regeneration commands are documented in
`tests/fixtures/public/opm/from_mdx/README.md`.

For fine-tick register replay, append `--max-ticks N` to set a positive playback
tick budget. The roundtrip verifier derives this budget from the projected
source end; the default 100000 ticks covers only 25.6 seconds at @t255.
See [OPM MDX target](../../docs/opm_mdx.md) for conversion and comparison.

## Existing MDX playback and inspection

Play an existing MDX directly, preserving its compiled commands and tone bank:

```bash
mdx-fixture-generator --from-mdx input.mdx output.vgm --max-ticks 1000000
```

This reads the original MDX without rewriting or recompiling it. The same
4 MHz clock, PDX/PCM rejection, and single traversal policy apply. The VGM
may be saved beside the MDX when preparing private input fixtures.

Inspect the compiled tone bank without running playback:

```bash
mdx-fixture-generator --inspect-mdx input.mdx tones.csv
```

The CSV contains each local voice ID, algorithm, feedback, enabled operator
mask, and operator parameters in `m1, m2, c1, c2` order. IDs are local to each
MDX bank: compare complete parameters when comparing different files.
The inspector uses soundlog's typed MDX parser; it does not infer SCC-to-FM
conversion rules or simulate the resulting sound.
