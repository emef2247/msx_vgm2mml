# Optional musical duration normalization

```sh
python vgm2mml.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalize-lengths --dump-passes
```

`--normalize-lengths` infers one musical clock from native OPLL rising KEYON
edges, then projects the target MML onto that clock. Reference MML is not an
input. Without the flag, conversion behavior stays unchanged. The flag cannot
be combined with `--raw-ticks`.

## Source evidence and target projection

The reader automatically retains integer `vgmticks` when this flag is enabled.
Source traces, passes, Segments, register values and edge order stay native.
The inferred clock has one origin shared by all parts; individual chips are
not rebased. Exact source Segment CSVs remain available through `--dump-passes`.

Clock inference currently uses OPLL melodic attacks, integer candidate tempos
80..200, and sixteenth/thirty-second lattices. It fits source spacing and phase;
it does not assume the reference tempo. At least 95% of clustered onset anchors
must fit. Clustering is for estimation only and does not merge source attacks.
The correction bound is one nominal 60 Hz frame (735 samples), reduced to a
quarter of the smallest usable observed inter-onset interval when smaller.

If a reliable clock cannot be found, an attack would collide, a state/gate
boundary exceeds the bound, or the target cannot represent a duration, the
whole song keeps its conventional target output. There is no partial change
of tempo across chips. Current melodic projection supports the existing six
OPLL melody tracks; keyed channels 6..8 cause this conservative fallback.

For OPLL, keyed state runs become notes with inferred nominal lengths and gate
ratios (`q`). Intra-note changes use ties rather than additional attacks.
Positive state runs of at most 44 samples (about 1 ms) may be omitted from this
target projection, with their indices recorded. A complete source attack is
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
maximum onset/gate corrections relative to the fitted source clock.
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
