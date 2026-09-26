# VGM → MGSDRV MML / MS2

## Project Knowledge & Design Context

### Initial Draft for Codex

> This document records project-specific knowledge, design intentions,
> experimental findings, and unresolved questions for
> `emef2247/msx_vgm2mml`.
>
> Not every statement in this document is a formal specification.
> Distinguish between:
>
> -   confirmed facts / specifications
> -   measurements
> -   implementation decisions
> -   hypotheses
> -   unresolved questions
>
> Do not silently turn hypotheses into specifications.

------------------------------------------------------------------------

# 1. Project Overview

The project converts MSX-related VGM sound-chip data into human-readable
and editable musical representations, primarily MGSDRV MML and
MS2/MAmidiMemo-compatible data.

The currently relevant source chip families include:

-   PSG / SSG
-   YM2413 / OPLL
-   SCC
-   OPLL rhythm mode

The project may grow to support additional Yamaha or MSX-related
sound-chip families. Such extensions must preserve the architectural
principles in this document.

The broader goal is not merely to produce output that "sounds similar".
The project aims to preserve as much of the musical behavior and
source-chip information encoded in the original VGM as practical while
still producing useful target representations.

The conceptual processing pipeline is:

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
Target Representation
 ↓
MGSDRV MML / MS2 / other targets
```

The exact implementation does not have to map one-to-one onto these
conceptual stages.

Do not perform a large refactor merely to make the file/module structure
match this diagram.

The intermediate representations are a primary part of the project, not
disposable implementation details.

------------------------------------------------------------------------

# 2. Primary Project Requirement: Preserve Inspectable Intermediate Results

Generating inspectable intermediate results is a primary project
requirement, not merely a debugging aid.

For non-trivial conversions, the project should make it possible to
inspect how the source VGM was interpreted before the final MML/MS2
output was produced.

Intermediate CSV or equivalent outputs should be treated as first-class
artifacts.

They exist so that a human can answer questions such as:

-   What register event caused this musical event?
-   What was the reconstructed chip state at this time?
-   Where was a Key-On or Key-Off detected?
-   What FNUM/BLOCK or tone period produced this frequency?
-   What volume value was present in the source?
-   Was this event retriggered or continued?
-   At which analysis pass did an event become a note/segment?
-   Which information was discarded when projecting to the target
    format?

Do not remove intermediate outputs merely because the final MML appears
correct.

Do not optimize intermediate representations for database-like
normalization.

Redundancy is acceptable when it improves human traceability.

> Redundancy that improves traceability is acceptable.
>
> Loss of source information for structural elegance is not.

------------------------------------------------------------------------

# 3. VGM Is a Register Event Stream, Not a Score

A VGM contains register writes and timing information.

It does not directly contain conventional musical notation.

Important information may exist in:

-   Key-On / Key-Off timing
-   F-number changes
-   BLOCK changes
-   tone-period changes
-   instrument changes
-   volume changes
-   mixer changes
-   noise state
-   envelope state
-   SCC waveform changes
-   retrigger behavior
-   pitch changes
-   portamento-like behavior
-   register-write ordering
-   repeated writes that appear redundant from a purely musical
    perspective

Some apparently redundant events may matter.

Therefore:

> Do not aggressively merge or normalize events merely because they
> eventually produce the same musical note.

The converter must reconstruct musical meaning from the register stream
rather than assume that note data already exists.

------------------------------------------------------------------------

# 4. Separation of Responsibilities

The processing responsibilities should remain conceptually separated:

``` text
Raw Register Writes
        ↓
Chip-Specific State / Events
        ↓
Inspectable Analysis Passes
        ↓
Musical Segments
        ↓
