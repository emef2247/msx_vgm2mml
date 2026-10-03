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

## Shared step comments in merged MML (2026-09-27)

The main converter annotates the final merged MML at common note/rest
boundaries across all still-playing tracks. Step counts use target MML time
(48 per quarter note), not raw VGM samples or Segment ticks. Tied continuations
are not synchronization boundaries. Ended tracks do not block later markers.
The CLI defaults to a minimum gap of 1000 target-MML steps between selected
markers; start and final end are always retained. `--sync-min-gap 0` restores
all shared boundaries. This spacing is not phrase or bar detection.
This is a target-stage formatting operation: retain source timing and Segment
evidence, and verify the expanded note/command timeline before and after it.
See [MML sync points](mml_sync.md) for the implemented scope and tests.

# 45. Final Rule for Agents

Target-stage envelope projection (2026-09-28): keep source Segments unchanged.
Remove silent tracks from final merged output and defer rest-time state changes
until the next sounding interval. Use explicit 60 Hz volume holds for inferred
software envelopes; do not assume fitted interpolation parameters reproduce
observed register values. Preserve hardware envelope operation and pitch-write
boundaries. Dump target note intervals and selected envelope IDs for inspection.

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

## OPLL rhythm inspection (2026-09-28)

The main MML path now dumps all native OPLL Segments before target voice
assignment to `.opll.segments.csv` with --dump-passes. Legacy pass0 remains.
Rhythm channels 9..13 represent BD/SD/TOM/CYM/HH, not MML track IDs.
For rhythm_expand, keyon is the per-instrument rising-edge result; the
bd/sd/tom/tc/hh fields retain source flags and must not each be interpreted
as a fresh trigger. PASS4 includes non-trigger rows omitted from Segments.
Reference parity is not proof of all chip edge cases. MML rhythm output and
a common cross-chip schema remain separate work. See docs/opll_rhythm.md.

## Rhythm grouping and exact repetition analysis

Native OPLL Segments remain unchanged. rhythm_patterns.py groups eligible
rhythm triggers by existing 60 Hz tick, retaining duplicate hits, source times
and channel/index references. Separate definitions and ordered occurrences
encode exact adjacent repeats; equality includes gaps, instrument volume and
pitch state, and native interval lengths. No timing tolerance, quantization,
phrase inference or acoustic duration inference is applied. The final gap is
unknown, not an inferred rest. The stage cannot restore earlier lost triggers.
See docs/opll_rhythm.md for schemas and extraction limits.

## MGSDRV / libkss timing observation

The msxplay.com sample timing is consistent with approximately 735.77 samples
per playback frame at 44100 Hz, rather than exactly 60 Hz. This is a measured
libkss playback observation, not a universal MGSDRV constant. Preserve VGM
timestamps and distinguish driver frames from MML steps. See
[measurement and scope](../field_notes/2026-09-28_mgsdrv_libkss_timing.md)
before changing timing conversion. Current converter timing is unchanged.

## Rhythm target projection

Main output now includes MGSDRV rhythm track f from exact Segment groups.
The target renderer applies per-instrument levels, combines simultaneous
instruments, and renders exact adjacent repeats as finite loops. Sync and
allocation parse rhythm only for f in OPLL mode 1. Long encoded gaps continue
as rests, not new attacks. Same-tick duplicate instruments are rejected.
The final positive length is a target encoding choice, not acoustic decay.
No source timing correction or raw/state reinterpretation was made. See
docs/opll_rhythm.md for validation and unrepresented source-state limits.

Rhythm tail correction: target end includes the latest OPLL trace tick as
well as Segment ends. Attack-only rhythm Segments omit the final key-off;
using their ends alone truncated the last cymbal in rhythm_only_test02.
The fixture now ends at tick 77 rather than 41, retaining its tick-40 attack.
This does not reconstruct unlogged trailing VGM waits or acoustic decay.
Seven rhythm renderer tests pass, including normal/raw tail checks.

## OPLL target voice and note correction

The final projection now lives in opll_target.py. Decode registers 00/01 as
operator flags, 02 as modulator KL/TL, 03 as carrier KL/WF/FB, 04/05 as AR/DR,
and 06/07 as SL/RR. MGSDRV operator WF is modulator bit 3 / carrier bit 4
of register 03, and FB is its low three bits. The previous main renderer
used an incorrect interleaved register layout.

MGSDRV ROM voices @0..@14 correspond to YM2413 instruments 1..15. User
definitions and selections use @16 upwards, avoiding ROM-number collisions.
The supplied fifteen user definitions now match the hand-written reference
including waveform bits. Rests do not allocate unused user definitions.
Long note splitting must use ties; splitting a held note into untied notes
creates unwanted attacks. Source Segment boundaries are otherwise preserved.
The existing same-tick final-patch policy is retained. Arbitrary mid-note
global patch changes still require separate state/segmentation validation.

