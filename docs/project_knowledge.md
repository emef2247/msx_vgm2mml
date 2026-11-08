# VGM → Musical Representation / MSX Targets

## Project Knowledge & Design Principles

This document records stable technical principles and durable domain knowledge for `emef2247/msx_vgm2mml`.

It defines what information must be preserved, how source behavior should be interpreted, and where target-specific transformations belong.

It complements:

- `AGENTS.md`: repository operating rules and development workflow.
- `docs/collaboration_principles.md`: collaboration and decision-making principles.
- Focused `docs/*.md`: subsystem designs, implementation details, and target-specific behavior.
- External private `field_notes/`: experiments, measurements, rejected approaches, regressions, and provisional findings.

Keep this document focused on principles that should remain valid across implementations and targets.

Not every statement is a formal specification. Distinguish confirmed facts, implementation decisions, measurements, hypotheses, and unresolved questions.

Do not silently promote a hypothesis, fixture-specific observation, or test expectation into a project invariant.

---

# 1. Project Goal

The project interprets VGM sound-chip performances and produces inspectable, editable musical representations and target-specific outputs.

The primary MSX output is MGSDRV MML/MGS. Other paths include score Blueprints, MIDI, reference VGM, and VGM variants for different MSX sound hardware configurations.

Additional source chips and target systems may be supported through native analysis and target projection.

The goal is not merely to generate a valid file, produce similar sound, reduce output size, or pass regression tests.

The project aims to:

1. Preserve observable source-chip behavior.
2. Derive meaningful musical information from that evidence.
3. Keep important interpretations and transformations inspectable.
4. Support independent target projections without unnecessarily constraining shared information.
5. Make approximation, uncertainty, and information loss explicit.

Conceptually:

```text
VGM
  |
  v
Raw Register Writes / Source Timing
  |
  v
Chip-Specific State / Native Events
  |
  v
Inspectable Analysis Passes
  |
  v
Segments / Native Musical Interpretation
  |
  v
Shared Musical Representation
  |
  +--> MGSDRV MML / MGS
  |
  +--> Score Blueprint / MIDI
  |
  +--> Reference / Target VGM
  |
  +--> Future Target Projections
```

This diagram describes conceptual responsibilities, not a mandatory one-to-one module layout.

Do not refactor merely to make module boundaries match the diagram.

A valid source performance must not become invalid merely because one target projection fails.

---

# 2. Intermediate Results Are First-Class Artifacts

Inspectable intermediate results are a primary project requirement, not merely a debugging convenience.

A human should be able to determine, where relevant:

- Which source register event caused a musical event.
- What chip state existed at that point.
- Where Key-On, Key-Off, trigger, and control edges occurred.
- Which source pitch, volume, instrument, waveform, and rhythm values were present.
- When source evidence became an interpreted Segment or musical unit.
- Which information was changed, approximated, or discarded by a target projection.

CSV or equivalent pass output should favor human traceability over compactness.

Redundancy is acceptable when it makes an analyzed event self-contained.

**Redundancy that improves traceability is acceptable. Loss of source information for structural elegance is not.**

Do not remove, merge, split, normalize, or reshape an intermediate representation merely because doing so makes final output cleaner or makes a regression test pass.

Tests are evidence, not the objective.

If a test conflicts with the information-preservation model, determine whether the implementation, test expectation, musical interpretation, or target projection is incorrect.

When an intermediate schema must change, explain the semantic reason and identify what information is added, removed, or reinterpreted.

---

# 3. Transformation Boundaries

Keep the following responsibilities conceptually separate.

## 3.1 Raw Register Writes

Preserve what was written to the source chip, when it was written, and the ordering between writes.

Avoid musical interpretation at this stage.

Repeated writes and writes that appear musically redundant may still be significant.

## 3.2 Chip-Specific State and Native Events

Reconstruct the effective meaning of register writes using the native semantics of the source chip.

Examples include:

- OPLL: FNUM, BLOCK, instrument, volume, Key state.
- PSG/SSG: tone period, mixer, noise, fixed volume, hardware envelope.
- SCC: frequency, volume, waveform state.
- Rhythm sources: trigger and per-instrument state.
- OPM: KC/KF, operator parameters, partial Key state, shared controls.