Target Projection
```

Each stage answers a different question.

## 4.1 Raw Register Writes

Raw register writes preserve what was actually written to the source
chip and when.

This stage should avoid musical interpretation.

## 4.2 Chip-Specific State / Events

This stage reconstructs what the register writes meant to the source
chip.

Examples include:

-   OPLL FNUM/BLOCK/instrument/volume/Key-On state
-   PSG tone period/noise/mixer/envelope state
-   SCC frequency/volume/waveform state
-   OPLL rhythm trigger and per-instrument state

Chip-specific concepts should remain chip-specific where appropriate.

## 4.3 Inspectable Analysis Passes

Analysis passes may progressively derive higher-level information.

Their output should remain understandable to a human.

A later pass may intentionally repeat information already present in an
earlier trace if doing so makes the analyzed event self-contained.

## 4.4 Musical Segments

Segments represent interpreted musical objects or sounding intervals.

This is the point where concepts such as start/end, duration, retrigger,
continuity, or note identity may be derived.

A Segment is not the same thing as a raw register event.

## 4.5 Target Projection

The target stage decides how the interpreted information can be
represented in:

-   MGSDRV MML
-   MS2 / MAmidiMemo
-   future output formats

Target limitations must not unnecessarily propagate backward into
source-state or analysis representations.

------------------------------------------------------------------------

# 5. Chip-Specific State Must Not Be Artificially Unified

The project supports chips with fundamentally different synthesis and
register models.

For example:

-   OPLL has FNUM, BLOCK, instrument, volume and Key-On state.
-   PSG/SSG has tone periods, mixer state, noise and hardware envelope
    behavior.
-   SCC has programmable waveform memory in addition to pitch and
    volume.
-   Rhythm modes introduce trigger-oriented behavior that is not
    identical to melodic channels.

Do not force these differences into a lowest-common-denominator event
structure.

Common code and common fields should be introduced only where semantics
are genuinely common.

Do not unify fields merely because their numerical values look similar.

The correct direction is:

``` text
different source-chip states
          ↓
preserve their real semantics
          ↓
derive common musical meaning only where justified
          ↓
target representation
```

------------------------------------------------------------------------

# 6. Preserve Both Source Representation and Physical Meaning

Whenever practical, preserve both:

1.  how the source chip represented a value; and
2.  the physical or musical meaning derived from it.

For Yamaha FM pitch data, for example:

``` text
fnum
block
frequency_hz
```

are not redundant in purpose.

-   `fnum` and `block` preserve the source-chip representation.
-   `frequency_hz` preserves the interpreted physical pitch and provides
    a chip-independent basis for later processing.

Likewise, for PSG it may be useful to retain both the original tone
period and the interpreted frequency.

Do not discard the source representation simply because a derived value
exists.

Derived values should not silently replace the original evidence.

------------------------------------------------------------------------

# 7. Segment Intermediate Representation

The Segment representation exists between chip-specific analysis and
target generation.

Its purpose is to retain meaningful musical behavior without prematurely
reducing the data to the limitations of MGSDRV, MS2, or another target.

Segments may represent information such as:

-   start
-   end
-   pitch/frequency
-   volume
-   instrument identity
-   retrigger
-   legato/continuity
-   note boundaries
-   waveform identity
-   noise/envelope-related interpretation where appropriate
-   rhythm instrument identity

Not every chip family needs every field.

Do not expand Segment into a universal dump of every source register.

Likewise, do not make Segment so minimal that important musical
distinctions disappear.

------------------------------------------------------------------------

# 8. Event State vs Segment State

Do not invent information at the event/state stage that can only be
inferred later.

For example, a VGM rhythm stream may contain:

``` text
t=100  BD key=1
t=240  BD key=0
```

The source stream does not explicitly contain a musical object with:

``` text
start=100
end=240
```

That interpretation belongs to Segment construction.

Therefore:

-   Event/state representations should preserve observed Key-On/Key-Off
    transitions.
-   Segment construction may derive `start`, `end`, and duration.
-   Once a Segment represents a sounding interval, a separate `key_on`
    member is normally unnecessary.

This distinction is important for zero-length or same-timestamp trigger
patterns.

If the source contains:

``` text
t=100 key=1
t=100 key=0
```

the event representation must preserve that fact.

How a target handles such an interval is a target-specific decision.

------------------------------------------------------------------------

# 9. Retrigger vs Legato / Continuity

Retrigger and continuation are intentionally distinct concepts.

Repeated pitch activity in a VGM does not necessarily mean a new musical
note, and a repeated note value does not necessarily mean legato.

Envelope restart behavior matters.

The project should retain enough information to determine whether:

-   a note was newly triggered;
-   the previous sounding state continued;
-   the pitch changed while sounding;
-   a new event should become a separate Segment.

Do not remove these distinctions merely because the final textual MML
could be shorter.

------------------------------------------------------------------------

# 10. Preserve Event Sparsity Unless Proven Otherwise

A sparse-looking event stream may be correct.

Do not automatically fill gaps, duplicate notes, or merge events merely
to make the output appear more regular.

Before normalizing suspicious timing, compare against:

-   the source VGM
-   reference playback
-   intermediate traces
-   chip state transitions

> Preserve event sparsity unless there is evidence that the sparsity is
> an artifact rather than meaningful source behavior.

------------------------------------------------------------------------

# 11. OPLL / YM2413 Pitch and Volume Semantics

For YM2413/OPLL, pitch is represented using FNUM and BLOCK.

Preserve both values when they are available.

Also derive `frequency_hz` where useful for analysis and cross-target
conversion.

For OPLL volume:

``` text
VOL = 0   → loudest
VOL = 15  → quietest / near silence
```

The direction is inverted relative to many conventional volume
representations.

A useful approximate rule from project experience is:

``` text
1 OPLL volume step ≈ 3 dB
```

Treat exact perceptual equivalence separately from register semantics.

Do not accidentally interpret larger OPLL VOL values as louder.

------------------------------------------------------------------------

# 12. OPLL Register Write Ordering Matters

Do not assume that OPLL register writes arrive in a convenient
note-oriented order.

Observed sequences may conceptually resemble:

``` text
Key-On
 ↓
