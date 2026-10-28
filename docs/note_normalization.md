# Optional musical duration normalization

The independent sample-based score mode is documented in
[score_normalization.md](score_normalization.md). Its `--score-tempo` defaults
to 225; it does not require an inferred OPLL clock. The following sections
describe the older fitted-clock mode, which remains separately selectable.

```sh
python vgm2mml.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalization-ms 8 --fm-state-ms 1 --dump-passes
```

`--normalize-lengths` infers one musical clock from native OPLL rising KEYON
edges, then projects the target MML onto that clock. Reference MML is not an
input. With none of these normalization switches, the existing conversion stays
unchanged. Explicit `--normalization-ms N` or `--fm-state-ms N` also enables this
optional projection, so a sweep does not silently ignore its requested settings.
All normalization switches conflict with `--raw-ticks`. Values must be finite,
positive and span at least one original 44.1 kHz sample.

## Source evidence and target projection

The reader automatically retains integer `vgmticks` when this flag is enabled.
Source traces, passes, Segments, register values and edge order stay native.
The inferred clock has one origin shared by all parts; individual chips are
not rebased. Exact source Segment CSVs remain available through `--dump-passes`.

Clock inference currently uses OPLL melodic attacks, integer candidate tempos
80..200, and sixteenth/thirty-second lattices. It fits source spacing and phase;
it does not assume the reference tempo. At least 95% of clustered onset anchors
must fit. Clustering is for estimation only and does not merge source attacks.
`--normalization-ms` sets the maximum target correction budget (default 8 ms,
352 original samples after flooring), further reduced to one quarter of the
smallest usable observed inter-onset interval when smaller. This caps clock fit,
onsets, gates, rhythm boundaries and retained internal state boundaries.
New collisions between distinct rhythm attacks reject the whole normalization. Anchor interval eligibility
keeps its existing independent735-sample cutoff. Increasing the correction
budget does not reinterpret source timestamps or guarantee a smaller MML.
Unlike the X68000 MDX normalizer, this option does not delete complete short
sounding gates.

If a reliable clock cannot be found, an attack would collide, a state/gate
boundary exceeds the bound, or the target cannot represent a duration, the
whole song keeps its conventional target output. There is no partial change
of tempo across chips. Melodic projection supports six melodic tracks in rhythm
mode, or nine in melodic mode; layout follows source rhythm activity.

For OPLL, keyed state runs become notes with inferred nominal lengths and gate
ratios (`q`). Intra-note changes use ties rather than additional attacks.
`--fm-state-ms` selects the OPLL internal pitch/level state threshold (MSX
default 1 ms,44 samples; inclusive after flooring). The shared `fm_state_runs`
selector is also used by the X68000/MUCOM adapters, but the MSX default retains
its inherited 1 ms setting; X68000's 24 ms listening results do not establish OPLL
fidelity. This filter is applied only if the whole normalization projection is
accepted. The final state at release, plus both sides of voice/custom-patch and
sustain changes, are protected. Whole source attacks are
never removed merely because all its runs are short. Unclosed terminal KEYONs
receive a minimum positive target duration and are explicitly marked in the
report; this does not assert a source KEYOFF.

OPLL rhythm uses the same clock. PSG/SCC target durations are recoded onto that
clock, preserving command order and frame-based software envelope definitions.
PSG/SCC envelope frames are not musical steps and must not be scaled with tempo.
This is not yet an independent PSG/SCC musical clock estimator; material without
a suitable OPLL anchor clock remains unchanged. Existing MGSDRV pitch, sustain
and rhythm timbre limitations still apply.

Standard note lengths are used where representable, with `%N` otherwise.
This is not a switch that prohibits all step notation. `export_mgs.py` already
requests normalization through its default correction/state thresholds; the
explicit `--normalize-lengths` flag there is a compatibility alias. Inspect the
normalization report's `applied`/`reason` fields, since unsupported or unanchored
material retains its ordinary target timing.

Native-source blueprint is a separate backend: it uses its own shared monotone
score clock (currently tempo 75) and does not apply the ordinary MGS fitted
clock or its `--normalize-lengths` timing corrections. It also emits note-value
notation where exact and `%N` otherwise. A public integration check verifies
that accepted ordinary-MML normalization can change the MML tempo while its
native-source blueprint remains byte-identical. Preserving this independence
also permits blueprint output when ordinary MGS timing/projection fails.

Minimum lengths respect MGSC's tempo-dependent representation: a one-step
interval can be accepted at tempo 120 but rejected at 160. Unsupported ordinary
length divisors such as `96`/`192` are never emitted. The current 80..200 range
uses `max(1, tempo // 75)` as its minimum, based on MGSC 1.11 probes rather than
a universal chip timing rule.

Exact loops are extracted from normalized note units. Expanding the resulting
loops must reproduce the uncompressed normalized command/timing stream.
Redundant absolute setters are then pruned with both first and repeated loop
entries considered; effective note states and times must still match.
Synchronization comments and macro compression run afterward as usual.

## Reports

With the flag, `<stem>.normalization.json` records applied/unchanged status,
fallback reason, inferred timing, target note count, applied loop count and
maximum onset/gate corrections relative to the fitted source clock, requested
thresholds and whether candidate short-state decisions were actually applied.
`<stem>.conversion.json` records effective frontend settings even when conversion
fails. `<stem>.fm.short_states.json` records scope/activation and applied versus
candidate omissions; its CSV maps each considered state to source Segment
indices, sample boundaries and protection decisions. Candidate decisions from a
rejected projection are explicitly marked `applied=false`, not presented as
losses in the final output. Disabled runs emit an explicit disabled summary.
These errors describe projection, not measured end-to-end driver clock error.

With `--dump-passes`, additional evidence is retained:

- `<stem>.<chip>.before.normalize.mml`: conventional target input.
- `<stem>.opll.normalized.expanded.mml`: normalized melody before loops.
- `<stem>.opll.normalized.notes.csv`: source Segment indices and sample bounds,
  normalized onset/gate/end steps, correction amounts and retained state runs.
- `<stem>.opll.normalized.loops.csv`: normalized-unit loop decisions.

Source/native `.segments.csv` is not replaced with normalized data. Target-only
evidence is removed on a rejected re-run so it cannot be mistaken for current
results. No output is written into source fixtures.

Batch conversion forwards the same optional flag:

```sh
python scripts/batch_vgm_to_mgs.py INPUT_DIR --outdir OUTPUT_DIR --normalize-lengths
```

See [the bounded benchmark](../field_notes/2026-10-02_note_normalization_benchmark.md)
for sample, grider and sx01v. Successful compilation and matching KEYON totals
do not prove waveform identity or optimal compression.

## Reproducible threshold comparison

```sh
python scripts/batch_vgm_to_mgs.py INPUT_DIR --outdir outputs/state24 \
  --normalization-ms 8 --fm-state-ms 24 --dump-passes
```

Use a different output directory for each setting. Inspect `normalization_status`
and `normalization_reason` in the batch results: a sparse/irregular OPLL clock,
a protected state which cannot fit, or PSG/SCC-only input can keep the ordinary
output unchanged. Changing a requested threshold is not proof it was applied.
The inherited shared-clock estimator has no independent PSG/SCC anchor path.
PSG/SCC SW-envelope volume curves are not filtered by the FM threshold, and
frame-based envelope durations remain unchanged.
