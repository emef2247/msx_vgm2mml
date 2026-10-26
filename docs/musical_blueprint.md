# Editable blueprint MML

The canonical converter, `export_mgs.py` / `batch_vgm_to_mgs.py`, and
`export_vgm.py` automatically emit an additional MGSDRV score template:

```text
<output>/<input-relative-parent>/
  blueprint/<stem>.mml
  tracks/...ordinary MML/MGS or reconstructed VGM...
  _diagnostics/<stem>/
    <stem>.blueprint.json
    <stem>.blueprint.units.csv
    ...shared musical plan and native evidence...
```

For standalone `vgm2mml.py`, `blueprint/` is directly beneath its `--outdir`.
Existing export defaults and ordinary output products are unchanged. VGM-only
conversion does not invoke the ordinary MML backend or MGSC; the separate
blueprint attempt does not have to succeed for VGM generation to succeed.
The historical `mml_generated` field refers to the ordinary MML product;
the additional template has its own `blueprint.status` and path.

## What remains editable

The template is lowered from accepted `MusicalPlan` sounding units and control
holds. It is not made by deleting lines from the final ordinary MML. Native
PSG/SCC/OPLL lane identities, accepted pitches, rests, gates, internal pitch
changes and numeric volume changes are retained. Software volume curves become
inline `v` commands and tied continuations, without envelope definitions or
dangling `@e` references. Fixed-preset OPLL rhythm attacks and levels use the
ordinary rhythm grammar. Rhythm is an attack-grid/preset-decay template:
independent native key-off lengths are retained in the sidecar, not encoded as
per-instrument gates. A positive held percussion volume change blocks the
template instead of being discarded or turned into a fabricated new attack.
Same-sample release/setup transients are distinguished from positive holds.
PSG hardware-envelope controls remain hardware controls.

Source SCC waveforms, OPLL patches/instrument selections and software-envelope
banks are not copied. Each melodic lane has an editable `@0` placeholder.
OPLL therefore uses its first preset until edited. SCC users must supply their
own `@s0` waveform (or change the selection and add a matching definition).
The template is a composition starting point, not a timbre-faithful rendition.
Volume numbers remain accepted target levels, without loudness normalization
for the new instrument.

Finite repeats are reconstructed over complete emitted sounding units before
the existing lossless macro compactor runs. Durations use ordinary note values
where possible and bounded tied pieces otherwise. Internal volume or pitch
controls do not become new attacks. The accepted finite traversal is emitted;
the optional source-song-loop location remains in the shared plan rather than
being turned into an infinite MGSDRV loop.

## Other source chips

The HuC6280 adapter now retains its source-to-profile channel allocation in
projection metadata. Blueprint allocation uses this provenance: those parts
are placed in free OPLL lanes first, then free PSG lanes, rather than retaining
the temporary SCC projection as the template destination. Native active lanes
are reserved; a whole sounding unit is never moved halfway through its gate.
An existing source-to-template affinity is preferred when that lane is free.
Pitch is translated from the accepted profile frequency; OPLL spill uses the
nearest supported semitone. Native evidence and the normal target remain intact.

This is not a general implementation for unanalysed source chips. Future adapters
must supply source provenance and accepted executable musical controls first.
There is no silent capacity-based omission. Exhausted OPLL/PSG lanes, overlapping
units, a positive gate collapsing on the MML step clock, or a nine-melody-channel
OPLL/rhythm layout conflict block only the template and give a diagnostic reason.
Every encoded note/rest must also satisfy MGSC's tempo-dependent frame bound
`max(1, tempo // 75)`. Below-bound intervals block only the blueprint, with unit,
sample/step boundaries and responsible controls recorded in `projection_detail`.
Do not silently remove a volume hold or introduce a new 60-Hz timing approximation
to make compilation succeed. Long durations are split so the final tied piece
also satisfies this bound; raw `%1`/`%2` notation is used only at tempos that
support it, never invalid `c192`/`c96` note divisors.

## Inspection and ownership

The JSON and unit CSV expose source identity, shared-plan lane, template lane,
accepted sample boundaries, MML steps and each unit's explicit score commands.
The JSON also records finite-loop decisions, stripped control counts, rhythm
attacks and sample-to-step rounding. These are backend decisions; native
Segments and the shared plan are never overwritten by template approximations.

The blueprint is not automatically compiled into MGS. Long inline volume curves
can still exceed MGSDRV track buffers even when the template MML is valid.
Compilation is not proof of preserved musical interpretation, and removal of
SCC waves deliberately prevents a claim of identical audio.

Existing blueprint files require matching ownership digests for regeneration.
Edited/unowned package templates are preserved and only their update is skipped;
ordinary MML/VGM conversion continues. Standalone template attempts likewise
report `blocked` and preserve the file. A failed attempt keeps the last
owned artifact without labelling it a success for the new source. Successful
templates may be published even when ordinary MML lowering or MGS compilation
fails; the previous listening pair remains protected independently.
