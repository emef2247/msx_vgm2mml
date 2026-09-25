# Project AGENTS.md

## What this repo is
- Convert MSX-related VGM data into MGSDRV MML.
- Supported source chips in the main converter: PSG, YM2413/OPLL, and SCC.
- `vgm2mml_grid.py` is an OPLL-specific path that quantizes musical events to a step grid and supports user-defined OPLL patches and rhythm instruments.
- Main language: Python 3.
- Primary working environment: WSL.
- Goal: preserve observable VGM/chip behavior and make every important transformation inspectable, not merely produce compact or musically cleaner MML.

## How to run
- Register-oriented converter: `python vgm2mml.py <input.vgm>`
- OPLL grid converter: `python vgm2mml_grid.py <input.vgm>`
- For work on `vgm2mml.py`, use `--dump-passes` whenever intermediate results are needed for inspection.
- If a requested command or option is not documented here or in `README.md`, inspect the repository and report the actual command. Do not invent a workflow.

## Layout
- `vgm2mml.py`: main PSG / OPLL / SCC conversion entry point.
- `vgm2mml_grid.py`: OPLL step-grid conversion entry point.
- `py/vgm_reader.py`: VGM parsing / trace-side implementation.
- `py/opll.py`, `py/opll_mml.py`: OPLL processing and MML generation.
- `py/psg_mml.py`: PSG processing and MML generation.
- `py/scc_mml.py`: SCC processing and MML generation.
- `py/segment_utils.py`: shared segment/pass processing.
- `py/mml_utils.py`: shared MML utilities.
- `tests/`: automated checks.
- `docs/project_knowledge.md`: project design context and transformation rules. Read before changing conversion behavior.
- `inputs/`: source/reference material if present locally. Do not commit private game-derived material.
- `outputs/`: generated artifacts and intermediate results if present locally.
- `field_notes/`: reusable discoveries if this workflow directory is added.
- `handoffs/current.md`: current restart state if this workflow directory is added.
- `mistaken.md`: do-not-repeat rules if present.

## Most important rule: preserve intermediate results
- Intermediate results are first-class project artifacts for development and validation.
- Do not design a conversion as an opaque VGM -> MML transformation when a meaningful intermediate representation can be emitted.
- Every non-trivial interpretation or transformation should be inspectable before the next transformation consumes it.
- Prefer CSV or another stable, human-readable representation that can be diffed and inspected outside Python.
- When adding a new transformation stage, add or preserve a way to dump its input and output.
- Do not remove, merge away, or silently bypass existing pass dumps merely because the final MML still sounds correct.
- A change is not considered well validated only because final MML was generated. Inspect the relevant intermediate result as part of debugging conversion behavior.

## Transformation boundary
Keep these conceptual stages separate:

`Raw VGM -> State / trace -> Segment / interpreted event -> Target MML`

- Raw VGM: source commands, waits, register writes, and timing facts.
- State / trace: chip state reconstructed from those writes.
- Segment / interpreted event: notes, rests, volumes, instruments, rhythm events, envelopes, waveforms, legato/retrigger and similar musical interpretations.
- Target MML: MGSDRV-specific representation, formatting, quantization, compression, macros, and notation choices.

Do not move target-format convenience backward into earlier stages unless the user explicitly decides that the intermediate representation itself should change.

## Evidence and inference
- Preserve directly observed values separately from inferred values whenever practical.
- Do not overwrite source-derived timing/register/state information with a quantized or normalized value without retaining the pre-transformation value somewhere inspectable.
- If a value is inferred, make that fact visible in naming, fields, comments, or documentation where useful.
- Do not promote an experimental heuristic to a chip specification or project invariant.
- When behavior is unclear, inspect source VGM, traces, pass CSVs, and existing code before changing the algorithm.

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
- Preserve enough identifiers/timestamps/channel information in intermediate data to trace a final MML event back toward its source.

## Do not
- Do not rewrite the whole project merely to introduce this workflow.
- Do not put long-form design documentation into this file; put it in `docs/project_knowledge.md`.
- Do not collapse Raw, State, Segment, and Target into one representation for convenience.
- Do not discard intermediate information solely to make MML shorter or cleaner.
- Do not change timing, note boundaries, retrigger/legato behavior, volume, envelope, rhythm interpretation, SCC waveform handling, or OPLL patch handling without checking the relevant intermediate stage.
- Do not treat quantized values from `vgm2mml_grid.py` as if they were raw VGM timing.
- Do not promote experimental mappings or heuristics to specifications.

## Done means
- The requested change is implemented.
- Relevant automated checks were run, or the blocker is reported.
- Relevant intermediate results were generated and inspected when conversion behavior changed.
- Final MML generation was checked when applicable.
- Any newly learned stable rule is recorded in the appropriate project knowledge / field note rather than being left only in chat or code archaeology.
- If `handoffs/current.md` is in use, update it with what changed, what is unfinished, the next allowed action, and what must not happen next.

## When you learn something useful
- One-off observation or experiment: `field_notes/YYYY-MM-DD_topic.md` if that workflow is present.
- Repeated failure / known trap: `mistaken.md` if present.
- Stable design principle or domain knowledge: `docs/project_knowledge.md`.
- Always-on short rule: only then add a concise bullet here.

## Project knowledge
Before changing parsing, timing, pass structure, note segmentation, volume, envelopes, rhythm, retrigger/legato, SCC waveforms, OPLL patches, quantization, or MML rendering, read `docs/project_knowledge.md`.
