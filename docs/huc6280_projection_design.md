# HuC6280 to MGSDRV projection: design proposal

Status: the initial single-HuC6280 periodic-wave route is implemented. Ordinary
SCC is the primary target; a 50% square-wave overflow can use AY PSG. OPLL,
noise, active DDA/LFO, mixed-chip inputs and dynamic audible wave changes remain
future work and fail explicitly. They are not silently omitted by `--force`.

## Current implementation and validation

Use the existing export entry point; no source-selection switch is required:

```sh
python scripts/export_mgs.py <input.vgm-or-directory> --outdir <output>
```

Actual B9 commands select this route; a header clock alone does not. The package
layout remains `tracks/`, `_source_inputs/`, `_diagnostics/<stem>/`, results and
the listening manifest. The canonical `vgm2mml.py` entry also accepts this source.

`py/huc6280.py` emits ordered writes, immutable native states, positive-duration
Segments, observed waveform versions and source assumptions. Wave RAM starts
as an explicitly unobserved reference-reset assumption. The source profile is
checked against unchanged libvgm `c6280_mame.c`, commit
`bad50c571db45b872304bdcd0603dd2214f0663e`; it is not a hardware-equivalence claim.
Optional independent checks can be installed and run with:

```sh
python scripts/huc6280_reference.py --setup
python scripts/huc6280_reference.py --self-test
```

The initial allocator uses stable source-to-target assignments. Each audible
source channel must have one observed static waveform. Five SCC voices require
an identical-wave pair in the shared RAM slots; otherwise only four independent
SCC waves can be assigned. Up to three overflow voices can use PSG if their
source waves have two levels, two transitions and a 16/16 duty cycle. Planning
may examine the whole input, but target wave upload waits for complete observed
source RAM and does not preload a future waveform into an earlier sound.

`py/huc6280_projection.py` saves an inspectable target VGM under
`_diagnostics/<stem>/_huc6280_target/<stem>.vgm`. This target feeds the existing
PSG/SCC sounding-unit, repeat, macro and shared software-envelope pipeline. It
does not introduce another MML renderer. Source-native Segments remain in
`<stem>.huc6280.segments.csv`; subsequent PSG/SCC Segments describe the projected
target. Allocation, enable/audibility gates, controls and target writes each
have separate HuC6280 CSVs with source event IDs and VGM timestamps. These gates
are not claimed to be recovered score notes.

Native stereo gain is folded to mono before nearest fixed-volume quantization.
SCC uses linear 4-bit volume; PSG uses an approximate 3-dB volume law and a
libkss target-mixer calibration. Wave amplitude is retained rather than
normalized separately per instrument. PSG spill loses DC offset and phase;
SCC phase/reset and all chip-to-chip absolute gain equivalence are approximate.
Quiet sounds quantized to zero remain allocated and are reported in controls.

The target clock profile is 1,789,773 Hz for both AY and SCC. Source pitch is
`HuC clock / (32 * (period or 4096))`; target pitch is
`AY clock / (16 * period)` or `2 * SCC clock / (32 * (period + 1))`.
Actual MGSDRV playback was checked for all six authored parts, pitch registers,
nonzero audio and exported header clocks, not merely compiler acceptance.

Declared loops retain command boundaries, duration and GD3 metadata. A second
native traversal checks audible register/wave dependencies, including upload
pointer effects. Phase-dependent loop RAM writes are rejected: disabled uploads
require an explicit observed pointer reset inside each loop, and enabling the
oscillator invalidates that proof. A finite number of equal traversals alone
cannot establish that an enabled RAM write never reaches another sample later.
Dependent source writes remain in the target loop even when
redundant on its first entry. Two target traversals also check audible register
states. Nonperiodic dependencies are rejected rather than resetting unrelated
held voices to a first-pass snapshot. These checks do not prove phase equality.

Batch verification still exports the compiled MGS to VGM. It reports
`projected_source`, not a misleading OPLL 0/0 equality result. Cross-chip
source-register equality is inapplicable; target playback checks are separate
from source-native validation. Existing PSG/SCC/OPLL routes retain their usual
verification behavior.

The remainder describes the broader design, including unimplemented routes.

## Native source representation

Keep ordered B9 writes, selected channel, raw clock/header flags and original
44100-Hz source timestamps before interpretation. The VGM HuC6280 clock field
is 0xA4. Actual command usage selects the source; unrelated header clocks do not
allocate output parts. Detect native data separately from a filename extension.

Native State/Segments retain all six channels: period, enable/DDA bits, volume,
channel/global stereo balance, all waveform RAM writes/index evidence, noise
and LFO state. Keep 32-point unsigned 5-bit source waves and their versions.
Wave upload, direct D/A writes, and software envelope writes are different
operations. Do not normalize transport bytes as if they were short notes.

Infer sounding units and internal pitch/gain/wave/control curves separately
from source register slices. Enable remaining asserted does not establish one
musical note lasting the whole song. Conversely, each volume or period write
is not a new note. Pin an independently checked source profile before deciding
write-pointer, oscillator phase, LFO or DDA behavior; emulator uncertainties are
not hardware facts.

## SCC as the primary target

