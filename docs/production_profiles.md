# Production MML comparison profiles

`export_mgs.py` defaults to `--macro-mode v110 --loop-mode v110`.
The musical layer, native evidence, reference VGM, blueprint and MIDI remain
available. Only ordinary production rendering/compaction uses the selected
policy. FM24ms, normalization8ms and software volume curves retain their
export defaults.

| Selection | Meaning |
|---|---|
| `--macro-mode v110` | v1.1.0 greedy preparation plus its historical enhanced allocation; excludes later relative/phrase preprocessing |
| `--macro-mode current` / `--current-macros` | Current relative-state and complete-phrase preprocessing plus enhanced allocation |
| `--macro-mode greedy` / `--greedy-macros` | Current shared preprocessing with greedy allocation (formerly legacy-macros) |
| `--loop-mode v110` | Historical loop-first software-envelope rendering |
| `--loop-mode current` | Current loop-first rendering |
| `--loop-mode envelope-first` / `--envelope-first-loops` | Current older envelope-first route (formerly legacy-loops) |
| `--loop-mode score-guided` / `--score-guided-loops` | Current loop-first route with source-score guidance |

To reproduce the previous enhanced default, use both
`--macro-mode current --loop-mode current`. To reproduce the previous hybrid
legacy+legacy choice, use `--macro-mode greedy --loop-mode envelope-first`.
Old switch spellings remain hidden compatibility aliases. Neither legacy name
means the v1.1.0 release preset. The two axes are independently selectable.
Explicit score normalization uses the current timing-aware envelope renderer;
that opt-in is outside strict v1.1.0 reproduction.

The batch API and canonical converter retain their current defaults; export
forwards its explicit choices and records them in batch diagnostics. Blueprint
rendering happens before the production macro policy is entered and retains its
current independent score-oriented implementation. Final ordinary MML retains
current layout, so whitespace may differ even when compiled bytes match.

The isolated `py/production_v110/` modules are copied from tag v1.1.0, with
only their intra-package imports qualified. They depend on unchanged shared
source/target helpers. Do not apply later blueprint compaction changes there
without a separate baseline compatibility decision. Native evidence is never
replaced with a historical or target-normalized source representation.
