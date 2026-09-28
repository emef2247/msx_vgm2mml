# Current handoff

Date: 2026-09-28
Status: ready to resume

## Last completed
- Added target-stage PSG/SCC rest cleanup and software-envelope extraction in
  py/mml_envelopes.py. Source Segments are unchanged; target_notes CSV and target
  MML are retained with --dump-passes. Shared envelope bank is limited to 32.
- Removed silent tracks from final body, allocation and sync-point calculation.
- Checked both supplied envelope fixtures in standard/raw modes and gra2_003:
  rendered pitch/volume/mode/wave state matches Segment intervals tick by tick.
- Full suite of 29 tests passed, then all six envelope tests passed after adding
  hardware-envelope/retrigger and definition-limit fallback coverage.
- Corrected SCC to five channels, one enable bit per channel, and shared
  waveform updates for channels 4/5 (MML 7/8).
- SCC PASS1 now describes post-write state until the next event; PASS2 does
  not move waveform-setup time into later notes. Repeat compression preserves
  duration and only groups identical adjacent states; waveform/volume/octave
  changes are applied immediately by the MGS renderer.
- Merged #alloc now distributes 15000 proportionally to emitted track-text
  size (excluding whitespace, track IDs and comments). Silent tracks get no
  allocation; their MML is retained pending a later cleanup step.
- gra2_002 raw SCC tracks 4..8 each total 356 ticks, matching trace intervals.
- Public conversion checks now use trace-state timing/pitch/volume assertions
  for SCC rather than old hashes that encoded the corrected bugs.
- Added --sync-min-gap (default 1000 target-MML steps, 0 for all shared points).
  Select the first shared boundary at least that far from the previous marker;
  start and final end are always retained. No note splitting or retiming.
- Fixed blank-line accumulation when sync annotation extracts track bodies:
  final header now keeps at most one blank separator. Regenerated outputs/check/giselle.mml;
  all nonblank lines (including music and sync comments) match the previous output.
- Added shared step comments to final merged MML via py/mml_sync.py. Common
  boundaries are calculated across all still-playing channels in target MML time.
- Preserved expanded note/command timelines; loops crossing a marker are expanded
  only as needed. Event/PASS/Segment generation remains unchanged.
- Verified all 20 existing/current unittest methods (including 134 conversion
  scenarios), then all 10 sync tests after adding a two-mode mixed-VGM CLI test.
- Verified all 12 mixed public VGMs in standard and raw modes (24 conversions).
- Documented sync semantics and time units in docs/mml_sync.md.
- Refactored PSG/SCC into event CSV -> analysis -> immutable chip-specific Segment -> MML.
- Added py/psg.py, py/scc.py and py/chip_segments.py; renderers consume named fields.
- Retained PASS0-3 and added Segment/waveform CSVs. --dump-passes now keeps input event CSVs.
- Initial 134-case comparison preserved an existing SCC-header bug. Corrected
  the clock offset from 0xCC (ES5503) to 0x9C (K051649), added header-boundary
  checking and clock-flag masking. Regression expectations now come from the
  old non-Segment converter plus only that header fix.
- Verified SCC note output from an unmodified public VGM; header tests added.
- Header correction validation: all 11 unittest methods passed, including 134
  conversion scenarios against the header-corrected pre-refactor reference.
- Inspected PSG zero-length/envelope fields and SCC waveform/Segment CSVs.
- Documented the architecture and preserved legacy heuristics in docs/psg_scc_segments.md.

## Unfinished
- No required implementation remains for automatic shared sync comments.
- Completed rest-only track removal, deferred rest-time controls, and explicit
  volume-hold envelope definitions. Fitting compact linear ramps (= syntax) is
  not implemented; supplied references therefore differ in envelope spelling.
- Supplied envelope reference lengths differ from VGM-derived timing by 3 ticks
  for 001 and 2 ticks for 002; do not claim exact reference-file equality.
- gra2_002 is not yet an exact match to the hand-authored reference: initial
  timing, PSG behavior and envelope representation remain distinct. Allocation
  weights are textual estimates, not measurements from an MML compiler.
- Hardware playback and WSL execution have not been checked.
- Changes are local and uncommitted; existing user-generated/untracked data was left intact.

## Next allowed action
- Review the local diff and run `python -m unittest discover -s tests -v`.
- Treat any changes to timing, waveform reconstruction or note-boundary heuristics as separate work.

## Do not do next
- Do not discard event/PASS evidence or replace chip-specific fields with OPLL defaults.
- Do not mistake 0xCC for SCC or infer valid conversion from old-output equality alone.
- Do not overwrite private fixtures or regenerate regression hashes to hide a mismatch.

## OPLL rhythm inspection update (2026-09-28)

Added native `.opll.segments.csv` output before target voice assignment,
including rhythm channels. Preserved legacy dumps and MML behavior. Added
optional reference parity tests for traces, PASS1-4 and rhythm Segment fields,
and synthetic edge-expansion tests. Private reference data remains untracked.
Next: assess remaining edge cases through the complete pipeline, then agree
on a common rhythm schema before implementing rhythm MML output. Do not
interpret source rhythm flags as independent triggers; use keyon and channel.

Validation: all 37 unittest methods passed (including 134 conversion cases
and all three optional rhythm references). CLI sample Segment CSV contains
282 rhythm rows; merged sample MML is byte-identical to the pre-change output.

