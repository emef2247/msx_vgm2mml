# VGM → MGSDRV MML / MS2

## Project Knowledge & Design Principles

This document records **stable project principles and durable domain
knowledge** for `emef2247/msx_vgm2mml`.

Keep this file small enough to read before changing conversion behavior.
Implementation history, measurements, fixture-specific results, rejected
experiments, and dated observations belong in `field_notes/` or focused
documents under `docs/`.

Not every statement is a formal specification. Distinguish:

-   confirmed facts / specifications
-   implementation decisions
-   measurements
-   hypotheses
-   unresolved questions

Do not silently promote a hypothesis, test expectation, or
fixture-specific observation into a project invariant.

------------------------------------------------------------------------

# 1. Project Goal

The project converts MSX-related VGM sound-chip data into human-readable
and editable musical representations, primarily MGSDRV MML and
MS2/MAmidiMemo compatible data. It also contains native analysis/target
paths for additional chips such as OPM/YM2151.

The goal is **not merely to produce output that sounds similar or passes
a regression test**. The project aims to preserve observable source-chip
behavior and make important transformations inspectable.

Conceptually:

``` text
VGM
 ↓
Raw Register Writes
 ↓
Reconstructed Chip State / Events
 ↓
Inspectable Analysis Passes
 ↓
Musical Segments
 ↓
Target Projection
 ↓
MGSDRV MML / MS2 / MDX / other targets
```

The implementation does not have to mirror this diagram one-to-one. Do
not refactor merely to make module boundaries match it.

------------------------------------------------------------------------

# 2. Primary Rule: Intermediate Results Are First-Class Artifacts

Generating inspectable intermediate results is a primary project
requirement, not merely a debugging aid.

A human should be able to determine, where relevant:

-   which source register event caused a musical event;
-   what chip state existed at that point;
-   where Key-On/Key-Off or trigger edges occurred;
-   which source pitch/volume/instrument/waveform values were present;
-   when an event became an interpreted Segment;
-   which information was changed or discarded by target projection.

CSV or equivalent pass output should favor human traceability over
compactness. Redundancy is acceptable when it makes an analyzed event
self-contained.

> Redundancy that improves traceability is acceptable.\
> Loss of source information for structural elegance is not.

Do not remove, merge, split, normalize, or reshape an intermediate
representation merely because doing so makes final output cleaner or
makes a regression test pass.

**Tests are evidence, not the objective.** If a test conflicts with the
information-preservation model, first determine whether the
implementation, the test expectation, or the target projection is wrong.

When an intermediate schema must change, explain the semantic reason and
what information is added, removed, or reinterpreted.

------------------------------------------------------------------------

# 3. Transformation Boundaries

Keep these responsibilities conceptually separate.

## 3.1 Raw Register Writes

Preserve what was written to the source chip, when it was written, and
ordering between writes. Avoid musical interpretation here.

## 3.2 Chip-Specific State / Events

Reconstruct the meaning of register writes using the native semantics of
the source chip.

Examples:

-   OPLL: FNUM, BLOCK, instrument, volume, Key state
-   PSG/SSG: tone period, mixer, noise, fixed/hardware envelope state
-   SCC: frequency, volume, waveform state
-   rhythm modes: trigger and per-instrument state
-   OPM: KC/KF, operator parameters, partial Key state and shared
    controls

Do not force different chips into a lowest-common-denominator state
schema.

## 3.3 Inspectable Analysis Passes

Analysis may progressively derive higher-level information. Later passes
may repeat earlier fields when this improves human inspection.

A pass is not disposable debug text.

## 3.4 Musical Segments

Segments represent interpreted musical objects or sounding intervals.
This is where concepts such as start/end, duration, retrigger,
continuity, note identity, waveform identity, or rhythm identity may be
derived.

A Segment is not a raw register event.

Do not invent information at the event/state stage that can only be
inferred during Segment construction.

Do not split or merge Segments solely to accommodate target notation,
compression, buffer limits, or a regression oracle. Such operations
belong to a later representation unless they reflect a justified change
in musical interpretation.

## 3.5 Target Projection

The target stage decides how interpreted information can be represented
in MGSDRV MML, MS2/MAmidiMemo, MDX MML, or future formats.

