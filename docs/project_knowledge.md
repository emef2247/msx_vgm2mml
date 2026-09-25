# Project Knowledge — msx_vgm2mml

## Purpose

This repository converts VGM data for MSX sound hardware into MGSDRV MML.

The final MML is important, but it is **not the only important output of the project**.
The highest-priority engineering requirement is that the conversion process remain
observable through intermediate results.

A conversion that produces plausible MML but hides how it reached that result is
harder to validate, debug, improve, and explain. Therefore this project treats
intermediate data as a first-class part of the converter architecture.

---

## 1. Highest-priority principle: generate intermediate results

**Generating and preserving inspectable intermediate results is the highest-priority
design principle of this project.**

Whenever the converter performs a meaningful transformation, the state before and
after that transformation should be inspectable whenever practical.

The preferred development model is not:

```text
VGM -> MML
```

but:

```text
VGM
  -> raw events / register trace
  -> reconstructed chip state
  -> interpreted musical segments/events
  -> optional timing/grid transformation
  -> MGSDRV representation
  -> final MML
```

Intermediate files are not temporary clutter. They are evidence showing what the
converter believed at each stage.

### Why this matters

The source VGM contains hardware-oriented facts: register writes and waits. MML
contains a musical/programming interpretation of those facts. Between them are
decisions about frequency, note boundaries, key state, volume, envelopes,
instruments, SCC waveforms, OPLL rhythm, legato/retrigger, timing and quantization.

Intermediate results should make it possible to answer questions such as:

- Was the VGM register write parsed correctly?
- Was chip state reconstructed correctly?
- At what timestamp did the converter decide a note started or ended?
- Was a pitch change interpreted as a new note, legato, vibrato, or portamento?
- Was an OPLL rhythm event expanded correctly?
- Was a PSG mixer/noise/envelope state interpreted correctly?
- Was an SCC waveform identified correctly?
- Did an error appear before or after grid quantization?
- Is the final difference caused by source interpretation or merely MML rendering?

### Required behavior for new work

When adding a new non-trivial processing stage:

1. Define what information enters the stage.
2. Define what information leaves the stage.
3. Preserve enough source identity (timestamp/tick, channel, register/state/event
   identity) to trace the output backward.
4. Provide a human-readable dump when practical, preferably CSV for tabular event data.
5. Do not destroy the previous-stage value merely because a normalized or quantized
   value is easier for the next stage.
6. Validate changes by looking at the relevant intermediate representation, not only
   by listening to or compiling final MML.

`vgm2mml.py` already exposes `--dump-passes`; preserving and extending this
observability is preferred over hiding stages.

---

## 2. Keep transformation layers separate

The conceptual model is:

```text
Raw -> State -> Segment -> Target
```

These boundaries are intentional.

### Raw

Facts obtained directly from the VGM stream:

- VGM command order
- waits / timestamps
- chip register writes
- data blocks or waveform-related source data where applicable

Raw data should contain as little musical interpretation as possible.

### State

Hardware state reconstructed from raw writes:

- register-derived frequency state
- key/rhythm state
- volume state
- instrument/patch state
- PSG mixer/noise/envelope state
- SCC waveform/channel state
- other chip state needed to interpret audible behavior

State is derived from raw events, but it should still describe the chip rather than
MGSDRV syntax.

### Segment / interpreted event

Musical or behavioral interpretation built from state over time:

- note/rest segments
- onset and duration
- pitch/frequency interpretation
- volume changes
- instrument changes
- rhythm events
- legato/retrigger decisions
- vibrato/portamento/envelope-related interpretation
- SCC waveform identity/use

This layer may contain inference. Inferred information must not silently replace the
source-derived information used to produce it.

### Target

MGSDRV-specific representation:

- note spelling and length notation
- raw `%` tick notation where supported by the converter
- MML commands
- instrument/envelope/waveform definitions
- rhythm track syntax
- compression or delta-token choices
- grid-aligned note lengths
- ties / dotted-note representation
- formatting and allocation choices

Target limitations must not redefine source truth in earlier layers.

---

## 3. Two conversion paths have different purposes

### `vgm2mml.py`

Supports PSG, OPLL, and SCC and aims to generate MML closely reflecting
register-level source behavior.

Its intermediate/pass outputs are especially important because this path attempts to
preserve source behavior rather than first forcing events onto a musical grid.

### `vgm2mml_grid.py`

Currently OPLL-specific. It quantizes events to a step grid and supports user-defined
OPLL patches and rhythm instruments.

Grid timing is a **target-side transformation**. A quantized onset or duration must
not be confused with the original VGM timestamp/duration.

When debugging this path, retain or reconstruct the distinction between:

```text
source timing -> interpreted timing -> quantized timing
```

A quantization improvement should not require rewriting source interpretation unless
the source interpretation itself is demonstrated to be wrong.

---

## 4. Intermediate data should be useful to humans

Intermediate output exists partly so a person can inspect the converter's reasoning
without reading Python internals.

Depending on the stage/chip, useful fields can include:

- source timestamp / tick
- channel
- register/value or source event identity
- frequency / FNUM / block / period as applicable
- key state
- volume
- instrument / patch
- mixer state
- noise state
- envelope state
- waveform ID
- segment start/end/duration
- interpreted note
- onset / IOI
- legato/retrigger markers
- rhythm instrument/event
- pre-quantization timing
- post-quantization timing

Do not add every possible field everywhere. Preserve the information needed to
explain the transformation performed by that stage.

CSV is preferred for event/pass data because it is easy to diff, filter, inspect,
and process independently.

---

## 5. Traceability over convenience

A final MML event should be traceable backward through the conversion pipeline as
far as practical.

When choosing between a smaller internal structure that discards provenance and a
slightly larger structure that preserves timestamp/channel/source identity, prefer
traceability unless there is a demonstrated correctness or performance reason not to.

For example:

```text
raw_tick       -> segment_tick      -> quantized_tick
raw_frequency  -> interpreted_note  -> MML note spelling
raw_volume     -> interpreted level -> MGSDRV volume command
```

The exact field names may differ. The separation is what matters.

---

## 6. Chip-specific knowledge belongs behind the common pipeline

PSG, OPLL, and SCC behave differently. Do not force them into identical chip-state
structures merely for architectural symmetry.

### OPLL

OPLL processing may involve melodic channels, preset/user patches, key state,
frequency state, volume, and rhythm mode. Rhythm handling and user-patch handling
must remain inspectable before final MML rendering.

### PSG

PSG interpretation may depend on tone period/frequency, channel volume, mixer state,
noise, and envelope behavior. These source/state concepts should remain visible
independently of how MGSDRV ultimately expresses them.

### SCC

SCC processing includes waveform state in addition to pitch/volume/channel behavior.
Preserve waveform identity/data relationships sufficiently to explain which waveform
the generated MML uses and when it changes.

Detailed chip facts should be added here only after verification from code,
experiments, hardware/reference testing, or trusted specifications.

---

## 7. Timing is evidence

Timing must be treated as source information before it becomes notation.

Do not prematurely convert source timing into note values, dotted notes, ties, or
grid steps. Those are representations of timing, not the timing itself.

Where practical, preserve an integer/raw timing representation until the Target stage.

For grid conversion, keep measured/interpreted event timing separate from snapped
grid timing. Tempo or grid detection is an inference and must not destroy the
original timing evidence.

---

## 8. Interpretation must remain revisable

Many transformations from chip activity to musical notation are interpretations
rather than direct facts.

Examples include deciding whether closely related pitch changes represent:

- separate notes
- legato
- vibrato
- portamento
- envelope-related behavior

Avoid structures where an early heuristic irreversibly erases observations that a
different interpretation would need.

When an interpretation rule changes, compare intermediate results before and after
the change.

---

## 9. MGSDRV / MGSC MML is the target specification

MGSDRV MML syntax must not be guessed from generic MML knowledge.

Before adding, changing, optimizing, or diagnosing generated MML syntax, consult the
MGSDRV/MGSC references below.

### Primary references

1. **MGSDRV ver.3.20 documentation (`MGSDR320.TXT`)**
   - https://p.gigamix.jp/mgsdrv/MGSDR320.TXT
   - This is documentation distributed for MGSDRV ver.3.20.
   - The current Gigamix MGSDRV page identifies ver.3.20 as the current driver
     release and explicitly directs users to read `MGSDR320.TXT`.

2. **MGSC MML compiler ver.1.11 documentation / Japanese transcription**
   - https://z80.msx.click/index.php?title=MGSDRV_MML_11_JP
   - This documents the MML accepted by MGSC 1.11, including control directives,
     definitions, track syntax, and MML commands.

These references serve different roles: MGSDRV is the playback driver, while MGSC is
the compiler that converts textual MML into MGS data. For generated MML syntax, the
MGSC MML documentation is therefore particularly important.

### Source hierarchy for MML syntax

When deciding whether generated syntax is valid, use this order:

```text
MGSDRV / MGSC original documentation
        ↓
MGSC 1.11 Japanese documentation/transcription
        ↓
known working MML examples / compiler tests
        ↓
current converter behavior
        ↓
assumption
```

Do not preserve converter behavior merely because it already exists if it conflicts
with verified MGSC syntax.

Conversely, do not "correct" working syntax from memory. Check the references or
compile a minimal test first.

### Important documented MGSC concepts

The MGSC 1.11 documentation includes, among other things:

- `#opll_mode <0|1>`
- `#machine_id`
- `#lfo_mode`
- `#title`
- `#alloc`
- `#psg_tune`
- `#opll_tune`
- `#tempo`
- macro definitions and `#macro_offset`
- FM/PSG/SCC-related tone, envelope, waveform and volume definitions
- track/MML commands for tempo, default length, gate, volume, instrument, octave,
  notes/rests, loops, detune and other playback controls

Do not copy this list into implementation as a substitute for reading the actual
syntax definition when changing a command.

### `#opll_mode`

MGSC documents `#opll_mode` as mandatory before other control/MML commands.
Mode 0 is FM 9-channel mode and mode 1 is FM 6-channel + rhythm mode.

The converter must choose target mode based on the intended generated track layout,
not by rewriting source evidence to fit the mode.

