# PSG/SCC software-envelope selection

This documents concrete target behavior retained from the archived project
knowledge on 2026-10-05 and checked against the current implementation.
[Project principles](project_knowledge.md) govern source preservation.
The relevant modules are `py/mml_envelopes.py` and `py/pre_envelope_loops.py`.
OPLL hardware instrument envelopes do not use this software bank.

## Extracted target notes and curves

The renderer derives notes/rests from immutable PSG/SCC Segments and records
their contributing Segment indices. Contiguous sounding intervals may share
one note only while their settings match, volume does not rise, and no retained
pitch-write or PSG hardware-envelope-reset boundary intervenes. Volume rises,
pitch writes and relevant state changes remain boundaries; the algorithm does
not import attack positions or envelope lengths from reference MML.

An observed curve consists of `(volume, duration)` holds on the existing 60 Hz
analysis/target tick basis. Definitions use explicit hexadecimal levels and
hold counts (`level:count`), splitting counts above 255. Fitted interpolated
ramps are not assumed to reproduce the observed register values. These ticks
are not raw 44100 Hz VGM samples or musical score steps.

PSG hardware-envelope notes retain hardware operation rather than receiving a
software curve. Rest-only channels are not emitted; rest-time settings are
deferred until the next sounding note. Neither decision deletes source Segments.

## Shared bank and priority

PSG and SCC submit candidates to one bank before rendering. SCC must not consume
the entire bank merely because it is processed first.

The current bank reserves ID 0 for a constant full-level definition and allows
32 IDs in total. Only genuinely varying software curves are candidate entries;
a long constant hold alone does not deserve another slot. The implementation
also rejects a new definition whose encoded envelope data exceeds 220 characters.
These are current selection/representation bounds, not general chip laws.

The user's selection preference is longer observed varying curves first, for
MML compression. Current ordering is descending total duration, then descending
run count, with deterministic curve ordering on ties. Occurrence count affects
eligibility of very short curves: a single-use curve with fewer than three runs
does not get its own definition, though it can reuse a selected prefix match.
The policy is not a globally optimal byte-saving allocator. Estimated saved
commands and definition/reference overhead are useful future benefit checks;
they must not be reported as an implemented optimizer.

## Exact prefix sharing

A short note may use the observed prefix of an already selected longer varying
curve. Every observed tick of the short curve must equal the corresponding tick
of the longer curve. Matching only run labels, final volume, note length or an
approximate slope is insufficient.

No unseen tail is invented: the longer definition comes from another observed
curve, and sharing is checked only over the short note's observed extent.
Base-volume-offset families and inferred release parameters are not implemented.
The earlier reference-driven proposal for those families is not current behavior.

When no eligible definition/prefix exists, or capacity is exhausted, the note
uses explicit tied volume changes with the constant `@e0` definition. This
preserves the observed trajectory instead of silently flattening it.

## Structure before bank selection

The default path builds reversible source loop plans from complete interpreted
notes/rests, chip settings and volume runs **before** choosing envelope IDs.
Selection counts stored representatives of the chosen tree rather than every
expanded repetition. All original occurrences are still rendered with actual
running state; only equal target command iterations become physical loops.

`--legacy-loops` restores the earlier envelope-first path. Longer curves retain
priority in either case. Source candidates, projected brackets and envelope
usage are different concepts; their counts need not change together. See
[melody patterns](melody_patterns.md) and the
[order experiment](../field_notes/2026-10-03_psg_scc_pre_envelope_structure.md)
for mappings and measured limits.

## Inspection

With `--dump-passes`, the integrated `<stem>.<chip>.segments.csv` appends actual
selected `envelope_id` and `envelope_kind`, preserving original cells and row
order. The kind values and assignment coverage are defined in
[the Segment annotation section](melody_patterns.md#target-volume-envelope-ids-in-segment-csvs).
The IDs are real shared MML `@e` IDs, not a second analysis-only namespace.

The structural default's `<stem>.<chip>.pre_envelope_counts.csv` records observed
volume runs, expanded count, stored structural count and selected ID. The older
envelope-bank path's `.envelope_candidates.csv` records `definition`,
`exact_prefix` or `inline`, duration, occurrences and runs. These reports describe
different selection paths; do not assume both are always produced. Target note
CSVs retain rendered intervals/runs, and native pass/Segment dumps remain source
evidence.

Hardware-envelope period spelling and PSG/SCC detune are separate target issues;
see [the register-period review](../field_notes/2026-09-29_psg_scc_periods.md).
Frame-based software-envelope holds must not be scaled as musical steps when
[optional note normalization](note_normalization.md) changes the score clock.
