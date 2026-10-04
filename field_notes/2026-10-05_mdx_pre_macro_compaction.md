# MDX target compaction before macros (2026-10-05)

## Scope and reviewed precedents

The user requested redundant-command/duration optimization before MDX macros,
and specifically asked to review the OPLL/PSG/SCC implementation history.
MDX macro extraction is still not implemented.

Relevant existing behavior was checked in code:

- `opll_note_units.group_notes` distinguishes KeyOn edges, KeyOff and timing
  gaps from a continuously keyed trajectory. Zero-duration attacks remain
  boundaries; pitch/volume updates while keyed are not new attacks.
- `opll_target.render` retains pending edges across zero-length source rows,
  ties genuine continuations and uses MGSDRV gate control to avoid unwanted
  retriggers across pitch changes. Repeated setters are emitted only on change.
- `opll_inner_loops.OpllLoopPlan` discovers child repeats inside continuous
  notes as well as outer note/phrase repeats. Expanded target commands are
  checked exactly. This was important to the FFMSX01 recovery.
- `pre_envelope_loops.LoopFirstEnvelopeBank` builds source plans and selects
  representative curves before allocating PSG/SCC software envelopes.
  `mml_envelopes.extract_notes` retains pitch-write/reset and volume-rise
  boundaries; these chips do not share OPLL's explicit FM KeyOn register model.
- `opm_loops.OpmSourceLoops` already distinguishes rising/falling operator
  masks and held/released states, retaining inner Segment plans. Equality
  includes Key edges and complete native state, not only note name/length.

MGSDRV-specific `q0` behavior is not transplanted into MDX. The common principle
is to preserve actual attacks and continuous-note membership, then use the
target's own gates/ties. Source structure still precedes target compaction;
there is no OPM software-envelope extraction stage added here.

## Implementation

`py/mdx_compaction.py` operates on each generated MDX track after source-loop
projection. It does not reshape source Segments or alter their loop plans.

1. Reuse unchanged voice, volume, pan, gate, detune and octave settings.
   Raw operator/algorithm writes invalidate voice/volume/pan reuse, since
   loading the same voice can be required to restore chip state. The first
   setters inside each loop remain explicit; a back edge can have different
   incoming state from the first pass.
2. Encode sufficiently long rests as finite loops over the same 128-tick
   chunks emitted by the MDX compiler. Keep the final remainder unchanged.
3. Encode repeated tied 256-tick chunks as note-and-tie loops, with `&` inside
   the body. Expansion preserves the original note/tie token sequence and
   compiler lookahead; a final untied chunk still ends the original note.
   Untied repeated notes remain distinct attacks. Controls and different notes
   interrupt this duration-only factoring.

Repeat counts stay within the compiler's 255 limit. New duration loops are
not added at its 64-level nesting limit; this does not limit native loop
discovery or truncate existing structure. `--no-loops` suppresses duration
loops too, while setter reuse remains enabled.

No raw register controls are removed. No clock retuning, source normalization,
new note boundaries, noise-note lowering, or changes to comparison criteria
are included. Arbitrary held-note/noise controls still use the existing raw
fallback. Their more compact target expression remains separate future work.

## Inspection

With `--dump-passes`:

- `.mdx.structure.plain.mml`: original flat target spelling.
- `.mdx.structure.uncompacted.mml`: source-loop projection before compaction.
- `.mdx.structure.compaction.csv`: track, original target token position,
  before/after spelling, decision and estimated compiled bytes saved.
- `.mdx.structure.units.csv`: unchanged target units and native membership.
- `.opm.segments.csv`: unchanged integrated native source/loop evidence.

Token positions in the compaction CSV exclude header `A @t255` initialization.
The timing summary now distinguishes source loop commands from total emitted
loops, so duration factoring is not misreported as new musical phrase discovery.

## Validation and measurements

Working repository: `/mnt/i/wsl/repositories/emef2247/test/msx_vgm2mml`.
Artifacts: `outputs/opm/pre_macro_compaction/`.
External compiler/replayer: existing Windows MDX helper using mmlx/soundlog.

- 12 target-compaction tests passed: setter reuse/invalidation, loop back edges,
  distinct untied attacks, explicit raw KeyOff/KeyOn, exact tied expansion,
  rest chunk identity, count and nesting boundaries, and no-loops behavior.
- All 58 existing OPM tests passed. The loop-count assertion now checks the
  unchanged **source** loop count separately from added target-duration loops.
- Public OPM inputs: 38/38 fresh full-pipeline roundtrips passed.
- Local 4-MHz cohort: 52 saved target MML files were compacted and compiled;
  replay was compared with native Segments rebuilt from their saved source
  traces. This isolates the new target pass without rerunning expensive source
  loop discovery for every song. Unsupported 3.57958-MHz inputs were excluded.
- Fresh full-pipeline runs additionally covered M_G2_08S (success) and WARNOP
  (still capacity-limited). Native M_G2_08S evidence and uncompacted target
  were byte/text compared with the previous regression.

| Local result | Before | After |
| --- | ---: | ---: |
| Success | 35 | 36 |
| MDX capacity failure | 17 | 16 |
| Previously successful cases becoming failures | — | 0 |

All 36 successful comparisons have zero missing/extra channel attacks,
operator KeyOns/KeyOffs and known-state mismatches. Channel attacks total
17,506 on both sides. Existing projected timing and Key-sequence checks passed.
No audio or hardware equivalence claim is made.

For the **same original successful 35 inputs**, the saved-target benchmark gives:

| Measurement | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| MML characters | 1,453,826 | 1,165,412 | 19.84% |
| Actual MDX file bytes | 639,547 | 443,491 | 30.66% |

This benchmark folds the tempo line into A's wrapped stream; a fresh normal
renderer preserves its separate header line. The small formatting difference
is not a musical or binary optimization. The benchmark saves the actual text
measured, its compiler output and comparisons. Its command-byte saving estimates
equal actual MDX file-size differences for all 35 originally successful cases.

One case, M_G2_18S, grows by 14 text characters while its MDX shrinks by 102
bytes. Rest-loop syntax can be longer text yet substantially cheaper binary.
Text and binary benefits are recorded separately instead of claiming monotonic
improvement in both metrics.

### Newly successful M_G2_08S

Fresh normal conversion:

- MML before/after: 166,872 -> 145,270 characters.
- Compiled MDX: 56,208 bytes (previously compilation failed on track offsets).
- Source/returned channel attacks: 1,757 / 1,757.
- Source/returned operator KeyOns: 6,200 / 6,200; missing/extra keys: zero.
- Known-state mismatches: zero.
- Native Segment CSV, raw/state trace CSVs and target unit CSV are byte-identical
  to the prior run. The uncompacted MML equals the prior structured MML.

See `m08_native_preservation.json`, `local_m08/`, and
`saved_local_targets/results.csv` under the artifact directory.

## Remaining limits

The other 16 failed cases still exceed MDX address capacity, including WARNOP
and the large WBIIIAC control streams. Their text is smaller, but that does not
guarantee compilation. The saved-target diagnostic labels these as
`mdx_capacity_error`; the regular verifier's status vocabulary was not changed.

Next optimization should inspect held-note/noise target lowering while retaining
every required operator and Key transition. Further source-loop improvements
and MDX macros remain separate decisions. Do not change source Segments, invent
attacks, flatten modulation, or weaken comparisons to fit target capacity.
