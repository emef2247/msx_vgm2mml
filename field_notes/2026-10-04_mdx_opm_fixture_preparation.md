# Native MDX/MML OPM fixture preparation (2026-10-04)

## Scope and provenance

The user supplied a local MDX collection and requested matching MML + MDX
pairs as native OPM fixtures. The earlier `.MDL` spelling was corrected to
`.MDX`. These private files and all generated music remain under
`tests/fixtures/local_only/opm/` or ignored `outputs/`; they are not
redistributed. This changes fixture preparation, not the converter engine.

Source: `H:/_env/X68K/emu/x68000/images/MDX`.
Preserve the source title-directory hierarchy; do not flatten vendor/game
folders. A same-stem MDX in the MML's immediate parent directory is accepted
when the source stores MML in a separate `MML/` subdirectory. Use the MDX's
title directory as the destination directory. Never overwrite different
existing references. Original MML/MDX bytes are preserved.

## Result

- 37 MML files found; 32 have uniquely matching MDX files (20 siblings and
  12 in the immediate parent directory). Five MML files remain unpaired.
- Copied all 32 pairs (64 original reference files).
- Generated 20 input VGMs using mmlx 0.2.0 MML parsing/compilation followed
  by soundlog 0.15.0 MDX playback conversion.
- Twelve pairs remain without an input VGM because their MML dialect is not
  accepted by this mmlx version. Detailed local logs are retained. Causes
  include independent compiler directives, default-length dotted notes,
  old comment/title syntax, and standalone prose labels.
- Do not silently fall back to original MDX playback for a failed MML input,
  or remove musical commands to obtain an apparently successful fixture.

The temporary compilation source is decoded from CP932, has normalized
line endings and its DOS EOF marker removed. In files without any `*/`,
full-line legacy `/*` and `//` comment prefixes become `;` for mmlx. These
adaptations affect only the working copy, not reference files. Musical
commands, note values and patches are not altered.

## Validation

The successful inputs declare YM2151 at 4,000,000 Hz. Existing native OPM
analysis checked every generated input against its own raw VGM Key edges
and source end: 155,326 OPM writes, 11,309 channel attack events, and 45,236
operator KeyOns. No operator KeyOn/KeyOff count was lost or added by Segment
construction. Generated raw/state/Segment CSVs are retained.

An additional, separately labeled VGM was generated directly from each
original reference MDX using soundlog. This is comparison evidence, not a
replacement input. All 20 MML-derived and MDX-derived VGMs have matching
operator KeyOn counts and end sample positions. Seventeen have identical
ordered OPM writes including sample positions. The other three each differ
in one final register 0x28 (KC) write at the exact source-end sample:
HYDS_03, HYDS_05, HYDS_07. Keep this evidence; do not claim byte-for-byte or
acoustic equivalence. Both routes use the same external MDX playback engine,
so this does not independently validate that engine against real hardware.

The existing 13 OPM automated tests also passed after fixture preparation.
No Segment-to-MML or Segment-to-VGM OPM output is implemented by this work.

## Local artifacts and tool boundary

- `tests/fixtures/local_only/opm/<title-directory>/<stem>/<stem>.vgm`
- `tests/fixtures/local_only/opm/<title-directory>/<stem>/reference/`
- `tests/fixtures/local_only/opm/preparation_results.json`
- `outputs/opm/mdx_preparation/results.csv` and `results.json`
- Per-case generation logs, UTF-8 working MML, compiled `.mmlx.mdx`,
  separately labeled reference-MDX VGM, and OPM CSVs below that output root.

External fixture tools and verified Rust dependencies are kept outside the
converter at `C:/Users/ef110/Documents/Codex/2026-09-25/co/tools/opm-fixtures`.
A copy of the helper sources/Cargo lock is retained in the ignored output
root's `tools/` directory. Rust was installed into that workspace only;
no system PATH change or user Rust installation was needed. The engine
imports neither mmlx nor soundlog. No mml2vgm source was used.

Playback conversion uses `loop_count=Some(1)` (intro plus one traversal;
finite nested loops are preserved), with the external library's explicit
resource limits. Resolve PDX case-insensitively from original source
folders when requested; reject missing PCM data rather than silently
omitting it. OPM analysis currently does not analyze the accompanying PCM
chip, so PCM evidence is not an OPM roundtrip claim.

## Next verification path

The user proposes eventually accepting MDX-only fixtures after an OPM MDX
MML renderer exists:

`original MDX -> VGM -> Segment -> output MML -> mmlx MDX -> VGM -> Segment`

Compare Segment-level keys, pitch/patch/control evidence and timing while
keeping source and target-derived facts separate. MDX-only playback can
also serve as source evidence, but it has no original textual MML oracle.
Do not label generated MML as the original composition.
