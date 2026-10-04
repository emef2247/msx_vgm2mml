# Public OPM native-state validation

Date: 2026-10-04. Scope: source register evidence and state intervals, not
target MML, audio fidelity or envelope simulation.

## Input provenance

The user supplied 19 VGMs under `tests/fixtures/public/opm/from_fm/`.
The local `vgm-conv/run_create_testpattern.sh` converts OPLL-derived test data
through OPNA, then runs `vgm-conv -f ym2608.fm -t ym2151` to produce these
OPM inputs. Files in each `reference/` are original MGSDRV/OPLL MML, not native
OPM scores. The generator/repository was inspected but not modified.

All 19 OPM clocks are 4000000 Hz. Explicit OPM Key writes address channel0
only, with masks0/15. The three rhythm-only files have no OPM Key writes;
they still contain initialization registers. This describes the supplied
files, not a guess about why the external conversion selected these events.
Their names must not be used to claim multi-channel, partial-Key or native
OPM noise/rhythm coverage. Synthetic fixtures fill those gaps.

## Implemented state/Segment stage

Added `py/opm.py`, consuming the raw trace dispatched by the existing reader
loop. It preserves KC/KF, four named operators, channel controls, independently
latched AMD/PMD, shared controls and raw register snapshots. Segment CSV is
self-contained. Parameter changes split intervals without inventing KeyOn.
Repeated nonchanges stay in source/state CSV. Same-time changes retain their
order and zero-length intervals. Final intervals close at the actual VGM end.

Unwritten parameters remain unknown. The initially cleared Key gates are an
explicit reset assumption, not observed events. Released gates are not labeled
silent rests. Hz conversion, internal envelope/LFO/timer simulation and CSM
attacks are deferred; no target voice mapping was introduced.

Reader CLI directly generates raw/state/Segment CSVs. Main converter dump/debug
mode also generates them. Normal PSG/SCC/OPLL MML behavior is unchanged. See
[OPM analysis usage](../docs/opm_segments.md) for commands and field semantics.

## Results

The complete CSVs and a local `results.csv` are in `outputs/opm/from_fm/`.
These generated files are not staged. Raw output was compared to source command
address, ordinal, sample and payload. An independent raw-Key replay checked
source counts against state and Segment edges. Each channel's intervals were
checked for ordering, contiguous boundaries and full source-duration coverage.
All post-write raw snapshots and per-operator TL values were checked as well.

| Pattern | Raw writes | Segments | Source/Segment channel attack events |
|---|---:|---:|---:|
| 3ch_test | 306 | 335 | 10 / 10 |
| block_boundary | 533 | 562 | 35 / 35 |
| chords_mix | 301 | 330 | 9 / 9 |
| custom_voice | 451 | 480 | 30 / 30 |
| highlow_range | 462 | 491 | 21 / 21 |
| legato_patch_mix | 296 | 325 | 2 / 2 |
| patch_change_midnote | 288 | 317 | 2 / 2 |
| redundant_fnum_writes | 237 | 266 | 14 / 14 |
| release_retrigger | 244 | 273 | 6 / 6 |
| retrigger | 257 | 286 | 19 / 19 |
| rhythm_mode_basic | 341 | 370 | 12 / 12 |
| rhythm_mode_toggle | 459 | 488 | 27 / 27 |
| rhythm_only_test01 | 189 | 218 | 0 / 0 |
| rhythm_only_test02 | 189 | 218 | 0 / 0 |
| rhythm_only_test03 | 189 | 218 | 0 / 0 |
| scale_chromatic | 302 | 331 | 13 / 13 |
| scale_rom1 | 341 | 370 | 15 / 15 |
| short_pulses | 302 | 331 | 19 / 19 |
| volume_sweep | 253 | 282 | 15 / 15 |
| **Total** | **5940** | **6491** | **249 / 249** |

Operator KeyOns:996 source/996 Segment. KeyOffs likewise996. Missing/added
operator KeyOns are zero in every file. All supplied KeyOns assert all four
operators, so the factor of four is expected here; it is not generally valid
for arbitrary OPM music. No CSM mode was observed in these 19 inputs.

Segment counts include register initialization, released/unknown states and
zero-duration updates; they are not note counts. The many initialization and
multi-register changes within one sample intentionally remain available for
later note interpretation. Inspection of `legato_patch_mix` and
`patch_change_midnote` confirmed that held pitch/TL/patch changes retain the
same continuity ID and have zero rising masks. `short_pulses` retains both
brief held and release intervals.

The 13 OPM tests passed, including the all-19 public-fixture test. Existing VGM
timing/loop tests and the public conversion baseline regression passed. The
known input-test GD3 space expectation still
fails, as already confirmed with the HEAD reader before this work. Audio and
Segment-to-VGM output have not been tested or implemented in this stage.