Legacy per-chip melodic variant files and legacy voice assignment remain for
regression comparison; corrected final output comes from `.opll.target.mml`.
Use `.opll.target_notes.csv` for final target voice mappings, not legacy pass0
voice IDs. The shared Segment schema is unchanged.

## Rhythm notation state

Segment-derived patterns remain authoritative. rhythm_notation.py only
shortens target notation: absolute instrument-volume deduplication and one
profitable global default length. Loop entry must account for both incoming
state and the preceding iteration's exit; ordinary linear deduplication can
corrupt later iterations. Keep pattern/occurrence CSVs intact. Before/after
target dumps and character metrics are available with --dump-passes.
Sync formatting wraps preserved loop text across track-prefixed lines;
physical newlines must not reset state or expand a repeat. Melody and macro
optimization remain pending.

## MGSDRV octave and voice numbering verification

The final OPLL projection must use MGSDRV octave numbering, not scientific
pitch octave labels. MGSC 1.11 + libkss-js 3.0.0 experimentally writes block 3
for `9 @9v12o4a4` and block 2 for `o3a4`. The source grider begins with Fnum
290/block 3; scientific A3 must therefore render as MGSDRV o4 a. The prior
target renderer emitted one octave too low. target_note now uses MIDI // 12,
including the lowest block without the legacy scientific-octave clamp.
Legacy melodic variant output remains unchanged for regression comparison.

YM2413 register instrument 1..15 maps to MGSDRV @0..@14. YM2413 instrument
0 selects its shared user registers; generated MML uses allocated user IDs
starting at @16. These MML IDs are not hardware ROM table indices: 16..18 in
a ROM table describing rhythm patches do not reserve MML @16..@18.
The msxplay-js public/demo/rom.mml example confirms @0/@16 for Violin, etc.
https://github.com/digital-sound-antiques/msxplay-js/blob/main/public/demo/rom.mml

Controlled MGSC/libkss roundtrips of the same patch defined as @16 and @v20,
with matching selections, produce identical user registers 00..07. Renumbering
is safe provided definition and selection agree. The final operator field is
WF (waveform); DT in the older reference is a comment and does not alter the
parameter order. Do not change the data order to match a comment label.

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

## Melody Segment pattern candidates

melody_patterns.py applies the existing greedy exact tandem-repeat search to
per-channel PSG/SCC/OPLL Segment signatures. Timing is relative in definitions;
source index/time/ticks remain in markings. State equality includes articulation,
chip controls, SCC waveform content and OPLL user-patch content/interior writes.
Do not match user patches using instrument zero or target voice ID alone.
Unknown patches are conservatively distinct. Zero-duration rows remain ordered.

With --dump-passes, three melody CSVs allow reconstruction without changing
source Segment values or final MML. These are candidates, not proof of safe MML loops.
State at the loop entry/back-edge, shared chip state and envelope continuity
must be addressed by a later target projection. No macro extraction or timing
tolerance was introduced. See docs/melody_patterns.md.

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

## Shared envelope selection

PSG and SCC now contribute candidates to one bank before target rendering.
Longer varying curves have priority; only full observed-tick equality permits
sharing a prefix of a longer definition. No source-driver identity is required.
With `--dump-passes`, `<stem>.<chip>.envelope_candidates.csv` records the selected
ID, definition/exact_prefix/inline status, observed duration, occurrences and
volume runs. Segment envelope annotations retain the actual selected IDs.
This does not infer unseen tails, release parameters or base-volume offsets.

## Performed-unit loop projection

PSG/SCC complete extracted notes and OPLL patch-aware note Segments feed a
second, nested pattern projection. PSG noise-containing intervals ending in
rest may form coarse percussion candidates, retaining all internal states.
Candidate equality alone never authorizes rewriting: emitted command sequences
must repeat exactly. Limit emitted nesting to two levels and counts to 255.
Segment dumps keep original fields and add performed-unit/hierarchy metadata.
See docs/melody_patterns.md for reports, ambiguity and validation limits.

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
## Zero-duration OPLL events

Do not equate l=0 with an irrelevant event. Partial-register pitch states may
be consolidated for a quantized target, but key/rhythm edges must be extracted
and retained before reducing state updates. Keep source timestamp and order;
same quantized tick does not imply the same source time. The agreed design and
its unverified assumptions are recorded in
[zero-length event notes](../field_notes/2026-09-30_opll_zero_length_events.md).


## Quantized rhythm collisions (2026-10-01)

MGSDRV target projection keeps the last attack for each instrument at each
60 Hz tick when the earlier attack has zero tick duration. Source timestamps,
states and rhythm Segments are unchanged. This deliberately loses sub-tick
retrigger information in MML, including differing volume/pitch state; it is
not evidence that the source edges were redundant. No later attack is shifted.
Positive-duration duplicate entries or reversed source time still fail.

