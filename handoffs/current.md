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

## Latest: exact melody pattern analysis

Added melody_patterns.py and per-chip pattern/occurrence/marking CSVs under
--dump-passes for PSG, SCC and OPLL. Reuses exact adjacent-repeat search; source
Segments and MML remain unchanged. Added six tests covering state/timing keys,
patch changes, zero-length rows, CSV reconstruction and nonmutation.

Local checks: grider OPLL has 50 repeated occurrences (39 multi-Segment),
PSG/SCC test001 has 202 PSG and 32 SCC repeated occurrences. All compared
state fields and intervals reconstruct from the emitted CSVs. grider final
MML is byte-identical to the pre-analysis output. No private fixture content
was added to tracked files. No staging or commit by the agent.

Next: inspect candidate grouping before implementing state-safe target loops.
Do not apply naive textual loops to relative commands or assume matching
Segment states prove envelope/shared-state equivalence. Macros are optional.

Validation completed: all 69 unittest methods passed.

## Pattern metadata in Segment CSVs

The main --dump-passes pipeline appends segment_index, pattern_id,
occurrence_id, repeat_index, pattern_step, pattern_segments and pattern_repeats
to each chip's existing segments.csv. Original cells and row order are preserved;
in-memory Segments remain unchanged. IDs are local to each chip/channel and
all indices are zero-based. pattern_segments is the unit size; pattern_repeats
is the number of consecutive repetitions in the occurrence. Filter
pattern_repeats > 1 to inspect adjacent repeats alongside pitch/volume/state.
Unmatched singleton candidates still have IDs with pattern_repeats = 1.
OPLL rhythm rows (channels 9..13) have blank melody-pattern columns.
The separate analysis CSVs remain available for definition-level inspection.

Validation: seven melody-pattern tests pass, including original-cell retention,
channel-local indices, zero-length rows, blank rhythm metadata and idempotence.

## Target volume-envelope IDs in Segment CSVs

PSG/SCC rendering appends envelope_id and envelope_kind to segments.csv when
--dump-passes is enabled. IDs are the actual shared MML @e IDs, not separately
allocated analysis IDs. Every positive-length source Segment contributing to
an extracted note receives that note's selection, including merged volume runs.

Kinds: software = extracted @e curve; constant = constant-volume @e0;
inline = tied explicit volume changes using @e0 (including bank-limit fallback);
hardware = PSG hardware envelope, no software ID; rest = no assignment;
zero_length = an event without its own rendered interval, no assignment.
Silent channels retain blank IDs. Pattern columns and all source cells are
preserved. Internal Segments, MML and the existing target_notes CSV are unchanged.
OPLL hardware instrument envelopes are not part of this PSG/SCC software bank.

Eight envelope tests passed, covering merged rows, bank overflow, hardware,
silent channels, zero-length rows, cell preservation and repeatable annotation.
The public PSG/SCC 001 fixture retains identical final MML and existing CSV
cells, including pattern metadata.

## MML loop projection

Final PSG/SCC/OPLL melody renderers now project Segment-derived candidates
through melody_loops.py. No MML string-pattern discovery is performed: candidate
positions and unit lengths come from melody_patterns.analyze. Every iteration
boundary must coincide with a complete rendered note boundary. Candidates that
cut an extracted envelope note are retained as ordinary MML.

Within a candidate, only consecutive units with exactly identical emitted
command sequences are replaced by finite loops, and only when text is shorter.
An initial iteration with different initialization is retained. This preserves
the expanded command stream exactly, including relative octave/volume commands,
envelope selections and tied continuations. Loop counts are split at 255.
No additional state resets, quantization, macros or new note boundaries are
introduced. This conservative first implementation leaves many candidates
uncompressed. Sync annotation can expand loops crossing a synchronization mark.