FNUM update
 ↓
INST/VOL update
```

or other orders determined by the original driver.

The converter may need to reconstruct the effective state surrounding
the trigger.

Do not assume:

``` text
all note parameters are complete
 ↓
Key-On
```

simply because that model is convenient for MML.

Register-write ordering is evidence and should remain traceable in
intermediate outputs.

------------------------------------------------------------------------

# 13. OPLL User-Defined Patches

OPLL user-defined instrument data present in the VGM should be treated
as meaningful source data.

Where the target supports it, user patches may be exported as instrument
definitions.

Do not silently replace a user patch with a preset merely because the
preset is perceptually similar.

If approximation or substitution is necessary, make that a target-stage
decision and preserve the original patch data in intermediate output
where practical.

------------------------------------------------------------------------

# 14. Rhythm Semantic Vocabulary

For a common rhythm representation, use the following semantic
instrument identifiers:

``` text
BD
SD
TOM
HH
CYM
RIM
```

Use `CYM` as the common semantic name even if a source chip/document
calls the corresponding instrument `TOP`, `TOP-CY`, or another
chip-specific name.

Source-specific terminology may still be retained in source-state/debug
fields.

The common vocabulary describes musical meaning, not the implementation
technology used to produce the sound.

------------------------------------------------------------------------

# 15. Rhythm Event Representation

Rhythm event/state data should preserve information available from the
source.

Useful fields include:

``` text
timestamp
instrument
key_state / trigger
fnum           # where applicable
block          # where applicable
frequency_hz   # where meaningful
volume
pan            # where applicable
```

Not every chip supports every field.

Fields should be optional or chip-specific rather than filled with
invented values.

For OPLL rhythm mode, FNUM/BLOCK information remains valuable because
the underlying channel frequency affects the resulting rhythm sound.

A future target such as OPN3 rhythm may not use that frequency
information, but that is not a reason to discard it from the
OPLL-derived intermediate representation.

Information loss should occur as late as possible.

------------------------------------------------------------------------

# 16. Rhythm Segments

When rhythm Key-On/Key-Off events can be interpreted into sounding
intervals, Segment may use:

``` text
instrument
start
end
frequency_hz
volume
pan
```

plus source-related diagnostic fields when useful.

The presence of `start` and `end` already expresses the sounding
interval.

A `key_on` field is normally unnecessary in the Segment itself unless a
specific analysis requirement justifies it.

Do not force Segment creation when the available source evidence is
insufficient.

------------------------------------------------------------------------

# 17. PSG / SSG State Is Structurally Different

PSG/SSG must not be modeled as if it were OPLL with different
parameters.

Relevant PSG concepts include:

-   tone period
-   tone enable/disable
-   noise enable/disable
-   noise period
-   mixer state
-   fixed volume
-   hardware envelope enable
-   hardware envelope period
-   hardware envelope shape

These may interact across channels.

Preserve chip-level state where required to interpret a channel
correctly.

Do not reduce PSG to only:

``` text
frequency
volume
```

before mixer/noise/envelope behavior has been interpreted.

------------------------------------------------------------------------

# 18. PSG Noise and Envelope Interpretation

Noise and hardware envelope behavior are part of the musical source
data.

If the final MGSDRV representation requires an ID, macro, or
reconstructed command sequence, keep the original/decoded state
available in an earlier pass.

Do not discard noise or envelope changes merely because conventional
note notation has no direct equivalent.

If several source states are intentionally collapsed into one target
representation, document that loss.

------------------------------------------------------------------------

# 19. SCC Waveform Data Is First-Class Source Information

SCC is not simply a pitched oscillator with an instrument number.

Its programmable waveform data is part of the source sound.

Where waveform changes are detected, preserve:

-   waveform bytes or a stable waveform identifier
-   the channel(s) using the waveform
-   timing of waveform changes
-   pitch
-   volume

If waveform IDs such as `s00`, `s01`, etc. are generated, the mapping
from ID to waveform data must remain inspectable.

Do not deduplicate waveforms in a way that makes source reconstruction
or human analysis unnecessarily difficult.

Exact waveform equality may be used for stable identification, but any
normalization beyond exact equivalence should be deliberate.

------------------------------------------------------------------------

# 20. Raw Trace and Analyzed Passes May Intentionally Overlap

Intermediate representations are diagnostic tools as well as program
data.

It is acceptable for decoded information to appear both in:

-   a raw/state trace; and
-   a later PASS output.

PASS output should preferably be understandable without forcing a human
to manually reconstruct all previous chip state.

For example, if PASS4 represents an analyzed event, it is acceptable for
it to repeat:

-   channel
-   frequency
-   volume
-   instrument/wave ID
-   noise/mixer information
-   rhythm identity
-   source pitch fields

when that makes the event understandable on its own.

Do not remove such fields solely because they are derivable from earlier
passes.

------------------------------------------------------------------------

# 21. PASS Files Are Part of the Contract

When `--dump-passes` or an equivalent diagnostic option is used, the
generated intermediate files are expected to be useful for human
inspection.

Do not treat PASS files as arbitrary temporary implementation dumps.

When changing a PASS schema:

1.  identify what information is added, removed, or reinterpreted;
2.  explain why;
3.  preserve source traceability;
4.  update documentation/tests/fixtures where applicable.

A cleaner internal architecture is not sufficient justification for
making PASS output less informative.

------------------------------------------------------------------------

# 22. MGSDRV MML Is a Target Representation

MGSDRV MML is a target language, not the canonical internal
representation.

Do not shape earlier intermediate data solely around what is convenient
to express in MGSDRV syntax.

The final MML may necessarily:

-   quantize or encode durations
-   select instrument commands
-   choose noise/envelope commands
-   express SCC waveform definitions
-   emit rhythm commands
-   use ties/rests
-   use macros
-   allocate channel buffers

These are target-projection decisions.

The source/intermediate representation should retain information that
MGSDRV cannot express directly whenever that information is useful for
analysis or another future target.

------------------------------------------------------------------------

# 23. MGSDRV Syntax References

When implementing or changing MGSDRV output, consult the actual MGSDRV
documentation rather than guessing syntax from examples.

Primary/reference material used by the project includes:

-   MGSDRV documentation: `https://p.gigamix.jp/mgsdrv/MGSDR320.TXT`
-   MGSDRV MML reference on Z80 Machines Wiki:
    `https://z80.msx.click/index.php?title=MGSDRV_MML_11_JP`

