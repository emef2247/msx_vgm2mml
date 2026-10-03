# Reversible OPLL loop structure (2026-10-03)

## Objective and scope

The user prioritizes final MML character count, subject to successful MGSC compilation without track buffer errors. Compiled byte count is not the ranking objective. This supersedes the adoption criterion in the earlier loop-strategy experiment.

Build structure before choosing macro spelling. Preserve every exact adjacent repetition candidate on the original note-unit sequence, including overlapping alternatives. A selected nested tree is reversible; its markers can be expanded later when comparing macro candidates. This does not yet implement macro-aware unrolling or approximate musical matching.

## Implementation

`py/loop_structure.py` catalogs all exact start/body-width candidates and repeat counts. It removes the earlier experimental width 128 and depth 3 bounds. Interval selection minimizes stored literal units, then repeat nodes, independently of MML text cost. Original unit positions remain available. Source repeats above 255 are retained and split into valid target repeat counts during rendering.

The structural CSV contains marker and parent IDs, canonical pattern IDs, source intervals and depth. The candidate CSV retains alternatives not simultaneously representable in one tree. Exact source expansion and final emitted timed-command expansion are checked separately.

This remains an explicit experimental OPLL rendering strategy. The normal converter default is unchanged. Normalization is disabled consistently in this comparison, and existing macro processing is unchanged.

## Full-output results

| Fixture | Current MML characters | Structural MML characters | MGSC compilation | Buffer error | Expanded timed commands |
| --- | ---: | ---: | --- | --- | --- |
| sample | 6333 | 6333 | both successful | none | identical |
| sx01v | 17428 | 17187 | both successful | none | identical |

Character counts include comments. Code character counts are 4420/4420 for sample and 16497/16259 for sx01v. The structural result saves 241 total characters for sx01v. These outputs match the previous retained strategy in size; removing search bounds provides no additional savings on these two fixtures.

sample has 287 candidate families representing 419 repeat-count alternatives, 23 selected markers and depth 3. sx01v has 1331 families, 1966 alternatives, 101 selected markers and depth 3. Marker counts refer to stored tree nodes, not expanded occurrences. Long phrases, deeper nesting, overlapping alternatives, source reversibility and target repeat splitting are covered by synthetic tests.

Compiler: local mgsc-js 2.0.0, MGSC 1.11. Private artifacts and compile logs: Codex `outputs/opll-loop-structure/{sample,sx01v}`. This check establishes command preservation and compilation for these fixtures; it does not establish recovery of every authored reference loop or audio equivalence.

## Next step

Use the retained candidate graph and reversible markers to compare final macro alternatives, including selective inner-loop expansion. Rank complete equivalent MML by characters with compilation as the acceptance gate. Exact note signatures still exclude repetitions affected by timing or state differences; tolerant matching is a separate decision.

## Final sx01v MML structure inventory

Count physical bracket loops in the final MML, without multiplying by repeat counts or macro call counts. Parse track and macro definitions separately.

| Metric | Current | Structural |
| --- | ---: | ---: |
| Physical loops | 73 | 91 |
| Loops nested inside another loop | 4 | 17 |
| Maximum depth | 2 | 3 |
| Macro definitions | 32 | 32 |
| Loops in macro definitions | 0 | 0 |

Per-track loop counts current/structural: 9=4/6, a=18/16, b=6/11, c=5/11, d=4/9, e=25/27, f=11/11. Macro calls are already applied in both final outputs. The unfinished work is structure-aware macro selection, not initial macro support.

## Proposed structure-aware macro selection

The existing text compressor greedily chooses exact repeated command sequences, permits 4..24 parsed top-level nodes and bodies at most 160 characters, and uses at most 32 definitions. A bracket loop is one top-level node; its interior is not independently searched. Candidates cannot include existing macro calls, and synchronization comments partition search blocks. These are current search policy limits, not asserted MGSC format limits.

1. Preserve the source candidate graph and reversible loop tree. Build a target command tree with original unit mappings.
2. Search exact reusable command sequences at each tree level, including loop interiors. Compare alternatives retaining loops, selectively expanding inner loops, or putting a larger phrase containing loops into one macro. Do not fully flatten every repeat: use lazy expansion and bounded candidate enumeration.
3. Initially require exact command-token expansion equality, respecting ties, rhythm grammar and synchronization boundaries. Context-dependent setter omission and macro nesting are separate later optimizations.
4. Select a portfolio of non-overlapping replacements under the available definition budget. Re-evaluate competing candidates after selection and try replacement of earlier selections, rather than permanently accepting the first greedy choice. Include definition text, call text, separators and final wrapping in whole-MML character cost.
5. Emit candidate/selection CSVs with macro IDs, source-unit intervals, loop marker IDs, occurrence counts, definition/call cost and measured whole-output saving. Keep the baseline as a candidate.
6. Validate expanded timed commands and compile complete sample/sx01v MML. Rank by final characters among equivalent successfully compiled outputs without buffer errors. Macro substitution alone normally reduces source text rather than compiled track usage; loop retention/expansion can affect compiled usage, so compiler validation remains necessary.

First compare improved search with loop spelling fixed, then add selective loop expansion. This isolates whether gains come from better macro allocation or representation changes. No structure-aware macro implementation was made as part of this planning update.
