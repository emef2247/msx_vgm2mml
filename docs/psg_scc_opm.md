# Experimental PSG/SCC OPM output

This separate prototype projects existing, unchanged native PSG/SCC Segments to
an explicit OPM target plan. It does not fabricate native OPM Segments or change
the normal vgm2mml.py conversion. No composite-channel merging is performed.

## Usage

For MDX MML through the main entry point:

```sh
python vgm2mml.py INPUT.vgm --target opm --outdir outputs/opm/NAME
```

The OPM target uses an independently implemented **FM/feedback PSG tone profile**
by default. `--psg-model additive` selects the previous four-sine PSG model.
SCC continues to use waveform-derived additive synthesis in either case:
vgm-conv's AY-to-OPM profile is not a mapping for arbitrary SCC waves.
`--target opm-additive` is a compatibility spelling that explicitly selects the
old additive model; the MGSDRV default target remains `mgs`.

```sh
python vgm2mml.py INPUT.vgm --target opm --psg-model additive --outdir outputs/opm/ADDITIVE
```

`--opm-pitch-policy clamp` bounds out-of-range pitch to the closest nominal
KC/KF boundary and records the loss. It is the FM default and applies to both
PSG and SCC in the selected target. `--opm-pitch-policy error` retains the old
range-rejection policy, including explicitly omitted zero-target-duration
transients; it is the additive default. Changing tone model and range policy
are independent choices: selecting FM does not enlarge the OPM's physical range.
No hardware-compatible approximation is described as exact source-frequency
preservation.

For diagnostics use `--dump-passes`. In `<stem>.opm_target.csv`, `frequency_hz`
is the requested frequency derived from the unchanged source period/clock;
`target_frequency_hz` is the projected nominal OPM frequency; `pitch_error_cents`
is signed `1200*log2(target/requested)`. `approximation` labels range limiting.
The JSON records model, gains, target clock, pitch policy and the number of
clamped rows. Source channel/row and native timestamps remain available for
future multi-chip or OPL3 allocation comparisons. FM tone tables describe
algorithm, feedback and native operator-bank parameters rather than fictional
DFT components.

Only `<stem>.mdx.mml` remains by default. Add `--dump-passes` to retain native
PSG/SCC Segments and target mapping/voice/write CSVs. `--title` and GD3 title
selection are shared with the main entry point. `--psg-gain` and `--scc-gain`
adjust the two source-chip gains. The default target remains MGSDRV;
MGSDRV allocation/normalization/compression switches are rejected for this target.

For an external compiler/player roundtrip and a listening catalog:

```sh
python scripts/psg_scc_to_mdx.py tests/fixtures/public/psg \
  --outdir outputs/opm/psg_scc_public/psg \
  --generator /path/to/mdx-fixture-generator \
  --comparison-dir tests/fixtures/public/opm/from_psg
python scripts/psg_scc_to_mdx.py tests/fixtures/public/scc \
  --outdir outputs/opm/psg_scc_public/scc \
  --generator /path/to/mdx-fixture-generator
```

The external generator is built from `scripts/mdx_fixture_generator`.
The standalone script accepts a VGM/VGZ file or a directory. It always retains
source/target evidence. `--generator` additionally produces MDX, OPM VGM and a
verification JSON; without it only MML and diagnostics are generated.
Directory runs write results.csv/results.json and continue after unsupported
inputs, returning nonzero if any input is unsupported or fails. Compiler failures
retain MML and compiler logs. Timeouts have a separate status.
`--comparison-dir` copies existing VGM files at matching relative paths as
`<stem>.vgm-conv.vgm`; matching paths do not prove matching source or timbre.

MSX driver initialization for unused chips is permitted conservatively:
OPLL writes only when there are no melodic KeyOns or enabled rhythm triggers;
zero-clock SCC initialization only when no nonzero volume writes occur.
Counts remain in target JSON and raw source trace evidence is retained on request.
Active OPLL, unknown commands and unsupported SCC modes still fail explicitly.
Shared version-bounded header reading accepts AY VGM 1.51+ and AY8910 flags
0..3. Standard K051649 is supported; not every PSG/SSG or SCC variant is.

A..E correspond to SCC1..5, F..H to PSG1..3. Silent-only parts need no oscillator.
Source channel, row, native sample boundaries and target write IDs remain visible
in the unified target CSV. Source CSVs remain integrated per chip.

## Approximation

