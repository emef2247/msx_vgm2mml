# Optional note normalization: local regression comparison

Date: 2026-10-02. Branch intended for the user commit: `codex/normalize-lengths`.
This records the user's completed runs, not an additional agent-run regression.
No generated outputs, fixtures, conversion code or Git staging were changed by
this review. Successful compilation and completed playback comparison are
reported separately. This is an opt-in checkpoint, not blanket audio validation.

## Evidence

```sh
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/psg_opll \
  --outdir outputs/mgs/normalize-lengths/psg_opll --normalize-lengths
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/normalize-lengths/opll --normalize-lengths
```

Compared `results.csv` and `results.json` in those folders with the conventional
runs in `outputs/mgs/psg_opll` and `outputs/mgs/opll`. CSV/JSON row values agree
for all four result sets. Per-input normalization JSON exists for all 591 current
inputs; applied/unchanged status and reasons were inspected. Compiler logs were
read for the two newly failing inputs. Playback errors are reported in the result
JSON and `keyon.log`.

The interrupted PSG/SCC-only run is not part of this comparison. It need not be
repeated for this experiment: current clock inference requires OPLL anchors.

## Compilation and normalization

| Catalog | Baseline inputs | Current inputs | Current success | Current buffer_error | Current compile_failed | Correction applied | Correction unchanged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PSG + OPLL | 26 | 26 | 15 | 11 | 0 | 3 | 23 |
| OPLL | 545 | 565 | 331 | 232 | 2 | 101 | 464 |
| Current total | — | 591 | 346 | 243 | 2 | 104 | 487 |

There are no current conversion failures. The previous OPLL result set had
306 successes, 238 buffer errors and one missing-input conversion failure.
The current OPLL catalog adds 22 F1SPRT3D paths, all successful, and removes
`temp/export_from_msxplay.com/Alest202.vgm` and
`temp/export_from_msxplay.com/YsSMS01.vgm`. These catalog changes are not evidence
of normalization benefit. Reference KEYON totals agree on both sides for every
paired input with completed comparisons.

For the 543 shared OPLL paths:

| Previous status | Current status | Inputs |
| --- | --- | ---: |
| success | success | 304 |
| buffer_error | buffer_error | 232 |
| buffer_error | success | 5 |
| success | compile_failed | 2 |

All 26 shared PSG + OPLL compilation statuses are unchanged (15 successes,
11 buffer errors). Thus five existing buffer failures are resolved, two former
successes now fail compilation, and the net shared-input success gain is three.
This outcome is limited. Source/compiled size reductions in already-successful
inputs were not catalog-wide measured here; they are not included in the five.

### Five buffer errors resolved

- `vgmrips.net/ALESTE2/Alest208.vgm`
- `vgmrips.net/ALESTE2/Alest211.vgm`
- `vgmrips.net/FRAY/FRAY06.vgm`
- `vgmrips.net/FRAY/FRAY11.vgm`
- `vgmrips.net/ILCITY/ILCITY23.vgm`

All five have correction applied and compile successfully. All five also reach
the MGS export duration limit, so reproduction/KEYON comparison is not complete.
Do not describe them as validated musical reproduction merely because they fit.

### Two new compiler failures

`vgmrips.net/XEVIFS/XEVIFS07.vgm` and `XEVIFS08.vgm` were previously successful.
Both have correction applied, inferred tempo 149, and now report `Invalid length`.
The rejected lines contain an initial `r%1`. Current minimum-length handling
allowed that spelling; it is not valid for these MGSC outputs. Record this as an
unresolved normalization regression, rather than a source-VGM conversion error.
No private MML contents are copied into this note.

### Conservative fallbacks

Across both catalogs, the most frequent unchanged reasons are:

| Reason | Inputs |
| --- | ---: |
| No confident shared clock | 239 |
| Gate boundary would exceed correction tolerance | 157 |
| Positive/minimum target length cannot be represented | 45 |
| Keyed zero-frequency material requires conventional projection | 9 |
| Keyed OPLL channels 6..8 outside current normalized target renderer | 6 |