A modern compiler/player implementation may also be useful for
validation, but implementation behavior should not silently replace
documented syntax.

When documentation and observed compiler behavior differ, record the
discrepancy as an explicit finding.

------------------------------------------------------------------------

# 24. MGSDRV Output Size Is a Real Target Constraint

MGSDRV compiled data has practical memory/buffer constraints.

The current project README notes that generated MML may require manual
`#alloc` adjustment and/or macroization when compiled data becomes too
large.

This is a target constraint.

Do not prematurely delete source events from intermediate
representations merely to reduce final MML size.

Optimization for compiled size should happen at or near target
generation.

Possible target-level strategies include:

-   macros
-   repeated-pattern factoring
-   command simplification where semantically safe
-   `#alloc` adjustment
-   target-aware note/rest encoding

Such optimizations must not silently change musical behavior.

------------------------------------------------------------------------

# 25. Register-Accurate Path vs Grid-Quantized Path

The project currently has at least two conceptually different output
approaches:

## 25.1 Register-oriented conversion

`vgm2mml.py` aims to produce MML that closely reflects source register
behavior.

For this path, preserving timing and source-event semantics has priority
over producing a visually regular score.

## 25.2 Grid-quantized conversion

`vgm2mml_grid.py` intentionally maps events onto a musical step grid.