Target limitations and conveniences must not rewrite source history.

Information loss should occur as late as practical and should remain
inspectable.

------------------------------------------------------------------------

# 4. VGM Is a Register Event Stream, Not a Score

A VGM contains register writes and timing information, not conventional
musical notation.

Potentially meaningful information includes:

-   Key-On / Key-Off timing
-   F-number, BLOCK or tone-period changes
-   instrument and volume changes
-   mixer, noise and envelope state
-   SCC waveform changes
-   retrigger behavior
-   pitch changes and portamento-like behavior
-   register-write ordering
-   repeated writes that appear musically redundant

Do not aggressively merge or normalize events merely because they
eventually produce the same note.

A sparse-looking event stream may be correct. Preserve event sparsity
unless there is evidence that it is an artifact.

------------------------------------------------------------------------

# 5. Preserve Evidence and Derived Meaning Separately

Whenever practical, preserve both:

1.  the source-chip representation; and
2.  the physical or musical quantity derived from it.

For example, Yamaha FM pitch analysis may retain:

``` text
fnum
block
frequency_hz
```

For PSG, retain source tone period when deriving frequency. For SCC,
retain waveform data or a stable waveform identity. Derived values must
not silently replace source evidence.

Unknown or unwritten source state must remain unknown unless an
explicit, documented reset assumption applies. Do not fill absent fields
with invented values.

------------------------------------------------------------------------

# 6. Timing Is Source Evidence

VGM waits are source timing evidence. Preserve native timing before
target quantization.

The shared VGM source clock accumulates wait samples as integer samples
at 44100 Hz. Chips share the same stream origin; do not rebase each chip
at its first write.

Same-sample writes remain ordered. A physical sub-tick interval must not
disappear merely because a later 60 Hz or musical-grid projection rounds
it to zero.

A source timestamp, target tick, musical step, and playback-driver frame
are different concepts. Do not silently substitute one for another.

See `docs/vgm_timing.md` for implementation details and measured
limitations.

------------------------------------------------------------------------

# 7. Key Edges, Retrigger, Continuity, and Zero-Length Events

Retrigger and continuation are distinct.

Retain enough evidence to determine whether:

-   a note was newly triggered;
-   an existing sounding state continued;
-   pitch/state changed while the key remained active;
-   a new Segment is justified.

Do not equate zero target duration with an irrelevant source event.
Same-tick or zero-length events may contain real Key or rhythm edges.

For OPLL, distinguish an inferred musical `onset` from a real source
`key_on_edge`. Volume recovery or another inferred onset is not
permission to restart a hardware envelope.

Do not merge a real same-pitch Key-Off/Key-On sequence merely because
the resulting pitch is unchanged.

How a target represents an unrepresentable sub-tick event is a
target-stage decision; the source evidence must remain available.

------------------------------------------------------------------------

# 8. Chip-Specific Durable Semantics

## 8.1 OPLL / YM2413

Pitch uses FNUM and BLOCK; preserve both when available.

OPLL volume direction is inverted relative to conventional loudness:

``` text
VOL = 0   -> loudest
VOL = 15  -> quietest / near silence
```

Register writes need not arrive in convenient note-oriented order.
Reconstruct effective state without assuming all parameters precede
Key-On.

User-defined patch registers are meaningful source data. Do not silently
replace them with perceptually similar presets.

OPLL rhythm trigger edges and channel 6--8 pitch state should be
preserved before target projection.

The final MGSDRV layout may differ between melodic mode and rhythm mode,
but layout selection is a target concern and must not delete source
Segments.

## 8.2 PSG / SSG

PSG state is not "OPLL with different parameters." Preserve tone period,
tone/noise enable state, noise period, mixer state, fixed volume, and
hardware envelope state as required for interpretation.

Noise and hardware envelope behavior are musical source data. If the
target needs IDs, macros, or reconstructed commands, retain decoded
source state in an earlier pass.

## 8.3 SCC

Programmable waveform data is first-class source information.

Preserve waveform bytes or a stable identity, timing of waveform
changes, channel use, pitch, and volume where relevant. Exact equality
may be used for stable deduplication; stronger normalization requires
explicit justification.

