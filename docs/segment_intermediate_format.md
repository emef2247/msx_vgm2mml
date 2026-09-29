# Segment / Intermediate CSV Enhancement Requirements

## 1. Goal

Extend the current Segment and intermediate CSV architecture so that it can represent:

* Yamaha FM melodic channels
* Yamaha preset rhythm instruments
* PSG / SSG
* SCC

without losing source-chip information and without forcing fundamentally different chip architectures into one lowest-common-denominator structure.

The purpose is **not** to create one universal register representation.

The purpose is to establish a stable musical/semantic intermediate layer while retaining chip-specific evidence needed for analysis and future targets.

The existing principle remains:

**Raw Register Writes → Chip-Specific State / Events → Analysis Passes → Segments → Target**

---

## 2. Preserve the Current PSG/SCC Direction

The current `Segment`, `PsgSegment`, and `SccSegment` approach should be treated as the starting point.

Do not flatten PSG and SCC fields into the base `Segment` merely to make all CSVs have identical columns.

Common fields belong in the base Segment only when they have genuinely common semantics.

Chip-specific fields should remain in chip-specific Segment types.

`pass3_row` or an equivalent source-evidence mechanism should remain available until all important legacy fields have explicit semantic representations.

Do not remove it merely because the new schema appears cleaner.

---

## 3. Define a Small Common Semantic Core

Review the current base `Segment` and redefine it around information that is genuinely meaningful across sound-chip families.

Candidate common concepts include:

```text
source_chip
channel
start
end
frequency_hz
volume
pan
```

Not every field must be mandatory.

Do not invent values for chips that do not support a concept.

In particular, distinguish carefully between:

```text
source representation
```

and:

```text
interpreted physical / musical meaning
```

For example:

```text
FNUM + BLOCK       = Yamaha FM source representation
tone_period        = PSG/SCC source representation
frequency_hz       = common interpreted physical quantity
```

Both representations may coexist intentionally.

---

## 4. Do Not Over-Generalize Pitch

Pitch representation differs by chip family.

### Yamaha FM

Preserve where applicable:

```text
fnum
block
frequency_hz
```

`FNUM/BLOCK` must not be discarded merely because `frequency_hz` can be derived from them.

### PSG / SCC

Preserve:

```text
tone_period
frequency_hz
```

where frequency can be meaningfully derived.

Do not rename all of these fields to a generic `pitch` and lose their source meaning.

---

## 5. Yamaha FM Segment Support

Enhance the intermediate representation so that Yamaha FM-family melodic channels can use the same Segment architecture.

The initial target is OPLL, but the representation should not be designed so narrowly that later OPN / OPNA / OPN3 / OPL-family support becomes difficult.

A Yamaha FM melodic Segment may contain concepts such as:

```text
source_chip
channel

start
end

fnum
block
frequency_hz

instrument
volume
pan
```

plus chip-specific fields where required.

Do not attempt to define a universal FM register structure at this stage.

OPLL-specific instrument/register information may remain OPLL-specific.

---

## 6. Add a Semantic Rhythm Segment

Introduce a rhythm representation for chips with dedicated rhythm instruments.

Use the common semantic vocabulary:

```text
BD
SD
TOM
HH
CYM
RIM
```

Use `CYM` as the common semantic name.

Source-specific names such as `TOP` or `TOP-CY` may remain in diagnostic/source fields but should map to semantic `CYM`.

The common rhythm representation should be usable by at least:

```text
OPLL rhythm
OPNA rhythm
OPN3 rhythm
```

without assuming that those chips generate the sound in the same way.

---

## 7. Rhythm Source Events and Rhythm Segments Are Different

Do not immediately turn register trigger bits into musical note objects.

At the source/event stage preserve information such as:

```text
timestamp
instrument
trigger / key state
fnum
block
frequency_hz
volume
pan
```

where applicable.

Then derive a rhythm Segment only when start/end can be inferred.

A rhythm Segment may contain:

```text
instrument
start
end
frequency_hz
volume
pan
```

plus retained source fields where useful.

A Segment representing a sounding interval normally does not need a separate `key_on` member because `start/end` already express that interpretation.

However, the original trigger/key transition must remain inspectable in an earlier representation.

