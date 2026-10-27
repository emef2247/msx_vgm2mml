# Editable score blueprint

The canonical converter, `export_mgs.py` / `batch_vgm_to_mgs.py`, and
`export_vgm.py` independently attempt a score template from retained musical
source evidence:

```text
<output>/<input-relative-parent>/
  blueprint/<stem>.mml
  blueprint/<stem>.part02.mml       # only when additional parts need another page
  tracks/<stem>.mml
  tracks/<stem>.mgs                # when ordinary compilation succeeds
  tracks/<stem>.vgm
  _diagnostics/<stem>/
    <stem>.blueprint.json
    <stem>.blueprint.units.csv
    <stem>.native_music.json
    ...native evidence, timing maps and ordinary projection diagnostics...
```

Standalone `vgm2mml.py` keeps its ordinary MML directly under `--outdir`;
`blueprint/` and `tracks/<stem>.vgm` are also beneath that directory. Default
canonical output is `both`; explicit `--output-format mml` or `vgm` remains
available. MGS exports request both ordinary MML and reconstructed VGM.

## Score and fixed audition initialization

Blueprint retains pitches, sounding durations, rests, attacks, held pitch
changes and finite repeated phrases. Source instrument selections, waveform/patch
definitions, software envelopes and volume commands are removed. Volume-only
and timbre-only control boundaries therefore do not subdivide its notes.
Each melodic track starts with fixed audition initialization: `v15`, OPLL ROM
voice `@1`, or SCC `@0` with a shared square-wave definition where applicable.
These editable target defaults do not reproduce source dynamics or timbres and
do not participate in score repeat detection.

Source chip, instance, section, channel and projected track are written before
each part. Comments document source timbre identities, available FM parameters,
SCC waveform data, source pitch ranges, part counts and timing statistics. Full
source curves remain in NativePerformance and diagnostic sidecars; stripping
controls from a score never deletes them from the shared musical representation.
Users supply their own instruments and dynamics when arranging. The fixed
initialization allows the generated score to sound before those edits.

## Structure before target notation

Repeated phrases are detected over score events: pitch, duration, rest and
attack/continuation. Timbre identities and volume curves do not participate in
repeat equality. Internal pitch phrases in a long held gate can also repeat;
the entire gate need not match another complete gate to obtain a finite loop.
Source attacks remain distinct from held continuations. The existing lossless
macro compactor follows structural repeat selection.

Both ordinary MML and blueprint use a whitespace-only presentation pass. A loop
starts on a new line; nested loops are indented after the repeated track prefix.
Every loop closure ends its line. Leaf loops may remain inline; loops containing
nested loops close on a separate line at their opening indentation. Following
commands use the current nesting indentation. This formatting changes no commands.
Finite repeats describe the rendered traversal; they do not automatically turn
a declared VGM song loop into an infinite MGSDRV loop.

## Target clock and part allocation

The default score tempo is 75, giving one MML step per 1/60 second. Native time
remains 44,100-Hz source samples. A shared monotone sample-to-step map satisfies
positive rendered note, rest and actual semitone-change intervals, so short
sounding units are not discarded merely because ordinary rounding would make
them zero length. Nearby timestamps on independent parts need not consume
separate steps. All pages share the same map and time origin.

This is an explicit target approximation, not a source timing correction.
Arbitrarily dense events cannot retain every positive duration with a bounded
error on a coarser clock. Sidecars report each mapping, maximum displacement,
duration expansion, pitch placeholders and octave folds. Unknown pitches use a
reported C placeholder; out-of-range pitches use a reported octave displacement.
Long durations use legal bounded note/tie pieces. Volume changes introduce no
extra score intervals.

Native PSG/SCC/OPLL parts retain their preferred target family. Other analyzed
melodic sources use free OPLL, then PSG tracks. Source identity is documentary,
not replaced by the destination identity. Overlapping source parts and channel
capacity overflow receive additional lanes/pages rather than silent omission.
Timbre count does not consume score channels or force additional pages. PCM is
excluded from blueprint and does not cause WAV asset generation.

OPLL percussion is a separate attack-grid score page using rhythm labels.
Simultaneous duplicate instruments receive extra pages; independent source stops
remain in source evidence rather than becoming independent MGSDRV drum gates.
A rhythm attack exactly at source EOF receives an explicitly reported one-step
target-only tail shared by every page; the source endpoint is unchanged.
Non-OPLL native percussion currently has no score-rhythm mapping. Its event IDs,
chip and family are listed in `excluded_percussion` and comments, while melodic
pages continue. This is a documented blueprint limitation, not source-data loss
or an implicit claim that OPNA percussion is excluded by the PCM policy.

## Independent outcomes and ownership

Source analysis precedes accepted MGS lowering. Supported source evidence can
therefore produce blueprint and native reference VGM when ordinary MGS timing,
projection policy or compilation fails. The failed target stage is recorded;
source analysis is not silently replaced with a different successful basis.
The accepted legacy execution is retained when it succeeds. See
[musical_hal.md](musical_hal.md) for direct-VGM timing and scope.

Blueprint generation, ordinary MML/MGS and reference VGM have separate outcomes.
Successful text generation does not guarantee that MGSC has sufficient track
buffer, nor prove musical accuracy. Blueprint is not automatically compiled as
a normal listening product. Its JSON/CSV expose source-to-score allocation,
score-atom ranges, removed controls, repeat decisions and target approximations.

Existing products require matching ownership digests for regeneration. Edited
or unowned files are preserved with an explicit conflict outcome. A failed
attempt preserves the previous owned artifact without claiming it was generated
for the new source. Invalid/unsupported source evidence and ownership conflicts
remain explicit failures; "always output" is not permission to overwrite edits
or invent missing source analysis.
