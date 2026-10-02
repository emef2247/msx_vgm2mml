# Shared VGM timing: local regression and adoption

Date: 2026-10-02. Branch: `codex/experiment-vgmticks`.
The user ran the batch regression and approved the shared VGM sample clock
for adoption after reviewing these results. Merge into main is to be performed
by the user through a PR. Musical duration normalization is the next separate
task; it is not enabled by this adoption.

## Runs and evidence

```sh
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/psg_scc --outdir outputs/mgs/psg_scc
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/psg_opll --outdir outputs/mgs/psg_opll
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/opll
```

An earlier invocation used the misspelled `pgs_opll` input directory. The
subsequent correctly spelled run produced the PSG/OPLL report reviewed here.
Evidence: each output directory's `results.csv`, `results.json` and per-input
conversion/compilation logs. CSV and JSON row counts and status totals agree.
The reports and private fixtures remain outside this documentation commit.
This review read the existing outputs; it did not rerun or alter conversions.

| Input group | Reported inputs | MGS success | Track buffer full | Conversion failure |
| --- | ---: | ---: | ---: | ---: |
| PSG/SCC | 98 | 78 | 20 | 0 |
| PSG/OPLL | 26 | 15 | 11 | 0 |
| OPLL | 545 | 306 | 238 | 1 |
| Total | 669 | 399 | 269 | 1 |

All 269 compilation failures explicitly report `Track buffer full`. The one
conversion failure is `temp/export_from_msxplay.com/YsSMS01.vgm`: its log says
the input was not found. The user confirmed deliberately deleting this file.
Exclude it from converter failure/adoption assessment while preserving the
reported raw totals. There are 668 present inputs: 399 MGS successes, 269 buffer
failures, and zero observed converter exceptions. No `Bad MML` or `Object too
big` failure appears in these reports.

## OPLL melodic KEYON counts

All 399 compiled inputs have `keyon_status=compared`; there are no comparison
errors. Failed compilations have no comparison counts and are excluded below.
Group names describe input directories, not the chips measured by this metric.

| Input group | Compared inputs | Source KEYON | Exported KEYON | Missing count | Extra count |
| --- | ---: | ---: | ---: | ---: | ---: |
| PSG/SCC | 78 | 24100 | 23658 | 442 | 0 |
| PSG/OPLL | 15 | 5294 | 5241 | 53 | 0 |
| OPLL | 306 | 201152 | 199190 | 1994 | 32 |
| Total | 399 | 230546 | 228089 | 2489 | 32 |

These are OPLL melodic rising-edge counts only. They exclude rhythm attacks
and do not measure PSG/SCC notes. Missing/extra values sum per-channel count
shortages/excesses, not time-matched event identities. Opposing errors within
one channel can cancel. Equal totals do not prove matching sound or notes.
The fixture collection also contains duplicate inputs, so totals are per file,
not per unique musical work. See `docs/opll_keyon_counts.md`.

Representative OPLL results:

| Input | Source | Exported | Missing | Extra |
| --- | ---: | ---: | ---: | ---: |
| www.smspower.org/YSSMS/YsSMS01.vgm | 559 | 558 | 1 | 0 |
| msxplay.com/grider/grider.vgm | 2596 | 2559 | 37 | 0 |
| msxplay.com/sx01v/sx01v.vgm | 1615 | 1604 | 11 | 0 |
| vgmrips.net/PRIMK/PRIMK09.vgm | 1416 | 1022 | 394 | 0 |
| vgmrips.net/PRIMK/PRIMK13.vgm | 767 | 466 | 301 | 0 |
| vgmrips.net/FMPAC/FMPAC03.vgm | 307 | 167 | 140 | 0 |

Large count differences remain investigation candidates. This review does not
attribute them to the timing change; no before/after catalog baseline was
compared. It also does not explain individual shortages as EOF truncation
without inspecting those inputs. Successful compilation is not playback proof.

## Decision and next boundary

The user accepted shared integer timing, complete wait accounting and source
sample metadata as the production baseline. This regression found no converter
exception for a present input; buffer capacity and KEYON fidelity remain
separate known concerns. The result is not a claim of sample-exact audio or
optimal compression.

After the user's PR/merge, proceed to musical duration normalization with raw
`vgmticks` retained as evidence. Keep correction output separate from source
Segment timing and evaluate compression, compilation and KEYON counts. Do not
silently treat tolerant musical matching as exact source equality.