With --dump-passes, inspect `.melody.before.target.mml`,
`.melody.after.target.mml` and `.melody.loops.csv`. The report references ch,
pattern_id and occurrence_id and gives candidate/looped repetition counts and
an applied/skip status. Existing Segment annotations keep their candidate IDs.
The dump files are per-chip intermediates, before final merge/sync formatting.

Validation includes exact expanded-command equivalence, distinct first entry,
relative changes, envelope/tie boundary rejection, large repeat counts and
unmatched material. In normal mode, grider final MML changes from 32660 to
32438 characters; public PSG/SCC 001 changes from 8330 to 7834 characters.
Both grider versions compile with MGSC 1.11; regenerated VGM has the same
1934 ordered distinct interrupt-grouped register snapshots. This is not a
claim of sample-exact audio or optimal compression. Its padded MGS file size
remains 11264 bytes, so text reduction is not a binary-size guarantee.

Validation update: full discovery ran 77 tests; only the line-by-line sync test
helper failed on multiline loops. It now parses complete prefixes between marks
and checks final duration. All 11 sync tests pass on rerun; five new loop tests
pass. Twelve normal/raw chip projections have identical expanded timelines.

## gra2_005 compression investigation (2026-09-29)

No production conversion changes in this investigation. Baseline compiles;
track 3 is the largest byte consumer. SCC fills the shared 32-envelope bank
before PSG. Complete-note loop experiments preserve expanded commands but
only reduce total used bytes 7859 -> 7404; a few tracks grow in compiled size.
Next design: attack groups -> safe loop boundaries -> envelope extraction ->
global bank allocation -> final loops. Do not force every raw Segment repeat
boundary into an envelope break. See field_notes/2026-09-29_gra2_compression.md.

## User direction: musical structure and long envelopes (2026-09-29)

Use the supplied reference MML and ROM-analysis commentary as an evaluation
oracle for intended musical structure, not merely a source of arbitrary repeated
register patterns. Distinguish percussion gestures, repeated note/rest motifs,
nested phrases, reusable subroutines and outer song loops. Do not paste private
musical content into tracked documentation or hard-code a fixture's phrases.

The reference reuses envelope definitions across different note lengths and
base volumes. Matching entire observed volume-run tuples is too restrictive:
short notes can be observed prefixes of a longer shared envelope. Detect attack
boundaries and preserve envelope restart/continuation semantics before comparing
phrases. A mode-changing percussion gesture must not be absorbed into a volume
curve alone. Reference annotations inform validation; VGM observations remain
primary input. Do not invent an unobserved envelope tail.

The user prefers longer envelopes when the shared bank is limited, for MML size
reduction. Prioritize longer genuinely varying volume trajectories; inspect
saved explicit volume commands and definition/reference overhead as a benefit
check and tie-breaker. A long constant hold alone must not consume a new slot.
Evaluate the shared PSG/SCC candidate bank together, not SCC first. Do not
replace this preference with frequency-only ranking of expanded loop copies.

Next implementation target: recover representative long PSG envelope behavior,
reuse compatible observed prefixes/base-level variants with exact target
semantics, then match note/rest motifs and nested phrases using those envelope
identities. Keep Segment, note/envelope, pattern and occurrence mappings visible.

## SCC driver book review (2026-09-29)

Reviewed the user-provided book photographs; findings and page/photo index are
in [scc_driver_analysis.md](local_only/scc_driver_analysis.md). No converter changes.
Macro playback may truncate or pad with rests according to requested duration.
Gradius2 envelopes have phase-dependent release checks: shared prefixes alone
are insufficient to establish compatible envelopes across note lengths.
This qualifies the prefix-sharing proposal above. Next: validate complete
observed trajectories, release and restart semantics before implementing reuse.
Keep inferred musical structure separate from facts observed in VGM; do not
transcribe or commit the private source photos or musical listings.

## Generic shared envelope selection (2026-09-29)

