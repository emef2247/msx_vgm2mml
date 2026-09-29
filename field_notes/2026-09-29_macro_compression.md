# Non-adjacent macro experiment and gra2_003 compression

Date: 2026-09-29

## Scope

Investigated macros as a text representation; did not enable automatic macro
output in the converter. Added optional local regression fixtures gra2_003 and
gra2_005 in tests/test_local_compression.py. Private music data stays local.
Missing local fixtures skip individually. The tests compare expanded before/after
commands and final per-tick PSG/SCC states against Segment CSVs.

## Method and limits

MGSC 1.11 through the locally available mgsc-js package was used for compilation.
Experimental macro discovery used identical sequences of complete parsed target
nodes, including balanced loops, at separated positions. It considered widths
4..24 nodes, up to 32 definitions, and kept definition lines below 200 characters.
These are experiment bounds, not driver specifications or an optimal search.
No recursive macro calls were introduced. Tied continuations were not cut.
A production implementation should nominate phrases from performed-unit IDs and
retain occurrence mappings, rather than use this target-only experimental search.

Whitespace/comments were removed equally in compact/macro comparisons; track
lines were wrapped below 180 characters at token boundaries. Very long unwrapped
lines caused misleading truncation/errors in preliminary compiler probes and are
not included in the results below. Expanded macro/loop command sequences match
between the compared candidates. No new listening or sample-exact audio claim.

## Measurements

| Fixture | Current generated characters | Compact, no macros | Macro prototype |
| --- | ---: | ---: | ---: |
| gra2_003 | 58450 | 40218 | 24284 |
| gra2_005 | 12575 | 8438 | 5347 |

Both prototypes selected 32 definitions. These results demonstrate text savings,
not runtime byte savings. Gra2_005 compiles to 4794 used bytes with and without
macros. A small synthetic probe increased from 141 to 167 bytes when macroized;
therefore macro spelling must not be treated as guaranteed binary compression.

Gra2_003's unmodified generated text exceeds this mgsc-js wrapper's 49152-byte
source limit. Compact formatting avoids that limit, but both compact and macro
versions then fail with track-buffer-full under the normal allocation.

Individual tracks were compiled in isolation, keeping definitions and giving the
selected track 15000 bytes. This is measurement only: no production allocation
limit was changed, and isolated totals are not a successful whole-song compile.

| MML track | Default sync gap 1000 | Macro prototype | Only start/end sync |
| --- | ---: | ---: | ---: |
| 2 | 8402 | 8402 | 4524 |
| 3 | 5783 | 5783 | 4699 |
| 5 | 2888 | 2888 | 2592 |
| 6 | 3301 | 3301 | 3309 |
| 7 | 3013 | 3013 | 2964 |
| 8 | 3564 | 3564 | 3515 |
| Track total | 26951 | 26951 | 21603 |

Definitions consume another 886 bytes in track 0. The last column used
`--sync-min-gap 1000000000` as an experiment; default settings remain unchanged.
The small increase in track 6 reinforces that textual compactness is not a
binary-cost model. Even 21603 exceeds the 15000-byte total track budget.

## Conclusions and next work

- Macros can improve readability and source-size limits. The tested real-song
  macros do not reduce compiled track bytes, so do not enable them as a claimed
  solution to buffer-full.
- Sync-boundary expansion is material: retaining loops across the song reduces
  gra2_003's isolated track sum by 5348 bytes. Consider loop-aware sync marker
  placement that keeps valid common boundaries without forcing loop expansion;
  discuss the change in marker spacing before changing the existing contract.
- The 15000-byte budget requires further structural compression even after that.
  Investigate note/gesture variants and a validated compiled-byte cost model.
  Do not assume either improvement will recover the original authored program.
- Keep gra2_003 alongside gra2_005 for future validation; the longer fixture
  exposes source length, allocation and synchronization interactions.

Local artifacts: outputs/gra2_003_compression/, outputs/gra2_003_sparse_sync/,
outputs/macro_investigation/ (prototype MML, reports and compiler logs).
