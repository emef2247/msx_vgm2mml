# Hierarchical-loop catalog regression (PR55)

Recorded: 2026-10-04. The user identifies the completed test-checkout run as PR55 (correcting the earlier PR56 label).

## Scope and provenance

- Current results and this record belong to `I:/wsl/repositories/emef2247/test/msx_vgm2mml`; the original checkout is being used independently for OPM work.
- Current inputs: `outputs/mgs/hierarchical_loop/{opll,psg_opll,psg_scc}/results.csv` in the test checkout.
- Baselines: original checkout `outputs/mgs/{opll,psg_opll,psg_scc}`, `outputs/mgs/normalize-lengths/{opll,psg_opll,psg_scc}`, and `outputs/mgs/hierarchical_loop/{opll,psg_scc}`.
- The user path `normalize-lengths/osg_opll` resolves to the existing `psg_opll` directory.
- Previous hierarchical OPLL has only 126 recorded CSV rows and no results.json. Previous hierarchical psg_opll is unavailable.
- Audit artifacts: `outputs/mgs/hierarchical_loop/comparison_20261004/`. The Japanese report and seven CSVs retain the per-input evidence. Source CSV SHA-256 values and CSV/JSON consistency checks are in comparison.json.
- Test checkout HEAD at audit time is `e661dc372ea23333fa9770d5fdad1f40c019eac7`; result files do not certify the commit used for the earlier execution.
- Counts are input paths, not deduplicated recordings. No conversion behavior, original results, allocation, fixtures or music contents were changed. No regression was rerun.

## Aggregate compile outcomes

| Run | Category | Inputs | Success | Buffer error | Conversion timeout | Other compile failure | Other failure |
|---|---|---:|---:|---:|---:|---:|---:|
| old | opll | 545 | 306 | 238 | 0 | 0 | 1 |
| old | psg_opll | 26 | 15 | 11 | 0 | 0 | 0 |
| old | psg_scc | 98 | 78 | 20 | 0 | 0 | 0 |
| normalized | opll | 565 | 331 | 232 | 0 | 2 | 0 |
| normalized | psg_opll | 26 | 15 | 11 | 0 | 0 | 0 |
| normalized | psg_scc | 98 | 78 | 20 | 0 | 0 | 0 |
| previous | opll | 126 | 92 | 33 | 1 | 0 | 0 |
| previous | psg_scc | 98 | 78 | 19 | 1 | 0 | 0 |
| current | opll | 565 | 324 | 181 | 59 | 1 | 0 |
| current | psg_opll | 26 | 15 | 8 | 3 | 0 | 0 |
| current | psg_scc | 98 | 78 | 19 | 1 | 0 | 0 |

Current total: 689 inputs, 417 successes, 208 buffer errors, 63 conversion timeouts, one other compiler failure. All 63 raw convert_error rows have retained logs reporting a 300-second timeout. They were previously buffer errors, so their disappearance from the buffer_error count is not a recovery. The old missing YsSMS01 temporary export was deliberately deleted and is not a converter regression.

## Matched compile outcomes

| Baseline | Category | Shared | Recovered successes | Lost successes |
|---|---|---:|---:|---:|
| old | opll | 543 | 1 | 5 |
| normalized | opll | 565 | 3 | 10 |
| previous | opll | 126 | 5 | 1 |
| old | psg_opll | 26 | 1 | 1 |
| normalized | psg_opll | 26 | 1 | 1 |
| old | psg_scc | 98 | 0 | 0 |
| normalized | psg_scc | 98 | 0 | 0 |
| previous | psg_scc | 97 | 0 | 0 |

Old/current OPLL: 306 to 302 successes among 543 shared paths. The raw increase from 306 to 324 includes 22 added, successful F1SPRT3D paths (including aliases); two temporary-export paths were removed. Old/current psg_opll has one recovery and one lost success; psg_scc has no changed success membership.

Previous/current OPLL: 92 to 96 successes among the 126 recorded paths. Recovered ALESTE09, ALESTE17, Alest216, FFMSX01 and FFMSX11; lost FFMSX14 to buffer_error. This confirms the intended FFMSX01 recovery in the catalog run, but does not establish a whole-catalog comparison with that partial baseline.

Compared with the oldest baseline, lost successes are Alest213, FFMSX14, TOGZL15, XAK_II12, GF2SMS02 and the psg_opll FinalFantasy/14_GurguVolcano input. PRIMK15 changed from buffer_error to the compiler diagnostic "Can't defined Macro in 121" (macro *31); it was not a previous success.

Normalized/current OPLL: 331 to 324 successes among 565 paths, three recoveries and ten lost successes. Do not describe the current structure as uniformly better than normalization.

## KeyOn findings

Only OPLL melodic rising edges are counted. This does not measure PSG/SCC notes or OPLL rhythm triggers. A directory category is not a guarantee that every contained file has only the named chips. Unmeasured counts stay blank, not zero.

- Current opll: 324 comparisons; source 220,684, regenerated 219,181, missing 1,535, extra 32.
- Current psg_opll: 15 comparisons; source 5,103, regenerated 5,048, missing 55, extra 0.
- Current psg_scc: 78 comparisons; source 24,100, regenerated 23,658, missing 442, extra 0.
- Old/current shared OPLL comparisons (301): source 196,078 in both; missing 1,975 to 1,089, extra 32 unchanged. Missing edges decreased by 886 across FMPAC03 and PRIMK01/09/13. This cannot be attributed solely to loop compression across historical runs.
- Previous/current shared OPLL comparisons (91): all counts unchanged (missing 702, extra 0).
- Normalized OPLL 24 and psg_opll two successful compiles lacked completed KeyOn export comparisons due to the playback-duration limit. These are not compiler failures.

## Size findings

Only inputs compiling successfully in both compared runs are included. MML character totals include whitespace/comments/newlines, decoded strictly as UTF-8 or CP932 (recorded per file); MGS bytes include headers/padding and are not per-track buffer use.

| Baseline | Category | Paired successes | MML characters before / after | Change | MGS bytes change |
|---|---|---:|---|---:|---:|
| old | opll | 301 | 2,675,234 / 2,555,918 | -4.46% | +2.40% |
| normalized | opll | 321 | 2,700,620 / 2,793,828 | +3.45% | +10.79% |
| previous | opll | 91 | 849,280 / 807,017 | -4.98% | -5.20% |
| old | psg_opll | 14 | 133,753 / 127,687 | -4.54% | +1.86% |
| normalized | psg_opll | 14 | 138,353 / 127,687 | -7.71% | +1.72% |
| old | psg_scc | 78 | 708,340 / 645,430 | -8.88% | -0.77% |
| normalized | psg_scc | 78 | 708,340 / 645,430 | -8.88% | -0.77% |
| previous | psg_scc | 77 | 631,253 / 634,750 | +0.55% | +0.00% |

Against the oldest baseline, source MML became shorter in all categories, while MGS totals grew in opll and psg_opll. Against previous hierarchical OPLL, both MML characters and MGS bytes decreased by about 5%. Source compression and compiled track capacity must be evaluated separately.

## Remaining evaluation

- Investigate the lost compile successes separately from timeout cases: macro selection, loop spelling, actual per-track usage and allocation may matter; their causes have not been established by this audit.
- Timeout cases need a separately authorized longer run before claiming completion or capacity recovery. Timing out is not proof of a conversion exception, nor proof that completion will be bounded.
- Keep compile status, MML character count and KeyOn differences as separate measurements. No composite score or audio-equivalence claim is made.
- Input matching uses category and relative path. Historical input hashes/options manifests are unavailable; do not infer an isolated causal effect from these whole-run comparisons.
