# AGENTS.md — msx_vgm2mml

## What this repo is

- Convert VGM sound-chip performances into inspectable, editable musical representations and target-specific outputs.
- The primary MSX output is MGSDRV MML/MGS. Other output paths include score Blueprints, MIDI, reference VGM, and cartridge-specific VGM variants.
- Source analysis includes PSG, YM2413/OPLL, SCC, and additional supported chips through native analysis and musical projection.
- `vgm2mml.py` is the established register-oriented conversion path.
- `vgm2mml_grid.py` is an OPLL-specific path that quantizes musical events to a step grid and supports user-defined OPLL patches and rhythm instruments.
- Main language: Python 3.
- Primary working environment: WSL.
- The goal is to preserve observable source evidence, derive useful musical information, and make important transformations inspectable. Producing compact or musically cleaner output is not sufficient by itself.

## How to run

- Register-oriented converter: `python vgm2mml.py <input.vgm>`
- OPLL grid converter: `python vgm2mml_grid.py <input.vgm>`
- Main export workflow: `python scripts/export_mgs.py INPUT --outdir OUTPUT`
- Optional cartridge VGM variants: `python scripts/export_mgs.py INPUT --outdir OUTPUT --vgm-variants`
- Automated checks: `python -m unittest discover -s tests/script -v`
- For isolated conversion checks, specify `--outdir <directory>` outside source fixtures.
- For work on `vgm2mml.py`, use `--dump-passes` whenever intermediate results are needed for inspection.
- If a requested command or option is not documented here or in `README.md`, inspect the repository and report the actual command. Do not invent a workflow.

## Layout

- `vgm2mml.py`: established PSG / OPLL / SCC conversion entry point.
- `vgm2mml_grid.py`: OPLL step-grid conversion entry point.
- `scripts/export_mgs.py`: main export workflow and optional cartridge VGM variants.
- `py/vgm_reader.py`: VGM parsing / trace-side implementation.
- `py/opll.py`, `py/opll_mml.py`: OPLL processing and MML generation.
- `py/psg.py`, `py/scc.py`: PSG/SCC event analysis and Segment construction.
- `py/chip_segments.py`: immutable PSG/SCC Segment types and CSV dumping.
- `py/psg_mml.py`, `py/scc_mml.py`: Segment-to-MML rendering and compatibility entry points.
- `py/segment_utils.py`: shared segment/pass processing.
- `py/mml_utils.py`: shared MML utilities.
- `py/native_music.py`: shared native musical representation.
- `py/musical_variants.py`: cartridge VGM variant orchestration.
- `py/musical_fm_target.py`, `py/musical_wave_target.py`: musical projection for FM and waveform sources.
- `py/musical_pcm_target.py`, `py/musical_rhythm_target.py`: musical projection for PCM and rhythm sources.
- `py/native_pcm.py`: native PCM representation and processing.
- `tests/script/`: automated checks; `tests/fixtures/`: source/reference material.
- `docs/collaboration_principles.md`: shared AI collaboration and decision-making principles.
- `docs/project_knowledge.md`: stable project design principles and durable domain knowledge.
- `docs/musical_blueprint.md`: editable score Blueprint projection.
- `docs/musical_vgm_variants.md`: cartridge VGM variants and their limitations.
- `docs/psg_scc_segments.md`: PSG/SCC pipeline, Segment fields and validation limits.
- `inputs/`: source/reference material if present locally. Do not commit private game-derived material.
- `outputs/`: generated artifacts and intermediate results if present locally.
- `field_notes/`: references to external private field notes, as described below.
- `handoffs/current.md`: current restart state if this workflow directory is added.
- `mistaken.md`: do-not-repeat rules if present.

## Collaboration and decision-making

Read `docs/collaboration_principles.md` before making significant architectural decisions, revisiting established design choices, or proposing changes that materially affect project scope.

This document defines collaboration principles shared across the MSX, X68000, and MUCOM projects.