The main pipeline now collects both PSG/SCC candidates before assigning the
shared 32 slots. Longer varying observed curves rank first, independently of
chip processing order or expanded occurrence frequency. Exact observed prefixes
can reuse a selected definition: every tick, including any release portion,
must agree. No Konami commands, fixture names or inferred envelope tails are
used. Existing Segment envelope IDs identify the actual shared definition.

Gra2_005: 19551 -> 14870 MML characters; MGSC 1.11 used bytes 7859 -> 5286.
All six rendered tracks match Segment pitch/volume/mode/wave state per tick.
Public mixed-envelope fixtures pass in standard and raw modes. This is not
sample-exact audio verification. Envelope extraction boundaries are unchanged.
Further work: gesture-aware percussion grouping and nested note-level phrases;
base-volume normalization and parametric envelope inference remain unimplemented.

## CLI metadata and default artifacts (2026-09-29)

Merged metadata name now defaults to the input stem. --name and --title override
name/title independently; --tile aliases --title. Output filenames remain unchanged.
Normal cleanup now covers all three chip pipelines, including absent chips, whose
empty legacy compress variants previously leaked into the output directory.
Debug and pass-dump modes remain available. No music conversion behavior changed.

## Performed units and nested loops (2026-09-29)

`performed_patterns.py` adds a source-derived performed-unit layer without
changing note boundaries or envelope extraction. PSG/SCC units start from complete
extracted notes/rests. A PSG sounding interval followed by a rest, containing noise,
is conservatively grouped with its trailing rest as a `percussion_candidate`.
Mode, noise period, tone period, volume trajectory and hardware-envelope settings
remain in its constituent signatures. This is an inferred coarse gesture, not a
recovered original drum macro. Uninterrupted or ambiguously separated hits are
not split by a new heuristic. Duration variants are not merged or truncated.

The hierarchy detects exact adjacent repeats of these units, then searches each
repeated phrase for inner repeats. OPLL melody uses its existing complete Segment
notes and patch-aware signatures. Source timing, envelope and patch differences
prevent candidate equality. The greedy search is not an optimal grammar recovery.
There are at most two emitted loop levels and 255 repetitions per loop command.
Only equal emitted command iterations are looped; different initialization stays
outside. Ties and complete envelope notes remain inside one unit. The result
expands to exactly the original commands, including relative state changes.
The smaller textual result of legacy and performed-unit projection is selected
per channel. Text savings do not guarantee smaller compiled bytes per channel.

With `--dump-passes`, `.performed.units.csv` retains constituent Segment indices,
relative signatures and hierarchy paths. `.performed.loops.csv` records channel,
pattern/occurrence/parent IDs, depth, unit range, repeat count and application status.
IDs are local to the channel and this analysis, distinct from raw Segment pattern
IDs. Segment CSVs append `performed_unit_id`, `performed_unit_kind`, and JSON
`performed_loop_path`; existing source, pattern and envelope columns are retained.
Zero-length source rows not contributing to a rendered note have blank unit IDs.
Nested occurrence records describe source occurrences, including copies represented
by one loop body. `legacy_projection_selected` means this hierarchy was not emitted.
Existing before/after target MML dumps show the actual selected projection.

Validation: synthetic nested phrases, differing initialization, counts above 255,
tied notes, release differences, noise/mode trajectories and source-cell preservation.
Gra2_005 expanded commands and all six per-tick state timelines match; MGSC 1.11
compiles it with 4806 used bytes (previous shared-envelope output: 5286).
No book-specific commands, source addresses or fixture-specific phrases are used.
Further work includes continuous-drum onset inference, duration-variant gesture
families, non-adjacent macros and compiled-size-aware selection.

Validation completion: all 84 tests passed. Gra2_005 normal/raw expanded commands
and per-tick states match; grider's six OPLL melody command streams match and
MGSC compiles the final output. Legacy report statuses explicitly indicate when
the performed projection was selected. No staging or commit was performed.

