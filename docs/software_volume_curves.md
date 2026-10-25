# Experimental PSG/SCC software volume curves

`--software-volume-curves` enables a derived fixed-pitch volume-curve projection
for the MGS target. It is available in `vgm2mml.py`, `scripts/export_mgs.py` and
`scripts/batch_vgm_to_mgs.py`. It is enabled by default in `export_mgs.py`; the canonical converter and
legacy batch retain an opt-in default. It does not implicitly enable timing
normalization. Add `--dump-passes` to inspect its decisions.

The first implementation joins compatible legacy renderer partitions into a
single observed rise-and-decay volume curve. It does not smooth, rescale or
remove volume holds, infer an original instrument command, or synthesize a
release tail. Pitch LFO/bends and lossy PSG/SCC state-duration options remain
future work. Existing software envelopes already work without this option;
the new stage changes which complete curves reach structural analysis.

Before curve recognition, the option coalesces derived fixed-tone PSG boundaries
caused solely by an inactive hardware-envelope reset. Both endpoints and every
intervening source row, including zero-duration rows, must keep the hardware
envelope disabled and the same tone settings. A single audibility gate and
continuous source/target time are required. Native reset events, controls and
original performance partitions remain available. Active hardware resets,
noise, pitch/mixer writes, transient enables and unknown timing stay protected.

`--no-software-volume-curves` explicitly selects the ordinary projection. These
two switches are mutually exclusive in all three entry points. The current
default is enabled only for `export_mgs.py`. Configuration forwards either polarity explicitly,
so a future default change will not erase a caller's ordinary-path selection.
Envelope and macro candidate-selection policies are unchanged.

## Preserved boundaries and ownership

Native Segments, control snapshots and the original PerformanceIR remain intact.
A separate immutable projection retains source Segment membership and timestamps.
It protects pitch writes, rests, source-time gaps, ambiguous audibility boundaries,
SCC waveform changes, PSG noise/mixer/active-hardware-envelope operations and unknown
ordered operations. The scan includes zero-duration source rows. Missing source
timestamps cause abstention. A source audibility span is not asserted to be an
original score note or hardware Key-On.

Only a supported fixed-setting curve with a rising portion followed by a falling
portion is joined. A later rise after a fall remains unresolved and preserves the
existing partitions. This conservative first stage does not recover every kind
of software envelope, tremolo or percussion gesture.

The same projected units feed loop planning, shared PSG/SCC envelope selection
and rendering. The existing 32-envelope capacity, encoded-definition length limit
and explicit-volume fallback remain in force. Envelope holds run at the existing
renderer cadence; timing normalization must not scale those holds as score steps.

## Unchanged-period release continuation

PSG fixed-tone partitions separated solely by `pitch_write` can also be joined
when every ordered source row keeps the same effective period and settings,
volume never rises, and one continuous audibility gate spans them. This includes
zero-duration low/high-byte writes; an intermediate period excursion, zero-time
volume rise, mixer/noise operation, active hardware envelope, silence or unknown
source time protects the boundary. SCC writes are not covered by this rule.

This recovers a complete observed sounding curve when a software-release tail
was detached by a redundant period write. The next volume rise or real pitch
change remains a boundary. It does not recover an original note-off, `q` command
or release parameter. Native writes and original boundaries remain available;
`unchanged_period_joins` and the decision reason
`unchanged_period_write_release_continuation` identify the inference.

Same-period AY/YM tone writes recompute period without resetting tone counters
in the inspected emu2149 implementation. An authored actual MGSDRV/libkss probe
checks the resulting sound-state timing and next restart. These checks are not
a universal hardware-phase or audio-equivalence claim.

## Final target tie compensation

The validated MGSC/libkss MGSDRV playback path advances a software envelope an
additional time when it processes a tied note continuation. A long musical curve
encoded as several notes can therefore advance ahead of its intended holds.

After score normalization and before final allocation/macros, the optional path
jointly checks PSG/SCC definitions and every expanded use. At the validated
75/225 tempos it accepts the renderer's uniform 255-step split schedule only.
It extends each encoded hold by the number of internal tie boundaries in that
hold's half-open interval. Original musical curves and onset/end coordinates
remain untouched. Shared prefixes use the same relative schedule; no additional
envelope IDs are allocated. Note, loop and macro bodies are preserved.

An unsupported clock/schedule, changing binding inside a varying envelope, or
an oversized compensated definition rejects the whole shared-bank update.
The ordinary complete pipeline then runs again, including clock acceptance and
drum-boundary mapping. Its additional boundaries must pass timing checks afresh.
Candidate joins remain inspectable but are reported as unapplied. Normalization
that actually succeeds currently takes this fallback; merely requesting optional
normalization does not disable curves when no clock is accepted.

## Diagnostics

Each chip emits `<stem>.<chip>.volume_curves.json`; `inactive_reset_joins`
counts irrelevant-reset joins separately from recognized attack curves.
`unchanged_period_joins` counts the release-continuation rule separately. With pass dumps enabled,
`.candidates.csv`, `.notes.csv` and `.decisions.csv` retain source membership,
full volume runs and accepted/protected/unresolved decisions. Existing native
performance and Segment dumps are retained separately. The final summary's
`applied` field distinguishes candidates from the emitted route.

`<stem>.volume_curves.target.json` records encoded hold corrections, validated
uses or the global fallback reason. With pass dumps, each chip's
`.before.envelope_ties.mml` retains the target before encoded-hold compensation.
The final `.target.mml` contains the encoded definitions consumed downstream.

The zero-error fields describe equality on the existing renderer tick timeline
and unchanged projected onset/end coordinates. They are not measurements of raw
register-write timing, acoustic equality or real-driver replay error.

## Validation limits

Fewer inferred partitions or fewer MML characters do not guarantee fewer compiled
MGS bytes. Shared-envelope selection can displace other curves, and a whole-song
bank can behave differently from banks selected for isolated excerpts. Compare
both text and compiled sizes and inspect loop/envelope decisions.

Authored tests cover protected operations, exact curve expansion, shared/inline
fallback, long ties, normalization and real MGSDRV restart behavior. Real-driver
replay must also be checked: a simulated target timeline alone cannot certify
playback equivalence. Instruction-count changes can shift register writes within
a frame, so a fixed-grid mismatch needs a source-sample transition comparison
before it is classified as a changed note or changed envelope.

Fixture-specific measurements and unresolved replay observations belong in local
diagnostics and external private field notes. This experimental option is not
a claim of complete source-score recovery or universal compression improvement.

See [the design plan](psg_scc_curve_projection_plan.md) and
[existing envelope rendering](software_envelopes.md).

Reference score comparisons must verify provenance: compiling a same-name MML
must reproduce the intended MGS/music interval, or its relation to an independently
validated master timeline must be established. Matching filenames alone do not
prove the same captured interval. Keep score-window mapping and playback claims
separate from target compression measurements.

## Long sounding units and target length limits

Keep a complete sounding unit and its full observed control trajectory for
structure and envelope selection. Target length encoding is a separate stage:
`length_tokens` splits notes into at most 255 score steps joined by ties, while
software-envelope holds are encoded in chunks of at most 255 driver frames.
These two counts use different clocks. Neither split creates an observed attack.

The x68k SCC-to-OPM route follows the same separation: source note/volume units
remain complete, and the MDX renderer splits legal target durations with ties.
It is not evidence for cutting long source envelopes into newly attacked notes.
The MGS shared bank still selects observed curves and exact prefixes; arbitrary
subcurve rebinding, inferred release tails and a compiled-byte-optimal allocator
are not implemented. Their semantics need separate validation rather than an
implicit duration threshold.