This is a deliberate musical transformation.

Quantization is therefore allowed in this path, but it must not be
confused with faithful reconstruction of the original event timing.

Keep the distinction explicit:

``` text
source-faithful interpretation
        ≠
intentional grid quantization
```

Do not make grid behavior a hidden property of shared parsing/Segment
code.

------------------------------------------------------------------------

# 26. Tempo and Grid Inference

Tempo/grid inference is an interpretation step.

It must not modify the raw source event evidence.

When inferring a grid:

-   retain original timestamps;
-   retain the inferred tempo/grid parameters;
-   make quantization decisions inspectable where practical;
-   avoid treating a single song-specific pattern as a universal rule.

A previously useful conceptual approach has been to infer a stable grid
from inter-onset timing, including considering a grid finer than the
minimum observed IOI where needed.

Such heuristics are experimental unless explicitly established by tests.

If tempo/grid inference fails or lacks sufficient evidence, do not
fabricate certainty.

------------------------------------------------------------------------

# 27. MS2 / MAmidiMemo Is a Separate Target

MS2 output should be treated as a target projection separate from MGSDRV
MML.

Do not assume that an optimization or representation chosen for MGSDRV
automatically applies to MS2.

MS2-related conversion may use the same:

-   raw VGM parser
-   chip-state reconstruction
-   analyzed passes
-   Segment data

while having different requirements for:

-   instrument definitions
-   rhythm representation
-   tempo/grid encoding
-   target commands
-   channel layout

Shared source analysis is desirable.

Shared target assumptions are not.

------------------------------------------------------------------------

# 28. OPLL Rhythm and MS2

OPLL rhythm processing should preserve source rhythm behavior before
projecting it into MS2.

Relevant source information may include:

-   BD / SD / TOM / HH / CYM trigger state
-   per-instrument volume
-   channel 6--8 FNUM/BLOCK state
-   derived frequency
-   rhythm mode state

If the source hardware uses edge-sensitive trigger behavior, preserve
the observed transitions before converting them into target note/segment
concepts.

Do not infer a duration earlier than necessary.

------------------------------------------------------------------------

# 29. Target Limitations Must Not Rewrite Source History

A target may be unable to express some source behavior.

Examples may include:

-   a source pitch change that the target cannot represent exactly;
-   a source waveform behavior with no direct MML equivalent;
-   a rhythm parameter unused by the target;
-   a source envelope/noise combination that must be approximated;
-   timing finer than a grid-quantized target path permits.

In such cases:

1.  preserve the source information in earlier intermediate output;
2.  document the target approximation;
3.  perform the loss at target projection;
4.  do not modify earlier stages to pretend the source never contained
    the information.

------------------------------------------------------------------------

