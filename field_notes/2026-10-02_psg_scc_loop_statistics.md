# PSG/SCC MML loop survey: results and sampling limitations

## Corrected reference scope (2026-10-03)

The user confirmed that only the seventeen original `gra2_001` through
`gra2_017` MML files under `psg_scc/msxplay.com/gra2_msx` are valid references.
Exclude all `with_sync_mark` variants, including files split at loop boundaries.
Also exclude `vgmrips.net/NEMESIS2`: these are VGM-derived conversion outputs.
The older mixed-population statistics below are historical and superseded.

```sh
python scripts/audit_mml_loops.py tests/fixtures/local_only/psg_scc/msxplay.com \
  --exclude-dir with_sync_mark --outdir outputs/mml-loop-statistics/psg_scc-original
```

The scoped audit found exactly 17 files: 3 parsed and 14 unsupported. Parsed
files are gra2_002 (13 definitions), gra2_008 (23), and gra2_017 (none).
Totals: 36 definitions, 30 finite, 6 infinite, 0 observed last-pass exits,
5 definitions containing child loops, maximum depth 2. Depth counts: 1=19,
2=17. Repeat counts: 2=20, 4=6, 5=2, 15=2, infinite=6.

Ordinary phrase lengths (quarter=48 steps): 7=1, 10=10, 12=2, 24=10,
48=7, 1152=6 definitions. No variable ordinary lengths were observed.

The fourteen unsupported originals are gra2_001, 003, 004, 005, 006, 007,
009, 010, 011, 012, 013, 014, 015, and 016. Macro calls and unsupported
control syntax prevent their duration analysis. These are audit limitations,
not invalid MML. They must not count as zero-loop files. Thus no conclusion
about the general absence of exits or phrase-length distribution is justified.
Next improve parser coverage before comparing the reference population with OPLL.

Reports were saved separately under
`C:/Users/ef110/Documents/Codex/2026-09-25/co/outputs/mml-loop-statistics/psg_scc-original/`
(`summary.json`, `files.csv`, `loops.csv`). The user's previous reports and
private fixtures were untouched. The audit's exit code 1 indicates unsupported
files; it still writes the partial results.

## Historical initial review

The user ran the following audit after the OPLL survey and requested that the
results and interpretation be recorded. The existing CSV/JSON files were read;
no conversion, compilation or second survey was run, and no fixture was modified.

```sh
python scripts/audit_mml_loops.py tests/fixtures/local_only/psg_scc \
  --outdir outputs/mml-loop-statistics/psg_scc
```

Evidence: `outputs/mml-loop-statistics/psg_scc/{summary.json,files.csv,loops.csv}`.
Compare with `field_notes/2026-10-02_opll_reference_loop_statistics.md`.

## Recorded aggregate results

| Measure | Result |
| --- | ---: |
| MML files found | 189 |
| Parsed files | 115 |
| Unsupported files | 74 |
| Source loop definitions | 4,253 |
| Channel-expanded definitions | 4,253 |
| Finite definitions | 4,235 |
| Infinite definitions | 18 |
| Definitions with last-pass exit | 0 |
| Definitions containing child loops | 15 |
| Maximum depth | 2 |
| Depth-one definitions | 4,202 |
| Depth-two definitions | 51 |
| Variable ordinary phrase lengths | 0 among parsed definitions |

Repeat distribution: 2=974, 3=513, 4=651, 5=693, 6=507, 7=578,
8=135, 9=145, 10=1, 11=3, 12=11, 13=16, 15=6, 16=2, infinite=18.
No repeated-track source bracket expansion changes the denominator in this run.

Ordinary loop-body length distribution (quarter=48 score steps):

| Steps | Definitions |
| ---: | ---: |
| 1 | 1,608 |
| 2 | 95 |
| 3 | 2,097 |
| 4 | 37 |
| 6 | 12 |
| 7 | 3 |
| 9 | 178 |
| 10 | 30 |
| 12 | 36 |
| 14 | 8 |
| 15 | 2 |
| 18 | 4 |
| 24 | 32 |
| 45 | 70 |
| 48 | 23 |
| 1,152 | 18 |

3,800 definitions (about 89.3%) have bodies of at most three score steps.
The largest parsed body is 1,152 steps: six whole notes, or six bars only if
assuming 4/4. Whole-note equivalents do not establish the score's meter.

## What the parsed population actually contains

`files.csv` permits separating two provenance groups:

| Subtree | Files found | Parsed | Unsupported | Parsed zero-loop files | Parsed loop definitions |
| --- | ---: | ---: | ---: | ---: | ---: |
| msxplay.com/gra2_msx | 169 | 95 | 74 | 89 | 108 |
| vgmrips.net/NEMESIS2 | 20 | 20 | 0 | 16 | 4,145 |