---

## 8. OPLL Rhythm Must Preserve Frequency Information

OPLL rhythm uses melodic-channel frequency state as part of rhythm generation.

Therefore preserve:

```text
fnum
block
frequency_hz
```

for OPLL rhythm events/segments where applicable.

Do not discard these fields merely because an OPNA/OPN3 rhythm target would ignore them.

Example:

```text
OPLL TOM
    fnum
    block
    frequency_hz
    volume
```

may later map to:

```text
OPN3 TOM
    volume
    pan
```

The loss of frequency information occurs at target projection, not in the source intermediate representation.

---

## 9. OPNA / OPN3 Rhythm Must Be Representable

Design the rhythm semantic layer so that future OPNA/OPN3 input can preserve:

```text
BD
SD
TOM
HH
CYM
RIM

trigger
volume
pan
```

and any relevant chip-specific level/state information.

Do not model OPNA/OPN3 rhythm as if it were OPLL rhythm.

They share semantic drum identities but not the same synthesis implementation or register model.

---

## 10. PSG Segment Requirements

Keep PSG-specific musical/source state outside the generic Segment where appropriate.

Preserve at least the already interpreted concepts such as:

```text
tone_period
frequency_hz
volume

tone/noise mode
noise_period

envelope_enabled
envelope_period
envelope_shape

mixer
amplitude_register
```

Do not reduce PSG Segment to only frequency and volume.

Noise, mixer and envelope state are part of the source performance.

Review whether `mode` should remain a derived convenience field while the underlying mixer/noise/envelope evidence is also retained.

---

## 11. SCC Segment Requirements

Keep SCC-specific information such as:

```text
tone_period
frequency_hz
volume

enabled

waveform_id
waveform data
enable_register
```

and any state required to explain waveform transitions.

Waveform data is first-class musical/source information.

Do not reduce SCC to:

```text
frequency + volume + instrument number
```

unless the waveform-to-instrument mapping remains losslessly inspectable.

Stable waveform IDs are useful, but the ID → waveform-data mapping must remain available.

---

## 12. Intermediate CSVs Must Be Human-Inspectable

Intermediate CSV output is a first-class project artifact.

The enhanced Segment dump should make it possible to understand an event without repeatedly reconstructing hidden state from previous rows.

Intentional redundancy is acceptable.

For example, an FM Segment CSV may contain:

```text
source_chip
channel
start
end
fnum
block
frequency_hz
instrument
volume
pan
```

A PSG Segment CSV may contain:

```text
source_chip
channel
start
end
tone_period
frequency_hz
volume
mode
noise_period
envelope_enabled
envelope_period
envelope_shape
mixer
```

An SCC Segment CSV may additionally contain waveform identity.

A Rhythm Segment CSV may contain:

```text
source_chip
instrument
start
end
fnum
block
frequency_hz
volume
pan
```

Fields that do not apply to a chip should not be populated with invented values.

Separate chip-specific CSV schemas are acceptable.

Identical CSV columns across all chips are **not** a requirement.

---

## 13. Keep Raw Evidence Separate from Semantic Fields

The current `pass3_row` mechanism preserves the exact analyzed source row.

Keep this principle during the migration.

The goal should eventually be to give important values explicit semantic names, but do not remove raw evidence prematurely.

The preferred relationship is:

```text
raw/pass row
    ↓
named source fields
    ↓
derived physical fields
    ↓
Segment semantics
```

not:

```text
raw/pass row
    ↓
replace with normalized Segment
    ↓
original evidence lost
```

---

## 14. Start / End and Key-On / Key-Off

Review the current timing members:

```text
time
ticks
l
tick_start
tick_end
```

and clarify their semantics.

The desired conceptual model is:

```text
source event:
    timestamp / tick
    trigger state

segment:
    start
    end
```

Do not rename fields solely for aesthetics if doing so causes unnecessary compatibility changes.

However, new code should clearly distinguish:

```text
source timestamp
segment start
segment end
duration
```

Avoid carrying `key_on` into Segment when it is redundant with a sounding interval.

---

## 15. Volume Must Preserve Source Meaning

Do not immediately force all chip volumes into one normalized scale.

Preserve source volume representation first.