## Rhythm grouping update

Added rhythm_patterns.py and group/definition/occurrence CSVs under --dump-passes.
Preserves native Segment data and MML output. Exact adjacent repeats only;
no timing tolerance or common OPNA schema yet. Tests reconstruct timing and
hit states from exported patterns and check every source reference, duplicates,
volume/pitch distinctions, initial silence and the unknown final gap.
Next: review sample patterns before implementing MGSDRV rhythm rendering.

Validation: all 42 unittest methods passed, including the existing 134-case
conversion regression. Sample: 282 input hits, 213 groups, 18 definitions and
71 occurrences; expanded pattern data matches groups and source references.
The sample merged MML remains byte-identical to the previous output.

## Timing field note

Recorded the external oplldrv/libkss timing evidence and sample recalculation
in field_notes/2026-09-28_mgsdrv_libkss_timing.md, linked from project knowledge.
This is documentation only: do not globally replace the existing 60 Hz clock.
Future timing profiles must separate VGM samples, playback frames and MML steps.

## Rhythm MML output update

Implemented rhythm_mml.py, OPLL target projection selection, rhythm-aware sync
and allocation, and five semantic tests. Exact loops and absolute per-drum
levels preserve group onsets/volumes. Legacy melodic variants remain unchanged.
All 47 tests passed. Six fixtures in both modes match grouped rhythm events.
All eight isolated rhythm outputs compile with MGSC 1.11 / mgsc-js 2.0.0;
full sample normal/raw and sx01v raw compile. Other full outputs hit source
length or melodic track buffer limits. No listening test performed.
Next: user playback review; overall melodic size/allocation tuning remains
separate. Do not apply a global 59.94 Hz correction or collapse duplicate hits.

Rhythm tail correction: target end includes the latest OPLL trace tick as
well as Segment ends. Attack-only rhythm Segments omit the final key-off;
using their ends alone truncated the last cymbal in rhythm_only_test02.
The fixture now ends at tick 77 rather than 41, retaining its tick-40 attack.
This does not reconstruct unlogged trailing VGM waits or acoustic decay.
Seven rhythm renderer tests pass, including normal/raw tail checks.

## OPLL custom voice and notation correction

Added opll_target.py and tests/test_opll_target.py. Final merged OPLL output
uses correct YM2413 patch decoding, ROM @0..@14 and user @16+ definitions,
and exact note lengths with ties on splits. Legacy variants remain unchanged
for regression comparisons. Target note CSV records source index and patch.
Custom-voice reference: all 15 definitions and alternating selections match
in normal/raw modes; MGSC 1.11 compiles normal output. No listening check.
Next: user audition; remaining mid-note patch scheduling and source Segment
boundary interpretation are separate from this target-format correction.

## Latest: rhythm notation optimization

Added py/rhythm_notation.py and tests/test_rhythm_notation.py. Final rhythm
output deduplicates absolute volumes safely across loop boundaries and uses
one default length if shorter. Pattern discovery remains Segment-based; no
new loops or macros are inferred from text. Added before/after target dumps
and optimization metrics under --dump-passes. Fixed physical line wrapping
inside long preserved loops after MGSC rejected an overlong line.

Six fixtures in normal/raw modes preserve attacks, volumes and duration.
All 24 isolated before/after rhythm files compile with MGSC 1.11. Sample
normal rhythm text: 1175 -> 633 characters; compiled bytes: 736 -> 449.
Next: extend Segment-based pattern analysis and notation reduction to melody;
macro extraction remains optional. No files staged or committed by the agent.

Full unittest discovery passed all 59 tests after the line-wrapping fix.

## Latest: OPLL octave correction after voice review

Fixed final target notes being one octave too low: MGSDRV octave = MIDI // 12.
Verified block 3 from o4 a versus block 2 from o3 a through MGSC/libkss.
Voice number mapping and custom patch decoding were correct and are unchanged.
Equivalent @16 and @v20 definitions/selectors produce identical user registers.
Generated grider compiles and its opening melody block now matches the source.
Added all-eight-block pitch tests and all-fifteen-ROM-instrument mapping tests.
No files staged or committed. Full audio equivalence remains unproven.

## Relative melody notation and export-tail observation

Final PSG/SCC/OPLL melodic renderers now use >/< for one-octave changes and
)/( for one-volume changes when the previously emitted state is known.
Initial values and larger changes remain absolute. Rest-time source changes
are deferred; relative commands use emitted state, not skipped source state.
Rhythm instrument volumes and Segment/pattern data remain unchanged.

Validation: 63 unittest methods pass. MGSC/libkss checks of absolute versus
relative PSG/OPLL phrases have identical ordered register states. Full grider
has 1934 matching distinct register snapshots after grouping interrupt writes.
PCM and raw VGM bytes are not bit-identical: command processing can change
within-frame write timing. Do not claim sample-exact audio equivalence.

The reference grider MML ends in an infinite repeat without an explicit fade.
Its input VGM has no loop and ends at 121.948390 s, only 19 samples after the
last chip write. A visible WAV fade/release tail may come from export/playback
handling; the screenshot alone cannot establish its origin. No automatic fade
or inferred tail padding was added. Preserve captured data versus target
encoding/export choices as separate concerns.
