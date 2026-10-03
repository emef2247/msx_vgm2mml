# Full PSG/SCC benchmark on authored loop blocks

## Scope and controlled comparison

The user wanted actual old/new conversion differences and coverage of different
loop shapes, not only a split-file inventory. Compare all35 matching loop-block
MML/VGM pairs from the ten multi-block songs under the private msxplay.com/
gra2_msx catalog. Reuse the six already verified gra2_001 conversion pairs and
run the other29 pairs. Private source fixtures remain unchanged.

Both variants use enhanced macros, ordinary target ticks, default allocations
and sync policy, with normalization OFF. Only the PSG/SCC bank/projection
changes: earlier envelope-first implementation versus current source-loop-first
structural implementation. This is the same comparison as the preceding eight
inputs, not a combined change to the macro algorithm or historical chip fixes.
Every run retains --dump-passes artifacts, including candidate catalog, selected
source tree, projection status, envelope counts, target notes and Segment metadata.

No production conversion code was changed for this benchmark. Local measurement
helpers live outside the repository. A duplicate keyword in an early local
measurement script was repaired; successful conversion dumps were reused and
rechecked. This harness error was not a VGM conversion failure. Final results
include all35 complete pairs, not only the cases measured before that repair.

## Final MML sizes and compilation

Full decoded characters include definitions, comments and whitespace with LF
line endings. Positive saved percentages mean smaller new output. All generated
MMLs here are ASCII, so final character and byte counts coincide.

| Song | Blocks | Earlier characters | Structural characters | Saved | Compile successes, each variant |
| --- | ---: | ---: | ---: | ---: | ---: |
| gra2_001 | 6 | 49135 | 48902 | 0.47% | 6/6 |
| gra2_003 | 2 | 14224 | 14182 | 0.30% | 2/2 |
| gra2_004 | 3 | 14700 | 14242 | 3.12% | 3/3 |
| gra2_007 | 3 | 17124 | 17693 | -3.32% | 3/3 |
| gra2_009 | 2 | 13336 | 13242 | 0.70% | 2/2 |
| gra2_010 | 2 | 18122 | 18025 | 0.54% | 2/2 |
| gra2_011 | 3 | 13455 | 13754 | -2.22% | 3/3 |
| gra2_014 | 7 | 36948 | 36644 | 0.82% | 7/7 |
| gra2_015 | 4 | 14747 | 14625 | 0.83% | 4/4 |
| gra2_016 | 3 | 54733 | 53877 | 1.56% | 2/3 |
| Total | 35 | 246524 | 245186 | 0.54% | 34/35 |

23 blocks shrink, two are unchanged and ten grow. Excluding comment-only/blank
lines and trailing comments, code characters total218404->217724 (-0.31%).
Largest individual saving: gra2_004 block01,4611->4226 (-8.35%). Largest growth:
gra2_007 block02,8553->9088 (+6.26%). That growing pair has the same14 envelope
definitions occupying430 characters and32 macros; its physical loops increase
38->45. The current source-tree objective does not guarantee the best final
character count after stateful command projection and macro allocation.

All70 conversions succeed. MGSC1.11 via mgsc-js2.0.0 compiles68 MMLs. Both
variants of gra2_016 block03 fail with Track buffer full in track1. Its text
shrinks27254->26860, but that is insufficient to resolve the existing buffer
failure. No compilation regression or improvement in the pass/fail set occurs.
No manual allocation changes, removed tracks or shortened music are used.

## Source and effective-state preservation

All35 pairs preserve identical native PSG/SCC Segment dataclass fields, including
timestamps, source sample boundaries where recorded, register periods, volume,
hardware-envelope settings and waveform evidence. Target annotation IDs/paths
are excluded from this native-field equality check.

After expanding final macros/loops and applying software envelopes, each of the
70 MMLs matches its Segment effective pitch/octave/volume/mode/noise/hardware-
envelope/waveform timeline at every ordinary60Hz tick under the existing target
pitch interpretation. All35 old/new effective timelines also agree. Reversible
source-plan and macro expansion assertions run during conversion.

These are state/timing checks, not a new MGS->VGM/audio roundtrip. They do not
prove oscillator phase, sample-exact frequency, release-tail or human playback
equivalence. Source-size and successful compilation are separate measured goals.

## Reference-loop window audit

Use the loop-aware fixture splitter's AST/duration functions, which accept the
reference hardware-vibrato and numeric macros that the earlier general audit
parser could not handle. The supplied block MMLs retain contained finite loops.
Traverse their nested loops and expand parent invocations for window positions.
There are347 distinct channel loop definitions and477 finite invocation windows;
the latter includes multiple invocations of the same nested definition. Do not
interpret477 as477 physical source brackets or independent musical phrases.