Warnings summarize collisions per render. With --dump-passes,
<stem>.opll.rhythm.collisions.csv lists the dropped/kept Segment indices,
source times and state tuples (ordered by rhythm_patterns.STATE_FIELDS).
This supersedes the earlier identical-state, one-sample-only target rule.
The 16 reported FIREHAWK/FRAY/ILCITY/TOGZL/XAK cases are optional local
conversion regressions; private fixture data is not bundled.


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

Public OPLL regression checks now assert retained source attacks (key-on edges
and recovery from attenuation 15), alongside expanded target timeline checks.
Old OPLL artifact hashes encoded retrigger merging and are no longer the oracle.


## Withdrawn OPLL coalescing experiment (2026-10-01)

The user reported that the opening Alest202 guitar disappeared after projected
same-note coalescing. The optimization has been removed and rendering is back
to the YsSMS01 retrigger fix (slur/q0 and preserved source key edges).
Key-on counts and compile success were insufficient validation. Do not reinstate
coalescing without checking audible onset/envelope/patch behavior against source.
The precise cause is not established. No audio equivalence claim is warranted.

## OPLL inferred onset versus source key edge (2026-10-01)

Keep the legacy `onset` annotation (including attenuation-15 recovery) for
analysis, but never use it as permission to restart a hardware envelope.
`key_on_edge` independently records keyon 0->1, including edges at attenuation
15 and zero tick duration. PASS2/PASS3 and Segment CSVs expose both fields.
Target slur/gate decisions use key_on_edge, not onset. Pattern signatures retain
both so source attacks cannot be substituted with volume recovery gestures.

OPLL Segments no longer merge apparently silent rows: that merge discarded
key transitions and pitch/state changes at maximum attenuation. A keyed
nonzero-frequency interval at source vol=15 renders as a note with v0, retaining
key continuity; it is not replaced with a rest. Actual key-off still ends the
target note. This does not implement source release tails or sample-exact timing.

MGSC 1.11/libkss synthetic roundtrip preserves key-high across attenuation
15->3->15->4 and emits only the two explicit source attacks. Alest202 now retains
all source melodic edges in Segments; the previous ch0/ch1/ch2 losses were
5/5/1 edges. YsSMS01 had no nonedge onsets, so this correction alone cannot
explain its reported lighter sound. See the OPLL key/envelope field note.

## Declared VGM loops
The header field at 0x1C is relative to 0x1C; zero means no loop. Record the command boundary before consuming it. Preserve chip state and do not add a KEYON at this boundary. Trace time now uses the same absolute source-sample clock as loop metadata. See docs/vgm_loop.md and docs/vgm_timing.md.

Compressed VGM input must be detected by the gzip signature, not the extension.
Read GD3 and command headers after decompression. VGM versions below 1.50 and
a zero data-offset field use data start 0x40. Reject invalid headers/offsets
instead of silently producing an empty conversion.

## Shared source clock and optional sample evidence

VGM wait samples are accumulated as integers at 44100 Hz. Every chip uses the
same origin at stream sample zero; do not rebase each chip at its first write.
All waits count, including short waits 0x77/0x7A, DAC waits and overrides.
Command payloads must be skipped by length rather than scanned as commands.
Trace time is derived from the accumulated samples; 60 Hz ticks remain a target
quantization and are not source timing evidence.

`--vgmticks` preserves absolute start/end samples in trace/pass/Segment dumps.
Missing source samples in old CSVs remain unavailable, not inferred from rounded
time. Source interval ends are not necessarily musical gate ends. Same-sample
writes stay ordered, and physical sub-tick intervals must not disappear solely
because their derived 60 Hz length is zero. See docs/vgm_timing.md.

Raw sample timing may still vary between reference-MML repetitions. Keep exact
evidence and diagnostic stable-state views separate from a future tolerant loop
or musical-normalization policy. The sample PSG volume-reset alignment is only
a reference-specific audit method and must not become a general KEYON definition.

## Optional source-inferred musical duration projection

`--normalize-lengths` is a target-stage inference, not a rewrite of Segment
timing. Keep native integer samples and edges, and record corrected positions,
gate ratios, omitted sub-millisecond target intermediates and source indices.
One fitted clock must serve all chips. Apply all part projections together or
keep conventional output when clock confidence/representability fails.

Reference MML may validate compression but must not supply production note,
tempo or gate choices. Frame-based software envelopes do not scale with musical
tempo. Exact loop expansion and effective state equivalence after setter pruning
are separate checks. Count equality is not audio equivalence, and reference
one-loop playback may have a different horizon from the source VGM capture.
See docs/note_normalization.md and the 2026-10-02 benchmark field note.

## Loop structure and output selection

Preserve reversible source loop markers and overlapping repeat alternatives before macro selection. A short inner loop must remain expandable so later macro extraction can choose another boundary. For the current compression work, rank equivalent final MML by character count and require successful MGSC compilation without buffer errors; minimum compiled byte count is not the objective. See field_notes/2026-10-03_reversible_loop_structure.md.