- Use `AGENTS.md` for repository operating rules and workflow.
- Use `docs/collaboration_principles.md` for reasoning, communication, autonomy, and decision-making principles.
- Use `docs/project_knowledge.md` for established architecture and domain knowledge.
- Use focused documentation and external field notes for implementation details, experiments, and prior decisions.

Exercise independent technical judgment within the authorized task scope.

Do not treat recommendations as authorization for unrelated changes.

Proceed with routine implementation decisions when existing requirements provide sufficient guidance. Seek the owner's decision when material architectural tradeoffs or changes to established principles remain unresolved.

If instructions appear to conflict, identify the conflict and seek clarification rather than silently choosing an interpretation that overrides explicit instructions.

## Most important rule: preserve intermediate results

- Intermediate results are first-class project artifacts for development and validation.
- Do not design a conversion as an opaque VGM-to-output transformation when a meaningful intermediate representation can be emitted.
- Every non-trivial interpretation or transformation should be inspectable before the next transformation consumes it.
- Prefer CSV or another human-readable representation that can be diffed and inspected outside Python.
- When adding a new transformation stage, add or preserve a way to dump its input and output.
- Do not remove, merge away, or silently bypass existing pass dumps merely because final output still sounds correct.
- A change is not considered well validated only because final output was generated. Inspect the relevant intermediate result when debugging conversion behavior.

## Transformation boundary

Keep these conceptual stages separate:

```text
Raw VGM
  |
  v
Chip State / Native Events
  |
  v
Inspectable Analysis Passes
  |
  v
Segments / Native Musical Interpretation
  |
  v
Shared Musical Representation
  |
  +--> MML / MGS
  |
  +--> Score Blueprint / MIDI
  |
  +--> Reference / Target VGM
  |
  +--> Future Target Projections
```

This is a conceptual separation of responsibilities, not a mandatory one-to-one module layout.

- **Raw VGM:** source commands, waits, register writes, and ordering.
- **Chip State / Native Events:** chip-specific state reconstructed from source commands.
- **Analysis Passes:** inspectable transformations and progressively derived information.
- **Segments / Native Musical Interpretation:** notes, sounding spans, rhythms, envelopes, waveforms, retrigger/continuation, and other interpreted musical information.
- **Shared Musical Representation:** retained musical units, controls, curves, provenance, and source relationships available to independent projections.
- **Target Projection:** target-specific mapping, approximation, quantization, allocation, compression, and output encoding.

Do not move target-format convenience backward into earlier stages unless the user explicitly decides that the intermediate representation itself should change.

Do not assume that a target failure invalidates a retained native performance or other independent output paths.

## Evidence and inference

- Preserve directly observed values separately from inferred values whenever practical.
- Do not overwrite source-derived timing, register, or state information with quantized or normalized values without retaining the original values somewhere inspectable.
- If a value is inferred, make that fact visible in naming, fields, comments, or documentation where useful.
- Do not promote an experimental heuristic to a chip specification or project invariant.
- When behavior is unclear, inspect source VGM, traces, pass CSVs, existing code, and relevant field notes before changing the algorithm.
- Distinguish source evidence from target-projected data, particularly in cross-chip conversions.
- Record intentional approximation and information loss at the appropriate projection boundary.
- Do not claim hardware or playback equivalence based solely on successful file generation or automated tests.

## Private fixtures

- Private VGM, ROM-derived data, WAV, MML test material, and other copyrighted fixtures stay outside git unless explicitly safe to commit.
- If a local fixture configuration exists, local checks may use it.
- If private fixtures are unavailable, skip those playback/data checks and report that limitation.
- Never paste private fixture contents into documentation, logs intended for commit, issues, or pull requests.

## Conventions

- Follow existing style in the nearest files.
- Keep changes small and attributable to one transformation stage when practical.
- Prefer existing utilities and pass structures over parallel implementations.
- Do not add comments that merely restate code.
- Keep source material, intermediate/generated data, and hand-written project knowledge conceptually separate.
- Preserve enough identifiers, timestamps, channel information, and source relationships in intermediate data to trace target events back toward their source.
- Keep shared musical information independent of target-specific compiler limits, notation syntax, and cartridge resource allocation.
- Preserve the independence of source analysis and output-specific projection.

