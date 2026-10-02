# Exact melody pattern candidates

With `--dump-passes`, PSG, SCC and OPLL emit three additional files:

- `<stem>.<chip>.melody.patterns.csv`: channel-local pattern definitions.
- `<stem>.<chip>.melody.occurrences.csv`: ordered uses and adjacent repeat counts.
- `<stem>.<chip>.melody.markings.csv`: one row per source Segment, referencing
  its occurrence, pattern, repetition and step. Source indices are zero-based
  within each channel and include zero-length events.

Original Segment values are unchanged; Segment CSVs append analysis columns. These are analysis
candidates; eligible candidates are projected as described below. No macros are generated. Rhythm analysis remains separate.

## Equality and reconstruction

Comparison uses duration, advance to the following Segment, event type and
chip state. Absolute timestamps and indices are retained as provenance but
excluded from equality. Pattern offsets are relative to the first Segment.
The final Segment's advance is its own duration. Zero-length events, explicit
rests, inter-event gaps and source order are preserved; nothing is merged.

OPLL compares key state, onset/legato and other articulation flags, Fnum,
block, instrument, attenuation and sustain. Instrument zero also compares
user-patch content at entry and patch writes inside the interval. Same-tick
patch selection follows the existing final-write policy. Without a patch
trace, unknown user patches cannot match across Segments. Channels 0..8 are
included; expanded rhythm channels 9..13 are excluded.

PSG compares tone, volume, octave/note, mixer/mode, noise and hardware envelope
state. SCC compares tone, volume, octave/note, enable state and waveform
content, rather than allocated waveform IDs. Shared-register fields are kept
conservatively even when another channel might explain their changes.
See `melody_patterns.FIELDS` for the complete equality fields.

The existing exact tandem-repeat search from rhythm analysis is reused.
At each position it chooses the adjacent repeat saving the most Segment
entries, preferring shorter units on ties. Unmatched entries become singleton
definitions; identical selected definitions reuse IDs within a channel.
This greedy analysis does not discover every possible phrase, search for
transpositions, infer beats, tolerate tick differences, or optimize globally.
Separated multi-Segment phrases without adjacent repetition are not searched
as macro candidates. Pattern IDs are deterministic for an unchanged input,
but are not persistent identities across edits.

For a unit, sum `advance_ticks` to obtain the repeat stride. Add each row's
`offset_ticks` to the occurrence start plus repetition index times stride;
add `duration_ticks` for the interval end. `markings` maps the reconstructed
rows to the original source evidence.

## Validation and next step

Tests cover all chips, timing and state differences, zero-length events,
channel isolation, unknown/changed user patches, CSV reconstruction, empty
input, invalid timing and source nonmutation. Fixture checks reconstruct
every compared state field and interval from definitions and occurrences.

Matching Segment rows do not establish that a target loop is safe: running
hardware envelopes, shared patch state, ties, oscillator phase and target
entry/exit state need separate treatment. The next stage should inspect the
candidates, then implement state-safe target loop projection with an
expanded-timeline equivalence check. Macro extraction remains optional.

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

## OPLL performed-note candidates (2026-10-01)

OPLL now has an additional performed-note layer in `opll_note_units.py`.
Continuous keyed intervals are grouped across pitch/volume register updates.
Observed rising edges, key-off transitions and timing gaps delimit units;
zero-duration key transitions still split them. Original Segments are retained.
This does not coalesce emitted notes or alter gate/tie behavior.

Candidate equality first uses note/rest kind and total duration. Replacement
also requires equal positive-duration source-state trajectories (FNUM/BLOCK,
volume, instrument/user patch and sustain) and identical expanded emitted
commands. Equal adjacent source states may be compared as one trajectory run.
Zero-duration state writes remain source members but do not enter the rendered
trajectory; their key transitions still define boundaries. Analysis flags are
not audible-state equality fields. No timing tolerance or pitch approximation
is added to the loop matcher.

The shorter of performed-note and existing Segment-based projections is chosen
per channel. Existing projections remain the fallback; neither source text nor
compiled capacity is guaranteed optimal after the separate macro stage.
`.performed.units.csv` and Segment `performed_unit_id` now identify complete
OPLL note/rest units with all constituent Segment indices. Loop reports retain
`candidate_status` separately from the final selection status, including
`different_state` when equal durations fail state validation. The same reason
is included in Segment `performed_loop_path`.

Measured compiled used bytes: sample 3489 -> 2963, sx01v 9189 -> 9125,
grider 12954 -> 13096. Expanded melodic commands/times match the pre-change
renderer in all three and Alest202. Alest202 remains unchanged and buffer-full;
gra2_001 still exceeds the JS compiler source-size limit. These are remaining
capacity problems, not resolved by this first note-unit layer.

Gra2_005 selected output: 12688 -> 12575 characters; MGSC used bytes 4806 -> 4794.
A weighted-only experiment used 4754 bytes but had longer text on some channels;
that experiment is not the production selection policy. Expanded command streams
and per-tick states of the selected output match the source-derived baseline.
No note timing, gesture boundaries, envelope selection or voice mapping changed.
Larger future gains likely require non-adjacent reusable phrases or a validated
compiled-byte cost model; do not claim current selection is byte-optimal.
