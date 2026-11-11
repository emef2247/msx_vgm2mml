# Musical-layer cartridge VGM variants

`export_mgs.py --vgm-variants` adds independent target VGM products. The
ordinary MML/MGS, native reference VGM and score blueprint keep their existing
roles. An unavailable MGS mapping does not prevent the variant pass from
running. Normal MGS status and variant status are reported separately.

Example:

```sh
python scripts/export_mgs.py INPUT --outdir OUTPUT --vgm-variants --force
```

The input-relative parent directory is retained. Within each output package:

```text
tracks/<stem>.mml, <stem>.mgs, <stem>.vgm
blueprint/<stem>.mml, <stem>.midi
vgm-variants/sfg01/<stem>.vgm
vgm-variants/makoto/<stem>.vgm
vgm-variants/sfg01_makoto/<stem>.vgm
vgm-variants/sfg01_msxaudio/<stem>.vgm
vgm-variants/layered/<stem>.vgm
vgm-variants/scc_sfg01/<stem>.vgm
vgm-variants/scc_makoto/<stem>.vgm
vgm-variants/scc_layered/<stem>.vgm
_diagnostics/<stem>/vgm_variants/
```

Only applicable, successful profiles are published. PCM-free sources can use
sfg01, makoto, and layered. PCM-bearing sources can use makoto, layered, and the
two auxiliary SFG01 compositions; plain sfg01 cannot play their PCM. Native OPNA rhythm can
also use the Makoto auxiliary composition. Unsupported profiles have explicit
reasons in `_diagnostics/<stem>/vgm_variants.json`.

| Profile | FM / auxiliary sound hardware |
| --- | --- |
| sfg01 | YM2151 at 3,579,545 Hz, plus native YM2413 and AY PSG |
| makoto | YM2608 at 8 MHz, plus native YM2413 and AY PSG |
| sfg01_makoto | YM2151 FM, YM2608 ADPCM-B / native rhythm, YM2413 and PSG |
| sfg01_msxaudio | YM2151 FM, Y8950 Delta-T, YM2413 and PSG |
| layered | YM2151 and YM2608 FM in parallel, YM2608 ADPCM-B / native rhythm, YM2413 and PSG |
| scc_sfg01 | Real SCC plus the sfg01 composition |
| scc_makoto | Real SCC plus the makoto composition |
| scc_layered | Real SCC plus both FM layers |

## Layered FM

`layered` projects the same musical FM voices independently to SFG01 at
3,579,545 Hz and Makoto at 8 MHz. Waveform voices approximated by FM also use
both targets. Each chip has its own allocation and approximation diagnostics
under `plan.fm_layers`; the Makoto layer retains its six-channel limit even
though SFG01 has eight. Without force, a required capacity omission blocks the
profile; with force, omissions are reported separately for each FM layer.

PSG, OPLL, native rhythm, and PCM are projected once. PCM uses Makoto's existing
256 KiB ADPCM-B path, including representative reuse where supported. There is
no additional MSX-Audio bank or automatic FM gain reduction in this profile.
Both FM layers retain the ordinary mapping levels, so listening balance may
differ from a single-chip profile. Song timing and loop positions are shared.

## Real SCC with FM companions

SCC-bearing sources additionally publish `scc_sfg01`, `scc_makoto`, and
`scc_layered`: real SCC plus respectively OPM, OPNA, or both FM approximations.
The real SCC lane is reconstructed from the same NativePerformance pitch,
volume and waveform curves, without reopening the source file. Its original
clock/level are retained.
PSG, OPLL, noise and PCM are not duplicated. Makoto-containing compositions
retain their existing single PCM bank and 256 KiB budget.

The additional profiles require sounding SCC units on one primary cartridge.
Ordinary SCC channel 4/5 wave sharing is checked; incompatible simultaneous
waveforms are unavailable rather than silently overwritten. SCC+ independent
wave banks retain the native chip-type flag. Extended test/phase controls,
unknown waveforms or unrepresentable pitch also yield explicit unavailable
reasons. This does not add HuC/APU/FDS-to-SCC mapping. Musical time is unchanged;
the SCC loop boundary reasserts its enable mask and active voice state.
Per-profile write CSVs and `plan.real_scc` make the additional lane inspectable.
No detune is added and relative loudness still needs user listening checks.

## Representation boundary

The pipeline is source analysis -> `NativePerformance` -> target projection
-> VGM serialization. Target projectors do not open the source VGM or invoke
Segment/event-based conversion choreography. Authored performances without a
source file are valid inputs. Native controls preserve the original register
semantics and event order; they are not an alternative owner of editable
pitch, volume, voice, gate or percussion curves.

Native FM units group complete gates and retain mid-gate voice changes,
partial operator key transitions and shared effects. Carrier attenuation is
separated from native voice TL and recombined at projection, including after
an algorithm change. OPN-family FNUM high/low writes remain atomic.

All times are original integer VGM samples (44,100 per second). Target
frequency encoders use physical Hz and the clock actually stamped into the
output. No 60 Hz grid replaces source timing. Native pattern descriptions do
not duplicate or retime source controls. VGM song loops retain the native
loop time; serializer compaction keeps first register assignments within the
loop even when their values match the introduction. Decoded PCM runs crossing
the song-loop entry are partitioned there, so continuation triggers are inside
the repeat rather than only in the introduction.

## Sources and approximations

- OPN2, OPNA and OPM FM use musical pitch, volume and voice curves. Existing
  measured conversion helpers and LFO depth tables are reused. Native FM
  channel limits are applied only to the target. Excess lanes require force
  for explicit omission.