# 30. "Register Correct", "Musically Correct", and "Target Correct"

There are at least three distinct objectives.

## A. Register correctness

Reconstruct the original source-chip register state and behavior
accurately.

## B. Musical correctness

Represent the intended musical performance in a useful musical form.

## C. Target correctness

Generate MGSDRV MML, MS2, or another target representation that behaves
appropriately within the target's constraints.

These objectives can conflict.

For example, a grid-quantized MML may be musically useful while no
longer preserving exact register timing.

Whenever an algorithm changes behavior, state which objective is being
optimized.

------------------------------------------------------------------------

# 31. Equivalent Audible Output Does Not Mean Equivalent Information

Two outputs may sound nearly identical while representing different
source behavior.

Conversely, preserving every register event literally may produce an
awkward or inefficient target representation.

The project must distinguish:

-   audible similarity
-   musical equivalence
-   source-chip behavioral equivalence
-   target-format convenience

Do not collapse these into a single definition of "correct".

------------------------------------------------------------------------

# 32. Real Playback and Reference Playback Are Validation Tools

Where practical, compare generated output against reference playback.

Useful validation may include:

``` text
source VGM
 ↓
reference playback
 ↓
listen / record / inspect

source VGM
 ↓
conversion
 ↓
MGSDRV MML / MS2
 ↓
target playback
 ↓
listen / record / inspect
```

Software playback is useful, but when a behavior depends on real chip
semantics, hardware-derived observations should not be casually replaced
by theoretical assumptions.

Document whether a finding comes from:

-   chip documentation
-   emulator/software behavior
-   real hardware observation
-   subjective listening
-   code inspection
-   hypothesis

------------------------------------------------------------------------

# 33. Do Not Overfit to One Song

A rule that works for one VGM is not necessarily a general rule.

Especially validate multiple pieces when changing:

-   note segmentation
-   retrigger behavior
-   legato/continuity
-   rhythm interpretation
-   pitch conversion
-   volume interpretation
-   PSG noise/envelope handling
-   SCC waveform handling
-   tempo/grid inference
-   quantization

A successful result on one track is evidence, not proof.

------------------------------------------------------------------------

# 34. Experiments and Rejected Approaches

Record failed or rejected approaches so future agents do not repeat
them.

## 34.1 Treating VGM as conventional note data

Problem:

Register-level behavior and timing information are lost.

Status:

Rejected.

Use chip-state reconstruction and inspectable intermediate
representations.

## 34.2 Excessive event merging

Problem:

Merging events may produce cleaner output while destroying retrigger,
rhythm, or source-timing behavior.

Status:

Rejected as a general strategy.

## 34.3 Lowest-common-denominator chip state

Problem:

Forcing OPLL, PSG, SCC, and rhythm into one universal source-event
schema loses chip-specific meaning.

Status:

Rejected.

Unify only at a semantic layer where meaning is genuinely shared.

## 34.4 Target-driven destruction of intermediate information

Problem:

Removing fields because MGSDRV/MS2 does not need them prevents later
analysis and other targets from using them.

Status:

Rejected.

Information loss should occur as late as possible.

## 34.5 Treating PASS output as disposable debug text

Problem:

Humans can no longer trace how a final result was produced.

Status:

Rejected.

Intermediate outputs are first-class artifacts.

------------------------------------------------------------------------

# 35. Confirmed Principles vs Experimental Heuristics

The project should maintain a strict distinction.

## Confirmed / high-confidence project principles

-   VGM is a register/timing event stream, not a score.
-   Intermediate outputs are first-class artifacts.
-   Chip-specific state should not be artificially unified.
-   Source representation and derived physical meaning may both be worth
    preserving.
-   Segment is an interpreted layer, not raw register data.
-   Target limitations should not unnecessarily propagate backward.
-   Register-oriented and grid-quantized output are different goals.
-   Redundancy is acceptable when it improves traceability.

## Experimental / implementation-dependent areas

-   exact tempo/grid inference
-   exact note-boundary heuristics
-   interpretation of ambiguous repeated writes
-   target-specific volume mappings
-   target-specific compression/macro strategies
-   perceptual equivalence of different chip/target behaviors