Do not force different chips into a lowest-common-denominator state schema.

Unknown or unwritten source state must remain unknown unless an explicit, documented reset assumption applies.

## 3.3 Inspectable Analysis Passes

Analysis may progressively derive higher-level information.

Later passes may repeat earlier fields when this improves human inspection.

A pass is not disposable debug text.

Preserve source identifiers, timestamps, channel relationships, and other information needed to trace derived events back toward their source.

## 3.4 Segments and Native Musical Interpretation

Segments represent interpreted musical objects, sounding intervals, or other meaningful units.

This is where concepts such as start/end, duration, retrigger, continuity, note identity, waveform identity, and rhythm identity may be derived.

A Segment is not a raw register event.

Do not invent information at the event/state stage that can only be inferred during Segment construction.

Do not split or merge source Segments solely to accommodate target notation, compression, buffer limits, or regression expectations.

Such operations belong to a later representation unless they reflect a justified change in musical interpretation.

## 3.5 Shared Musical Representation

The shared musical representation, currently represented by `NativePerformance` and related structures, retains interpreted musical information independently of a particular output driver or encoding.

`NativePerformance` is an implementation-level representation of this architectural concept, not a requirement that every future target or subsystem use an identical data structure.

It may include:

- Musical units and sounding spans.
- Pitch, volume, timbre, and other control curves.
- Attack, gate, retrigger, and continuation information.
- Rhythm and waveform identities.
- Native source provenance.
- Relationships between original evidence and interpreted information.

The representation must not be reduced to the capabilities of MGSDRV, a particular sound cartridge, or another current target.

The shared representation may retain information that some targets cannot express.

A target failure must not rewrite or invalidate that retained information.

## 3.6 Target Projection and Encoding

Target projection determines how retained musical information can be represented by a particular sound chip, driver, or output format.

Target-specific decisions may include:

- Pitch and timing quantization.
- Instrument and channel allocation.
- Waveform or FM approximation.
- Envelope and rhythm commands.
- PCM encoding and memory allocation.
- Loops, macros, and notation compression.
- Target-specific resource limitations.

Information loss should occur as late as practical.

Preserve the original information in an earlier inspectable representation and report meaningful target losses explicitly.

Do not rewrite source history to make an unsupported target operation appear valid.

---

# 4. VGM Is a Register Event Stream, Not a Score

VGM contains register writes and timing information, not conventional musical notation.

Potentially meaningful source information includes:

- Key-On and Key-Off timing.
- F-number, BLOCK, or tone-period changes.
- Instrument and volume changes.
- Mixer, noise, and envelope state.
- Programmable waveform changes.
- Retrigger and continuation behavior.
- Pitch changes and portamento-like behavior.
- Register-write ordering.
- Repeated writes that appear musically redundant.

Do not aggressively merge or normalize events merely because they eventually produce the same note.

A sparse-looking event stream may be correct.

Preserve event sparsity unless there is evidence that it is an artifact.

A musical score is an interpretation of source evidence, not a replacement for it.

---

# 5. Preserve Evidence and Derived Meaning Separately

Whenever practical, retain both:

1. The original source-chip representation.
2. The physical or musical quantity derived from it.

For Yamaha FM pitch analysis, this may include:

```text
fnum
block
frequency_hz
```

For PSG, retain the source tone period when deriving frequency.

For SCC, retain waveform data or a stable waveform identity.

For OPM, retain native KC/KF and operator state rather than inventing OPLL-style parameters.

Derived values must not silently replace source evidence.

Keep observed source values, inferred musical meaning, and target-projected values distinguishable.

Typed source register evidence must not silently override edited musical records during target projection.

The source evidence remains authoritative for what was observed; the musical representation owns intentional musical interpretation and edits.

---

# 6. Timing Is Source Evidence

VGM waits are source timing evidence.

The shared VGM source clock accumulates wait samples as integer samples at 44100 Hz.

Chips share the same stream origin. Do not rebase each chip at its first write.

Same-sample writes remain ordered.

A physical sub-tick interval must not disappear merely because a later 60 Hz or musical-grid projection rounds it to zero.