- Default PSG FM profile: AL4/FB7, a MUL2 modulator at TL27 and a MUL1 carrier
  driven by a fixed volume-to-TL curve with eight attenuation steps of headroom.
  Other operators are muted. Source level changes do not restart its envelope.
  These are compatible published mapping parameters, independently implemented;
  no vgm-conv library/code is incorporated or required at runtime.
- The optional AL7 PSG model supplies independent sine carriers at 1,3,5,7.
  SCC selects the four largest DFT bins among 1..15 from its signed 32-byte wave.
- Relative SCC wave amplitudes are retained; waves are not individually normalized.
  DC, arbitrary phase and unselected harmonics are not reproduced. Stored DFT phases
  and retained AC energy are diagnostics, not perceptual quality measurements.
- One held KeyOn per used part avoids introducing attacks at each Segment.
  Pitch and carrier TL follow source changes; output routing handles mute intervals.
  SCC volume is linear. Additive PSG uses approximate 3 dB/level steps; FM PSG
  uses the fixed attenuation curve. PSG gain defaults to FM=1, additive=0.125;
  SCC gain remains 0.125. FM gain adjusts the carrier only, retaining modulator
  feedback. These gains are not a universal acoustic calibration.
- Output assumes 4 MHz OPM. KC/KF uses nominal equal-tempered clock correction;
  oscillator phase and exact chip frequency-table rounding are not verified.
- MDX quantizes time. Range handling follows the explicit clamp/error policy
  above. Native source samples, periods and Segment evidence are never removed.
- Noise, mixed tone/noise, hardware envelopes and unsupported input controls fail
  explicitly. This is not yet a converter for the full NEMESIS2 catalog.
- One stored VGM traversal is rendered; loop repetition and MML compression are
  not implemented in this prototype. Raw register MML is intentionally inspectable.

## Clock convention and verification

Use the VGM AY clock / (16 * period), with period zero treated as one.
For these K051649 VGM inputs, the libvgm playback convention is VGM clock /
(16 * (period+1)); period <=8 is nonoscillating. Do not substitute the physical
SCC wave-step-clock /32 formula without accounting for header clock convention.
Reference: https://github.com/ValleyBell/libvgm/blob/master/emu/cores/k051649.c
OPM nominal pitch reference: https://map.grauw.nl/resources/sound/yamaha_ym2151_synthesis.pdf

Roundtrip verification compares the explicit target write stream to external
MDX playback, after separately checking compiler initialization. It tests target
controls, timing, keys and ending, not acoustic equivalence to PSG/SCC.

## Public fixture check (2026-10-05)

26 files were attempted: 11/13 under public/psg and 13/13 under public/scc
compiled and passed exact target-control roundtrip. Eight focused tests cover
DFT amplitude, source immutability, continuity, initialization exclusion,
unsupported controls, and main-entry output behavior. This is listening preparation,
not a sound-quality score. Source Segments were inspected for active part mapping.

Remaining unsupported files: PSG legato_patch_mix and patch_change_midnote use
noise. After the user updated block_boundary and SCC short_pulses, both passed
conversion and target-control roundtrip. Folder names are not used to decide native
chip semantics. The existing vgm-conv block_boundary output predates the updated
input and must not be treated as a matched comparison.

Artifacts: outputs/opm/psg_scc_public/LISTEN.md and its listen/ tree; all 11
successful PSG-directory inputs have copies of the existing from_psg OPM VGMs.
No source fixtures were changed. Noise/hardware EG, unsupported variants and
later OPN/OPNA/OPS output remain future work. The DFT voice description is separate
from OPM register allocation so future targets can reuse the spectral analysis
without treating OPM register fields as a universal voice format.

## Local listening (2026-10-05)

VGM loading and version-bounded chip-header interpretation use the shared reader.
AY headers from VGM 1.51 are accepted; this target no longer requires VGM 1.61.
This does not add noise or hardware-envelope synthesis. Unsupported active modes
are reported rather than silently omitted.

Generate a directory of MDX MML, MDX, OPM VGM and diagnostic CSVs in WSL:

```sh
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/psg_scc_to_mdx.py tests/fixtures/local_only/psg \
  --outdir outputs/opm/local_only/psg \
  --generator scripts/mdx_fixture_generator/target/release/mdx-fixture-generator
```

Use another input directory and output directory for PSG/SCC mixtures. The batch
continues after unsupported files and writes results.csv/results.json; its exit
status is nonzero if any input was unsupported or failed. Without --generator,
only the MML and diagnostic data are produced, not playable MDX/VGM.

