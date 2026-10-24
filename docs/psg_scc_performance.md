# PSG/SCC sounding units and internal control curves

This stage separates source-linked sounding spans, internal control trajectories,
and inferred renderer note partitions. It consumes interpreted native PSG/SCC
Segments, before loop planning, envelope-bank selection and MML rendering.
OPLL is outside this stage.

```text
native Segments
  -> immutable PerformanceIR
       source-audibility spans
       ordered pitch / volume / timbre / mode / hardware-envelope controls
       inferred note/rest partitions and their boundary reasons
  -> complete-unit loop plans
  -> shared software-envelope selection
  -> MGSDRV MML and target envelope assignments
```

## Sounding span versus inferred note

PSG/SCC have no OPLL-style explicit KEYON edge in these Segment types. A
source-audibility span therefore describes interpreted enable/mixer/volume
continuity; it does not prove a score attack. The current conservative renderer
partitions at pitch writes, volume rises, relevant settings/waveform changes,
PSG hardware-envelope resets, silence and gaps. Those are explicit interpretation
reasons, not newly discovered hardware key-ons.

A broader span can contain several such partitions and multiple pitch, volume
or timbre controls. This first milestone preserves the existing partition policy
and rendered behavior. It does not claim completed vibrato, portamento or authored
score-note recognition. Changing those decisions requires separate evidence.

## Evidence and timing

The immutable representation retains source Segment indices and event ordering.
Control points are typed, ordered per-Segment state snapshots, not independently
observed register writes. Repeated values can therefore appear without a new
write to that particular register. Internal control types distinguish pitch,
volume, SCC waveform/timbre,
mode/noise and PSG hardware-envelope state/reset. Same-time controls remain
ordered; a repeated same-value hardware-envelope reset is still an operation.
Terminal states and zero-renderer-length rows remain inspectable.

Original `vgmticks` and `vgmticks_end` are sample coordinates at 44,100 Hz when
present. They may be unknown for older input paths. Missing sample times are
never reconstructed from floating-point timestamps or 60 Hz ticks. Renderer ticks
and frame-based envelope holds are separate coordinates. In particular, a source
mute with positive sample duration can interrupt source audibility even when its
renderer duration is zero.

Reconstruction validation concerns retained Segment state, ordering and lineage;
it does not establish control-stream replay or musical fidelity. It is not
a claim that Segment-derived curves reconstruct every raw VGM register write.
The original State/trace/pass/Segment evidence remains authoritative and intact.

## Consumption and structural equality

One PerformanceIR is created for each chip submission and passed through loop
preparation, envelope candidate selection and rendering. The legacy `Note`
adapter remains available for callers, but it no longer owns source interpretation.
Mutable target envelope assignments stay outside immutable note identity.

Repeat keys retain complete relative duration, pitch/settings and observed volume
runs. Absolute timestamps, source IDs and diagnostic gate IDs do not participate
in equality. Reusing a source pattern still requires exact emitted command
iteration equality. Structure is selected before the shared software-envelope
bank, preserving observed curves and explicit inline fallbacks.

No blanket FM-state threshold is applied to PSG/SCC curves. This change does not
delete short gates, flatten software envelopes, invent release tails or rescale
envelope frames with a musical clock. The existing renderer remains responsible
for target timing and chip/compiler limitations.

## Inspection

With `--dump-passes`, the chip submission emits `<stem>.<chip>.performance.*`
CSV/JSON evidence alongside existing passes, native Segment dumps, source-loop
plans, envelope counts and target-note reports. Inspect the sounding spans,
control rows, note memberships and boundary classifications separately from the
selected target envelope IDs.

See [software envelopes](software_envelopes.md),
[melody/loop structure](melody_patterns.md) and
[project principles](project_knowledge.md).
