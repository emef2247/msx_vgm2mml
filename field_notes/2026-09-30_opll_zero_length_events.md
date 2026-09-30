# OPLL zero-length events: state versus trigger

## Provenance and scope

Design discussion with the user, 2026-09-30, following the GF2SMS03 conversion
failure. This is project knowledge from code inspection and a local observation,
not an externally verified chip specification or an acoustic measurement.
No private fixture contents are reproduced here.

The user accepts 60 Hz quantization for MGSDRV MML. The objective is useful
musical reconstruction while retaining source evidence, rather than reproducing
every sub-tick hardware transient. The user recalled merging zero-duration
events before Segment construction, and possible side effects, but did not
identify a specific historical failure. Do not treat that recollection as a
confirmed diagnosis.

## Distinctions to preserve

- `ticks=0` denotes an onset at the beginning; `l=0` denotes zero duration.
  Only the latter was intended in this discussion.
- Equal source timestamps with no VGM wait and distinct timestamps rounded to
  the same 60 Hz tick are different cases. Rounded duration zero does not prove
  that no source time elapsed.
- A state update and an action that retriggers sound are not interchangeable.
  Equal final register state does not prove equivalent playback.

OPLL FNUM is assembled from separate register writes. Their intermediate state
can look like an additional pitch change. Treating every such change as a note,
vibrato, or portamento can misrepresent a register-update sequence as a musical
gesture. A write may also affect key state or other fields; do not discard it
solely because it contributes part of FNUM.

## Observed implementation and fixture behavior

At inspection, `opll.py::_build_segments` calls
`pass2_mark_legato_vibrato_portamento_envelope` with a comment saying l=0 events
have been removed. The implementation in `py/segment_utils.py` does not filter
them there: it iterates events and updates previous key/pitch/volume state.
Thus intermediate writes can influence these classifications. This is a code
observation, not proof of an audible defect in all outputs.

GF2SMS03 had two HH triggers at source time zero with equal captured state;
the first had zero interval. The target renderer now coalesces this narrow case
and warns. Source trace, Segment and rhythm-group CSVs retain both events.
Conversion and MGSC compilation succeeded. Acoustic equivalence of the two
zero-time retriggers has not been established; this is a target approximation.
It must not be generalized to all collisions within a quantized tick.

## Agreed direction for future normalization

1. Retain original timestamp, order and intermediate register state in the trace.
2. Extract key edges and rhythm triggers before reducing state updates.
3. For a 60 Hz target timeline, use final pitch/volume state for each tick while
   carrying the extracted trigger information separately.
4. Classify legato and modulation using that normalized state plus edge history,
   rather than incidental partial-register states.

This is a proposed normalization design, not a description of a completed
pipeline refactor. Keep source-derived observations distinct from target
quantization. If normalization affects Segments, retain a mapping to every
contributing source event and expose the transformation in dumps.

Never blindly delete or merge all l=0 events. In particular, preserve evidence
of key ON -> OFF -> ON, rhythm rising edges, and patch changes around key-on.
These can change retrigger/envelope behavior despite an unchanged final key bit.
Multiple genuine attacks in one target tick require an explicit representation
policy; do not silently move them or collapse them as pitch-update noise.

## Unresolved questions and validation

Whether a transient is audible depends on write timing, synthesis behavior and
emulator implementation. Do not claim that intermediate writes are audible only
on hardware, universally absent in emulation, or definitely unintended by the
composer. No hardware/emulator comparison was performed in this discussion.

Before implementing broad normalization, test split FNUM writes, writes with
distinct source timestamps in one tick, same-tick OFF/ON, patch-at-onset changes,
rhythm retriggers, and zero-length terminal events. Verify retained edge counts,
final states, source-event mappings, and target duration independently. Preserve
existing public rhythm and optional local regressions.
