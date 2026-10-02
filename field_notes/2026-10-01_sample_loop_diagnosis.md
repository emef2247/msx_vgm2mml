# Sample: is each reference loop actually emitted?

Regenerated only the public sample fixture with the current converter and
`--dump-passes`. Compared reference MML lines with the performed-unit dumps,
before/after target MML, and the final merged MML including macro expansion.
No converter behavior, timing tolerance or source time fields were changed.

## First reference pass

| Reference lines | Tracks | Reference repeats | Current output |
| --- | --- | ---: | --- |
| 20 | 9/a | 4 | First iteration outside; remaining three looped |
| 21 | 9/a | 2 | Complete two-iteration loop |
| 22 | 9/a | 2 | Complete phrase not looped |
| 25-27 | b/c/d | 2 | Complete phrase not looped; c/d have smaller inner loops |
| 28-30 | b/c/d | 2 | Complete two-iteration loops, including inner loops |
| 33 | f | 4 with last-pass exit | Repeated core looped three times with shifted boundaries |
| 36 | 1 | 4 with last-pass exit | Repeated core looped three times with shifted boundaries |

The outer infinite reference loop is not emitted as an infinite MML loop.
Source-loop metadata and finite repetition compression are separate features.
Later recorded passes also contain additional selected loops. This table is
specifically about recovering the reference phrases in the first pass, not
whether the entire song has any compression or reusable macros.

## Confirmed timing rejection

Reference line 22 has two 28-unit note/rest phrases. On track 9 the actual source
unit ranges are 169-196 and 197-224 (inclusive), spanning ticks 722-842 and
842-963. Track a has corresponding ranges. After removing trajectory offsets
and durations, every corresponding positive-state sequence is identical,
including FNUM, block, instrument, attenuation, sustain, patch bytes and patch
changes. There are no extra note/rest units in either repetition.

Five corresponding units differ in duration on track 9, thirteen on track a;
every duration difference is one tick. The exact positive trajectory validation
keys differ at those same positions. Current candidate signatures use duration,
and replacement also requires exact timed trajectories and emitted commands.
Consequently the complete two-iteration phrase fails the current equality
criteria. Neither before-sync target output nor the final merged MML contains
a loop for that phrase. This is a concrete missed reference loop caused by the
current treatment of timing, rather than an unverified general possibility.

This proves a difference in the converter's existing integer ticks. It does not
yet establish whether the difference originated in the recorded VGM waits,
floating-point accumulation, or conversion to 60 Hz. That attribution requires
separate source-sample inspection. No timing tolerance has been enabled.

## Confirmed non-timing obstruction

For reference lines 25-27, the first and second phrases each have twelve
performed units, and their complete validation keys match exactly. Their
emitted commands do not match: first-pass voice/volume/octave initialization
is present only in the first phrase. Track b also restores octave at the start
of the second phrase. A whole two-iteration loop is not selected. This is not
a timing rejection. The greedy report also contains an initial-rest-aligned
candidate marked different_state; that candidate must not be confused with
the correctly aligned reference phrase starting at tick 2.

Thus sample already distinguishes timing differences, initialization/command
differences, and loops selected with different phase boundaries. A timing-only
relaxation would not by itself recover all reference loops.

## Inspectable outputs

Codex workspace `outputs/sample-loop-diagnosis` contains the regenerated MML,
existing pass dumps, and these additional local inspection artifacts:

- `reference_loop_verdicts.csv`: per-reference-loop result.
- `line22_unit_comparison.csv`: all corresponding unit IDs, durations and
  state/equality checks for tracks 9/a.
- `first_accompaniment_command_differences.json`: exact setup differences.
- `reference_windows/reference_loop_windows.csv`: approximate mapped windows.

Direct unit intervals and timed generated-loop nodes were checked for the
reported examples; approximate window mismatches alone were not used to
declare a conversion failure. This task does not change note timing or sound.