A normalized or MIDI-like value may be added later as a derived semantic value if useful.

For example:

```text
source_volume
volume_normalized
```

may coexist.

Do not silently replace:

```text
OPLL VOL
PSG amplitude
SCC volume
OPNA rhythm level
```

with one generic numerical field unless the conversion semantics are explicitly defined.

---

## 16. Pan Should Be Supported but Optional

Add semantic pan support where the source provides it.

This is particularly relevant for future Yamaha chips such as OPNA/OPN3 rhythm.

Do not invent pan for OPLL, PSG or SCC merely to fill the field.

The representation should allow:

```text
pan = unavailable
```

as a valid state.

---

## 17. No Target-Specific Assumptions in Segment

Segment must not become an MGSDRV-specific structure.

Do not add fields solely because MGSDRV syntax requires them.

Likewise, do not remove information because MGSDRV cannot express it.

The same Segment architecture should remain useful for:

```text
MGSDRV MML
MS2
future MIDI output
future FM-chip conversion
analysis tools
```

Target projection is responsible for approximation and information loss.

---

## 18. Backward Compatibility

The current PSG/SCC conversion behavior should remain functionally unchanged unless a deliberate behavior change is documented.

Existing tests and reference outputs should continue to pass where semantics have not intentionally changed.

Schema changes to intermediate CSVs are allowed, but:

1. document them;
2. preserve equivalent or richer information;
3. do not silently remove diagnostic evidence.

Do not perform a large rewrite of PSG/SCC renderers merely to adopt the new Segment classes.

---

## 19. Implementation Strategy

Prefer incremental implementation.

Suggested order:

1. Audit the current `Segment`, `PsgSegment`, `SccSegment`, and OPLL segment structures.
2. Document the semantic meaning of every existing field.
3. Identify the smallest genuinely common Segment core.
4. Add explicit physical fields such as `frequency_hz` without removing source pitch fields.
5. Bring OPLL melodic Segments into the same architectural model.
6. Add semantic rhythm event/Segment structures.
7. Migrate OPLL rhythm to the new rhythm representation.
8. Extend CSV dumps.
9. Add tests for information preservation.
10. Only then consider future OPNA/OPN3 support.

Do not implement OPNA/OPN3 parsing in this task unless required to validate the representation.

The immediate goal is to make the intermediate model capable of representing them later.

---

## 20. Acceptance Criteria

The enhancement is successful when:

* OPLL, PSG and SCC can all produce explicit Segment objects.
* The base Segment contains only genuinely common semantics.
* PSG-specific noise/mixer/envelope information remains preserved.
* SCC waveform information remains preserved and traceable.
* Yamaha FM source pitch can preserve FNUM/BLOCK and derived frequency.
* OPLL rhythm can be represented using semantic `BD/SD/TOM/HH/CYM`.
* The rhythm model can represent `RIM` for future OPNA/OPN3 input.
* Rhythm frequency information is retained where the source provides it.
* Optional pan can be represented without inventing values.
* source events and interpreted Segments remain conceptually distinct.
* zero-length or same-timestamp source transitions remain traceable.
* intermediate CSVs remain human-readable and diagnostically useful.
* `pass3_row` or equivalent raw evidence is not prematurely discarded.
* MGSDRV/MS2 limitations do not shape the source/intermediate model.
* existing PSG/SCC behavior does not regress without an explicit reason.
* tests demonstrate that source information survives through Segment construction.

---

## 21. Architectural Rule

When deciding whether a field belongs in the common Segment, ask:

> Does this field describe a genuinely common musical/physical concept, or merely how one chip implements that concept?

If it is genuinely common, it may belong in the shared semantic layer.

If it describes a chip implementation, preserve it in the chip-specific layer.

Examples:

```text
frequency_hz     → common physical meaning
volume           → potentially common semantic meaning, but source value must remain distinguishable
pan              → common when available

fnum             → Yamaha FM specific
block            → Yamaha FM specific
tone_period      → PSG/SCC source specific
noise_period     → PSG specific
waveform_hex     → SCC specific
envelope_shape   → PSG specific
```

The goal is not maximum abstraction.

The goal is **maximum traceability with useful semantic reuse**.


