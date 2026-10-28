# Structure-aware macros

Use `--enhance-macros` with `vgm2mml.py` or `scripts/batch_vgm_to_mgs.py`. It is enabled by default; use `--legacy-macros` to restore the previous compressor. The transformation applies to melodic PSG/SCC/OPLL commands and OPLL rhythm, after the existing merged MML and synchronization formatting. It works with conventional or normalized target output.

```sh
python vgm2mml.py input.vgm --outdir outputs/enhanced --enhance-macros --dump-passes
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/enhanced --enhance-macros
```

Existing generated macro calls are expanded for reselection. Finite loop bodies stay structured and become independently searchable. The search can also place an entire loop inside a larger macro. Rhythm and melodic grammar are kept separate; replacements never cross synchronization comments or break tie token boundaries. Macro bodies do not call other macros in this first implementation.

Candidate policy: 1..24 or 1..64 sibling nodes, bodies up to 512 characters, at most 32 definitions. These are bounded search policies, not MGSC format limits. Four allocations and the prepared baseline compressor are compared: narrow and wide greedy searches, plus wide searches starting with the second or third ranked first candidate. Subsequent choices are greedy. This revisits an initial decision but does not guarantee globally optimal allocation. Macro count takes precedence, with complete character count including definitions, spaces, wrapping and comments as the tie-breaker.

Before selection, generated macros are expanded and octave/volume setters are
canonicalized into entry state plus relative changes. Redundant setters are
removed. Absolute octave/volume commands are forbidden inside newly selected
macro bodies, including nested loops; entry resets remain in callers. Unknown
loop-entry state is treated conservatively so a reset needed by each iteration
is not deleted. This target pass changes neither native Segments nor score timing.

Macro bodies always retain relative changes, including changes of three or more
steps. Only callers may shorten such runs to absolute `oN`/`vN`. Rhythm volume
setters stay outside rhythm macros; melodic relative-volume grammar is not
imposed on percussion.

Every alternative must reproduce timed musical commands with the same effective
octave/volume state and exit state. Literal setter spelling can differ.
Among the bounded allocation alternatives, fewer macro definitions take priority
over source character count. This does not prove a globally minimal macro bank
and may increase text when entry resets must stay outside definitions.
Compilation is separate: the batch compiler or experiment runner checks
whole-output capacity. Macro substitution usually reduces MML source characters
rather than compiled track bytes. Relative/absolute driver bytecodes can have
slightly different dispatch timing even with matching musical semantics.

With `--dump-passes`, `*.macros.csv` records the selected macro bodies, occurrence counts, estimated savings and tree locations. Paths identify a synchronization-delimited block and nested-loop positions in the target command tree at that selection step. They are not Segment indices or persistent source marker IDs. `*.macro_selection.json` records all allocation character/macro counts and the selected strategy. When the prepared baseline wins, the structured-search CSV is empty; the baseline's relative definitions remain in the MML.

`*.macro_state.before.mml`, `*.macro_state.relative.mml` and
`*.macro_state.json` expose the mandatory state preparation before selection.
The JSON records original absolute values, known prior values, relative spelling
and target-tree locations. Blueprint uses the same preparation through the
shared compressor, while source timbres/dynamics remain absent from its score.

## Complete phrases and adjacent repeats

After relative-state preparation, exact adjacent command groups are folded into
finite loops before nonadjacent macro search. This includes repeated held-note
volume steps such as `( & e64`; accumulation is retained in each iteration.
Counts above 255 are split into legal chunks. Default-length changes (`lN`) are
not folded by this pass: equal literal text alone does not prove equivalent
MGSC compilation of a changing default length.

Macro selection prefers multiple-attack phrases over complete single-gate
gestures. It rejects control-only bodies, isolated single events, candidates
starting with a held continuation and candidates ending before another tied
continuation. A complete one-gate gesture can include a curve and its release
rest, so this is not a minimum-character or minimum-duration filter. Nested
scope endings without a confirmed release are treated conservatively. Candidate
class priority is preserved by all first-choice portfolio alternatives.

These boundaries are proven from target MML attack/tie/rest spelling; they are
not a reconstruction of source gate IDs. Native score, Segment and curve
evidence remains unchanged. The transformation does not create attacks or
select new software envelopes.

`*.macro_phrases.before.mml`, `*.macro_phrases.after.mml` and
`*.macro_phrases.loops.json` retain this pass. Selected macro CSV rows include
`phrase_kind` (`multiple_attacks` or `complete_gate`). Short continuation and
control fragments stay inline or inside finite loops and consume no macro slot.

For an already generated MML:

```sh
python scripts/experiment_structured_macros.py input.mml --outdir outputs/macro-check --mgsc-module /path/to/mgsc/package/dist/index.js
```

The runner preserves MML on compiler failure and writes `compile.log` and `comparison.json`. It is intended for converter-generated finite MML supported by the target parser, not arbitrary handwritten MML.

Selective expansion of inner loops for alternative macro boundaries and permanent Segment/marker mappings are deferred. This stage first measures better macro selection with loop spelling preserved.

Macro definitions are wrapped at 120 characters per physical line. Longer unwrapped definitions caused an Undefined Macro diagnostic in the es59 follow-up; wrapping preserves the command stream and character cost.