## Open questions

-   Which source events should become independent Segments?
-   How should ambiguous Key-On/Key-Off patterns be represented across
    chip families?
-   Which semantic fields should be common across melodic and rhythm
    Segments?
-   How much source-state redundancy should PASS4 carry?
-   How should future OPN/OPNA/OPN3 support integrate without damaging
    current abstractions?
-   Which target optimizations can reduce MGSDRV size without reducing
    traceability?

------------------------------------------------------------------------

# 36. Development Rules for Codex

When modifying this project:

1.  Read the relevant project knowledge and decision documents before
    architectural changes.
2.  Inspect the existing implementation before proposing a rewrite.
3.  Do not bypass the intermediate representations.
4.  Do not remove PASS outputs merely because final MML is correct.
5.  Do not simplify Segment without explaining what information is lost.
6.  Do not force different chip families into one source-state schema.
7.  Preserve source register semantics before applying musical
    interpretation.
8.  Preserve original source fields when adding derived fields such as
    frequency.
9.  Distinguish measured facts, specifications, hypotheses, and
    heuristics.
10. Do not replace hardware-derived observations with theory without
    evidence.
11. Preserve retrigger/continuity semantics unless deliberately changing
    them.
12. Treat quantization as an explicit transformation, never an invisible
    cleanup.
13. Keep MGSDRV-specific decisions in the target layer where practical.
14. Keep MS2-specific decisions in the target layer where practical.
15. Prefer reproducible tests and fixtures over intuition.
16. Validate non-trivial changes against multiple pieces.
17. Avoid large refactors when a local change is sufficient.
18. Before changing established behavior, identify why it exists.
19. Record significant discoveries and rejected approaches.
20. When changing intermediate schemas, prioritize human inspectability.
21. Never discard source information merely because the current target
    cannot use it.
22. Do not assume "shorter MML" means "better conversion".
23. Do not assume "cleaner architecture" justifies less traceable
    intermediate output.

------------------------------------------------------------------------

# 37. Preferred Development Workflow

For non-trivial changes:

``` text
1. Inspect existing implementation
2. Identify relevant project knowledge
3. Inspect representative intermediate outputs
4. Explain current behavior
5. Identify which conceptual stage owns the problem
6. Form a hypothesis
7. Design a minimal experiment/test
8. Run the experiment
9. Compare source/intermediate/target results
10. Implement the smallest justified change
11. Run regression tests
12. Inspect intermediate outputs again
13. Validate final MML/MS2
14. Record the result
```

Do not jump directly from a user request to a large rewrite.

------------------------------------------------------------------------

# 38. Fixtures and Reference Data

Representative source data and known-good intermediate outputs should be
treated as valuable project knowledge.

Where practical, fixtures should include:

-   source VGM
-   expected raw/state trace
-   expected analyzed PASS output
-   expected Segment behavior
-   expected final MML/MS2
-   notes describing why the fixture exists

A fixture should preferably demonstrate one specific behavior or
regression.

When a bug is fixed, consider adding a fixture that makes the failure
reproducible.

Do not update expected outputs blindly when a regression test fails.

First determine whether the implementation or the expectation is wrong.

------------------------------------------------------------------------

# 39. Human-Readable CSV / Intermediate Output Guidelines

Intermediate output should favor diagnosis over compactness.

Prefer explicit columns with stable meaning.

For example, Yamaha FM-related analysis may retain:

``` text
timestamp
channel
fnum
block
frequency_hz
instrument
volume
key_state
```

Rhythm analysis may retain:

``` text
timestamp
instrument
key_state
fnum
block
frequency_hz
volume
pan
```

PSG analysis may retain source-relevant mixer/noise/envelope fields.

SCC analysis may retain waveform identifiers and enough information to
recover/inspect waveform data.

Do not fill non-applicable fields with misleading values.

Use empty/null values or chip-specific schemas when appropriate.

------------------------------------------------------------------------

# 40. Naming Should Express Semantics

Names in common/intermediate layers should describe meaning rather than
one source chip's terminology.

