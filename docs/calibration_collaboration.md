# Calibration collaboration guide

This guide supports work shared between the project owner, Codex, and Muse.ai.
It complements [AGENTS.md](../AGENTS.md),
[collaboration principles](collaboration_principles.md), and
[project knowledge](project_knowledge.md); it does not override them or the
owner's explicit instructions. It is a working agreement, not an assessment of
an agent's abilities.

## Responsibilities and scope

- The owner sets priorities, chooses acceptable compromises, and performs the
  broad private-fixture regression and hardware listening checks unless a
  specific check has been delegated.
- Codex coordinates the overall architecture, shared representation, output
  contracts, cross-repository consistency, and integration.
- Muse.ai investigates focused chip behavior, conversion laws, calibration,
  and measurements. Scope each change to an identified transformation stage.

Routine implementation choices can proceed within the assigned task. Raise a
material change to source semantics, shared representation, supported behavior,
resource policy, or established defaults before implementing it. Do not turn a
focused calibration task into a pipeline redesign. Share newly discovered
architectural concerns with the owner and coordinating agent.

## Before changing code

1. Confirm the repository, checked-out branch, commit, working-tree changes,
   and destination branch. Branch names do not prove which representation the
   code actually consumes. Do not overwrite another contributor's work.
2. Read the current operating rules and relevant focused docs. Search external
   field notes for the reason behind existing behavior, rejected approaches,
   and known regressions. Cross-project rules need source/target scope checks.
3. Trace one case through the actual caller chain. Name the failing stage:
   parsing, native interpretation, shared music, target mapping, serialization,
   compilation, publication, or playback. Inspect its intermediate evidence.
4. State what will change, what evidence supports it, and what remains unknown.
   Prefer a narrow reproducible check to an expensive whole-game rerun.

## Architecture to preserve

The conceptual path is:

```text
VGM -> native State / Events -> Segments / interpreted music
    -> shared musical representation -> independent target projections
```

- Cartridge variants consume retained musical information (`NativePerformance`)
  rather than reopening the original VGM in the target projector. Reusing a
  low-level calibration or codec helper is appropriate; invoking a Segment-only
  conversion pipeline is not equivalent to musical-layer integration.
- Source evidence and intentional musical edits have different responsibilities.
  Keep register evidence for provenance and native semantics, but do not let it
  silently override edited pitch, volume, voice, gate, or PCM content.
- Source time uses integer VGM samples at 44,100 per second, including ordering
  between operations at the same sample. Target ticks, score steps, and driver
  frames are distinct. Do not introduce a 60 Hz source clock for convenience.
- Preserve original native information before quantization or approximation.
  Target channel limits, codecs, macro slots, and compiler buffers belong to
  target projection, not to source Segments or shared musical identity.
- Construct complete sounding units and internal curves before repeat analysis
  and target envelope selection. A control slice is not automatically a note.
- Preserve attack/continuation distinctions, partial operator keys, release
  tails, shared register ownership, and song-loop traversal dependencies.
  A locally redundant write can still be needed on the next traversal.
- MGS failure must not prevent independent Blueprint, reference VGM, or variant
  outputs. Report each artifact's processing and publication outcome separately.

See [VGM variants](musical_vgm_variants.md) and
[Blueprints](musical_blueprint.md) for the current contracts and limitations.

## Calibration evidence

For each experiment, record:

- Input representation, source chip and clock, target chip and actual clock.
- Native values, derived physical quantities, projected values, and event IDs.
- Reference implementation or specification and its applicability to this chip.
- Measurement method, configuration, expected value, observed value, and error.
- Supported cases, approximations, omissions, and checks not performed.

For pitch laws, test both Hz-to-register and register-to-Hz directions against
an independent reference or renderer. A round trip through two matching mistakes
can pass. Include an absolute pitch such as 440 Hz and representative blocks,
range boundaries, and clocks. Derive target values using the same clock written
to the output header; do not hide clock compensation elsewhere in the pipeline.

For level, envelope, or modulation calibration, include representative algorithms,
operator/carrier arrangements, and shared control changes as applicable. State
whether a result is a register-law check, emulator measurement, subjective
listening observation, or physical-hardware measurement. They are not equivalent.

Cross-chip register equality is not a musical-equivalence test. Successful
compilation, equal durations, matching event counts, or shorter output also do
not establish correct audible behavior.

## PCM and resource constraints

Keep sample assets and playback occurrences separate. Reusing an asset must not
silently remove its later occurrences or change their timing. Record target-only
replacement decisions and their losses. Count actual encoded storage, required
alignment and metadata, and distinguish storage from runtime/decoded memory.

Use the target profile's resource model. Do not import MDX's 96-slot limit into a
cartridge VGM encoder or combine separate cartridge memories without an approved
allocation policy. Numerical limits and current approximation policies belong in
focused target documentation.

## Verification and safe handoff

- Run focused authored/public checks for the affected stage, and inspect the
  relevant before/after CSV or JSON. Verify independent outputs if shared export
  code changes. Do not run broad local_only regression unless authorized.
- Keep private game data and generated outputs untracked. Use a separate output
  directory for experiments. Preserve user-modified products; an ownership
  failure is a publication problem, not proof of a conversion-law failure.
- Read the full log and per-route result rows. An ordinary MGS summary may appear
  before the independent variants pass finishes. Do not diagnose a missing
  artifact from a partial console transcript alone.
- Avoid changing README, defaults, or unrelated routes during calibration.
  Explain any necessary cross-cutting change before broadening the task.
- Keep changes small and reviewable. Commit task-related files only; preserve
  unrelated staged and untracked changes. Push only to an authorized destination.
- Record experiments in the external private field-notes repository and update
  the active handoff with completed work, remaining limitations, and next steps.
  Commit task notes separately; do not push that repository without authorization.

A useful handoff identifies the exact commit and consumed representation, the
changed stage, evidence and intermediate-artifact locations, focused check
results, intentional losses, and remaining questions. Say explicitly when
private regression, listening, or hardware checks remain with the owner.