## Cost-aware repeat placement (2026-09-29)

The performed-unit compressor now compares its original greedy hierarchy with
an alternative dynamic-programming placement of non-overlapping repeats. The
alternative considers emitted command length, overlapping starts and shorter
repeat counts, while still requiring identical source-unit signatures and exact
command iterations. Initialization differences can stay outside a repeat.
Both strategies recursively search inner repeats; maximum depth/count limits
remain two/255. The shorter textual projection wins, with greedy winning ties.
The performed loop report records `strategy` (`unit_count` or `text_cost`).
This is a text-cost optimization, not an exact model of MGSDRV compiled size.

Gra2_005 selected output: 12688 -> 12575 characters; MGSC used bytes 4806 -> 4794.
A weighted-only experiment used 4754 bytes but had longer text on some channels;
that experiment is not the production selection policy. Expanded command streams
and per-tick states of the selected output match the source-derived baseline.
No note timing, gesture boundaries, envelope selection or voice mapping changed.
Larger future gains likely require non-adjacent reusable phrases or a validated
compiled-byte cost model; do not claim current selection is byte-optimal.

Cost-placement validation: full suite of 84 tests passed; the added cost-selection
invariant test and all six performed-pattern tests subsequently passed. Gra2_005
normal/raw expanded commands and per-tick states match. MGSC 1.11 compiles the
normal output with 4794 used bytes. Output: outputs/gra2_weighted/gra2_005.mml.

## Non-adjacent macro investigation and gra2_003

See field_notes/2026-09-29_macro_compression.md. Added optional local regression
checks for gra2_003 and gra2_005; both pass expanded-command and per-tick state
comparisons. No automatic macro emission or default sync/allocation change.
Macro experiments reduce text but leave real-fixture compiled sizes unchanged.
Gra2_003 requires 26951 track bytes at default sync spacing (plus 886 definitions).
Keeping only start/end sync experimentally reduces tracks to 21603, still above
15000. Prioritize loop-aware sync placement and measured byte cost over assuming
macros are runtime compression. Generated source also exceeds the local mgsc-js
49152-byte source limit before whitespace/comment compaction.

## Loop-preserving synchronization (2026-09-29)

Shared sync candidates now require top-level token boundaries in every active
track, intersected with existing tie-safe leaf boundaries. Entire loops (including
all iterations and nested loops) and macro calls remain intact. No annotation-time
expansion is performed. Applies to PSG, SCC, OPLL melody and OPLL rhythm through
the common final formatter. min_gap remains a minimum, not a forced interval;
zero selects all safe common boundaries, and start/end remain mandatory.
Ended tracks do not constrain later marks. Physical-line wrapping is unchanged.

Gra2_005 MGSC 1.11 total used bytes: 4794 -> 3848, compilation succeeds.
Gra2_003 isolated track sum: 26951 -> 21603, plus 886 definition bytes. It still
exceeds the 15000 track budget; do not claim the complete song now compiles.
Gra2_003 output text is 46960 characters, below the tested wrapper source limit.
Expanded command and per-tick comparisons remain required alongside loop retention.

## PSG/SCC sound reproduction correction

Main target output now treats hardware-envelope m as a raw register period,
using direct y11/y12 writes for zero. Explicit PSG/SCC tuning plus signed detune
preserves observed tone periods within MGSDRV's -127..127 detune range.
Out-of-range cases warn and are marked in target_notes.csv. See
field_notes/2026-09-29_psg_scc_periods.md for independent MGSC/libkss evidence.
Source Segments and legacy debug renderer baselines remain unchanged. Old
pitch-name-only comparisons were insufficient to verify actual output frequency.
# Pitch roundtrip verifier

Reference-note audit now available in scripts/check_reference_pitch.py.
gra2_002: all 310 pitch changes match on all 8 tracks. gra2_008 two iterations:
1391 reference pitch changes match, one extra PSG ch3 observed change (889,
tick1940, CSV line5320) remains unexplained. Formula for both PSG/SCC is
(reference tuning[note] >> (octave-1)) - signed detune. No extra SCC -1.
Four synthetic parser/projection checks pass. No converter tuning change made.

