# MGSDRV melodic projection details

These target-specific details were extracted from the archived project knowledge
on 2026-10-05. [Project principles](project_knowledge.md) remain authoritative;
this document does not redefine source Segments. Implementation references are
`py/opll_target.py`, `py/mml_envelopes.py` and `py/mml_utils.py`.

## OPLL user-patch decoding

The eight YM2413 user registers are decoded into MGSDRV voice parameters as
follows. Preserve the original bytes separately from the target voice ID.

| Register | Target parameters |
| --- | --- |
| 00 / 01 | Modulator / carrier AM, VB, EG, KR and multiplier |
| 02 | Modulator KL and TL |
| 03 | Carrier KL, modulator/carrier WF and FB |
| 04 / 05 | Modulator / carrier AR and DR |
| 06 / 07 | Modulator / carrier SL and RR |

WF uses register 03 bit 3 for the modulator and bit 4 for the carrier; FB uses
its low three bits. Each emitted operator row has this order:

```text
AR DR SL RR KL MT AM VB EG KR WF
```

The older main renderer used an incorrect interleaved register layout. An older
reference comment labels the last field `DT`; that comment is not an instruction
to reorder the values. The target's last field here is WF.

## Hardware instrument numbers and MML voice IDs

YM2413 ROM instruments 1..15 map to MGSDRV `@0`..`@14`. Source instrument zero
selects the shared user-patch registers. The converter deduplicates their byte
contents and assigns MML user voices starting at `@16`; definitions and selections
must use the same ID.

These are separate numbering domains. Rhythm ROM table entries numbered 16..18
do not reserve MGSDRV user-definition IDs `@16`..`@18`. Historical controlled
MGSC 1.11/libkss probes defining the same patch as `@16` and `@v20`, with matching
selections, produced identical registers 00..07. This is a numbering check,
not a claim that any arbitrary instrument substitution is safe.

Use `<stem>.opll.target_notes.csv` for actual target voice mappings and patch
bytes. Legacy per-chip variant/pass voice IDs are not the final-output oracle.
Rests do not allocate otherwise unused user voices.

Same-tick patch lookup follows the existing final-write policy. It is a target
projection policy, not evidence that intermediate source writes did not occur.
Arbitrary mid-note changes to the global user patch still require separate
source-state and target-reproduction validation. Patch-aware candidate equality
is described in [melody patterns](melody_patterns.md).

## OPLL octave convention

MGSDRV octave labels differ from scientific pitch octave labels. The historical
MGSC 1.11/libkss-js 3.0.0 probe `9 @9v12o4a4` wrote OPLL block 3; `o3a4` wrote
block 2. Thus the scientific A3 in that probe must be emitted as MGSDRV `o4 a`.
The earlier projection emitted it an octave too low.

The current `target_note` converts source FNUM/BLOCK to a nearest semitone and
uses `MIDI_note // 12` for the MGSDRV octave, clamped to 1..8. This is the
implemented target mapping, not a promise of exact source frequency for every
FNUM or clock. Keep source FNUM/BLOCK available when inspecting pitch loss.
PSG/SCC period verification has its own [roundtrip document](pitch_roundtrip.md).

## Continuation and actual attacks

Splitting a long held interval into untied notes creates unwanted attacks.
The OPLL target carries real zero-duration Key-On edges forward to a timed
interval and distinguishes them from inferred `onset` annotations. Continuous
keyed pitch/state intervals use `&` and `q0`; a genuine note end restores `q8`.
The historical MGSC/libkss probe found that `&` alone still reattacked when
pitch changed, whereas `q0` retained key-high.

Keyed, nonzero-frequency intervals at maximum attenuation remain notes with
`v0`, retaining key continuity. They must not become rests simply because their
level appears silent. Actual source Key-Off/Key-On edges still delimit attacks.
These rules do not reconstruct source release tails or guarantee sample-exact
envelope behavior. Evidence and the withdrawn coalescing experiment are in the
[OPLL key/envelope note](../field_notes/2026-10-01_opll_key_and_envelope.md) and
[Alest202 evaluation](../field_notes/2026-10-01_alest202_retrigger_check.md).

## Emitted state and relative notation

PSG/SCC/OPLL melodic projection uses one-character relative setters when the
previously emitted value is known and the change is exactly one:

| Value | Increase | Decrease |
| --- | --- | --- |
| Octave | `>` | `<` |
| Volume | `)` | `(` |

Initial values and larger changes use absolute `oN`/`vN` commands. Equality
checks can omit an unchanged setter. Rest-time settings are deferred until the
next sounding interval, so relative changes must use the previously **emitted**
state, not a skipped source value. Rest-only tracks are omitted from final target
output; source evidence is retained.

Physical line breaks do not reset musical state. Loop entry/back-edge state and
macro expansion need independent checks; ordinary linear setter pruning is not
sufficient. Rhythm instrument volumes use their separate
[notation rules](opll_rhythm.md). PSG/SCC software-envelope handling is described
in [software envelopes](software_envelopes.md).

The earlier absolute/relative notation probes produced matching ordered register
states; the grider check matched 1934 distinct interrupt-grouped snapshots.
PCM and raw VGM bytes were not identical because within-frame write timing can
change. These historical checks support the notation choice within their scope;
they are not new validation runs or proof of acoustic identity.