Thus only ten of the 115 parsed files contain explicit loops; 105 have none.
Zero-loop files were successfully parsed, not treated as parse failures. The
recursive input contains whole scores, synchronized variants and split files,
so 189 files must not be described as 189 independent songs.

The parsed msxplay loop-bearing files are three versions each of gra2_002 and
gra2_008 (original, synchronization-marked, and a split/marked variant). They
contribute 13*3 + 23*3 = 108 definitions. Their distribution is:
10 steps=30, 7=3, 12=6, 24=30, 48=21, 1,152=18. The eighteen infinite-loop
counts and fifteen enclosing-child-loop counts all come from this group.
These are version-weighted counts, not independent observations.

The NEMESIS2 group contributes 97.5% of all counted definitions. In particular,
GRA2_01 contributes 2,348, GRA2_04 contributes 1,098, GRA2_05 contributes 665,
and GRA2_02 contributes 34. The first three alone contribute 4,111 definitions.
Sampled file headers have the converter-style player name, chip section headers
and per-track allocation layout, with tempos 225/75. Together with thousands
of tiny loops, this is consistent with conversion output rather than a clean
collection of authored phrase structures. File provenance should be confirmed
before labeling every NEMESIS2 file as an original score; the headers alone are
not proof of how it was produced.

## Unsupported coverage

All 74 unsupported files are in the msxplay subtree:

- 46 fail on macro calls, whose duration the current audit deliberately refuses
  to ignore.
- 28 fail the bounded reference lexer on other syntax. Examples include the
  multiple-argument `h` command. These are audit-parser limitations, not proof
  that the MML is invalid for MGSC.

Of the seventeen original `gra2_001`..`gra2_017` MML files (excluding synchronized
and split variants), only gra2_002, gra2_008 and gra2_017 parsed. The last has no
explicit loops. Fourteen original scores remain outside the statistics, including
gra2_001, gra2_003 and gra2_005, which are important compression examples.

The audit's nonzero exit and "Some files were unsupported" are intentional.
Partial aggregate statistics remain available, but excluded files must not be
implicitly assigned zero loops or zero exits. Do not paste private MML fragments
from parser error messages into public notes; error categories suffice here.

## Comparison with the OPLL survey

| Metric | OPLL parsed set | PSG/SCC parsed set |
| --- | ---: | ---: |
| Parsed / found files | 2 / 2 | 115 / 189 |
| Source loop definitions | 55 | 4,253 |
| Finite definitions | 49 | 4,235 |
| Infinite definitions | 6 | 18 |
| Last-pass exits | 23 | 0 |
| Enclosing-child definitions | 6 | 15 |
| Maximum depth | 2 | 2 |

This is not yet a fair authored-music comparison. OPLL contains two structured
reference scores; the PSG/SCC set mixes score versions/slices and apparent
converter outputs, while many original scores are excluded. Therefore:

1. Do not conclude that PSG/SCC music generally lacks `|` exits. The observed
   zero applies only to the parsed subset, with particularly biased exclusions.
2. Do not conclude that PSG/SCC's musical phrases are usually 1..3 steps. The
   distribution is dominated by a few very long, tiny-loop-heavy MML files.
3. The shared maximum depth of two is a description of syntax, not proof that
   two-stage loop reconstruction is sufficient or equally effective for both
   chip groups.
4. Compare both step spelling and tempo policy before making physical-duration
   claims. A step at tempo 75 and one at 225 are not the same wall-clock interval;
   representations of essentially the same frame length can contribute different
   score-step values. Neither survey infers durations from VGM sampling here.

## Useful conclusions and next work

The audit reveals two distinct compression targets: tiny repeated target commands
in conversion output, and authored multi-note phrases in structured scores.
They should be measured separately. It also shows that obtaining a representative
reference distribution requires better macro and control-syntax coverage first.

For a controlled comparison:

1. Extend the bounded audit for macros (including length-state changes and any
   loops in definitions) and the unsupported timing-neutral controls, rather than
   silently deleting commands whose semantics have not been established.
2. Select original reference scores once per song, keeping synchronized/split
   variants and converter outputs as separately labeled populations.
3. Recompute ordinary/common/final phrase lengths and exit/nesting statistics for
   that reference set. Keep unsupported coverage visible.
4. Only then measure whether generated output recovers those reference phrases.

The initial review left the user's reports untouched. The subsequent scoped
audit above uses a separate output tree and supersedes the mixed totals.
