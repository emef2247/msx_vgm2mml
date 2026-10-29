# Sample-based score timing

`--score-normalize` is an opt-in musical timing pass, separate from the existing
OPLL KEYON clock fitter selected by `--normalize-lengths`.

```sh
python scripts/export_mgs.py INPUT --outdir OUTPUT --score-normalize --score-tempo 225 --dump-passes
```

The reference tempo defaults to 225 and can be changed with `--score-tempo`.
The smallest retained note value is 1/64: exactly
`Fraction(44100 * 60, tempo * 16)` VGM samples, or 3 notation steps out of
192 per whole note. At tempo 225 it happens to equal 735 samples. That equality
does not make a 60 Hz frame clock the source of musical timing.

## Authority and transformation order

Original integer `vgmticks` and `vgmticks_end` remain authoritative. Original
State/Segments and native controls are retained. A compatibility copy supplies
sample-valued start/length fields to the established PSG/SCC/OPLL interpreters;
its clock is explicitly tagged 44100 Hz. The original legacy `ticks` field is
not removed from other conversion modes or redefined in the original dumps.

Original sample spans supply complete sounding units/internal curves. Source
repetition proposals and observed envelope candidates remain inspectable; final
score rendering and textual macro selection consume the musical durations.
The old OPLL fitted clock is not applied a second time in this mode.
OPLL's internal register intervals are not independently truncated as short
notes: a continuous keyed unit is scheduled once, then its controls are placed
inside that span. Shared user-patch lookup remains on original sample times.

A complete duration loses its residue below 1/64. There is no one-sample
tolerance that can promote a 734-sample duration to 735 at tempo 225.
Starts use a common grid for the original device; quiet-window anchors restore
the shared phase for that device. Discarded duration therefore appears as rest
before later anchored events, rather than independently advancing each channel.
Different chips and chip instances do not provide each other's anchors.
Rests use their mapped endpoints, including anchors they cross; they do not
independently truncate a duration and overrun the next synchronized onset.
Quiet means inferred score-gate inactivity, not proven acoustic silence of
release tails.

PCM/opaque streams, unmodeled CSM gates, incomplete gate coverage, unknown
percussion stops, unproven dual PSG/SCC coverage and source-song-loop mode
protect the affected device from score-grid normalization. Their supported MML
parts still receive the final target's notation-step projection, not the
1/64 duration truncation. Unrepresentable target intervals can still fail.

## Score time versus envelope time

Musical lengths are computed directly from samples at the requested tempo.
Only MGSDRV software-envelope holds are lowered separately to the driver's
60 Hz frame counters. Native PSG hardware-envelope period/shape registers are
not scaled with score tempo. Sample-clock PSG part selection preserves its
44100 Hz tag.

At tempo 225, the existing validated tied-envelope compensation can be used.
Other reference tempi currently retain varying curves as inline timed volume
controls instead of assuming that compensation works at a different clock.

The reference VGM is a separate projection of ordered source controls onto
device boundary grids. It can differ from per-note duration truncation. It is
reimported for inspection, but its already warped durations are **not** the
input to MML/blueprint duration decisions. The original native performance is
retained separately as `score_performance` in the in-memory plan.

## Inspectable artifacts

`export_mgs.py` always applies the score timing policy to its blueprint, using
`--score-tempo` (225 by default). It no longer exposes a
`--blueprint-score-normalize` switch. Without `--score-normalize`, production
MML, MGS and reference VGM keep their established timing. Blueprint timing
diagnostics are under `blueprint_score_timing/` in the input's diagnostic folder.
When full score normalization is enabled, the blueprint reuses that report.
Other entry points retain their optional `--blueprint-score-normalize` switch.

`--score-guided-loops` reads the in-memory native score guide rather than the
exported blueprint MML. It works independently of either output's duration
notation and remains disabled by default. With `export_mgs.py`, use
`--score-guided-loops` and leave `--score-normalize` absent for a note-value
blueprint alongside existing production timing.

- Original native evidence remains at the diagnostic root and `native_legacy/`.
- `_score_normalized/` retains sample-clock interpretation and MML lowering.
- `_score_normalized/reference/` contains the reparsed reference VGM view.
- `*.score_normalization.json` and `.anchors/.intervals/.controls.csv` describe
  the control-boundary projection, eligibility and original-device anchors.
- `*.sample_clock.csv` identifies compatibility time fields and sample bounds.
- `*.score_notes.csv` records original interpreted note spans, notation steps,
  discarded residues and separately lowered driver-envelope runs.
- Blueprint reports retain source-unit links, actual clock shifts and collapsed
  score units. Synchronization comments are documentary; they do not split loops.

## MGSC notation compaction

The final pass uses `lN` to omit matching lengths. An explicit `d1` does not
change the default established by `l32`; subsequent bare `d` remains 1/32.
Macro bodies keep explicit lengths so they do not inherit an accidental caller
default. Existing changing-`l` scopes are protected.

For eligible full-gate same-pitch continuations, `^N` adds length without
repeating the pitch. It is limited to a combined 256-step MGSC note and never
introduced at the start of a physical line, across controls, or in uncertain
octave/loop/macro contexts. Partial gate ratios retain their original spelling.
Required slurs and real repeated attacks remain. Dotted values shorten exact
decompositions when possible.

MGSC ignores spaces: deleting spaces from repeated notes does not turn them
into a tie. Authored compiler/driver checks cover actual key edges and timing;
successful compilation alone is insufficient. See the compiler's linked
[original MML documentation](https://github.com/digital-sound-antiques/mgsc#mgsc---mgsccom-emulator).

`*N` phrase macros and `@eN` software envelopes are separate candidate banks.
The phrase search factors octave/volume entry state before selection, folds
adjacent exact repeats first and rejects incomplete held fragments. Envelope
selection prefers longer observed curves and exact prefix sharing after source
loops. Similar curves with different internal holds or levels are not assumed
equivalent. This pass adds no approximate timbre/volume substitution.
