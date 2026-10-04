# OPM channel source-loop structure

Date: 2026-10-05. Scope: confirmed native OPM Segments -> musical source
structure -> MDX MML projection. This does not redesign VGM->Segment.

## Evidence and decision rules

Reuse `SourceLoopPlan`/`LoopStructure`, already used by the OPLL path. Build
independent lanes by `(chip_instance, ch)`. Group rising operator Key edges,
held/released transitions and timing gaps into source musical units. A released
gate is not silence. Keep every Segment ID/state/sample interval as a member.

Outer equality uses exact source sample lengths, relative positions, effective
operator/channel/shared state, explicit Key edges and reset/timer effects.
Absolute origins/IDs/continuity numbering and MDX ticks, voice IDs, note spelling
or formatting do not participate. Inner plans retain the original Segment
trajectory, including zero-duration intermediate state, under each outer unit.
There is no configured source nesting-depth cap.

A zero-duration released setup is not another musical rest leaf. Its rows stay
attached to the preceding note or initialization; the inner keys retain all
of them. Outer held-note equality includes sounding states and explicit end
Key edges, not inactive same-sample pitch setup. Zero-duration attacks remain
separate units; positive released intervals and reset/timer effects are not
absorbed under this rule. This abstraction is defined before output testing.
The MDX projection independently requires unchanged expanded command tokens.

Map existing MDX units to source members only after source plans exist. Preserve
source order and note/tie durations. Reject crossing/ambiguous boundary mappings
instead of guessing. Ordinary notes can contain immediate KC/KF setup and their
explicit terminal KeyOff. A source repeat can remain expanded when command
spelling differs. No timing tolerance/normalization or reference-derived phrases
are used in this first exact baseline. The previous command-key loop experiment
is superseded; compact setters/default lengths/macros are deferred.

## Human inspection

All native channels stay together in the same Segment CSV, with every original
cell unchanged. Source/target processing adds `opm_phrase_unit_id`,
`opm_source_loop_path`, `mdx_unit_ids`, `mdx_voice_ids`, `mdx_loop_path` and
`mdx_loop_projection`. Paths record phrase/Segment level, pattern/occurrence/
parent/depth/repeat position. `mdx_loop_projection=mapped` only confirms boundary
mapping, not that every marked source candidate becomes a bracket. The source
candidates and emitted target results are distinct.

Do not split channels/common control into separate CSVs. The earlier proposed
`analysis.streams` and extra streams.csv have been removed. Native engine/state
logic is unchanged from the user's confirmed chords_mix CSV. No per-track
source loop CSVs are created. Target units/tones remain inspectable as existing
auxiliary target dumps; the integrated Segment CSV does not require joining them
to understand native sounding state and source-loop membership.

## Native rationale tests

58 OPM tests pass. Tests cover source keys unchanged by absolute origins/IDs,
changed operator TL/KF/shared LFO/one-sample duration producing distinct keys,
independent channels, retained zero-time attacks, complete source membership,
reference nested structure and exact token projection. These tests establish
defined interpretation rules. Independent final roundtrip agreement alone is
not a justification for those rules.

## Projection results

The existing external mmlx helper compiled final MML -> MDX, generated VGM,
and the native reader rebuilt state/Segments. All 38 public and two short
local inputs passed. Missing/extra channel and operator KeyOns/KeyOffs and
source-known state mismatches are zero. Ordered per-channel Key edges match
projected times. All 40 cases have safe source/target boundary mappings.
This is not sample-exact source timing, waveform or physical envelope proof.

| Input | Hybrid flat MML chars | Source-loop MML chars | Emitted loop commands | Maximum emitted depth |
|---|---:|---:|---:|---:|
| from_fm/chords_mix/chords_mix.vgm | 2474 | 2474 | 0 | 0 |
| from_mdx/nested_phrase_loops/nested_phrase_loops.vgm | 1560 | 993 | 3 | 2 |
| from_psg/chords_mix/chords_mix.vgm | 2880 | 2818 | 1 | 1 |
| M_G2_17S.vgm | 10745 | 10745 | 0 | 0 |
| M_G2_18S.vgm | 19956 | 19487 | 1 | 1 |

The authored nested reference has `[[c d e g]2 r8]3`. Its source VGM combines the
last phrase delay with the song tail. Native final released duration consequently
is not another exact outer-repeat interval. Output retains two-level structure
with three physical bracket commands: one inner repeat followed by two copies
of a pause+inner-repeat region. It does not infer a source tail split to force
the reference's exact spelling. 1560 -> 993 chars is a 36.3% reduction from flat.

This exact source baseline is stricter than the preliminary MDX-command loop
experiment: local M_G2_17S has no exact source repetition, and M_G2_18S compresses
less. Earlier 10426/11156-char figures must not be presented as this version's
results. Further musical/tolerant equivalence requires an explicit rule and
native evidence; it is not authorized by final roundtrip agreement alone.

Artifacts: outputs/opm/source_loops_20261005/public/, local17/, local18/,
summary.json, plus listen/ containing generated MML/MDX/VGM for the nested
public fixture and the two short local inputs. Source/reference fixtures and
README are unchanged. No files staged/committed.

Generate with scripts/opm_to_mdx_mml.py INPUT.vgm --outdir OUTPUT --dump-passes.
The main vgm2mml.py still outputs MGSDRV MML; its native OPM dump is the existing
source-analysis entry point. MDX packaging into the main CLI is separate work.