HuC6280 periodic waves and SCC waves both have 32 samples. A starting amplitude
projection is (u5 - 16) * 8 into signed SCC bytes; waveform identity and gain
mapping remain separate. Compute source frequency and target period through
explicit clock/counter profiles, not by copying period registers. Zero-period,
high-frequency, phase/reset and volume-law differences need target diagnostics.
Fold stereo gains explicitly for the mono MSX targets, retaining source L/R.

Ordinary SCC has five oscillators but only four independent waveform memories:
channels 4/5 share one wave. Thus six distinct simultaneous source waveforms
usually require four SCC voices plus two complementary voices. Five SCC voices
can be used when the shared pair's wave trajectories are compatible throughout
their overlap. Wave equality at one instant alone is insufficient. Plan RAM
updates with the held voice, not just with new note allocation.

SCC+ has a different wave-memory capability. Do not assume the current MGSDRV
runtime selects its independent-five-wave mode; confirm that separately before
offering it as an enhanced target profile. Ordinary SCC is the baseline.

## Complementary targets and allocation

Proposed hybrid policy, in order of suitable representation:

1. Preserve complex or changing periodic timbres on SCC.
2. Place square-wave-like overflow on AY PSG tone channels where possible.
3. Place source noise on PSG noise/tone resources with frequency/gain losses
   reported. AY's noise generator is shared, so two independent source noise
   rates cannot be represented independently by assigning two AY channels.
4. Use OPLL for remaining periodic overflow, with explicit timbre approximation.
   Compare preset/suitable custom-voice spectra and envelope behavior; matching
   a steady spectrum alone is not sufficient.

The OPLL user patch is global. Defining multiple MML @v voices does not create
multiple simultaneous hardware user instruments. Prefer compatible fixed
presets or one shared custom patch; overlapping incompatible custom timbres
must not overwrite each other. Initial OPLL output can use nine-melody mode,
reserving rhythm mode for a separately justified percussion approximation.

Allocate complete sounding units or phrases and retain source links. Prefer
stable destinations and reuse loaded waves; avoid changing chips mid-note or
inventing an attack to solve a resource conflict. A soft/quiet voice is not
implicitly disposable. Log source/target part, wave-memory compatibility,
chosen voice/period/gain, approximation and capacity conflicts.

Use explicit source musical units before target projection. Then reuse existing
note-length, phrase/loop/macro and software-volume-curve/envelope facilities
through narrow target adapters. Preserve the established full-sounding-unit ->
repeat structure -> shared-envelope selection order, rather than rendering one
MML fragment and tie for every HuC6280 register interval. Timing thresholds are
output policy; they do not redefine native State/Segments.

## DDA and LFO boundaries

Direct D/A is a timed sample-value stream, not an ordinary periodic wavetable.
Preserve its native values, supply timestamps and gain/balance controls in a
separate inspectable representation. Standard note/wave MGSDRV output does not
automatically provide an arbitrary-rate sample player. Confirm any driver PCM
capability independently. Rhythm/tonal approximation can be a later explicit
policy, with losses; it must not silently discard DDA or label it as SCC-exact.

LFO couples source-channel state and phase. Retain native evidence before a
future explicit pitch-curve projection. Until independently validated, active
DDA/LFO and unsupported variants should produce source/target limitations, or
a specifically defined force omission with duration/source-linked diagnostics.

## Implementation sequence and acceptance

1. Native source analysis and authored tests: waveform pointer/reset/upload,
   six-voice controls, stereo gain, noise, DDA and LFO distinctions, unused clocks.
2. Source sounding units/curves and SCC+PSG allocation, including actual shared
   wave-memory constraints. Verify mapped pitch, gain, timing and emitted MML.
3. OPLL approximation with a global patch-resource guard and playback checks;
   then independent DDA/complex-feature work.

Tests should include five/six distinct waves, compatible/incompatible SCC shared
pairs, mid-overlap wave changes, differing noise rates, OPLL custom-patch
conflicts, and DDA-reset sequences that do not actually play DDA. Compare against
a pinned source emulator and the actual MGSDRV target, with native/target CSVs.
Approximate cross-chip projection requires timing and acoustic comparison;
register-byte equality is not an appropriate universal roundtrip criterion.

The existing batch collector currently accepts .vgm/.vgz only; extensionless
VGM inputs need a separate explicit discovery/staging decision. Do not rename
private originals implicitly. Preserve the established export package layout.
README remains user-maintained.

## Primary references

- [VGM specification](https://vgmrips.theclassicgamer.net/VGM_Specification):
  HuC6280 clock, B9 commands and optional PCM stream bank.
- [MAME HuC6280 sound core](https://github.com/mamedev/mame/blob/master/src/devices/sound/c6280.cpp):
  waveform/control, gain, DDA/noise/LFO reference behavior and known uncertainties.
- [MAME SCC core](https://github.com/mamedev/mame/blob/master/src/devices/sound/k051649.cpp):
  ordinary shared wave RAM and K052539 differences.
- [emu2413](https://github.com/digital-sound-antiques/emu2413/blob/master/emu2413.c):
  OPLL fixed/user patch resources.

These broader hardware references do not override the explicitly pinned source
profile used by the initial implementation.