Example:

``` text
CYM
```

is preferred as the common rhythm semantic identifier.

A source-specific field may still record:

``` text
TOP
TOP-CY
```

if that is the source chip's terminology.

Likewise, use `frequency_hz` for the interpreted physical quantity and
retain `fnum`, `block`, or `tone_period` for source representation.

Avoid ambiguous names such as `freq` when it is unclear whether the
value is Hz, FNUM, or a timer period.

------------------------------------------------------------------------

# 41. Future Chip Support

Future chip support should follow the existing information-preservation
model.

For a new chip:

1.  identify its native register/state model;
2.  preserve that model without forcing it into OPLL/PSG/SCC structures;
3.  expose inspectable state/events;
4.  derive physical quantities where useful;
5.  construct musical Segments only after source semantics are
    understood;
6.  project to MGSDRV/MS2 only where meaningful.

For example, future OPN/OPNA/OPN3 rhythm support may share the semantic
rhythm vocabulary:

``` text
BD / SD / TOM / HH / CYM / RIM
```

while keeping its source-specific trigger, level, pan, and
implementation details separate.

Do not design the common layer around only the chips currently
implemented.

At the same time, do not add speculative abstractions without a concrete
need.

------------------------------------------------------------------------

# 42. Documentation Is Part of the Implementation

When behavior is non-obvious, document why it exists.

Especially document:

-   unusual register ordering
-   edge-sensitive trigger behavior
-   timing heuristics
-   tempo/grid inference
-   volume interpretation
-   waveform deduplication rules
-   source-to-target approximations
-   intentional redundancy in PASS files
-   rejected simplifications

Future agents should be able to distinguish deliberate behavior from
accidental complexity.

------------------------------------------------------------------------

# 43. Guiding Principle

The project is fundamentally about preserving information while crossing
between representations:

``` text
chip register behavior
        ↓
reconstructed source state
        ↓
inspectable analyzed events
        ↓
musical interpretation
        ↓
Segment
        ↓
target language
        ↓
playback
```

Every conversion step can lose information.

The primary design question is therefore not:

> "How can we make this conversion simpler?"

but:

> "What information is being lost here, and is that loss intentional?"

And for this project specifically:

> A final MML file is not sufficient evidence that the conversion is
> correct.
>
> The path from the VGM register stream to that MML must remain
> inspectable.

This principle should guide architectural decisions.

------------------------------------------------------------------------

# 44. Repository-Specific Current Context

At the time this document was prepared, the public repository describes:

-   `vgm2mml.py` as supporting PSG, OPLL and SCC and producing
    register-oriented MGSDRV MML.
-   `vgm2mml.py --dump-passes` as producing intermediate files.
-   PSG/SCC analysis now lives in `py/psg.py` and `py/scc.py`; their MML
    renderers consume chip-specific immutable Segments. `--dump-passes`
    retains source event CSVs and emits Segment and SCC waveform CSVs.
    See `docs/psg_scc_segments.md` for the preserved interpretation and limits.
-   SCC clock detection reads 0x9C (K051649/K052539), not 0xCC (ES5503).
    The previous offset was a bug that suppressed valid SCC events.
-   `vgm2mml_grid.py` as an OPLL-specific grid-quantized path.
-   OPLL user-defined patch output.
-   OPLL rhythm output for bass drum, snare, tom, cymbal and hi-hat.
-   optional use of a base MS2 instrument library.
-   MGSDRV output-size constraints that may require `#alloc` adjustment
    or macroization.

These are current implementation facts, not permanent architectural
limits.

When repository behavior changes, update this section rather than
weakening the general principles above.

------------------------------------------------------------------------

# 45. Final Rule for Agents

When uncertain whether to simplify, merge, normalize, quantize, discard,
or reinterpret data:

1.  preserve the source evidence;
2.  expose it in an inspectable intermediate result;
3.  make the interpretation explicit;
4.  defer irreversible loss until the target stage;
5.  ask whether a human can still trace the final result back toward the
    original VGM.

If the answer to step 5 becomes "no", the change requires strong
justification.
