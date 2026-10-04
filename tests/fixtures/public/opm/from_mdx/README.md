# Original native OPM fixtures

These synthetic MML note sequences and operator parameters were newly
written for this repository. They do not contain commercial music,
extracted game patches, private MDX material, or PCM samples. The MML,
generated MDX and VGM data use the repository's MIT license (see LICENSE
at the repository root).

Each case contains:

- `<case>.vgm`: input to the native OPM reader/Segment engine.
- `reference/<case>.mml`: original UTF-8 MDX-dialect MML with intent comments.
- `reference/<case>.mdx`: MDX compiled from that MML by mmlx.

`manifest.json` records generator versions, hashes and expected attack
counts derived from the authored scenarios. Tests do not require Rust or
any external compiler; they read the committed VGM and verify its source
writes, Key edges, state and interval continuity against the native engine.

| Case | Purpose | Channel attacks | Operator KeyOns |
|---|---|---:|---:|
| eight_channels_pan | Eight simultaneous channels, independent pitch/pan | 16 | 64 |
| partial_operator_keys | Individual operator rises/falls on channel 3 | 5 | 8 |
| held_controls | Pitch, patch, TL and pan changes while the gate stays on | 1 | 4 |
| hardware_lfo_depths | AMD/PMD latches, hardware LFO/sensitivity/key sync | 1 | 4 |
| noise_channel7 | Channel 7 noise enable, rate changes and disable | 1 | 4 |
| same_sample_retrigger | Same-time off/on plus a redundant on write | 3 | 12 |
| release_retrigger | Four notes separated by positive release intervals | 4 | 16 |
| operator_register_banks | Distinct M1/M2/C1/C2 register controls | 1 | 4 |
| nested_phrase_loops | Three outer traversals of two four-note phrases | 24 | 96 |

Raw `y<register>,<value>` commands use decimal values and supplement normal
notes where MDX commands do not expose a chip feature. For example, the
partial-Key test first plays a normal note to load its patch, then writes
one operator at a time. There is no artificial OPM rhythm mode: the noise
case uses the actual channel-7 noise control.

## Regenerate

Rust edition 2024 is required only for regeneration. The small external
utility calls the public APIs of mmlx 0.2.0 and soundlog 0.15.0. Their source
is not copied into the converter and Python conversion does not load them.
The helper emits one song traversal and retains all finite nested repeats,
using a 4 MHz YM2151 and no PDX/PCM. Dependency versions/checksums are pinned
in the helper's Cargo.lock.

From the repository root:

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/generate_opm_public_fixtures.py
python -m unittest discover -s tests -p 'test_opm*.py' -v
```

Use `--generator /path/to/mdx-fixture-generator` for a binary built elsewhere,
and repeat `--case <name>` to select individual cases. Successful generation
replaces that case's generated MDX/VGM, preserving its MML. If intentionally
changing a case or generator version, review the output and update manifest
hashes and expectations; do not automatically accept changed attack counts.

The checked-in MDX/VGM files were regenerated twice with identical hashes.
The MDX MML is the source intent, not a Segment-to-MML renderer result.
No OPM acoustic roundtrip, CSM-generated attack simulation, dual-instance
MDX playback or PCM interpretation is claimed by these cases. Existing
synthetic reader/state tests separately cover dual instances and CSM flags.

The original migrated patterns remain under `../from_fm/`; their MGSDRV MML
is pre-conversion musical context. Use both sets, and add chip-specific
patterns beside shared musical ones when extending to OPN/OPNA.
