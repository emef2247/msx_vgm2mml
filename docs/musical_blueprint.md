# Editable score blueprint

The canonical converter, `export_mgs.py` / `batch_vgm_to_mgs.py`, and
`export_vgm.py` independently attempt a score template from retained musical
source evidence:

```text
<output>/<input-relative-parent>/
  blueprint/<stem>.mml
  blueprint/<stem>.midi            # standard MIDI file, paired with this score
  blueprint/<stem>.part02.mml       # only when additional parts need another page
  blueprint/<stem>.part02.midi
  tracks/<stem>.mml
  tracks/<stem>.mgs                # when ordinary compilation succeeds
  tracks/<stem>.vgm
  _diagnostics/<stem>/
    <stem>.blueprint.json
    <stem>.blueprint.units.csv
    <stem>.blueprint.notes.csv
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
Final note-value compaction preserves that indentation and physical line breaks.
Finite repeats describe the rendered traversal; they do not automatically turn
a declared VGM song loop into an infinite MGSDRV loop.

## Target clock and part allocation

`export_mgs.py` always requests note-value blueprint timing at `--score-tempo`
(default 225), independently of production MML. Sub-64th residues are truncated
in this score projection, including end/synchronization-anchor residues.
Other entry points retain the optional score normalization switch and their
legacy blueprint tempo of 75 when it is absent. Native time remains integer
44,100-Hz source samples. The fallback per-device monotone sample-to-step map satisfies
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

## Standard MIDI score

Each MML page has a matching `.midi` file. The writer uses only Python's standard
library and serializes the same final projected pitch/time spans as the MML;
it does not parse formatted MML or reinterpret native chip commands. Finite
repeats are expanded in MIDI. Held equal-pitch spans remain one note; actual
repeated attacks remain separate notes, with note-off before note-on at the
same time. Pitch-changing continuations remain documentary continuations in
the score sidecar; neutral MIDI audition does not emulate chip legato.

SMF type 1 uses 480 ticks per quarter note and a conductor tempo track. One
MGSDRV score step is normally 10 MIDI ticks. Every track retains trailing rest
through the page's projected endpoint. Fixed velocity 96 and melodic program 0
are audition defaults; source dynamics, controller curves and synthesis are
omitted. Documentary track names use UTF-8. Native parts, clock displacement,
unknown pitches and octave folds remain inspectable in the blueprint reports.

The supported OPLL rhythm score uses GM percussion notes 35 (BD), 38 (SD), 41 (TOM),
49 (CYM), 42 (HH) on MIDI channel 10. Its MIDI audition gate is one minimum score
interval, capped by the next attack; independent native stop/decay controls
are not applied. Non-OPLL percussion retains the existing explicit limitation.
Melodic parts avoid channel 10. More than 15 melodic parts use separate MIDI
ports before reusing channel numbers; the receiving application must honor
the port metadata. Track/port/channel allocation is recorded per MIDI file.

SMF's 24-bit tempo value cannot directly encode score tempos 1..3. Those use
an explicit metric scale in both MIDI tempo and event ticks, preserving elapsed
time; the sidecar records the scale. No external MIDI library is required.

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

MML and MIDI are one optional blueprint publication bundle. A hand-edited file
in either format protects the bundle without preventing ordinary products.
Older MML-only ownership records migrate when the MIDI sibling is absent;
an existing unowned MIDI file is never adopted. Stale paired pages are removed
only when owned. Failed rollback preserves disk recovery copies. Batch results
keep `blueprint_files` for MML and add `blueprint_midi_files`; the manifest owns
both formats and diagnostic JSON includes `midi_files` with checksums/metadata.
