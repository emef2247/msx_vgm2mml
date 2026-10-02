# Reference-guided sample note-length experiment

## Method and scope

Isolated experiment on the public PSG/OPLL sample. Original Segments and dumps
remain unchanged. Known reference settings supply tempo120, l16, q6 for 9/a,
q7 for b/c/d and q2 short notes. Note order, native pitch runs, voice and volume
come from the source, not copied reference notes. This is not a general musical
timing estimator or new converter default.

Attacks are aligned to the 16th-note lattice. Continuous keyed pitch changes
become tied notes. Gate fitting allows a maximum two-source-tick local duration
correction; EOF-truncated material is considered separately. Constant voice/
volume initialization stays outside repeated bodies and absolute octaves make
the command bodies repeatable. Existing loop and macro compressors are reused.
Thus the improvement is not attributable solely to timing tolerance.

PSG/rhythm state commands are retained and cumulative lengths recoded for
tempo120; these parts are controls rather than musical-normalization targets.
Their compiled usage increases, while OPLL savings reduce total usage.

## Results

| Measure | Current | Experiment |
| --- | ---: | ---: |
| Final MML characters | 6453 | 4341 |
| MGSC total used bytes, including track 0 | 2963 | 2410 |
| OPLL melodic tracks used bytes | 2137 | 972 |
| Fully recovered reference melodic loops, first pass, per channel | 5/12 | 12/12 |
| Exported melodic KEYON count | 604 | 604 |

The four-repeat 9/a phrase now forms a full loop. Reference line22 joins an
adjacent identical phrase into a six-repeat loop. First b/c/d accompaniment
phrases also form full two-repeat loops. PSG/rhythm last-pass exits and the
outer infinite loop are not newly recovered.

Maximum boundary/onset movement versus existing integer ticks is 2.625 ticks
(43.75 ms), including absolute grid alignment and accumulated clock/rounding
differences. All corrections are in CSV. Generalization requires inferred
musical timing and a justified tolerance, not these hard-coded reference values.

## Validation

- Source Segment fields snapshot-checked unchanged.
- Expanded normalized loops/macros exactly match the uncompressed normalized
  commands and target start/end steps on all tracks.
- Baseline and experiment compiled with MGSC1.11. The experiment MGS was
  exported with libkss-js and reparsed into Segment CSVs.
- Raw source KEYON609, exported604, count excess0. Source includes five
  terminal/sub-tick keyed units. These are inventories, not matched failures.
- Using raw timestamps and separating intermediate states shorter than 1ms for
  inspection, all604 substantive keyed units match in target-note, instrument,
  attenuation and sustain sequence, including tied pitch changes. Per-track
  counts are224/224/52/52/52.
- Full rhythm instrument/volume sequence matches (282hits), as do captured
  custom-patch byte sequences.

Unfiltered comparison is retained: one exported attack has l=0 despite positive
raw-time duration, and a separate intermediate FNUM state lasts one VGM sample.
The 1ms inspection threshold is explicit, experimental and changes no source
rows. No byte, native-FNUM, PSG acoustic or WAV identity is claimed.

## Artifacts

Codex outputs/sample-note-length-experiment contains sample.mml/sample.mgs,
run_experiment.py, normalized.expanded.mml, timing_corrections.csv,
performed.loops.csv, summary.json, keyon Segment/count dumps,
roundtrip_note_states.json (unfiltered) and roundtrip_stable_note_states.json
(raw-time inspection threshold declared). The helper reproduces this bounded
experiment without changing production conversion. Listening remains useful
before choosing a general target-stage normalization design.
