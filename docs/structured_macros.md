# Structure-aware macros

Use `--enhance-macros` with `vgm2mml.py` or `scripts/batch_vgm_to_mgs.py`. It is enabled by default; use `--legacy-macros` to restore the previous compressor. The transformation applies to melodic PSG/SCC/OPLL commands and OPLL rhythm, after the existing merged MML and synchronization formatting. It works with conventional or normalized target output.

```sh
python vgm2mml.py input.vgm --outdir outputs/enhanced --enhance-macros --dump-passes
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/enhanced --enhance-macros
```

Existing generated macro calls are expanded for reselection. Finite loop bodies stay structured and become independently searchable. The search can also place an entire loop inside a larger macro. Rhythm and melodic grammar are kept separate; replacements never cross synchronization comments or break tie token boundaries. Macro bodies do not call other macros in this first implementation.

Candidate policy: 1..24 or 1..64 sibling nodes, bodies up to 512 characters, at most 32 definitions. These are bounded search policies, not MGSC format limits. Four allocations are compared: narrow and wide greedy searches, plus wide searches starting with the second or third ranked first candidate. Subsequent choices are greedy. This revisits an initial decision but does not guarantee globally optimal allocation. The original output remains a candidate and wins ties; final complete character count includes definitions, spaces, wrapping and comments.

Every alternative must reproduce the exact expanded timed command stream. This includes setters as well as notes. Compilation is separate: the batch compiler or experiment runner checks whole-output capacity. Macro substitution usually reduces MML source characters rather than compiled track bytes.

With `--dump-passes`, `*.macros.csv` records the selected macro bodies, occurrence counts, estimated savings and tree locations. Paths identify a synchronization-delimited block and nested-loop positions in the target command tree at that selection step. They are not Segment indices or persistent source marker IDs. `*.macro_selection.json` records all allocation character counts and the selected strategy. When the baseline wins, the selected CSV is empty and its existing definitions remain in the MML.

For an already generated MML:

```sh
python scripts/experiment_structured_macros.py input.mml --outdir outputs/macro-check --mgsc-module /path/to/mgsc/package/dist/index.js
```

The runner preserves MML on compiler failure and writes `compile.log` and `comparison.json`. It is intended for converter-generated finite MML supported by the target parser, not arbitrary handwritten MML.

Selective expansion of inner loops for alternative macro boundaries and permanent Segment/marker mappings are deferred. This stage first measures better macro selection with loop spelling preserved.

Macro definitions are wrapped at 120 characters per physical line. Longer unwrapped definitions caused an Undefined Macro diagnostic in the es59 follow-up; wrapping preserves the command stream and character cost.
