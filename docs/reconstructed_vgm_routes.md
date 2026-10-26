# Reconstructed musical performance to VGM: route audit

Status: the initial shared musical-plan/direct PSG/SCC/OPLL VGM implementation is
available. See [implementation and usage](musical_hal.md). The route audit below
records the starting architecture and rationale; the text-coupled gaps listed
below have now been extracted where required for the direct path. HuC6280
listening/regression remains in progress with the user. Hardware audition and
broader source mappings remain separate work.

## Intended boundary

```text
Input VGM -> native State/Segments -> musical units, curves and repetitions
          -> accepted musical timing/pitch/control decisions
          -> shared executable performance plan
             -> MML lowering / optional MGS compilation
             -> PSG + SCC + OPLL scheduled writes -> one output VGM
```

Retain source clocks, samples, event ordering and provenance separately from
accepted target times/values. Keep chip-specific global operations alongside
part events. Independent note lists are insufficient for shared registers.

The MML/VGM branches should consume the same musical decisions. MGSDRV buffer
allocation, envelope-bank capacity and macro syntax remain MML lowering details.
Lossless curve sharing/packaging is distinct from a musical approximation.
Direct VGM must work when MML generation or compilation cannot fit those limits.

## Required routes

| Priority | Source / interpretation | Direct VGM target | Necessary semantics |
|---|---|---|---|
| 1 | PSG -> PSG | AY/YM2149 | Three tone parts, tone/noise mixer, shared noise period, fixed volume, shared hardware envelope and repeated shape resets, reconstructed software volume curves |
| 2 | SCC -> SCC | Ordinary SCC | Five voices, four independent wave RAMs, channel 4/5 shared waveform, wave updates during held sounds, period/volume/enable trajectories |
| 3 | PSG + SCC | One combined AY/SCC stream | Shared clock, deterministic simultaneous-write ordering, silence/end alignment, all controls retained |
| 4 | OPLL melody -> OPLL | YM2413 | Nine-melody or six-melody layout as applicable, accepted pitch changes, key-on/off/retrigger/legato/sustain, ROM instrument IDs, global custom-patch updates |
| 4 | Native OPLL rhythm -> OPLL | YM2413 | Five percussion instruments, per-instrument levels, mode state and transitions, shared melody/rhythm registers, actual trigger release timing |
| 5 | PSG + OPLL; SCC + OPLL; PSG + SCC + OPLL | One mixed VGM | Merge all chip schedules; preserve global state, ordering, declared activity and shared time |
| 6 | Optional PSG/SCC percussion inference | Original parts plus OPLL rhythm | Existing accepted inference decisions, native-rhythm priority, collision policy, guard against taking active melodic channels 6-8 |
| 6 | HuC6280 static periodic source | SCC + PSG, using the same final plan | Native source -> existing allocation adapter -> reconstructed target performance -> direct VGM; preserve source/target losses |

The first six rows provide the core without relying on HuC6280. HuC6280 and drum
enhancement are required integration paths before calling the existing feature
set fully covered, but should not define a parallel VGM implementation.

For every route, preserve zero-duration semantic transitions and register writes
that retrigger hardware even when their values are unchanged. Unused clock
declarations do not create audible parts. Part-selection and documented force
omissions must be shared output decisions, with diagnostics.

OPM/OPNA/DCSG -> MGSDRV are not implemented source projections in the current
main MSX converter; force can omit reviewed writes. They are not prerequisites
for this initial foundation. The separate `vgm2mml_grid.py` OPLL path can adopt
the common plan later without blocking the main converter.

## Reusable pieces and current gaps

- `py/psg_scc_performance.py`: retained Segments, audibility gates, score
  partitions and internal curves. It is explicitly not raw VGM reconstruction.
- `py/psg_scc_volume_curves.py` and `py/pre_envelope_loops.py`: existing curve,
  sounding-unit and repeat decisions. Preserve the established units -> repeats
  -> shared-envelope selection principle.
- `py/opll.py`, `py/opll_note_units.py`, `py/opll_target.py`: native OPLL evidence
  and reconstructed melody. Some gate/voice/pitch decisions currently occur
  during text rendering; these must be extracted rather than bypassed.
- `py/rhythm_patterns.py`, `py/rhythm_mml.py`: native rhythm grouping/rendering.
  Rhythm Segments retain attacks; they alone do not establish the final key-off
  timing needed for VGM. Retain the relevant native ordered control evidence.
- `py/note_normalization.py`: currently accepts/rejects a shared clock and
  retimes some PSG/SCC controls through MML text. Its accepted musical decisions
  need an explicit non-text representation.
- `py/mgs_envelope_ties.py`: MGSDRV execution compensation. Extract semantic
  curve timing before applying backend-specific compensation. A direct writer
  must not blindly interpret compensation commands as source music.
- `py/drum_enhancement.py`: retains inferred hit decisions but still reads
  target MML to map normalized boundaries. Share those boundaries through the
  plan so both outputs use the same accepted hits.
- `py/huc6280_projection.py`: already emits a target VGM, but before downstream
  musical restructuring/normalization. Returning that file alone does not meet
  the new output contract.
- `scripts/mgs_to_vgm.mjs`: useful independent playback oracle, but requires
  successful MGS compilation. It cannot be the capacity-independent output path.

The shared plan needs units/continuations, timed pitch/volume curves, instrument
and waveform identity, chip-global controls, repeated structures, source links,
original/accepted times, duration and loop intent. Keep native State intact.
Scheduling into integer 44,100-Hz VGM sample positions must use a declared clock
conversion, with no accumulated floating-point drift or per-chip time origins.

## Loops, storage and verification

MML loops/macros describe repeated score material. Direct VGM expands finite
repetitions into timed writes; its file size is not guaranteed to shrink.
The benefit here is independence from MGSDRV track/envelope/binary buffers.
Keep the compact structural plan and its provenance as separate artifacts.

A declared whole-song VGM loop is distinct from inferred phrase repetitions.
Current loop metadata inspection does not itself establish an executable musical
song-loop plan. Choose loop intent explicitly, map it through accepted timing,
and validate EOF-to-intro/loop state dependencies without resetting held voices.

Validate three boundaries independently:

1. Source evidence -> accepted musical plan (interpretation and explicit losses).
2. Plan -> direct VGM (pitch, gates, curves, waves, global operations and loop
   re-entry, plus independent playback).
3. Plan -> compiled MGS playback where compilation is possible (documented
   backend pitch/timing/gain differences, without treating compiler success or
   matching OPLL attack counts alone as musical correctness).

Retain CSVs for accepted units/curves, global operations, scheduled writes and
source/plan/output event mappings. Do not add MML parsing or MGS compilation as
a production prerequisite for direct VGM.