Distinguish:

- Source sample timestamps.
- Physical or reconstructed event timing.
- Musical score steps.
- Target ticks.
- Playback-driver frames.
- Software-envelope hold durations.

These are different concepts and must not be silently substituted for one another.

Source timing must be retained before target quantization.

Tempo and grid inference are interpretations, not source facts.

Preserve inferred parameters and their supporting evidence.

See `docs/vgm_timing.md` and `docs/score_normalization.md` for implementation details and measured limitations.

---

# 7. Key Edges, Retrigger, Continuity, and Zero-Length Events

Retrigger and continuation are distinct.

Retain enough evidence to determine whether:

- A note was newly triggered.
- An existing sounding state continued.
- Pitch or other state changed while the key remained active.
- A new Segment or musical unit is justified.

Do not equate zero target duration with an irrelevant source event.

Same-tick or zero-length events may contain real Key, rhythm, or control edges.

For OPLL, distinguish an inferred musical `onset` from a real source `key_on_edge`.

Volume recovery or another inferred onset is not permission to restart a hardware envelope.

Do not merge a real same-pitch Key-Off/Key-On sequence merely because the resulting pitch is unchanged.

Preserve ordered zero-duration controls.

An instantaneous transition group must include its settling state. Replaying only a zero-duration Key-On can invent a sustained note.

How a target represents an unrepresentable sub-tick event is a target-stage decision.

The original source evidence must remain available.

---

# 8. Chip-Specific Durable Semantics

## 8.1 OPLL / YM2413

Pitch uses FNUM and BLOCK. Preserve both when available.

OPLL volume direction is inverted relative to conventional loudness:

```text
VOL = 0   -> loudest
VOL = 15  -> quietest / near silence
```

Register writes need not arrive in convenient note-oriented order.

Reconstruct effective state without assuming all parameters precede Key-On.

User-defined patch registers are meaningful source data.

Do not silently replace them with perceptually similar presets.

Preserve rhythm trigger edges and channel 6–8 pitch state before target projection.

The final MGSDRV layout may differ between melodic mode and rhythm mode, but layout selection must not delete source Segments.

## 8.2 PSG / SSG

PSG state is not OPLL with different parameters.

Preserve, where relevant:

- Tone period.
- Tone/noise enable state.
- Noise period.
- Mixer state.
- Fixed volume.
- Hardware-envelope state.
- Envelope restart behavior.

Noise and hardware-envelope behavior are musical source data.

If the target requires IDs, macros, or reconstructed commands, retain decoded source state in an earlier pass.

Do not confuse a target note boundary with an observed source envelope restart.

## 8.3 SCC

Programmable waveform data is first-class source information.

Preserve waveform bytes or a stable identity, waveform-change timing, channel use, pitch, and volume where relevant.

Exact equality may be used for stable deduplication.

Stronger normalization requires explicit justification.

Do not discard waveform identity merely because a target represents the sound through FM or another synthesis method.

## 8.4 OPM / YM2151

Native OPM analysis must preserve OPM semantics rather than invent OPLL-like FNUM/BLOCK or preset voices.

Preserve:

- Four operator identities.
- KC/KF.
- Partial Key edges.
- Channel and shared controls.
- Same-time transitions.
- Unknown state where appropriate.

Parameter changes must not create artificial Key-Ons.

Detailed OPM state and target behavior belong in `docs/opm_segments.md` and `docs/opm_mdx.md`.

## 8.5 Additional Native Sources

Additional supported chips must retain their native semantics before musical projection.

Examples include OPN-family FM, DCSG, HuC6280, NES APU/FDS, and native PCM sources.

Do not reinterpret a source as another chip merely because the target uses that chip.

Cross-chip projection may create a useful target representation, but the projected chip state is not the original source evidence.

Keep source identities and source-to-target relationships inspectable.

---

# 9. Rhythm Semantic Layer

Where a common musical rhythm vocabulary is useful, use:

```text
BD
SD
TOM
HH
CYM
RIM
```

This vocabulary describes musical meaning, not source implementation.

Source-specific terminology should remain available in source or diagnostic fields.

Rhythm event/state representations should preserve, where applicable:

