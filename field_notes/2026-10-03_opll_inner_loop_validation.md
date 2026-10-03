# OPLL continuous-note child loops: FFMSX01 recovery

Implementation and focused validation in the separate test checkout:
`I:/wsl/repositories/emef2247/test/msx_vgm2mml`.
The original checkout and its running catalog regression were not modified.
No private musical content is included here.

## Cause and remedy

The outer source plan correctly grouped continuous keyed intervals, but treated
each entire note trajectory as a leaf. FFMSX01 contains long keyed trajectories
with exact adjacent pitch/state subphrases. Different complete trajectories
could not match as outer notes, while their internal repeats were unavailable to
that projection. This is not a nesting-depth or timing-jitter failure.

The previous four-way comparison isolated loop projection from macro selection:
legacy loops/enhanced macros produced 7,659 characters and compiled, while
outer-only structural loops/enhanced macros produced 49,922 characters and
failed. Substituting legacy macros alone did not fix the structural output.
The original older saved MML was 8,196 characters.

Add a separate source plan over the ordered Segment members of every OPLL note.
Keep the parent note tree, original register/timing cells and key boundaries.
Render the original command stream once, project child then parent loops, and
check exact expansion. Retain parent-only spelling when shorter before macros.
Existing enhanced macros follow this projection. Source markers remain visible
in Segment CSVs and per-channel source-plan dumps even if not emitted.

## FFMSX01 result

Normalization is OFF, source-sample dumps ON, default structural loops and
enhanced macros ON. No manual allocation override was supplied.

| Measurement | Outer-only regression | With child plans |
| --- | ---: | ---: |
| Final MML characters | 49,922 | 7,944 |
| Channel used bytes | 26,116 (isolated compiles) | 5,945 (full compile) |
| Full MGSC compile, ordinary 15,000 track allocation pool | buffer_error | success |

Character reduction: 84.1%. The repaired full compiler reports 5,999 used bytes
including the 54-byte track-zero header. The legacy-loops/enhanced-macros result
remains slightly smaller (7,659 characters / 5,426 total used bytes); this repair
restores capacity without claiming global optimality.

| Track | Regression used bytes | Repaired used bytes | Repaired allocation |
| --- | ---: | ---: | ---: |
| 1 | 866 | 866 | 2,564 |
| 2 | 861 | 861 | 2,547 |
| 3 | 862 | 862 | 2,402 |
| 9 | 6,211 | 843 | 1,861 |
| a | 6,214 | 846 | 1,867 |
| b | 4,686 | 809 | 1,718 |
| c | 99 | 99 | 347 |
| d | 89 | 107 | 308 |
| e | 6,228 | 652 | 1,386 |

PSG music and its compiled sizes did not change. Smaller OPLL runtime loops
also remove the disproportionate OPLL text lengths that previously left track3
with only 567 allocated bytes despite needing 862. This is the shared allocator
responding to different input lengths, not an OPLL transformation changing PSG
events. No allocation-estimation algorithm was changed.

All 8,735 OPLL and 4,647 PSG native Segment rows retain every source field
(68 and 20 distinct fields respectively); SCC has no rows here. All 14 trace/
pass CSVs are byte-identical. Expanded final timed commands match both the
outer-only output and the saved successful older MML on all tracks. Child
projection applies 42 marker occurrences across the OPLL channels.

## Focused regression

Baseline disables only the new child projection, retaining the same outer
source plans, all other chip paths, enhanced macros, titles and allocation.
Both sides use --dump-passes --vgmticks and leave normalization OFF.

| Fixture | Baseline characters | Child-plan characters | Used bytes before / after | MGSC both |
| --- | ---: | ---: | ---: | --- |
| sample | 4,913 | 4,913 | 2,956 / 2,956 | success |
| grider | 24,721 | 24,721 | 13,060 / 13,060 | success |
| sx01v | 15,024 | 15,048 | 9,200 / 9,204 | success |
| gra2_005 | 8,313 | 8,313 | 5,195 / 5,195 | success |

Every original Segment CSV cell other than newly introduced child annotations
matches across each pair. All 14 trace/pass CSVs per fixture are byte-identical.
Expanded timed final commands also match across each pair. No manual #alloc
was needed and no new buffer error occurred.

sx01v applies one child marker. Its final text grows by 24 characters (0.16%):
shorter pre-macro spelling is not guaranteed to be shorter after macro selection.
Its compiled usage also grows by four bytes. Record this small tradeoff rather
than claiming monotonic improvement; final macro-aware global selection remains
a separate optimization. sample/grider/gra2_005 are unchanged in final size.

## Validation scope and artifacts

Compiler: MGSC 1.11 via the existing mgsc-js adapter on Windows; the native WSL
executable was not invoked in this check. This is compiler and exact command/
Segment equivalence evidence, not a new audio or hardware playback test.

Local, uncommitted artifacts under the Codex workspace:

- `outputs/ffmsx01-investigation/inner_fixed`: MML/MGS, source and target dumps,
  per-note child markers and compiler log.
- `outputs/ffmsx01-investigation/inner-fixed-summary.json`: exact comparison.
- `outputs/opll-inner-loop-regression/<fixture>/{baseline,inner}`: all eight
  conversions and compiler logs; `summary.json` records the comparison.

Synthetic regressions cover continuous pitch repeats, initialization/gate state,
zero-duration true edges, pitch/volume/unknown-patch inequality, nested parents
and Segment annotation preservation. All 55 focused tests pass, including
existing target, source-plan, structural, macro, sync, mode and public conversion
checks. A wider catalog
regression and listening check remain the next user-controlled evaluation.
