# Short-first hierarchical loop experiment

## Scope and reproducibility

Compared immediate short-first replacement with retained overlapping candidates
on normalized OPLL melody note units from sample and sx01v. Production conversion
is unchanged. Run from the repository root:

```sh
python scripts/experiment_hierarchical_loops.py <input.vgm> --outdir <separate-output> --normalize-lengths
```

Inputs: public psg_opll/msxplay.com/sample/sample.vgm and local_only/opll/
msxplay.com/sx01v/sx01v.vgm under tests/fixtures. Reports and private target
fragments remain outside Git at
`C:/Users/ef110/Documents/Codex/2026-09-25/co/outputs/hierarchical-loops/`.
Each tree has comparison.csv, per-channel .loops.json and .mml fragments,
and baseline conversion/pass evidence. Channel indices enumerate captured active
OPLL melodic tracks; they are not VGM channel numbers. Fragments are diagnostics,
not standalone playable songs.

`--max-phrase` defaults to 128 original note/rest units; `--max-depth` to 3.
These are experiment bounds, not hardware limits or whole-song exhaustive search.
The immediate method scans increasing original-unit widths, substitutes markers,
and compares expanded signatures across marker boundaries. The retained method
keeps competing intervals until dynamic programming chooses minimum emitted text
cost; each candidate body can recursively contain shorter loops. Relative setters
and ties are preserved by exact emitted-command equality. Counts are capped at255.

## Measurements

Sum of OPLL melody body characters, before final setter pruning, synchronization
formatting and macro extraction; these are not full MML or compiled MGS sizes.

| Input | Flat | Existing | Immediate | Retained |
| --- | ---: | ---: | ---: | ---: |
| sample | 7649 | 4493 | 4493 | 4493 |
| sx01v | 17610 | 14240 | 14484 | 14204 |

sample reaches depth2; sx01v retained reaches depth3 in one track. Retained saves
36 characters (about0.25%) against existing sx01v processing. Immediate is244
characters worse. A small synthetic overlap example also demonstrates that
committing the shortest repeat first can hide a better larger placement.

Adjacent exact trajectory candidate pairs (overlapping pairs, not independent
phrases): sample287 with16 differing emitted command sequences; sx01v1337 with73.
This diagnoses one restriction but does not quantify all missed musical repeats:
trajectory differences exclude candidates before this count.

Reference syntax audit: sample has12 physical loop definitions,11finite,2with
last-pass exits and maxdepth2. Eleven ordinary bodies are192 score steps.
sx01v has40 definitions,35finite,11with exits,maxdepth2; phrase lengths include
12/48/384/768/1536 steps. These physical source counts cannot be compared directly
with generated per-channel tree counts. This experiment does not yet establish
which individual reference windows were recovered. In particular it does not
implement last-pass exits, infinite song loops, macros, or effective-state equality
between different command spellings.

## Preservation and interpretation

Every selected tree was expanded and checked against the entire original sequence
of trajectory validation keys AND emitted command blocks. No note/rest, duration,
KEYON-producing command, or control was added/deleted/reordered by these trees.
Five focused tests cover overlapping choices, nesting, depth limits, and source/
command mismatch rejection. No additional MGS-to-VGM/audio comparison was run;
exact expansion is evidence for this transformation only, not absolute converter
accuracy.

Important limitation: the harness observes the existing target rendering stage,
which already includes envelope decisions. It is a controlled comparison of loop
search strategies, not yet the proposed pre-envelope production pipeline. The
pure tree algorithm can consume earlier note units, but a safe integration needs
source-linked structure and envelope processing inside that structure.

The short-first idea works, but changing search order/depth alone did not recover
large additional compression here. Retaining candidates is preferable to an
irreversible greedy pass. Next investigate reference-window missed matches,
last-pass exits, and effective control-state equality before moving the hierarchy
before envelope/macro decisions. Keep source trajectories intact; do not infer
that matching pitch/duration alone authorizes repeating different envelopes.