- SCC, HuC6280 waveform voices, NES pulse/triangle and FDS waves use a
  four-operator additive approximation. Four selected harmonics are retained;
  phase and analog transfer are not reproduced. FDS's 64 cells are reduced to
  32 for this approximation. HuC LFO-dependent pitches currently use the
  retained base pitch and report the omission of phase modulation.
- HuC/NES noise and DCSG use available AY/SSG generators. Shared noise periods,
  range clamping, spectrum and volume approximations are diagnosed. There
  are at most three AY voices, plus three OPNA SSG voices where present.
- Native PSG/SSG and OPLL retain their own target chip families. PSG shared
  hardware envelope controls remain distinct from the score's sounding gates.
  Native OPLL/OPNA percussion attacks, stops and levels come from percussion
  records; oscillator/global/pan effects remain separate controls.
- `NativePCM` retains decoded signed16 source content independently of opaque
  original PCM packets. OPN2 DAC, NES DPCM and HuC DDA are decoded. OPN2 uses
  the inherited shared decoded-supply renderer, including run splitting,
  rate clustering, deduplication and ADPCM-B/Y8950 encoding. Edited amplitudes
  are taken from PCM samples, never from a copied source payload.
- Generic decoded PCM overlaps are mixed at target projection because a
  cartridge has one Delta-T voice. Makoto and MSX-Audio each have a 256 KiB
  (262,144-byte) PCM budget. These profiles do not combine them into a 512 KiB
  pool; joint allocation across both cartridges is future work. Clipping and DRAM-capacity omissions are
  reported. Native OPNA ADPCM is preserved only on Makoto; a Y8950 relocation
  of that opaque transport is not implemented.

Within one source sample, voice/level writes after key-on currently project
the final onset curve state before target key-on. Original control order is
retained in native evidence and these cases have an explicit onset-order loss.

Cross-chip CH3 special mode, CSM, noise/SSG-EG, post-gate channel effects and
clock-dependent envelope/timer differences have explicit loss records where
not implemented exactly. NES DPCM memory uses the source data-block image;
missing bytes and mid-play rate/level changes are diagnosed. Analog filtering
and cross-chip acoustic equivalence are not claimed. These are experimental
playback projections; source evidence is retained for improved future maps.

## Inspection and publication

Each variant has a `.writes.csv` and `.projection.json` in its diagnostic
profile directory, alongside native JSON/CSVs. The write CSV retains musical
unit/device/source identities, exact samples, target bytes and whether a
redundant assignment was emitted. PCM inventory/rate/DRAM statistics and
projection losses are recorded in JSON. A successful write/framing check does
not establish acoustic equivalence.

Publication uses the existing ownership hashes and atomic bundle rollback.
Failed or disabled profiles remove their owned old products; user-modified
files are protected. The previous underscore layout (`vgm_variants/<stem>/`)
is recognized for owned-file migration/removal, not used for new products.
Generated folders from either layout are excluded from recursive inputs.

## Byte-budget representative reuse

The OPN2 musical route first keeps exact payload/run sharing and the established
rate clustering. If the unique encoded bank still exceeds the cartridge budget,
a separate target-only policy selects existing representatives using playback
demand and coarse normalized-envelope/duration/zero-crossing features. Every
playback is mapped; DC-only or delayed-onset assets cannot replace an active
onset. The result has no 96-slot constraint, remains within 256 KiB, and records
source-to-representative distances, counts and playback rate changes. These
features are capacity heuristics, not a claim of perceptual equivalence. No
source PCM content or event time is changed. If no feasible audible
representative exists, the failure is explicit rather than silently dropping
playbacks. The generic NES/HuC renderer has not yet adopted this policy.

## MSM6258 musical PCM

Eligible primary MSM6258 ADPCM4 / 10-bit-output playback is decoded into source-native signed16
assets before cartridge projection. Encoded bytes, original controls, timing,
reset evidence and source identities remain available in native diagnostics.
ADPCM3, 12-bit output, mid-play pan changes, unknown reset/rate and incomplete supply remain explicit
source decisions; they must not silently become FM-only success.

OPM + MSM6258 inputs use the existing Makoto, SFG01 + Makoto,
SFG01 + MSX-Audio and layered profiles. PCM is re-encoded as target ADPCM-B,
with one 256 KiB budget per cartridge. Standalone SFG01 has no PCM destination.
Exact encoded payloads are shared first. Capacity windows and song-loop cuts
preserve the source sample origin and scheduled playback endpoints. Padding
is included in the budget. There is no MDX/PDX 96-slot constraint.

When the bank exceeds capacity, `--force` enables the existing representative
selection policy. Every eligible playback receives a sample; substitutions,
source/representative identities, rate changes and any rate clamping are
reported in projection JSON alongside the target write CSV. Source assets
are unchanged. This is lossy capacity fitting, not perceptual equivalence.
Without force, over-budget banks and unresolved source evidence are rejected.
Force can omit unresolved source assets, with explicit loss counts.

MSM pan and mute are retained per playback, independently of payload sharing.
MSX-Audio folds stereo routing to mono with a loss record. Overlapping MSM
assets or a mixture with another decoded PCM family require an explicit mix
policy and currently fail. Fresh target predictors at packaging cuts,
linear resampling and finite decoded coverage are reported limitations.
Hardware playback and private-fixture regression remain separate validation.

The first source decoder uses the established x68k 10-bit MSM transition,
low nibble first, known reset predictor -2/index 0 and signed16 scaling.
The 12-bit output mode is explicitly unresolved, not silently decoded as 10-bit.
Blocking native analysis issues conservatively invalidate all its decoded assets;
observations do not. At most one VGM tick of fractional finite-exhaustion
rounding can be clipped downward, with exact rational exhaustion and the
original gate endpoint retained in asset metadata and source decisions. Larger
overruns remain unresolved; no extra samples or last-value hold are invented.
