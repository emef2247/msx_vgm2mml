# OPLL reference MML loop inventory and phrase lengths

The user requested a small structural survey before further loop reconstruction,
including phrase lengths and a reusable method for later PSG/SCC comparison.
Only `tests/fixtures/local_only/opll` was surveyed; no conversion/catalog playback
was run and no reference fixture was modified. There are currently two MML files
in this tree: grider and sx01v. This is a two-score sample, not a catalog-wide
distribution of OPLL music. Private MML contents are not copied here.

## Definitions and method

`scripts/audit_mml_loops.py` reuses the bounded reference parser, strips semicolon
comments/headers/voice definitions, and interprets channel/grouped-channel bodies.
Each explicit `[` definition is counted once in source statistics, even when
applied to several tracks. The channel-expanded count is reported separately.
Loop execution/iteration count does not multiply the number of definitions.
Shared brackets are marked as containing an exit/child when any target track
contains one. Depth starts at one; children of whole-song loops have depth two.

Lengths are score steps: quarter=48 and whole note=192. Whole-note equivalents
may be read as 4/4 bar equivalents only; no time signature is inferred. Gates,
tempo-derived seconds, VGM sampling times and amplitude envelopes are outside
this length measure. Nested finite repetitions contribute their expanded score
length to the enclosing phrase. Default lengths, dots, ties/`^` extensions,
explicit `%` lengths and rhythm `:` are accounted for.

`body_steps_min/max` is the full ordinary iteration, including the section after
`|`; `common_steps_min/max` is the portion before the exit; `final_steps_min/max`
is the final finite pass, which skips the exit tail. Expanded finite totals are
recorded separately. Infinite loops are inspected for one body traversal and
have no asserted finite total. A phrase containing an infinite child cannot be
given a finite body length and is rejected. Durations are aggregated over nested
invocations; varying default-length effects produce ranges rather than a guessed
single duration.

Unsupported syntax is reported in `files.csv` and causes a nonzero exit status;
it is never counted as zero loops. The initial audit does not support macro calls
or portamento duration semantics inside a loop. Both current scores parsed fully.
Do not claim that every future PSG/SCC score is already supported.

## Results

| Score | Source loop definitions | Channel-expanded definitions | Finite | Infinite | With last-pass exit | Containing children | Maximum depth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| grider | 15 | 21 | 14 | 1 | 12 | 1 | 2 |
| sx01v | 40 | 48 | 35 | 5 | 11 | 5 | 2 |
| Total | 55 | 69 | 49 | 6 | 23 | 6 | 2 |

All 23 exit-bearing definitions are finite. These make up about 47% of finite
definitions. Grider's nested count includes the whole-song loop enclosing the
rhythm's short loops; it is not evidence of deeply nested melodic phrases.

Repeat-count distribution (source definitions): 2 times=25, 3=1, 4=4, 5=1,
6=1, 7=1, 8=4, 16=12, and infinite (`]0`)=6.

Full ordinary phrase-length distribution, counting source definitions once and
combining grouped tracks when they agree:

| Steps | Whole-note / 4/4-bar equivalent | Source definitions |
| ---: | ---: | ---: |
| 12 | 1/16 | 12 |
| 48 | 1/4 | 5 |
| 192 | 1 | 14 |
| 384 | 2 | 7 |
| 768 | 4 | 6 |
| 1,536 | 8 | 10 |
| 7,872 | 41 | 1 |

The longest entry is grider's entire infinite song-loop body, not a short phrase.
All grouped tracks' ordinary body lengths agree in these scores. Channel-expanded
length observations differ in frequency (69 rather than 55) and are separately
retained in summary JSON; do not mix the two denominators when comparing catalogs.

Grider's fourteen finite definitions are rhythm loops of one whole note each;
twelve use `|` and have final passes of 96 or 144 steps instead of 192.
Its melodic tracks use the enclosing 41-whole-note song loop rather than locally
written melodic loops. For sx01v, the musical structure includes 2/4/8-whole-note
phrases alongside one-note and short multi-note repeats, and several finite
phrase loops have different final-pass lengths. This supports examining phrase
hierarchy and last-pass exits rather than increasing depth alone.

## Artifacts and later comparison

Command used:

```sh
python scripts/audit_mml_loops.py tests/fixtures/local_only/opll \
  --outdir C:/Users/ef110/Documents/Codex/2026-09-25/co/outputs/mml-loop-statistics/opll
```

`loops.csv` contains channel/source identifiers, source line, nesting, repeat
count, ordinary/common/final/expanded lengths. `files.csv` contains per-score
counts and parse status; `summary.json` contains aggregate distributions.
No raw phrase text is exported. Six focused synthetic tests cover comments,
grouped tracks, nesting, last-pass exits, dotted/tied lengths and unbounded bodies.

For the planned PSG/SCC survey, use the same script with a separate output tree:

```sh
python scripts/audit_mml_loops.py tests/fixtures/local_only/psg_scc \
  --outdir outputs/mml-loop-statistics/psg_scc
```

That second survey has not been executed. Check unsupported files and duplicate
score variants before treating its distribution as comparable; do not count
original/reference/edited copies as independent songs without stating the scope.
This audit inventories authored structure, not which loops current conversion
recovers. A subsequent recovery study must align source loop definitions with
generated targets separately.