Added scripts/verify_pitch_roundtrip.py, scripts/mml_to_vgm.mjs and
py/roundtrip_pitch.py. Existing reference Segment CSVs remain untouched.
Six synthetic comparator checks pass. gra2_002 completes full MGSC/libkss
roundtrip but zero-offset comparison has differences; onset timing must be
separated from period errors before diagnosing the tuning formula.
See docs/pitch_roundtrip.md for commands, scope and dependency versions.
User suggests deriving a pitch table from original MML and reference CSV.
gra2_002 and gra2_008 original MML already declare a custom #psg_tune table;
validate that mapping first. Do not force a game-specific table on all VGM.
# Automatic target macros (2026-09-30)

py/mml_macros.py is applied after sync formatting in normal target output.
PSG/SCC/OPLL melody participate, ranked by source-character savings. Rhythm
is excluded pending rhythm-aware shared macro parsing. No sync boundary is
crossed; balanced loops and ties are preserved; no recursive definitions.
Allocation stays based on pre-macro text, since macro calls do not save binary
track bytes. GRA2_08 reallocated fixture shrinks 28600 -> 16600 characters;
expanded tokens/timing match. New tests cover melodic chips, loops and ties.
# OPLL rhythm macro completion (2026-09-30)

GF2SMS03 startup fix: rhythm_mml target projection coalesces identical same-time
HH retriggers when the first interval is zero, with a warning. Source CSVs stay
unchanged. Distinct sub-tick collisions remain errors. Reproduction now generates
MML; eight rhythm renderer tests pass including duration/state discrimination.

tests/test_rhythm_pipeline.py now includes optional local grider, using the same
attack/volume/duration checks as the public fixtures; missing input skips only
the local test. No private fixture is added to version control.

Rhythm now participates in automatic macros in its own grammar pool. Existing
Segment exact-repeat grouping/loop projection remains unchanged. mml_sync parses
macro definitions at call time with the calling track's grammar. Added public
pipeline checks for rhythm_only_test01..03 and sample, plus synthetic rhythm
macro/sync equivalence coverage. Sample emits rhythm macros containing existing
loops. Short fixtures need not produce macros when there is no text benefit.
## Zero-length event discussion recorded

See field_notes/2026-09-30_opll_zero_length_events.md before extending the
GF2SMS03 target workaround. Future normalization should separate final tick
state from trigger history. No broad l=0 merge/refactor was implemented in
this documentation update; hardware/emulator audibility remains unverified.
## Local catalog and batch MGS (2026-10-01)

Batch now prefers native mgsc from PATH, supports --mgsc, and uses positional
input/output arguments. JS fallback remains for environments without native
MGSC. Compilation success also requires nonempty output; failure logs are
printed. This Windows session could not launch WSL (E_ACCESSDENIED), so the
user-requested complete native run remains unverified here.

User outputs/mgs compilation failures included ERR_MODULE_NOT_FOUND for mgsc-js,
before MGSC ran. Batch now preflights module loading/initialization before any
conversion and reports setup separately. msxplay's public UI delegates directly
to MGSC.compile, as does our helper. Do not diagnose these old reports as MML
syntax or buffer errors. Tests cover setup failure and continuing genuine errors.

Validation: 56 requested VGMs convert after the fix. Initial regression run had
55 passes and WBIII12 failure before the mid-song one-sample extension; WBIII12
then passed on rerun. Batch MGSC result: 52 successes, four track-buffer failures
(Alest202, Alest204, Alest208, Alest214), intentionally not repaired. Logs and
reports are in outputs/local_mgs_check/. Batch continuation/stale-output test
and nine rhythm renderer tests pass.

