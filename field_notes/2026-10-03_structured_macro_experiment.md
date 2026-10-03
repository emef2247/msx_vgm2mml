# Structure-aware macro allocation (2026-10-03)

## Controlled comparison

Input: the previously validated structural sample and sx01v MML. Loop spelling and timing are preserved. Existing macros are expanded and reselected using recursive tree search and a bounded allocation portfolio. Normalization remains off.

| Fixture | Previous MML characters | Enhanced characters | Saved | Reduction | MGSC | Buffer error |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| sample | 6333 | 4913 | 1420 | 22.4% | success | none |
| sx01v | 17187 | 14938 | 2249 | 13.1% | success | none |

All alternatives pass exact expanded timed-command equality. Compiler: local mgsc-js 2.0.0 / MGSC 1.11. Artifacts: Codex `outputs/structured-macros/{sample,sx01v}`. The public sample was also converted through the new CLI option and compiled successfully.

sample allocation characters: baseline 6333; width24-first0 4913; width64-first0 4965; width64-first1/2 4993. sx01v: baseline 17187; width24-first0 16010; width64-first0 14938; width64-first1 15163; width64-first2 15099. Thus a larger search does not always produce the shortest allocation; retain and compare complete alternatives.

This confirms source-text savings for two already compilable fixtures. It does not demonstrate a previously failing buffer_error being resolved, or new audio equivalence. No whole-catalog regression was run. Existing allocation settings were preserved.

## Validation and limits

Tests cover loop interiors, reselection of existing calls, comments, ties, rhythm and small-output fallback. Existing macro and batch tests also pass. Optional `--enhance-macros` is available in conversion and batch entry points. Default output remains unchanged.

Loop expansion for alternate macro boundaries is the next stage. Search is bounded and later selections remain greedy. The dump records target-tree paths, not original Segment IDs. See docs/structured_macros.md for policies and commands.
