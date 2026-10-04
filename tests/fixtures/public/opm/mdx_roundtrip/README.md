# Original OPM Segment replay evidence

The nine case VGMs are external replay results for the newly authored synthetic
inputs in `../from_mdx/`. They contain no private/game music or PCM. They follow
the repository MIT license, like the source cases.

On 2026-10-04 each source was decoded into native Segments, projected to MDX MML
register controls by `py/opm_mdx.py`, compiled by mmlx 0.2.0 and played into VGM
by soundlog 0.15.0. `initialization.vgm` was generated independently from:

```text
#title "Compiler initialization"
A @t255 r%1
```

The initializer is compared with each returned prefix before exclusion. These
files are expected evidence, not inputs replacing the original patterns.
`tests/test_opm_mdx.py` verifies all nine control/state/Key/timing comparisons.
Neither an external compiler nor Rust is required to run that regression.

To reproduce with the pinned external helper:

```bash
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm/from_mdx \
  --outdir outputs/opm/mdx_roundtrip/reproduce
```

Add `--generator /path/to/mdx-fixture-generator` if built elsewhere. Returned
files are in `<outdir>/<case>/<case>/returned.vgm`, the initializer in
`<outdir>/_compiler_initialization/initialization.vgm`. Review comparisons before
replacing expected files; the verifier never updates this directory itself.