Local validation: DSLAYER4/DSLY4_04.vgm compiled and its MDX playback reproduced
all 7,568 projected target controls. This verifies the target roundtrip, not
source sound equivalence. XANADU01 passes header validation but contains unsupported
PSG noise. The timbre remains four-carrier additive synthesis, not vgm-conv's FM
mapping; it deliberately retains the previously auditioned A implementation.

## External vgm-conv comparison beside existing results

```sh
python scripts/batch_vgm_conv.py tests/fixtures/local_only/psg \
  --outdir outputs/opm/local_only/psg
```

This calls external `vgm-conv -f ay8910 -t ym2151`, preserving the directory
layout of psg_scc_to_mdx.py and writing `<stem>.vgm-conv.vgm` plus a conversion
log. Use `--vgm-conv /path/to/vgm-conv/bin/cmd.js --node node` if it is not on PATH.
The separate report is vgm-conv-results.csv; existing results.csv and additive
MDX/VGM are not replaced. Failed reruns may leave an older comparison file;
consult the current report. This script converts AY only: it does NOT map SCC
into OPM, and must not be presented as an all-OPM conversion of PSG/SCC mixtures.

With `--generator`, psg_scc_to_mdx.py already retains `<stem>.mdx` next to
`<stem>.mdx.mml` and `<stem>.vgm` for successful files. No second MDX conversion
is required. Unsupported projection or MDX size overflow does not produce a
new successful MDX. Player note displays may differ for raw-register MML.

## Note-based MDX listening preview (2026-10-06)

The additive raw renderer uses y commands and rests; it does not maintain normal
MDX note/volume state for a player display. A separate preview now renders the
existing target plan with tone definitions, notes, @v, pan and ties. Common TL
attenuation becomes track volume; differences between carriers remain in the
tone. This is a target notation change, not native Segment rewriting.

Run from the repository root (no new compiler build is needed):

```sh
python scripts/render_additive_mdx_notes.py \
  outputs/opm/local_only/psg/vgmrips.net/YUMADV/YUMADV18/YUMADV18.opm_writes.csv \
  --generator scripts/mdx_fixture_generator/target/release/mdx-fixture-generator
```

Pass `outputs/opm/local_only/psg` instead to process all existing additive plans.
PSG/SCC mixed output directories are also accepted. Only complete additive target plans
with .opm_writes.csv and .opm_target.json can be processed; previously unsupported
source conversions are not repaired by this step.

Alongside the original files it writes `<stem>.notes.mdx.mml`, `.notes.mdx`,
`.notes.vgm`, `.notes.mapping.csv` and `.notes.verification.json`. Original MDX/VGM
files are not replaced. A failed verification leaves the preview for diagnosis:
check the report before relying on it. The batch continues after errors and
returns a nonzero exit code if any file failed.

YUMADV18 passed audible positive-duration register-state and key-edge comparison
against the existing additive target plan. It has not yet been verified in
MMDSP on the user's system. Player meters/keyboard display and listening remain
required; do not claim this preview fixes the display until that is confirmed.
The original additive renderer remains the default during this preview.

## FM default validation (2026-10-06)

Both models passed external MDX roundtrips for 11 public PSG-directory inputs.
Two noise fixtures still fail explicitly. Local FM roundtrips also passed for
GRA1_03, GRA1_05, DSLY4_04 and mixed PSG/SCC GRA2_17. GRA1_03 previously stopped
at an intermediate out-of-range tone period; FM's clamp policy exposes three
limited rows and completes. Source Segment CSVs agree byte-for-byte across all
34 checked source-file/model pairs. This validates target controls and source
immutability, not source acoustic identity or MMDSP animation.

WAV comparisons for GRA1_05/DSLY4_04 confirm higher partial energy than the
finite additive profile and similar measured levels/spectral trends to external
vgm-conv. See `field_notes/2026-10-06_psg_fm_default.md`. Existing MDX note-renderer
work remains paused; `scripts/render_additive_mdx_notes.py` handles AL7 additive
plans only and must not be applied to FM plans expecting identical notation.

For a local FM listening batch:

```sh
python scripts/psg_scc_to_mdx.py tests/fixtures/local_only/psg \
  --outdir outputs/opm/local_only/psg_fm \
  --generator scripts/mdx_fixture_generator/target/release/mdx-fixture-generator
```

Add `--psg-model additive` and use a separate output directory for the original
model. Add `--opm-pitch-policy clamp` if evaluating additive timbre with the same
range policy as FM. Noise/hardware EG, SCC variants and MDX capacity limits
remain separate causes of failed conversion.