- Trigger state.
- Timestamp.
- Volume.
- Source pitch fields.
- Pan.
- Source instrument identity.

Segment construction may derive sounding intervals later.

Do not infer duration earlier than the available evidence justifies.

A target's rhythm-channel layout must not redefine the source rhythm event.

---

# 10. Musical Structure and Score Interpretation

Musical structure is an interpretation derived from source evidence.

Distinguish:

- Source sounding spans.
- Observed attacks and Key edges.
- Inferred score-note boundaries.
- Pitch and duration patterns.
- Control curves and envelope behavior.
- Target notation boundaries.

A source-audibility span does not by itself prove an observed Key-On or score attack.

A held sounding unit may contain an inferred repeated pitch phrase without a corresponding source gate restart.

Keep the boundary evidence and uncertainty explicit.

Source gate identity must remain distinct from boundaries introduced by target ties, rests, or notation.

Target envelope bindings should not become part of immutable note identity.

The musical representation should permit alternative interpretations without destroying original evidence.

---

# 11. Patterns, Envelopes, and Compression

Pattern detection and compression must not destroy the information-preservation pipeline.

First reconstruct complete sounding units and their internal control curves, then detect repeat structures, and only afterward select shared software envelopes for the target. Target envelope selection must not determine the earlier sounding-unit boundaries or score-repeat identity.

A repeated candidate is evidence of structural similarity, not automatic permission to rewrite source Segments.

Prefer reversible structural plans.

Retain mappings from patterns, occurrences, envelopes, and macros back to the original musical units or source events.

Target loops and macros may be selected only when their expansion preserves the required target command semantics.

Do not introduce new note boundaries, attacks, state resets, or quantization merely to improve compression.

## 11.1 Score Patterns

Score repeat candidates should be chip-independent.

When identifying score-level repetition, distinguish musical identity from documentary source details.

Pitch, duration, rests, and attack/continuation relationships may define score similarity without requiring identical source timbre IDs or volume slices.

However, score-level similarity does not establish equivalence of executable source controls.

When score keys omit dynamics or timbre, retain the complete set of source control variants associated with each structural position.

The first occurrence of a motif is not sufficient evidence for choosing a reusable target envelope.

## 11.2 Software Envelopes

Source volume trajectories and attack/restart semantics remain authoritative.

Do not invent unobserved envelope tails.

A repeated envelope-control fragment is not necessarily an independent musical phrase.

Prefer complete sounding gestures and phrases over arbitrary internal holds.

Exact adjacent repetitions may be folded when the operation preserves relative-state accumulation and command semantics.

Target macro slots and envelope-bank capacity must not constrain the shared musical representation.

## 11.3 Hardware Envelopes

A running hardware envelope is not automatically a barrier to score-level repetition.

Do not compare simulated oscillator or envelope phase as score identity.

Do not add hardware resets merely to make a loop entry or repeated phrase appear equivalent.

Preserve original target operations in every emitted iteration unless a separately validated approximation is selected.

For MGSDRV PSG hardware-envelope pitch partitions, adjacent untied notes are significant.

Do not replace these partitions with `&` ties merely to shorten notation.

A tie merges the partitions into a sustained note and prevents the intended envelope restart at each partition.

Gapless adjacent untied notes preserve the distinct attacks.

Loop or macro compression may group these notes but must not merge their attack semantics.

## 11.4 Target Compression

Target output size and MGSDRV buffer limits are real constraints.

Solving them belongs at or near target projection.

Shorter MML is not evidence of a better conversion.

Compiler acceptance, MML character count, compiled size, musical correctness, and source behavioral equivalence are separate validation dimensions.

Exact notation shortening must preserve real attacks, compiler default-length scope, and target command semantics.

Whitespace is not an MGSC tie operator.

Moving a compile-time default-length change into a finite loop requires semantic justification, not merely matching text.

See `docs/melody_patterns.md` and relevant focused documentation for current algorithms.

---

# 12. Source Loops and Target Loops

Declared VGM loops are source structure.

Preserve them without inventing a Key-On or other control event at the loop boundary.

Structural loop candidates should remain reversible until target selection.