## 8.4 OPM / YM2151

Native OPM analysis must preserve OPM semantics rather than invent
OPLL-like FNUM/BLOCK or preset voices.

Preserve four operator identities, KC/KF, partial Key edges,
channel/shared controls, same-time transitions, and unknown state where
appropriate. Parameter changes must not create artificial Key-Ons.

Detailed OPM state/target behavior belongs in `docs/opm_segments.md` and
`docs/opm_mdx.md`.

------------------------------------------------------------------------

# 9. Rhythm Semantic Layer

Where a common musical rhythm vocabulary is useful, use:

``` text
BD
SD
TOM
HH
CYM
RIM
```

This vocabulary describes musical meaning, not source implementation.
Source-specific terminology may still be retained in diagnostic/source
fields.

Rhythm event/state representations should preserve source trigger state,
timestamp, volume, source pitch fields and pan where applicable. Segment
construction may derive sounding intervals later.

Do not infer duration earlier than the available evidence justifies.

------------------------------------------------------------------------

# 10. Source Structure, Patterns, Envelopes, and Compression

Pattern detection and compression must operate without destroying the
information-preservation pipeline.

A repeated candidate is evidence of structural similarity, not automatic
permission to rewrite source Segments.

Prefer reversible structural plans and retain mappings from patterns,
occurrences, envelopes, or macros back to the original Segments/events.

Target loops/macros may be selected only when their expansion preserves
the required target command semantics.

Do not introduce new note boundaries, attacks, state resets, or
quantization merely to improve compression.

For software-envelope extraction, do not invent unobserved tails. Source
volume trajectories and attack/restart semantics remain authoritative.

Target output size and MGSDRV buffer limits are real constraints, but
solving them belongs at or near target projection. Shorter MML is not
evidence of a better conversion.

See `docs/melody_patterns.md` and focused field notes for current
algorithms and experimental results.

------------------------------------------------------------------------

# 11. Source Loops and Target Loops

Declared VGM loops are source structure and must be preserved without
inventing a Key-On at the loop boundary.

Structural loop candidates should remain reversible until target
selection. Overlapping or nested alternatives may be useful to later
macro selection.

Compiler acceptance, MML character count, compiled size, and
musical/source equivalence are separate validation dimensions. Success
in one does not prove the others.

See `docs/vgm_loop.md` for VGM loop details.

------------------------------------------------------------------------

# 12. Register-Oriented vs Grid/Normalized Projection

The project contains intentionally different transformation paths.

`vgm2mml.py` is register-oriented: source timing and event semantics
have priority over visually regular notation.

`vgm2mml_grid.py` intentionally maps events onto a musical grid.

Optional normalization such as `--normalize-lengths` is a target-stage
inference. It must not rewrite native source timestamps or Segment
evidence.

Keep the distinction explicit:

``` text
source-faithful interpretation != intentional quantization/normalization
```

Tempo/grid inference is interpretation, not source fact. Preserve
original timestamps and make inferred parameters inspectable.

------------------------------------------------------------------------

# 13. Target Formats Are Not Canonical Internal Representations

MGSDRV MML, MS2/MAmidiMemo, MDX MML, and future targets have different
constraints.

Target-specific choices may include:

-   duration quantization/encoding
-   instrument commands
-   noise/envelope commands
-   waveform definitions
-   rhythm commands
-   ties, rests and gates
-   loops/macros
-   channel/buffer allocation
-   target-specific timing

Do not shape source/state/Segment data solely around one target's
syntax.

A target may intentionally approximate or discard information it cannot
represent. When it does:

1.  preserve the source information in an earlier inspectable stage;
2.  document or report the approximation where useful;
3.  perform the loss in target projection;
4.  do not alter earlier representations to pretend the source lacked
    it.

MGSDRV syntax references:

-   `https://p.gigamix.jp/mgsdrv/MGSDR320.TXT`
-   `https://z80.msx.click/index.php?title=MGSDRV_MML_11_JP`

------------------------------------------------------------------------

# 14. Validation: Correctness Has Multiple Meanings

Keep these objectives separate:

**Register correctness**\
Reconstruct source-chip state and behavior accurately.

