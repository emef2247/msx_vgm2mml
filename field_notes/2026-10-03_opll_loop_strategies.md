# OPLL loop strategy comparison: sample and sx01v

The user narrowed the question to OPLL loops and deferred envelope ordering.
The earlier rejected count-only envelope experiment and substituted gra2_005
results were deleted. This comparison uses exactly the two requested fixtures.

## Method

`scripts/experiment_opll_loop_strategies.py` runs three complete conversions:

- `current`: existing loop extraction and selection.
- `immediate`: scan short source-note phrases first, replace repetitions with
  hierarchical markers, then scan longer original-unit widths.
- `retained`: retain overlapping alternatives and select a tree by dynamic
  programming, rather than committing each shortest candidate immediately.

Both experimental trees are created before target-command generation. Keys retain
note/rest kind, duration and full OPLL pitch/volume/voice trajectories. Original
Segment indices remain available. All source notes have the same structural cost;
MML spelling/envelope IDs are not part of source-tree selection. Search bounds
are128 original note/rest units per phrase, depth3 and255 repeats per loop.
This is bounded exact matching, not a claim to recover the original score.

The actual tree drives command emission. Equal emitted passes become loops;
initialization can leave the first pass outside a loop. A node whose commands
differ is expanded while retaining its children. The projector asserts exact
command expansion. Source membership/status is dumped to `*.source_loops.csv`
and `*.source_loops.projection.csv`.

Only OPLL melodic loop selection changes. PSG/SCC envelope processing, rhythm,
synchronization and final macros are identical across strategies. Duration
normalization is off for every run. The macro/sync outcomes may differ because
their input loop structure differs, even though their algorithms/settings do not.
These full-output measurements must not be confused with earlier normalized
fragment-only statistics.

## Reproduce

```sh
python scripts/experiment_opll_loop_strategies.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm --outdir outputs/opll-loop-strategies/sample --mgsc-module <mgsc-js>/dist/index.js
python scripts/experiment_opll_loop_strategies.py tests/fixtures/local_only/opll/msxplay.com/sx01v/sx01v.vgm --outdir outputs/opll-loop-strategies/sx01v --mgsc-module <mgsc-js>/dist/index.js
```

The compiler argument is optional. No packages are installed by the experiment.
Actual outputs are under
`C:/Users/ef110/Documents/Codex/2026-09-25/co/outputs/opll-loop-strategies/`.
Each strategy has a playable full MML, compiled MGS, compile.log and pass evidence.
The song root has comparison.json. Private musical content remains outside Git.

## Results

| Song | Strategy | Full MML bytes | MGSC used bytes |
| --- | --- | ---: | ---: |
| sample | current |6333|2956|
| sample | immediate |6008|2956|
| sample | retained |6333|2956|
| sx01v | current |17428|9128|
| sx01v | immediate |17518|9428|
| sx01v | retained |17187|9168|

All six compiled with MGSC1.11 through the existing local mgsc-js2.0.0 package.
MGSC used bytes are the compiler's total used column, not the MGS file length.
sample immediate saves325 text bytes without saving compiled space. sx01v
immediate adds90 text bytes and300 compiled bytes; retained saves241 text bytes
but adds40 compiled bytes. The shortest final text and smallest compiled object
are distinct objectives.

The sample text saving is primarily formatting/comments, not musical-command
compression: excluding comments and stripping line edges, current/retained have
4420 characters and immediate4425. Different loop boundaries affect where sync
comments can be placed. For sx01v the corresponding counts are16497/16587/16259
(current/immediate/retained), so the retained reduction includes command text.
Do not attribute the entire325-byte sample decrease to fewer musical commands.

Experimental projected/applied occurrence counts: sample47/35 for either strategy;
sx01v immediate185/153 and retained158/123. These include nested invocations and
are not authored physical bracket counts. The current path has no new-plan
reports, so its corresponding JSON fields are null, not zero actual loops.

## Preservation and limits

For each song, all final MML macros and loops were expanded. Every track's token
text, start step and end step match the current output exactly. This includes
non-OPLL tracks, so the unaffected parts are checked too. Renderer tests exercise
key edges, ties, changing controls, nested plans, initial-pass differences and
rejected projections. No new VGM/audio roundtrip was performed: the preservation
claim is relative to the current conversion, not absolute input-VGM fidelity.

The existing envelope/OPLL renderer tests passed along with experimental tests.
The source-first plan is opt-in through the experiment, not the default converter.

## Interpretation

The proposed short-first hierarchy is functional and can reduce final MML text.
It is not uniformly better: early short-loop commitment can obstruct other
placements, and more loops can increase compiled control-flow overhead. Retaining
candidates is useful, but its source-unit cost does not minimize MGSC byte usage.
Unchanged output does not establish optimality; the marker/projection evidence
shows that the processing ran and sometimes reached an equivalent representation.

No envelope-order conclusion is drawn. Before production adoption, investigate
which reference phrases are missed and consider actual compiled-cost selection.
Last-pass exits, approximate timing matches and reference-loop recovery rates
remain outside this bounded experiment.