Overlapping or nested alternatives may be useful for later macro selection.

## 12.1 Repeated Traversal

Suppressing a redundant register write during the first traversal is not necessarily safe inside a song loop.

A write that appears redundant initially may restore a different state after the end of the preceding iteration.

Check repeated native and target dependencies, including:

- Held pitch and volume state.
- Muted pitch updates.
- Shared register ownership.
- Waveform upload pointers.
- Other evolving chip state.

Do not solve loop entry by resetting unrelated held voices to first-traversal snapshots.

A small number of equal loop traversals does not prove independence from phase or an evolving write pointer.

Either establish that the dependency is handled correctly or reject the unsupported operation explicitly.

Increasing the number of sampled traversals alone is not proof of periodic behavior.

## 12.2 Source Structure Versus Target Execution

A source score guide may propose target loops.

It cannot replace native pitch evidence or impose new envelope restarts.

Target execution must preserve the necessary control operations for every iteration.

Different complete command sequences require expansion or a separately validated approximation.

See `docs/vgm_loop.md` for source-loop details.

---

# 13. Register-Oriented and Score-Normalized Paths

The project contains intentionally different transformation paths.

`vgm2mml.py` is register-oriented: source timing and event semantics have priority over visually regular notation.

`vgm2mml_grid.py` intentionally maps events onto a musical grid.

Optional normalization such as `--normalize-lengths` is a target-stage inference.

It must not rewrite native source timestamps or Segment evidence.

Keep the distinction explicit:

```text
source-faithful interpretation
    !=
intentional quantization or normalization
```

## 13.1 Score Timing

Score normalization uses original integer VGM sample spans through musical interpretation.

Note values are derived at an explicit reference tempo.

Do not use a reference VGM's already warped gates to recover original note durations.

Keep musical score steps separate from driver-frame software-envelope holds.

Coarse score clocks require explicit interval mapping and displacement diagnostics.

Do not silently delete short positive-duration notes because they disappear after quantization.

Keep original and projected curves separate.

Post-clock clipping may invalidate an approximation budget that appeared acceptable before quantization.

See `docs/score_normalization.md` for detailed rules.

---

# 14. Target Formats Are Not Canonical Internal Representations

MGSDRV MML/MGS, Blueprint NDP MML, MIDI (SMF), and VGM outputs have different capabilities and constraints.

Do not shape source state, Segments, or shared musical information solely around one target's syntax.

Target-specific choices may include:

- Duration quantization and encoding.
- Instrument commands.
- Noise and envelope commands.
- Waveform definitions.
- Rhythm commands.
- Ties, rests, and gates.
- Loops and macros.
- Channel and buffer allocation.
- PCM format and memory limits.
- Target-specific timing.

A target may intentionally approximate or discard information it cannot represent.

When this happens:

1. Preserve source information in an earlier inspectable stage.
2. Make the interpretation or approximation explicit.
3. Perform the loss in target projection.
4. Record meaningful loss and omission diagnostics.
5. Do not alter earlier representations to pretend the source lacked the information.

Target-specific resource limitations must not become shared musical invariants.

MGSDRV syntax references:

- https://p.gigamix.jp/mgsdrv/MGSDR320.TXT
- https://z80.msx.click/index.php?title=MGSDRV_MML_11_JP

---

# 15. Independent Source Products and Output Projections

Build and retain source musical information before output-specific execution lowering.

Independent output paths must not depend unnecessarily on one another.

A valid source performance remains available to independent score and reference backends even if MGS projection fails.

Keep each artifact's outcome and failure cause separate.

Do not label a retained previous artifact as a newly generated success.

Successful legacy execution remains a distinct target projection.

When selecting native reference output, validate that target preparation has not substituted projected chip data for the original source performance.

This must be checked after successful target lowering as well as after failure.

An explicit partial projection must identify omitted source parts and retain original event links.

Failure to map one target part does not establish that all source parts are unmappable.

---

# 16. Editable Score Blueprints

An editable score Blueprint is a separate target projection of retained musical source evidence.

It deliberately omits executable synthesis and dynamics from the score representation while preserving the original curves and controls in the shared musical information.

The Blueprint must not redefine the original source performance.