Added 56 optional local conversion regressions and scripts/batch_vgm_to_mgs.py
with an MGSC JS helper; see docs/batch_mgs.md. Buffer failures are reported, not
repaired. WBIII08/12 identical startup rhythm collisions are one VGM sample apart:
target coalescing now also permits gaps up to 1/44100 second within one tick,
with equal state and zero preceding interval. Warn and retain all source CSVs;
do not generalize this to arbitrary sub-tick collisions.
## GD3 automatic titles (2026-10-01)

System now uses English only; System and the single release-date field normalize
full-width ASCII. Track/game/author retain per-field language fallback. User
confirmed Alest202 Object too big disappears with a shorter explicit title;
the 240-byte title-line safeguard does not guarantee the whole MGS fits.

py/gd3.py reads bounded UTF-16LE GD3 v1.00 fields. Main CLI uses metadata only
when --title is absent, with --gd3-language ja/en and per-field fallback.
Automatic titles have syntax sanitization and a conservative 240-byte CP932
budget. MGS text field is variable-length; MGSC physical lines are a separate
constraint. Three unit tests pass and Alest201 Japanese output compiles using
MGSC-js 2.0.0. Explicit titles and event interpretation are unchanged.
## Manual allocation override

vgm2mml.py now accepts --alloc with comma-separated channel=bytes entries.
Only specified tracks override final automatic #alloc; no redistribution or
total-budget clipping. Batch forwards the same value to each conversion.
tests/test_mml_alloc.py checks partial/full replacement and invalid input.


## Latest fix (2026-10-01)

Quantized duplicate rhythm hits no longer stop target MML generation: the
last zero-duration same-instrument hit per tick wins. Source Segments remain
unchanged; --dump-passes adds *.opll.rhythm.collisions.csv. See
docs/opll_rhythm.md for the approximation and retained evidence.
Added all 16 reported fixtures to optional local OPLL conversion regressions.
VGM header loop work remains paused; do not resume it as part of this fix.

Validation: all 16 requested conversions and final rhythm attack/volume comparisons
passed; 25 rhythm tests passed. test_conversion_regression.py could not import
fixture_helpers in this checkout. MGSC compilation/playback was not checked.

Restored the test-only SCC clock helper as tests/vgm_test_support.py so it
does not compete with tests/fixtures in shell completion. Updated its import
and excluded the new collision diagnostic CSV from legacy artifact hashes.


## OPLL continuous notes and source retriggers (2026-10-01)

Target rendering now carries zero-duration onset markers to the next timed
interval, slurs continuous intervals and uses q0 when a following pitch/state
interval must keep key-on. Restore q8 for a genuine note end. MGSC 1.11/libkss
roundtrip showed & alone still reattacked on pitch changes; q0 retained key-on.
Do not merge same-pitch key-off/on source events: the old PASS3 retrigger merge
removed real attacks and has been bypassed in Segment construction.

YsSMS01 source/export/fixed key-on counts for channels 0..4:
110/2507/110, 28/19/27, 158/139/158, 152/167/152, 111/110/111.
The remaining ch1 count is a source onset at tick 5951 with zero duration at
EOF, which has no timed target note. Source pitch modulation still rounds to
MGSDRV note names; this change does not promise sample-exact reproduction.
Use scripts/check_opll_key_edges.py reference.vgm actual.vgm --outdir <dir>
for separate traces, Segment dumps, key_edges.csv and count summary. Counts
alone are not timing equivalence; CSV retains explicit times with no alignment.
Generated checks are under outputs/ys_retrigger_check; no private data is tracked.

Validation: 9 OPLL target tests and 25 rhythm tests pass; MGSC 1.11/libkss
compiled/rendered YsSMS01 successfully. Paired 558 timed onsets; raw tick
offsets range 2..7 across playback, not sample-exact alignment. Regenerate
outputs/ys_retrigger_check/fixed/YsSMS01.mml for user listening.