## Do not

- Do not rewrite the whole project merely to introduce this workflow.
- Do not put long-form design documentation into this file; use focused documents and `docs/project_knowledge.md` as appropriate.
- Do not collapse Raw, State, Segment, Shared Musical Representation, and Target into one representation for convenience.
- Do not discard intermediate information solely to make output shorter or cleaner.
- Do not change timing, note boundaries, retrigger/legato behavior, volume, envelope, rhythm interpretation, SCC waveform handling, or OPLL patch handling without checking the relevant intermediate stage.
- Do not treat quantized values from `vgm2mml_grid.py` as if they were raw VGM timing.
- Do not promote experimental mappings or heuristics to specifications.
- Do not reshape shared musical information merely to satisfy a target-specific test, compiler, or output-size constraint.
- Do not treat a successful target projection as proof of source reconstruction correctness.
- Do not silently substitute target-chip state for original source evidence in reference output.

## Done means

- The requested change is implemented within the authorized scope.
- Relevant automated checks were run, or the blocker is reported.
- Relevant intermediate results were generated and inspected when conversion behavior changed.
- Final output generation was checked for the affected targets when applicable.
- Independent output paths were checked when a shared representation or shared export workflow changed.
- Any newly learned stable rule is recorded in the appropriate project knowledge or field note rather than being left only in chat or code archaeology.
- If `handoffs/current.md` is in use, update it with what changed, what is unfinished, the next allowed action, and what must not happen next.
- Report what was verified and what remains unverified.

## External private field notes

- Field notes are maintained in a separate private repository.
- Resolve this path relative to this project's repository root:
  `../my-external-intelligence/msx_vgm2mml/field_notes/`
- Treat references to `field_notes/...` in project documents as references to that external directory. A local directory or symbolic link is not required.
- Before changing established conversion behavior, search relevant notes for prior decisions, rejected approaches and known regressions.
- Classify notes by meaning, not filename or chip name. Repository separation or note relocation does not revoke established shared principles.
- If a relevant inherited decision is missing, also search `../my-external-intelligence/x68k_vgm2mml/field_notes/` and `../my-external-intelligence/mucom88_vgm2mml/field_notes/`. Evaluate each note's source/target scope; newer notes from another project do not automatically override this project's decisions.
- Keep new notes in this project's external directory. Do not recreate local field notes or copy private notes into this public repository.
- If external reading or writing is unavailable, report the limitation. Do not invent missing decisions. Continue independent work using public principles; identify ungrounded decisions or unsaved findings and their intended destination.
- Keep stable principles required for public maintenance in `docs/project_knowledge.md` without copying private experimental details.
- Inspect the private repository's status and diff separately. When task commits are requested, commit its note changes separately and report both repositories' commit status. Stage only task-related notes and preserve unrelated changes.
- A public-project commit does not include external note changes. Do not push the private repository unless the task's authorization includes that push.

## When you learn something useful

- One-off observation or experiment: external `field_notes/YYYY-MM-DD_topic.md`.
- Repeated failure / known trap: `mistaken.md` if present.
- Stable design principle or domain knowledge: `docs/project_knowledge.md`.
- Subsystem-specific implementation details: focused `docs/*.md`.
- Shared collaboration or decision-making principle: `docs/collaboration_principles.md`, when a deliberate revision is warranted.
- Always-on short operating rule: only then add a concise bullet here.

## Project knowledge

Before changing parsing, timing, pass structure, note segmentation, volume, envelopes, rhythm, retrigger/legato, SCC waveforms, OPLL patches, quantization, musical projection, or target rendering, read `docs/project_knowledge.md`.

Consult relevant focused documentation and external field notes before changing established behavior.

For substantial architectural decisions or changes to the project's direction, also consult `docs/collaboration_principles.md`.

