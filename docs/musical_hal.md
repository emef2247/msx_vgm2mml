# Shared musical performance and direct VGM output

The initial implementation provides inspectable musical units and controls
shared by MGSDRV lowering and a direct PSG/SCC/OPLL VGM backend. It does not
require generating MML or successfully compiling MGS to produce VGM.

## Usage

The recommended batch entry point is:

```sh
python scripts/export_vgm.py <input.vgm-or-directory> --outdir <output>
```

It recursively handles VGM/VGZ files. Omitting `--outdir` publishes beside each
source package. Input-relative parent directories are preserved. Products are
flat within each package's `tracks/`; original copies, diagnostics and manifests
remain separate:

```text
<output>/<input-relative-parent>/
  tracks/<stem>.vgm
  blueprint/<stem>.mml
  _source_inputs/<original-name>.vgm
  _diagnostics/<stem>/
    report.json
    <stem>.musical_plan.json
    <stem>.musical_plan.units.csv
    <stem>.musical_plan.controls.csv
    <stem>.vgm.writes.csv
    ...native/accepted Segments, curves and source evidence...
  listening_manifest.json
  results.csv
  results.json
```

The aggregate invocation result is also in `<output>/_diagnostics/results.csv`.
Failures retain the previously published owned VGM and its publication digest;
the latest diagnostic reports failure. Modified/unowned final products and
staged source copies are protected. Repeated adjacent exports exclude generated
trees. MGS and direct-VGM products can coexist in the package manifest.

The canonical converter additionally accepts:

```sh
python vgm2mml.py <input.vgm> --outdir <output> --output-format vgm
python vgm2mml.py <input.vgm> --outdir <output> --output-format both
```

Its default remains MML. `both` publishes VGM first; a subsequent MML capacity or
lowering error does not erase successful VGM output. Canonical VGM is placed in
`tracks/<stem>.vgm`; its existing standalone MML placement remains unchanged.

Use `--help` for all options. The batch VGM defaults match `export_mgs.py`'s
24-ms OPLL internal-state threshold, 8-ms normalization setting, enabled software
volume curves and 1200-second per-input timeout. `--no-normalization` retains the
existing unnormalized musical clock. No MGSC or Node installation is required.

## Layers and scope

All entry points also attempt an editable, timbre-free MGSDRV blueprint from
the same accepted musical plan. It keeps numeric volume changes inline and
publishes separately in `blueprint/`; a template failure does not block the
primary VGM/MML product. Edited templates are preserved. See
[musical_blueprint.md](musical_blueprint.md) for placeholders, source allocation,
diagnostics and the template's rhythm/capacity limits.

```text
Source VGM -> native State/Segments and ordered shared operations
           -> reconstructed sounding/score units, curves and repeats
           -> accepted timing and the initial MSX-standard target profile
           -> MusicalPlan
              -> MGSDRV syntax, envelope banks and textual compaction
              -> direct scheduled PSG/SCC/OPLL writes -> VGM
```

Native PSG/SCC `PerformanceIR` remains the interpreted source representation.
OPLL native Segments and source register evidence remain available separately.
`MusicalUnit` retains source intervals/indices, gate lineage and native timbre
parameters; `MusicalControl` retains original source time/event and accepted
sample time separately. Controls are typed; shared operations have no channel.
Units are half-open intervals and curves are ordered constant holds.

The initial profile deliberately uses the accepted MGS-compatible pitch
decisions: PSG/SCC detune projection and an independently measured OPLL semitone
table. Original pitch/timbre parameters and source clocks are not overwritten.
Additional MIDI/device or chip mappings should consume those retained musical
and native fields rather than reverse-engineering the MGS-specific encoding.
MIDI/TX802/FB-01 and additional chip backends are not implemented here.

Supported direct paths include native PSG, SCC and OPLL; all their mixed
combinations; existing HuC6280 static-wave allocation into SCC+PSG; and optional
inferred OPLL percussion. Source analysis and target limitations remain distinct.
Existing force-omission rules are reused and reported; unsupported active chips
are never silently copied or discarded. HuC noise/DDA/LFO and dynamic audible
HuC waves retain their previously documented limitations.

PSG shared noise, native hardware-envelope periods and repeated shape resets
remain ordered global operations. SCC wave writes preserve ordinary channel
4/5 RAM sharing, including partial updates during held sounds. OPLL patch
writes remain one global register bank. Rhythm mode protects shared channels
6-8 from melodic pitch/volume rewriting; native latent bank values are restored
at rhythm entry, and accepted melodic state is restored at exit. Zero-duration
key pulses retain their following settling state and cannot become held notes.

Optional percussion uses the same accepted hit groups as MML. Native percussion
wins when the same instrument is already held; native attack boundaries clip
overlapping inferred gates. Shared volume nibbles and subsequent native values
are retained. New percussion without native hits uses measured MGSDRV rhythm
pitch initialization, explicitly labeled as target configuration.

## Timing, structures and output limits

The plan records the accepted execution once. Pattern metadata describes that
already-expanded musical timeline; the writer must not expand it a second time.
VGM finite repetitions become timed writes. File size is not guaranteed to
shrink, but MGSDRV track buffers, macro/envelope-bank allocation and binary
compiler limits are not prerequisites for VGM output.

OPLL timing acceptance/state selection is shared with the MML renderer.
PSG/SCC logical note ends use common boundary fitting; internal volume holds
remain frame-based, independent of whether an MML bank can share the envelope.
Clipped controls are reported. MML packaging fallback decomposes retained
partitions only after checking equal musical volume timelines and records its
source-unit mapping; it does not replace the accepted shared clock.

The source evidence, legacy 60-Hz interpretation (including the existing early
tick convention), measured timing lattice, accepted musical time and backend
clock are distinct. Direct sample positions use rational declared-tempo
conversion without accumulated floating-point wait drift. The 8-ms normalization
setting bounds existing lattice-fit decisions; it is not a guarantee that every
absolute source-to-output difference stays below 8 ms after clock quantization
or long-term integer-tempo rounding.

Default output is one finite performance, matching the existing MML orientation.
`--song-loop source` explicitly requests the declared source loop. Its boundary
is mapped through accepted timing and serialized at a command boundary. Actual
audible register dependencies are checked over re-entry; incompatible state
requires explicit restoration instead of resetting unrelated held voices.
This checks register state, not oscillator/envelope phase equivalence.

## Backend differences and verification

The shared musical objects are not a claim of byte-for-byte equivalence between
driver playback and chip scheduling. MGSDRV has its own note dispatch, envelope
restart, sustain and frame timing behavior. In particular, existing MML lowering
does not encode the OPLL sustain bit: affected units are reported in canonical
`conversion.json` as an inherited backend loss, while the shared plan and direct
VGM retain it. A rhythm-layout MML backend cannot silently drop accepted melodic
channels 7-9; it reports the limitation and leaves successful direct VGM intact.

Validation is separated into native evidence -> musical decisions, decisions ->
direct register state/playback, and shared decisions -> compiled MGS playback
where representable. Successful compilation or matching attack counts alone do
not prove musical correctness.

Authored tests cover mixed output, clocks/waits, shared resources, retriggers,
zero pulses, provenance, loop re-entry, capacity independence and publication.
Supported public native/mixed groups are also conversion checks. Optional
`scripts/musical_vgm_reference.py --setup` builds unchanged locally available
pinned AY/OPLL/SCC cores for independent audio/frequency checks; it is not a
runtime dependency. It needs the reference checkout installed by
`scripts/huc6280_reference.py --setup`. No private music is redistributed.