Other reasons include merging/overlapping attacks, distinct state intervals
crossing the next attack, and PSG/SCC or OPLL state corrections exceeding the
bound. These are deliberate whole-song fallbacks, not converter exceptions.
The user's preferred future policy is per-note semantic boundary checks;
the current 95% clock-fit criterion remains a provisional heuristic, not a
theoretical safety guarantee. That redesign has not been implemented here.

## Playback completion

| Catalog | Compiled successes | KEYON compared | Export duration-limit errors |
| --- | ---: | ---: | ---: |
| PSG + OPLL | 15 | 13 | 2 |
| OPLL | 331 | 307 | 24 |

All 26 duration-limit cases have correction applied. The PSG + OPLL cases are
`msxplay.com/FinalFantasy/01_Prelude.vgm` and `07_Town.vgm`; both previously
completed comparison. Of the 24 OPLL cases, five previously could not compile
(the resolved buffer failures above), and 19 previously completed comparison.
These newly incomplete checks must not be silently omitted from fidelity claims.

The export limit is the source header duration times 1.25 plus two seconds.
This is a playback duration bound, not a CPU execution-speed timeout. A song
that does not finish within the bound is marked incomplete; counts are blank,
not zero. Whether correction lengthened the score, changed termination, or
encountered another playback issue is not established by this review. Do not
simply raise the limit and assume correctness without comparing intended length.

Applied outcomes are useful to separate from overall totals:

| Catalog | Applied + compiled + compared | Applied + compiled + incomplete export | Applied + buffer error | Applied + compile failure |
| --- | ---: | ---: | ---: | ---: |
| PSG + OPLL | 1 | 2 | 0 | 0 |
| OPLL | 54 | 24 | 21 | 2 |

## KEYON count comparison

Counts are per-channel inventories, not time-matched individual events, and
rhythm/PSG/SCC notes are not included. Compare the same completed input set to
avoid interpreting a changed catalog or incomplete export as a count improvement.

| Paired completed set | Inputs | Source total | Export before | Export after | Shortage before / after | Excess before / after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PSG + OPLL | 13 | 5,013 | 4,967 | 4,967 | 46 / 46 | 0 / 0 |
| OPLL | 285 | 192,686 | 190,777 | 190,870 | 1,941 / 1,848 | 32 / 32 |

On the paired OPLL set, 12 inputs improve in shortage-plus-excess count, 273
are unchanged, and none worsen. No weighted quality score is defined. Examples:

- `LGPNT01`: shortage/excess sum 58 -> 3.
- `sx01v`: 11 -> 0.
- `SORCER10`, `SORCER44`, `SORCER58`: 5 -> 0 each.

For completeness, totals over all currently completed exports are:

| Catalog | Compared | Source KEYON | Export KEYON | Shortage | Excess |
| --- | ---: | ---: | ---: | ---: | ---: |
| PSG + OPLL | 13 | 5,013 | 4,967 | 46 | 0 |
| OPLL | 307 | 216,786 | 214,528 | 2,290 | 32 |

Those latter totals are not a before/after improvement measurement.
Alest202 still has `buffer_error`; normalization was declined because a gate
boundary exceeded the bound. YsSMS01 has correction applied and completes
compilation/comparison; this does not by itself establish waveform equality.

## Follow-up priorities

1. Fix MGSC minimum representable lengths around tempo 149 (`r%1` failures).
2. Investigate the 26 incomplete exports against source/target durations and
   termination before claiming these cases reproduce the source.
3. Evaluate semantic per-note correction bounds, rather than treating the 95%
   global-fit heuristic as a safety proof.
4. Improve phrase-level compression separately. The sx01v inspection shows 95
   applied melodic loops, 58 of them single-unit repetitions. Last-pass exits
   (`|`) and inferred portamento are not reconstructed; current macro layout
   optimizes text length rather than musical presentation.

Keep normalization optional. Do not broaden claims from the successful sample
and sx01v benchmark to the full catalog, or overwrite native timing evidence.