Preserve, where relevant:

- Source gates.
- Attack and continuation decisions.
- Lane mappings.
- Original device identity.
- Projection losses.
- Source-to-score relationships.

Blueprint text and MIDI are encodings of the same projected score spans.

Derive both from the projected score representation before notation or macro compaction.

Do not reparse final MML text or rerun source interpretation independently for each encoding.

Keep original-device identity and explicit target pitch/time losses in the score sidecar.

MIDI audition defaults must not restore source synthesis or overwrite source dynamics.

A fixed audition initialization may set constant volume and a neutral instrument, but it must remain a target convenience.

It must not influence score-repeat equality or source musical interpretation.

Preserve user-edited templates without preventing other output paths.

A source score guide is not a one-to-one target note map.

Initially retain existing source boundaries where envelope-phase handling is unresolved.

Do not introduce guide cuts that require unsupported envelope restarts or phase reconstruction.

See `docs/musical_blueprint.md`.

---

# 17. Cartridge VGM Variants and Cross-Chip Projection

Cartridge VGM variants consume `NativePerformance` directly.

They are independent target projections of retained musical information, not reconstructions derived from final MML/MGS output.

Keep the source performance separate from the target-specific VGM encoding.

## 17.1 Musical Authority and Source Evidence

Preserve decoded PCM content separately from its original transport representation.

Keep reusable PCM sample assets separate from playback occurrences, including their start and stop times, playback rates, levels, and loop behavior. Sharing or merging sample assets does not by itself authorize merging or dropping playback occurrences. A target approximation must retain source-to-target playback mappings and report changes to playback behavior explicitly.

Native musical curves own projected pitch, level, timbre, and gates.

Typed source register evidence remains available for provenance and source-specific behavior.

It must not silently override intentionally edited musical records.

The shared musical plan separates interpreted units, control curves, and native provenance from the initial target profile and output encoding.

MML envelope-bank capacity, macro syntax, and compiler buffers must not limit direct VGM projection.

## 17.2 Cross-Chip Adaptation

A retained target VGM may adapt native source analysis into an established target pipeline.

However:

- Native source State and Segments must remain separately inspectable.
- Source-to-target event relationships must remain available.
- Later target-chip Segments must not be presented as original source evidence.
- Cross-chip register equality is not an appropriate equivalence criterion.

A useful approximation does not imply identical sound or behavior.

Backend-specific losses must be reported explicitly rather than redefining common musical information.

## 17.3 Shared Target Resources

When multiple target parts share a register, waveform memory, or other hardware resource, per-part caches alone may be insufficient.

Reconcile final positive-time shared demand after zero-time ownership transitions.

A transient owner must not leave its state on a continuing voice.

Shared chip operations remain ordered even outside notes.

For FM targets, Key-Off must preserve frequency while the release tail remains audible.

An inactive score gate does not imply immediate oscillator silence.

Target-specific resource conflicts must be resolved in the target projection, not by rewriting source evidence.

## 17.4 Target Capacity and Loss

Target channel counts, PCM memory, and available synthesis features may require approximation or omission.

Evaluate capacity using the actual target storage and allocation format, including required terminators, reference tables, alignment, and other mandatory overhead. Note or sample payload size alone is insufficient; distinguish encoded storage size from decoded or runtime buffer requirements.

Distinguish unsupported semantics from capacity exhaustion, implementation failure, and unverified behavior.

Do not silently substitute an unrelated target sound or omit a source part merely to generate a valid VGM.

Keep source identity and diagnostic evidence available.

See `docs/musical_vgm_variants.md` for supported profiles, conversion behavior, and limitations.

---

# 18. Validation: Correctness Has Multiple Meanings

Keep the following objectives separate.

**Register correctness**

Reconstruct source-chip state and observable behavior accurately.

**Musical correctness**

Represent the interpreted performance usefully and consistently with source evidence.

**Target correctness**

Produce valid target data within the target's constraints.

Also distinguish:

- Audible similarity.
- Source behavioral equivalence.
- Target command equivalence.
- Compiler acceptance.
- Textual and compiled-size optimization.
- Emulator playback.
- Physical hardware playback.

