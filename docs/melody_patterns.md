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