Map score positions with the declared tempo and a reported first-audible-note
anchor per channel. All measured offsets are3 or4 ordinary ticks. This is an
approximation, not VGM command-address correspondence. Window/body/end matching
permits at most1 ordinary tick difference. The shortest reference loop body in
this set is5 ticks. Report matches as approximate window coverage, not an exact
authored semantic-recovery percentage.

Compare three separately observable stages:

- Catalog: exact source-note-key repeats are present at corresponding windows.
- Selected: the reversible source tree retains that window, expanding parent
  shifts when inspecting its nested markers.
- Final: a bracket loop exists at that window in final MML after macro expansion.
  Macro calls alone are not counted as bracket recovery.

A full-window match covers the declared repeated region. A partial match means
at least two consecutive iterations of the same body length at an iteration
boundary; it includes full matches, and can represent an initializer left outside.
It does not count an arbitrary short loop somewhere inside a longer phrase.

| Reference window type | Windows | Catalog full / partial | Selected full / partial | Final old full / partial | Final new full / partial |
| --- | ---: | ---: | ---: | ---: | ---: |
| One timed note in body | 30 | 10 / 29 | 7 / 27 | 0 / 20 | 0 / 17 |
| Multiple timed notes in body | 404 | 203 / 293 | 161 / 231 | 32 / 161 | 33 / 180 |
| Parent body containing loops | 43 | 12 / 21 | 11 / 13 | 0 / 2 | 0 / 5 |
| Total | 477 | 225 / 343 | 179 / 271 | 32 / 183 | 33 / 202 |

These categories describe reference syntax; they do not infer percussion or
musical function. Nested loops, single-note repetitions and multi-note phrases
are all found, but coverage is incomplete. New final partial-window matches
increase183->202, while full-region bracket matches barely change32->33.
The single-note category becomes worse in final bracket coverage20->17; do not
hide this behind the total increase.

For454 windows, all inferred iteration boundaries align with complete source
note boundaries within the declared tolerance.217 have identical complete
note keys across all iterations.229 still match when note lengths and volume-
run lengths are omitted while retaining settings and volume-level sequences.
Thus there are12 timing-only differences under this particular mapping, and
many other differing sequences/volume trajectories or boundary ambiguities.
These diagnostic counts are not proof of a parser bug or a universally correct
timing normalization. The candidate stage continues to require exact source keys.

## Concrete projection limit and interpretation

Across all outputs, physical brackets increase758->789, with macro definition
bodies counted once and not multiplied by calls. Selected source trees contain
2116 markers and reach depth4. Final bracket nesting remains at most2 in both
variants. Marker counts and physical bracket counts measure different things.

gra2_004 block01 track5 provides a concrete inspected example. The reference
has a384-step nested body repeated twice. The new source tree selects a48-note
body repeated twice, containing inner6-note loops repeated4/2/2 times. The
projection CSV retains the parent with emitted_repeats=0 and status
expanded_different_commands. The first inner4-repeat loop emits only3 repeats
on the initial pass, whereas its next invocation emits4. Source note keys repeat,
but initialization/state-command suppression makes the emitted iteration texts
different. The same-boundary parent bracket is therefore absent from final MML.
This is evidence of a projection limitation after successful structural detection,
not evidence that nested-loop candidates cannot be found.

The benchmark supports the structural representation as useful inspection data,
but does not establish maximum final compression. More source structure can yield
smaller, equal or larger text. Further work could compare state-equivalent command
forms when projecting a parent and evaluate alternative macro allocations without
losing the reversible tree. That is a separate implementation decision; no such
optimization or automatic old/new winner selection is added in this benchmark.

## Artifacts

Private Codex output directory: co/outputs/gra2-source-structure.

- all-blocks-comparison.csv/json:35 paired character, compilation, source/state
  and structure measurements; JSON includes per-song totals.
- loop-recovery.csv/json: reference invocation windows, per-channel anchors,
  catalog/selected/final matches and diagnostic note-key comparisons.
- Per-input legacy/structural directories: MML/MGS, full pass/Segment/candidate/
  structure/projection/macro CSVs and conversion/compilation logs.

The earlier eight-input table includes unsplit002/005 and must not be summed
with this35-block table as an independent corpus. Private MML/VGM contents and
local helper scripts are not committed. Source fixtures were not regenerated,
deleted or edited by this measurement. No stage/commit/push was performed.
