# PSG/SCC sounding-unit and curve projection plan

Status: milestone 1 has an experimental opt-in implementation as of 2026-10-24.
See [Software volume curves](software_volume_curves.md) for its implemented scope
and validation limits. Milestones 2 and 3 remain proposals.

## Finding and scope

The current immutable PerformanceIR already retains native Segments, audibility
spans, ordered control snapshots and inferred renderer partitions. Its renderer
partitions still split at volume rises, pitch writes and settings changes.
Filtering only inside these partitions cannot recover a rising attack or an
entire vibrato trajectory. An audibility span is not proof of a score note.

The supplied Konami MSX-SCC driver analysis distinguishes authored notes,
software envelopes, amplitude/pitch modulation, bends and register/macro-mode
percussion. A single authored note can contain rising volume or changing pitch.
Its approximately frame-based update cadence is evidence for that driver family,
not a universal timing specification for arbitrary VGM inputs. The book is an
analysis reference, not a source of per-song conversion parameters.

The first implementation should target fixed-pitch, fixed-setting PSG software
volume curves and fixed-pitch, fixed-waveform SCC software volume curves.
Pitch LFO/bend output and waveform morphing need separate backend verification.

## Pipeline and ownership

```text
native State / Segments (unchanged)
  -> existing PerformanceIR and retained trace/event evidence
  -> candidate sounding units, full control curves, boundary classifications
  -> optional bounded target-curve projection
  -> complete projected-unit loop plans
  -> shared PSG/SCC software-envelope selection
  -> state-safe target MML, then source macros
```

Use a derived immutable projection rather than replacing native Segments or
silently redefining existing ScoreNote identities. Each candidate retains all
contributing source Segment/partition identifiers and source times. Existing
PerformanceIR dumps remain available. Loop planning, envelope selection and
rendering must consume the same confirmed projection.

Initial structural evidence can inform candidate grouping, but final executable
loops are chosen after the projected curves are fixed and before envelope IDs.
The current rule that only equal emitted command iterations become loops stays.

## Candidate boundaries and complete curves

Record each boundary as protected, candidate continuation, candidate retrigger,
or unresolved, with its evidence and decision. Volume rises and pitch writes
alone must not be promoted to observed Key-On events. Conversely, removing those
boundaries merely because they are close together is not justified.

Conservatively protect positive-duration silence, source gaps, channel disable,
hardware-envelope resets, noise/mixer changes, waveform changes and unknown
operation side effects. A zero-volume interval may be part of modulation rather
than a true note ending; preserving it as an initial grouping barrier is an
implementation precaution, not a permanent chip/score rule. Do not bridge
sub-renderer-tick silence that is visible in source samples.

Rejoining legacy partitions requires a complete supported control pattern plus
boundary evidence; regular cadence alone is insufficient. Ambiguous repetitions
can be authored repeated notes. Preserve the current rendering when the choice
cannot be resolved. Same-value writes and simultaneous operations remain ordered;
control snapshots must not be mistaken for independent observed register writes.

The initial exact path retains the complete observed volume curve, including
rising attack, decay and ending. Matching a driver-like curve is a hypothesis:
never assert that its original driver command or instrument ID was recovered.
Release behavior can depend on note length and driver revision. Do not invent
unobserved release tails or use a long curve's prefix without checking its
observed values and ending. Curve families that require base-volume scaling or
native LFO commands are not assumed representable without target replay probes.

## Optional approximation and proposed options

Proposed `--psg-state-ms` and `--scc-state-ms` are independent, initially disabled
by default. Their numerical defaults should be selected by later listening and
size sweeps; neither inherits the OPLL 24 ms default automatically. The options
must work without an OPLL clock estimate and remain separate from
`--normalization-ms`, which bounds score-timing correction.

A state duration is only a candidate limit. Define it as the maximum duration of
a contiguous changed source-time interval, not permission to erase every hold
shorter than that duration. Require an additional explicit volume-error budget
and an integrated trajectory-error budget. Numerical error defaults are not yet
chosen. The first approximation implementation should handle volume only;
pitch-error limits and native LFO synthesis are later work.

Compare every original curve directly with the proposed representative over its
entire observed extent. Do not accumulate pairwise merges or shift boundaries
repeatedly. Representatives initially come from observed equal-duration curves
with compatible pitch/settings; matching must be deterministic and independent
of input processing order. Require unchanged sounding-unit onset/end, protected
silence, initial/terminal states and protected operations. Reject candidates whose
benefit requires moving a note boundary. Keep the original curve as fallback.

Retain source timing in integer 44,100-Hz sample coordinates. Unknown source
times cause abstention for source-ms decisions; do not manufacture them from
renderer ticks. Evaluate output error again after the actual MGSDRV envelope
quantization. Existing 60-Hz envelope holds are not musical score steps and must
not be scaled by a normalized score tempo.

One-frame intentional attacks, modulation and drum changes are valid content.
A 24 ms threshold can cover such content, so duration alone is never a removal
criterion. Register/macro-like percussion and mixed noise/hardware-envelope
paths remain outside the initial volume approximation scope.

## Implementation milestones

1. Add derived sounding-unit candidates, complete volume curves and boundary
   decisions. Preserve the current route when disabled/unresolved. On authored
   cases with unambiguous boundaries, support complete rising attacks and exact
   curve reuse before introducing lossy projection.
2. Add independent opt-in PSG/SCC bounded volume approximation. Rebuild final
   loop keys from the projected units, then choose the shared envelope bank.
   Preserve the established shared-bank capacity and current fallback behavior.
3. Separately evaluate pitch/LFO/bend recipe recovery, percussion gestures and
   duration-dependent envelope families. Map them to MGSDRV features only after
   independent register/timing/phase checks; do not infer support from syntax.

Do not combine these milestones with a new global allocator or a compiler-limit
increase. A compiled-byte-aware benefit model is useful, but its calibration is
a separate measured step rather than an assumed result of fewer characters.

## Diagnostics and acceptance

Add source-to-candidate membership, original/projected control curves, boundary
reasons and every accepted/rejected approximation decision to CSV/JSON dumps.
Report source/control/unit counts, joined/protected/unresolved boundaries,
unique curves, exact/approximate envelope reuse, inline fallbacks, maximum and
integrated deviation, changed duration and estimated savings separately.

Public/authored tests should include a held tone with rising attack, decay and
release; amplitude/pitch LFO; equal-pitch rearticulation; ordinary melody changes;
short/sub-tick silence; ordered same-value resets; PSG noise/mixer/hardware
operations; SCC waveform changes; and missing source timestamps. Include both
PSG and SCC and distinguish readable-text savings from actual compiler usage.

Check native State/Segments unchanged, exact candidate expansion, protected
boundaries/order, and source-versus-projection error independently. Then check
that executable loops, shared envelopes and macros expand to that same projected
timeline. Compile and regenerate VGM using the public test workflow; source
comparisons must not demand exact volume equality where approximation was
explicitly accepted. Target replay does not establish arbitrary-source audio
fidelity. Keep local_only conversion/listening with the user.

## Related documents

- [Existing performance IR](psg_scc_performance.md)
- [Existing software-envelope semantics](software_envelopes.md)
- [Timing normalization](note_normalization.md)
- [Loop and melody structure](melody_patterns.md)

Historical measurements and the scan-page audit are recorded in the external
private field notes, separate from this proposed public design.