A final MML or VGM file, successful compilation, matching event count, or passing test suite is not sufficient by itself to prove conversion correctness.

For non-trivial behavior changes, inspect relevant intermediate results before and after the change.

Validate more than one representative piece where practical.

Real hardware, emulator behavior, compiler roundtrips, code inspection, generated diagnostics, and subjective listening provide different kinds of evidence.

Record which kind supports a conclusion.

Do not claim physical hardware compatibility based solely on emulator or software-renderer results.

Do not overfit a general rule to one song or fixture.

---

# 19. Tests and Fixtures

Fixtures should make specific behaviors reproducible.

Where practical, tests should cover relevant layers:

```text
Source VGM
    |
    v
Raw / State Trace
    |
    v
Analysis Passes
    |
    v
Segments / Native Performance
    |
    v
Target Projection
    |
    v
Generated Output
```

Do not blindly update expected artifacts when a regression test fails.

First determine whether:

1. The implementation violated source semantics.
2. Native state or musical interpretation is incorrect.
3. The shared representation lost necessary information.
4. The target projection is incorrect.
5. The test expectation encodes obsolete or incorrect behavior.

Never change an intermediate representation solely to satisfy an expected artifact.

A fixture is an oracle only for the behavior it was designed and justified to test.

Private copyrighted source material must not be copied into tracked documentation or fixtures unless explicitly safe to commit.

---

# 20. Human-Readable Intermediate Output

Intermediate output should favor diagnosis over compactness.

Use explicit names with stable semantics.

Prefer `frequency_hz` for physical frequency while retaining source representations such as `fnum`, `block`, or `tone_period`.

Do not fill non-applicable fields with misleading values.

Use empty/null values or chip-specific schemas.

Preserve enough timestamps, channel/source indices, pattern and occurrence IDs, and other identifiers to trace target behavior back toward source evidence.

PASS files generated by `--dump-passes` are part of the project's diagnostic contract, not arbitrary temporary dumps.

Target projection diagnostics should identify meaningful approximation, omission, and uncertainty without obscuring the original source information.

---

# 21. Development and Documentation Boundaries

For non-trivial conversion changes, use the existing repository workflow in `AGENTS.md`.

The technical investigation should establish:

- What the existing implementation does.
- Which transformation stage owns the behavior.
- What source and intermediate evidence supports the current interpretation.
- Which hypothesis is being tested.
- What information would change or be lost.
- How the proposed change can be validated.

Do not jump from a failing final artifact directly to reshaping Segments or earlier passes.

Before changing established behavior, identify why it exists.

Keep documentation responsibilities separate.

## 21.1 `AGENTS.md`

Short, always-on operating rules, repository navigation, and development workflow.

## 21.2 `docs/collaboration_principles.md`

How AI agents should understand intent, exercise technical judgment, communicate uncertainty, and respect the owner's decision authority.

## 21.3 `docs/project_knowledge.md`

Stable architecture, transformation principles, and durable chip/domain knowledge.

## 21.4 Focused `docs/*.md`

Detailed subsystem designs, target-specific behavior, implementation contracts, and established technical decisions.

## 21.5 External `field_notes/*.md`

Dated experiments, measurements, fixture-specific findings, regressions, rejected approaches, and provisional conclusions.

A finding should move into project knowledge only when it becomes a stable principle or durable domain rule.

Do not append implementation history to this document merely because it may be useful later.

---

# 22. Final Rule

When uncertain whether to simplify, merge, split, normalize, quantize, discard, or reinterpret data:

1. Preserve the source evidence.
2. Expose it in an inspectable intermediate result.
3. Make the interpretation explicit.
4. Defer irreversible loss until the appropriate target stage.
5. Ask whether a human can still trace the final result back toward the VGM.

If the answer to step 5 becomes "no", the change requires strong justification.

The central design question is not:

> How can we make this conversion simpler or make this test pass?

It is:

> What information is being changed or lost here, at which transformation stage, and is that loss intentional?

A final target file is not sufficient evidence that the conversion is correct.

The path from source register stream to musical interpretation and target output must remain inspectable.

**Preserve source evidence, maintain independent musical meaning, and make target-specific compromises explicit.**


