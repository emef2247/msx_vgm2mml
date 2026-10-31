# MGSEXC design memo (clean-room extended MGS compiler)

Status: implemented on branch `claude/mgsexc`. Differential result:
379/379 public fixture MMLs and 26/26 Salamander MMLs that MGSC
compiles are byte-identical; Salamander 02/06 (which MGSC rejects
with Track buffer full) compile and play through the stock driver.
`scripts/batch_vgm_to_mgs.py --compiler mgsexc` selects MGSEXC;
the default remains MGSC. This memo records observable behavior
only. No MGSC/MGSDRV source was read; the compiler binary is
treated as a black-box oracle through `scripts/compile_mgs.mjs`
(mgsc-js).

## Purpose

Compile MGSDRV MML to MGS without MGSC's 16 KB track-buffer pool,
so songs that fail with "Track buffer full" (e.g. Salamander 02/06)
compile, while staying byte-compatible with MGSC output wherever
MGSC succeeds. Bundle with msx_vgm2mml as a pure-Python module
(`py/mgsexc.py`, CLI `scripts/mgsexc_compile.py`) so the converter
can select it in place of the mgsc-js path.

## Established facts (measured / officially documented)

- The 16 KB limit is MGSC's creation limit, not a format or driver
  limit. MGSDRV API spec (Gigamix, ver 3.15): performance data over
  16 KB is processed correctly; MGSC just does not create it.
  MGSARC-compressed data separately needs a 16 KB expansion work
  area; MGSEXC emits uncompressed data only.
- `#alloc` semantics (MGSC111.DOC): each track buffer is normally
  auto-allocated (16K / track count) on first use; `#alloc`
  overrides sizes; the sum must be <= 16 KB. Allocations are
  capacities only: redistributing a fixed total yields
  **byte-identical** MGS output (verified 2026-10-31). Therefore
  MGSEXC parses `#alloc` and ignores the values; sizing is exact by
  construction (compile, then emit). No user tuning, no pool.
- Format reference: DSA's public `mgs-format.md` (MGSDRV v3.xx):
  ASCII header ("MGS313" + title + 0x1A), binary header (marker 00,
  mode byte %0d-mmmlo, tempo word, 18 WORD track offsets relative
  to the binary header top, 0 for empty tracks), Track 0 definition
  commands, Track 1-17 command streams, rhythm commands on track 15.
- MML reference: MGSC111.DOC (Gigamix). Track designators:
  mode 0: 1-3 PSG, 4-8 SCC, 9-h FM (a=10 .. h=17). Mode 1: 9-e FM,
  f (or r) = rhythm. Designator position = MGS track number.
  Track 0 is definitions only (@v/@e/@r/@s/@#, #psg_tune/#opll_tune,
  @m strings). Macros `*n = { }` (0-255), `#macro_offset`, loops
  `[n ... ]` / `|`, tie `^`, slur `&`, steps `%n` (quarter = 48,
  max 256 per note), defaults o4 / l4 / q8 / v0.

## Encoding anchors (probed against the oracle)

- `o4` -> D3 (octave-1). `l8` -> 42 18 (24 steps).
- A note whose length equals the current `l` state uses the short
  form 3n; an explicit different length uses 2n ll (ll = steps,
  00 = 256). Rests mirror this (3C / 2C ll).
- `t<n>` in a track -> 41 ll hh + a 48-byte tempo frame table. The
  table's generating formula resisted fitting (it carries
  floor(14400/T) one-bits in 384); all 1991 tables (tempos
  57..2047) are extracted from oracle output in
  `py/mgsexc_tempo_data.py` until a formula is found. Header
  `#tempo` writes only the word in the binary header.
- `#alloc` also marks tracks as present: an allocated-but-empty
  track is emitted as a lone FF terminator.
- MGSC reads each source line into a 255-byte buffer: longer lines
  are truncated (rest discarded), and when any line overflows, the
  output's first byte is 0x00 instead of 'M'. Output is zero-padded
  to a multiple of 128 bytes. MGSEXC reproduces all of this.

## Verification gates

1. Differential harness `scripts/check_mgsexc.py`: compile the same
   MML with MGSC (oracle) and MGSEXC; require byte-identical MGS.
   Corpus: public fixtures first, then generated song MMLs.
2. Songs MGSC cannot compile (Salamander 02/06): MGSEXC output is
   verified by playback trace (libkss -> VGM register stream vs the
   source VGM), the same method used for the v2.0.1 fixes.
3. Full existing test suite stays green; compiler selection is
   opt-in until gates 1-2 pass on the Salamander set.

## Non-goals for v1

- MGSARC compression output.
- MGSC error-message compatibility (only success-path bytes matter).
- New MML features beyond MGSC's dialect.
