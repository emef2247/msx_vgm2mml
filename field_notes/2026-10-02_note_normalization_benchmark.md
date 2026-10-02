# Source-inferred musical duration normalization benchmark

The user requested implementation using public sample first, then benchmarks
against sample, grider and sx01v, whose reference MML is available. The native
VGM is the conversion input; reference MML is used only as a size benchmark.
No reference note, tempo or gate setting is copied into production inference.
Private fixture contents are not reproduced here.

## Final measurements

MGSC 1.11 through the existing mgsc-js compiler wrapper; MGS exported using
libkss-js with `loop: 1`. Baseline and corrected outputs are finite conversions
of the same complete source capture. Every listed MML compiled successfully.

| Input | Baseline MML characters | Corrected characters | Baseline compiled used bytes | Corrected used bytes | Reference MML characters / used bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| sample | 6,333 | 3,544 | 2,956 | 1,678 | 810 / 664 |
| grider | 25,243 | 25,243 | 13,075 | 13,075 | 5,122 / 4,044 |
| sx01v | 17,428 | 11,248 | 9,128 | 7,183 | 6,267 / 2,860 |

Characters count the complete merged MML, including headers/macros/comments.
Used bytes sum MGSC's actual-used track figures, including track 0, rather than
allocation declarations or MGS file size. Sample shrinks 44.0% in source and
43.2% in used bytes; sx01v shrinks 35.5% and 21.3% respectively. Both duration
normalization and safe setter/layout changes contribute; these are not pure
loop-only savings.

| Input | Source melodic KEYON | Baseline export | Corrected export | Corrected shortage / excess |
| --- | ---: | ---: | ---: | ---: |
| sample | 609 | 604 | 609 | 0 / 0 |
| grider | 2,596 | 2,559 | 2,559 | 37 / 0 |
| sx01v | 1,615 | 1,604 | 1,615 | 0 / 0 |

Shortage/excess are sums of per-channel count differences, not matched individual
events. Source terminal sub-frame KEYONs are included. Retaining a minimum
positive terminal target note explains the increased corrected counts; it does
not establish a source KEYOFF or additional musical intent.

Grider did not meet the common-clock confidence requirement and stays byte-for-
byte unchanged. Its 37-count deficit belongs to the conventional output; this
implementation does not fix it. Do not force the known reference tempo to make
this benchmark appear successful.

Reference MML often loops or describes a different capture horizon. Reference
exports from `loop: 1` are not commensurate with the full native capture, so
their raw count differences are not treated as missing/extra conversion events.
The reference size is a useful target, not a like-for-like normalized score.

## Timing and state evidence

| Input | Inferred tempo | Anchor coverage | Applied target loops | Max onset shift | Max closed-gate shift |
| --- | ---: | ---: | ---: | ---: | ---: |
| sample | 120 | 100% | 29 | 269.1 samples (6.10 ms) | 408.3 samples (9.26 ms) |
| sx01v | 160 | 100% | 95 | 362.7 samples (8.22 ms) | 523.7 samples (11.88 ms) |

Both fitted lattices use 12 MML steps per sixteenth. Correction amounts are
relative to the fitted source clock, not raw MGS wall-clock alignment. Fitted
sample spacing and the driver's integer tempo can leave residual playback
duration differences. Source traces and Segments are untouched; a CLI regression
checks byte-identical sample PSG/OPLL Segment CSVs with and without correction.
The saved baseline/corrected native Segment CSVs also agree byte-for-byte for
all three cases and all chip files. The bounded normalization, rhythm rendering,
rhythm notation, batch and public conversion suites passed (39 tests total).

Ordered target pitch names, volumes, and preset/custom-patch bytes were compared
per OPLL attack after MGS export. With the declared 44-sample intermediate-state
inspection threshold, sample's 609 and sx01v's 1,615 note state sequences all
agree. Rhythm instrument/volume sequences agree: 282 hits for sample and 1,588
for sx01v. Raw register values and sub-millisecond intermediate states are not
claimed identical. No WAV comparison or PSG envelope waveform equivalence was
performed. Existing target pitch/sustain/rhythm limitations remain.

The uncompressed normalized melody and loop expansion have identical commands
and times. Setter compaction preserves effective note states and times, including
nested loop entry/back edges. The public conversion regression also passed,
confirming default conversion output remains unchanged for that fixture set.

## Artifacts and reproduction

Local artifacts: `C:/Users/ef110/Documents/Codex/2026-09-25/co/outputs/length-normalization/`.
Each case has `baseline`, `normalized`, and `reference` outputs. `benchmark.json`
contains complete measurements; `state-audit.json` contains per-channel checks.
The local helper scripts are `run_benchmark.py` and `check_states.py`; they and
generated/private material are not added to Git.

For each source VGM, run conventional conversion with `--vgmticks --dump-passes`,
then separately run `--normalize-lengths --dump-passes`. Compile both generated
MMLs and the original reference MML using `scripts/compile_mgs.mjs` (or native
MGSC). Export compiled MGS with `scripts/mgs_to_vgm.mjs`, then compare source and
export using `scripts/check_opll_key_edges.py`. Keep source fixtures read-only.

Further work: listen to the corrected scores, use opt-in batch regression, and
investigate a local/variable clock model for abstained material separately. Do
not loosen the estimator or adopt correction by default on these three results.