Alest202 evaluated per isolated track due to 20770-byte compiled track total.
ch0/ch1 attack counts match; ch2/ch3 differ by terminal zero-duration edges;
ch4 count equality hides one extra short retrigger and terminal-edge omission.
See field_notes/2026-10-01_alest202_retrigger_check.md. Conversion code unchanged
during this evaluation; volume-15 recovery versus true key edges remains to inspect.

Pre-fix Alest202 export comparison confirms excessive melodic retriggers:
887/2876/1169/1914/3425 versus source 164/163/398/515/515. Attached MML
compiles with 14834 track bytes, whereas fixed isolated tracks total 20770.
No additional conversion change during comparison; see Alest202 field note.


## Current state: coalescing withdrawn (2026-10-01)

Removed projected same-note coalescing after the user reported missing opening
guitar in Alest202. Keep YsSMS01 slur/q0 retrigger fixes and source key-edge
preservation. The user will compare YsSMS01 with its original VGM. Do not
continue compression experiments now. Existing coalesced artifacts are failed
experimental output and must not be recommended for playback or used as goldens.
Opening guitar loss remains unexplained; raw key counts do not prove sound.

Read-only follow-up reviewed duplicate_write_opl3 and vgm-conv's YM2413-to-OPL
converter. Conditional A/B ordering, optional waits and key-dependent RR mapping
are recorded in field_notes/2026-10-01_opll_key_and_envelope.md. Neither reviewed
path proves forced off/on for repeated key-high writes. No conversion behavior
changed; do not infer that this review resolves the weak-sound report.

Onset audit correction: preserve legacy onset, add independent key_on_edge;
target retriggers and continuation gates now use only observed key edges.
OPLL Segments preserve apparently silent rows instead of folding away keys or
register states. Keyed vol=15 intervals emit v0 notes rather than rests.
No coalescing/compression experiment restored. YsSMS01 roundtrips with the
same attack counts; Alest202 checked per isolated track because full capacity
is still exceeded. See outputs/opll_onset_review and the OPLL field note.
Do not claim that these checks resolve the reported lighter/missing sound.

The user accepts the current changes and reports a substantial retrigger
improvement. End audio investigation here. Relevant checks pass after a small
test-only macro-body API correction in test_mml_sync.py; MGSC/libkss roundtrip
checks are complete. Changes remain uncommitted for the user's review/commit.

Evaluation scope agreed with the user: key-on counts only. No timing,
frequency, volume metrics or combined score. check_opll_key_edges.py now emits
keyon_totals.csv and accepts --pairs for existing reference/exported VGM pairs.
missing_keyon/extra_keyon mean summed per-channel count shortages/excesses;
they are not time-matched event identities. Rhythm attacks are excluded.
Four count tests pass. Checked YsSMS01 current export (559/558, shortage 1)
and Alest202 PREVIOUS msxplay export (1755/10271, excess 8516). Do not label
the latter as the current corrected conversion. Sources/exports are untouched;
the tool does not compile or export MGS. See docs/opll_keyon_counts.md.

## 2026-10-01: declared VGM loop metadata
- Added read-only loop boundary inspection and optional .vgm.loop.csv dumps.
- Source samples and legacy wait-clock time remain separate; no KEYON/reset or MML loop emission.
- Seven synthetic tests cover boundaries, payloads, legacy waits and unchanged traces.
- Segment annotations and MML loop notation remain the next stage.
- User regression completed; loop metadata and compressed input fixes are ready for integration.
- Added gzip-signature input detection shared by trace decoding and GD3. VGM <1.50 / zero data-offset headers start at 0x40. Invalid headers/offsets fail explicitly.
- All 42 PS1FM/FFMSX fixtures now produce OPLL register traces; representative MML conversions succeeded.
- Regression conversion_failed entries are deleted duplicate RType fixtures, per user; do not treat them as decoder failures.