### `#alloc`

MGSC allocates track buffers and allows explicit `#alloc` declarations. The
documentation states that total track buffer allocation is limited to 16 KiB.

This is a **Target-layer constraint**.

If output must be reduced to satisfy allocation limits, optimize the MML representation
without discarding or rewriting earlier intermediate evidence. Intermediate CSV/pass
data must remain the full explanation of the conversion even if final MML is
compressed.

### `#tempo` and timing

MGSC has both target-side tempo concepts and musical length syntax. These are not a
replacement for VGM source timing.

The pipeline must remain:

```text
VGM timing
    -> interpreted segment timing
    -> target tempo / note-length representation
```

Never reason backward from a convenient MML note length and overwrite the source or
segment timing to make it fit.

### Instrument, envelope and waveform definitions

MGSC documentation defines target-side facilities including PSG envelope definitions,
SCC waveform definitions, volume-related definitions, and OPLL/FM tone assignment
and definition mechanisms.

These are Target representations of chip-derived behavior.

Keep source chip state and target definition numbers separate. For example, an SCC
waveform observed in VGM should retain a stable source/intermediate identity even if
the final MML assigns it a different `@s` number.

Likewise, an OPLL user patch should remain inspectable in chip-oriented form before
being serialized into MGSC-compatible tone syntax.

### Raw register-style / special commands

MGSC contains commands capable of expressing behavior below ordinary note notation.
Use such commands only according to documented syntax and only at the Target layer.

Do not use a low-level MML escape as an excuse to skip reconstruction of an
intermediate state when that state is important to understanding the conversion.

---

## 10. MML generation must be separately testable

MML rendering should be treated as its own transformation stage.

For a difficult MML syntax issue, prefer a minimal test such as:

```text
known intermediate event(s)
        ↓
MML renderer
        ↓
small .MUS/MML fragment
        ↓
MGSC compilation check
```

This separates:

- VGM interpretation bugs
- segment-generation bugs
- MML syntax bugs
- MGSC/compiler limitations

Do not use a complete game VGM as the only way to test one MML command.

When MGSC itself is available locally, successful compilation is strong evidence of
syntactic validity, but it does not prove that musical interpretation was correct.

---

## 11. Final MML fidelity comes after source fidelity

MGSDRV has syntax and practical constraints. The generated MML may require
target-specific choices or compromises.

Those compromises belong at the Target layer.

Do not alter earlier source/state/segment data merely to make MML prettier, shorter,
or easier to compile unless that tradeoff is explicitly intended.

---

## 12. Validation workflow

For a conversion-behavior change, prefer this order:

```text
1. Identify a reproducible source VGM / fixture.
2. Capture or generate the relevant raw/trace output.
3. Generate intermediate pass output.
4. Identify the first stage where actual behavior diverges from expected behavior.
5. Change the smallest responsible stage.
6. Regenerate intermediate outputs.
7. Diff/inspect the affected stage and downstream stages.
8. Generate final MML.
9. If MML syntax changed, check the MGSDRV/MGSC documentation.
10. Compile the generated MML with MGSC when available.
11. Play/listen when the required environment is available.
12. Record a stable discovery in project knowledge or a field note.
```

Do not begin with final MML and infer the cause solely from that representation when
earlier evidence is available.

---

## 13. Tests and fixtures

Automated tests and real VGM fixtures serve different purposes.

- Automated tests protect deterministic parsing/transformation rules with small,
  reproducible cases.
- Real VGM fixtures validate behavior emerging from realistic event sequences.
- Private or game-derived fixtures should stay outside git unless explicitly safe
  to distribute.
- Intermediate CSVs produced from private fixtures should also be treated as private
  if they expose source-derived content.

When fixing a bug, add a compact synthetic regression test when practical, while
still using real intermediate output for investigation when needed.

---

## 14. Documentation rule

Record knowledge according to its lifetime:

- Stable architecture/domain rule -> `docs/project_knowledge.md`
- Short always-on agent instruction -> `AGENTS.md`
- One-off experiment / observation -> `field_notes/` when present
- Repeated trap / known wrong approach -> `mistaken.md` when present
- Generated evidence -> output/pass files, normally not hand-written documentation

Do not turn `AGENTS.md` into a large chip or MML manual. It should tell an agent how
to work. This file records stable knowledge and points to authoritative specifications.

---

## 15. Current confirmed repository facts

As currently documented in the repository:

- `vgm2mml.py` supports PSG, OPLL, and SCC.
- `vgm2mml.py` has `--dump-passes` for intermediate files.
- `vgm2mml.py` has `--debug` and `--raw-ticks` modes.
- `vgm2mml_grid.py` currently supports OPLL.
- `vgm2mml_grid.py` supports user-defined OPLL patches and rhythm instruments.
- The Python modules include dedicated PSG, OPLL, SCC, VGM reader, segment, and MML
  utility code.

When these facts change, update this document only after confirming the
implementation and README.

---

## Core rule in one sentence

**Never let the final MML become the only surviving explanation of what happened
during conversion: preserve intermediate evidence so every important interpretation
can be inspected, challenged, and improved.**
