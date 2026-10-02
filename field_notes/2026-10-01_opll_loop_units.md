# OPLL loop review: units after key-edge preservation

## Scope

Alest202 is the main compression target. grider and sx01v have reference MML
for inspecting intended phrase structure. The public PSG+OPLL sample checks mixed
parts. The msxplay-exported PSG/SCC gra2_001 remains the major cross-chip target.
Reference MML is validation evidence, not an input to production conversion.

## Initial measurements

Fresh conversions used the current key-edge-preserving converter and
`--dump-passes`; outputs were isolated from the user's completed batch results.

| Input | Final MML bytes | Melodic Segment rows | Rendered melodic intervals | Source melodic KEYON edges |
|---|---:|---:|---:|---:|
| Alest202 | 30612 | 14725 | 10466 | 1755 |
| sample | 6065 | 2705 | 638 | 609 |

Segment and rendered-interval counts are not counts of separate notes.
Alest202's projection reports contain applied repeats; the problem is not an
absence of OPLL loop support. The current `opll_target.render` creates one
performed Unit per Segment, and `melody_patterns` compares state intervals with
analysis flags and relative interval lengths. This can prevent a complete
repeated attack/continuation phrase from matching when its internal state
partition or analysis context differs. The amount of recoverable compression
has not yet been measured for a replacement unit model.

## Proposed next implementation

Keep all source Segments, including zero-duration rows. Build a separate OPLL
performed-note layer bounded by observed key edges and release/silence, with
source Segment indices. Carry zero-duration key transitions into this layer;
never join two true KEYON attacks simply because pitches match.

Compare relative pitch, volume, instrument/user-patch, sustain and duration
trajectories within these units. Retain the distinction between raw observations
and analysis flags. Do not relax audible-state equality to force a match.

Projection must retain the current gate/tie behavior and complete expanded
commands. Different initialization can remain outside the repeated body. Dump
unit membership and rejection reasons so newly found and still-missed phrases
can be inspected in the Segment CSV. Keep existing loops/macros as a fallback.

Use reference phrase boundaries first in grider/sample, then sx01v. Evaluate
Alest202 by source text size, compiled capacity and unchanged key-on counts.
Confirm PSG/SCC behavior with gra2_001; do not transfer OPLL key-edge semantics
to chips without the same hardware key mechanism. An unchanged count alone does
not certify identical sound or event placement.

No loop optimization or musical conversion behavior was changed in this review.

## Implementation result

The performed-note layer is implemented. Alest202 has 3510 performed note/rest
units instead of 14725 melodic Segments, but its output remains unchanged.
Expanded commands and timings match the previous renderer for Alest202, sample,
grider and sx01v. Positive state trajectories ignore non-rendered zero-duration
register states while source members and key-transition boundaries are retained.

Compiled used bytes: sample 3489 -> 2963; sx01v 9189 -> 9125; grider
12954 -> 13096. Source-text and compiled-byte optima differ. The full sample
MML grew from 6065 to 6453 bytes despite shorter chip output, due to subsequent
macro placement. Alest202 remains buffer-full and gra2_001 exceeds the JS source
limit. Do not claim either capacity issue has been fixed.

Post-change exported counts (reference/actual/missing/extra): sample
609/604/5/0, grider 2596/2558/38/0, sx01v 1615/1604/11/0. Grider counts match
the earlier batch export. These counts are not event matching or sound scores.