**Musical correctness**\
Represent the intended performance usefully.

**Target correctness**\
Produce valid target data within target constraints.

Also distinguish audible similarity, source behavioral equivalence,
target command equivalence, and textual/compiled-size optimization.

A final MML file, successful compilation, matching event count, or
passing test suite is not sufficient by itself to prove conversion
correctness.

For non-trivial behavior changes, inspect the relevant intermediate
results before and after the change and validate more than one
representative piece where practical.

Real/reference playback, emulator behavior, compiler roundtrips,
hardware observations, code inspection, and subjective listening are
different kinds of evidence. Record which kind supports a conclusion.

Do not overfit a general rule to one song or fixture.

------------------------------------------------------------------------

# 15. Tests and Fixtures

Fixtures should make specific behaviors reproducible and, where
practical, cover the relevant layers:

``` text
source VGM
raw/state trace
analysis pass
Segments
target output
```

Do not blindly update expected artifacts when a regression test fails.

First determine whether:

1.  the implementation violated source semantics;
2.  the interpretation/Segment logic is wrong;
3.  the target projection is wrong;
4.  the test expectation encodes obsolete or incorrect behavior.

**Never change an intermediate representation solely to satisfy an
expected artifact.**

A fixture is an oracle only for the behavior it was designed and
justified to test.

Private copyrighted source material must not be copied into tracked
documentation or fixtures unless explicitly safe to commit.

------------------------------------------------------------------------

# 16. Human-Readable Intermediate Output

Intermediate output should favor diagnosis over compactness.

Use explicit names with stable semantics. Prefer `frequency_hz` for a
physical frequency and retain source representations such as `fnum`,
`block`, or `tone_period`.

Do not fill non-applicable fields with misleading values. Use empty/null
values or chip-specific schemas.

Preserve enough timestamps, channel/source indices, pattern/occurrence
IDs, and other identifiers to trace target behavior back toward source
evidence.

PASS files generated by `--dump-passes` are part of the project's
diagnostic contract, not arbitrary temporary dumps.

------------------------------------------------------------------------

# 17. Development Workflow

For a non-trivial conversion change:

``` text
1. Inspect the existing implementation.
2. Identify the conceptual stage that owns the problem.
3. Inspect representative source/intermediate evidence.
4. Explain current behavior.
5. Form a hypothesis.
6. Design the smallest useful experiment or test.
7. Implement the smallest justified change.
8. Run regression tests.
9. Inspect intermediate results again.
10. Validate target output.
11. Record durable knowledge in the appropriate place.
```

Do not jump from a failing final artifact directly to reshaping Segments
or earlier passes.

Before changing established behavior, identify why it exists.

------------------------------------------------------------------------

# 18. Documentation Placement

Keep documentation layered so the highest-priority rules remain visible.

## `AGENTS.md`

Only short, always-on operating rules and repository navigation.

## `docs/project_knowledge.md`

Only stable architectural principles and durable chip/domain knowledge
that should guide future work.

## Focused `docs/*.md`

Current design and usage of substantial subsystems, for example timing,
loops, patterns, OPLL rhythm, OPM Segments, or target formats.

## `field_notes/*.md`

Dated experiments, measurements, fixture-specific findings, regressions,
benchmarks, rejected approaches, and provisional conclusions.

A finding may move from a field note into this file only after it
becomes a stable project principle or durable domain rule.

Do not append implementation history to this document merely because it
may be useful later.

------------------------------------------------------------------------

# 19. Final Rule

When uncertain whether to simplify, merge, split, normalize, quantize,
discard, or reinterpret data:

1.  preserve the source evidence;
2.  expose it in an inspectable intermediate result;
3.  make the interpretation explicit;
4.  defer irreversible loss until the target stage;
5.  ask whether a human can still trace the final result back toward the
    VGM.

If the answer to step 5 becomes "no", the change requires strong
justification.

The central design question is not:

> "How can we make this conversion simpler or make this test pass?"

It is:

> "What information is being changed or lost here, at which
> transformation stage, and is that loss intentional?"

A final target file is not sufficient evidence that the conversion is
correct. The path from source register stream to target must remain
inspectable.
