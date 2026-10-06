# PSG/SCC to OPM through MDX: investigation and proposal

Date: 2026-10-05. Status: measured source inventory and target design proposal;
no cross-chip converter or converted listening set has been implemented here.

## Scope and inspected evidence

- Actual inputs are 17 files named `GRA2_01.vgm` through `GRA2_17.vgm` under
  `tests/fixtures/local_only/psg_scc/vgmrips.net/NEMESIS2/` (not `GRA_*.vgm`).
- Ran the existing reader with integer source timestamps and existing PSG/SCC
  Segment builders for all 17. Did not run target compression or change them.
- Inspected all 18 compiled tone banks in `local_only/opm/MDX/MSXGRA2S/` using
  the existing external generator's `--inspect-mdx`. Read MSXGRA2S.DOC and
  the MDX titles. This is an independently arranged reference, not an oracle
  for exact register/state correspondence or a production patch lookup table.
- Read chapter 7 of the user-provided MS.X development PDF, especially printed
  pages 52-53, and the existing additive-harmonic field note.
- Inspected current MDX projection/rendering and public native-OPM facilities.
  Current production MDX input requires native 4 MHz YM2151 Segments;
  cross-chip projection does not exist yet.

Private traces, integrated Segment CSVs, SCC waveform banks, tone-bank CSVs,
analysis script and aggregate CSVs are retained outside the repository:
`C:/Users/ef110/Documents/Codex/2026-09-25/co/tmp/psg_opm_study/`.
Do not commit these extracted private waveforms or tone parameters.

## Measurements

All 17 inputs declare 1,789,772 Hz for both AY/PSG and SCC clocks in their VGM
headers. Use these source clocks and each chip's divider semantics when
calculating target pitch, rather than assuming 3.58 MHz from the host system.

The source inventory counts only positive-source-duration intervals. PSG rows
must have an enabled mixer mode and either nonzero volume or envelope enabled;
SCC rows must have enable and nonzero volume. These are state-based candidates,
not proof that every interval is acoustically audible. Envelope phase, zero
periods, DC waveforms and sub-tick register transitions need separate treatment.

- SCC: 83 per-song waveform IDs across the catalog, 22 distinct byte waveforms
  after exact deduplication. IDs include observed intermediate states; these
  are not automatically 22 authored instruments.
- PSG noise enabled in 15 songs, tone+noise enabled in 14, hardware envelope
  enabled in 12. Each song's observed noise use belongs to one source channel:
  ch0 in GRA2_02/GRA2_16, ch1 in the other noise-using songs.
- GRA2_17: 3 SCC waveform IDs, no observed enabled PSG noise/hardware envelope.
- GRA2_05: 5 waveform IDs, noise/mixed mode, no enabled hardware envelope.
- GRA2_03: 5 waveform IDs, noise/mixed mode and enabled hardware envelope.
- Enabled hardware-envelope rows include periods 0, 11, 66, 184 and 768,
  and shapes 0, 9 and 10. Do not treat all such rows as a slow loudness fade.

For each SCC waveform, analyzed its 32 signed samples after removing DC, using
a real DFT. Selected four strongest bins among harmonics 1..15 (the direct
integer-MUL candidate set), retaining bin 16 in the residual denominator.
Selected AC energy fraction: minimum 66.39%, median per waveform-ID occurrence
87.42%, and channel-duration-weighted mean 86.90%. No volume weighting,
operator TL quantization, analog reconstruction/filtering, aliasing, phase
matching or OPM rendering was included. These fractions are **not audio quality
scores** or proof of a matching FM patch. Even harmonics are important in these
waves; applying a fixed 1/3/5/7 recipe to every SCC waveform is inappropriate.

The 18 manual MDX banks contain 203 definitions, with 134 distinct parameter
sets ignoring bank/voice ID. Definition counts by algorithm: AL5=88, AL4=51,
AL2=22, AL0=17, AL3=12, AL6=9, AL7=4. These are bank definitions, not measured
audible use counts. They do not support treating the manual arrangement as
pure AL7 additive synthesis or as a one-to-one SCC-wave-to-OPM-patch table.
The DOC describes channels 6/7/8 as PSG parts; that is evidence about this
arrangement, not a universal channel assignment rule.

## Proposed transformation boundary

```
PSG/SCC VGM -> existing native state and immutable Segments
  -> cross-chip OPM target plan (voice, pitch, volume, timing, channel mapping)
  -> MDX MML on A..H -> external mmlx/MDX replay -> 4 MHz OPM VGM
```

Keep source clocks, waveform bytes, periods, mixer/envelope state and vgmticks
unchanged. Do not manufacture native OpmSegments claiming the input had YM2151
registers merely to reuse the existing native-OPM renderer. The new target plan
must retain source chip/channel/row references and label generated OPM settings
as target choices. Keep each existing chip's integrated Segment CSV; additional
target annotations/CSV must not split source channels into separate files.

Reuse absolute MDX tick projection, channel scheduling, syntax helpers,
compaction where applicable, external compilation and returned-OPM analysis.
Native OPM source-loop matching is not automatically applicable to PSG/SCC;
use their source structural plans and validate projected target-loop expansion.
Start with a transparent target command stream, then ordinary notes where they
preserve the held-state behavior, followed by reversible loops/compaction.

## Timbre and performance policy

1. **PSG tone:** AL7 four-carrier 1/3/5/7 additive patch is a reproducible first
   approximation. Tune amplitude ratios from the intended square spectrum,
   measure actual target output and calibrate overall gain. Do not claim an
   exact square or full high-frequency behavior from four harmonics.
2. **SCC:** select up to four suitable harmonics per source waveform, using
   their measured magnitudes for relative carrier levels. Record DC, phases,
   selected/omitted components and quantization. Arbitrary source phase cannot
   simply be specified by MUL/TL; use spectral similarity as one limited test.
   Compare this baseline with independently designed FM/feedback candidates
   where omitted harmonics matter. Manual MSXGRA2S tones are listening examples,
   not parameters to hard-code into a generic converter.
3. **Continuity:** keep a sustaining FM configuration keyed on and change
   pitch/TL as PSG/SCC state changes. Mute output explicitly for source silence.
   Source waveform or volume updates must not automatically create new OPM
   attacks. Any required target retrigger must be explicit and inspectable.
4. **Volume:** spectral balance and musical amplitude are separate. Apply the
   source volume trajectory to active carriers together. PSG/YM volume curves
   and SCC amplitude scaling require different mappings, followed by chip-mix
   gain calibration. The PDF's table is a candidate for its Yamaha-PSG case,
   not a universal SCC or OPM-noise loudness table.
5. **Pitch/time:** derive physical pitch from the actual source divider/clock,
   then choose OPM KC/KF at the MDX player's 4 MHz clock. Record pitch error and
   out-of-range cases. Use common-origin source samples and absolute MDX tick
   rounding; do not round intervals independently or copy MGS note names.

## Noise, envelopes and eight-channel budget

Five SCC channels plus three PSG channels fit eight OPM channels as logical
parts, but this does not imply equivalent sound generation. OPM hardware noise
uses channel H's final operator. For this catalog, assign each song's single
noise-using PSG source channel to H, the other PSG parts to F/G, SCC to A..E,
with an explicit mapping table. This is based on measured use, not a hard-coded
rule that PSG ch1 always carries drums.

H can use its other operators for a tonal approximation, but adding a tone and
noise is not an exact emulation of the PSG mixer. The PDF's noise-rate inversion
is a practical approximation, not an exact frequency conversion across clocks.
Its XOR wording must not be adopted as a source-chip rule: emu2149's output
combines enabled tone/noise gates with AND. Verify noise spectrum/rate and
volume separately; report the approximation rather than silently dropping tone.
Multiple simultaneously noise-using PSG channels in other inputs need an
explicit policy and must not be silently merged into a maximum-volume lane.

Hardware envelopes require their shared phase and shape-write restart events,
including repeated writes of the same shape. Check that source evidence is
sufficient before deriving a target curve; retained raw/trace evidence remains
available. Slow trajectories may become TL changes; fast/zero-period operation
cannot be assumed representable by the current 256-us MDX tick. This needs an
explicit approximation strategy and acoustic evaluation, not generic FM EG
settings or a new KeyOn for every envelope step.

## Implementation and validation sequence

1. Synthetic public square/sine/multi-harmonic and volume-continuity cases,
   plus GRA2_17 as the first private listening conversion. Keep MML, MDX, VGM
   and target-to-source mappings. No noise/envelope omission is required there.
2. GRA2_05 adds noise and tone/noise approximation; GRA2_03 adds hardware
   envelope handling. Do not call either complete until those behaviors have
   an explicit implementation and report.
3. Compare corresponding passages of MSXGRA2S by title/melody, not numeric
   filenames. E.g. its boss track is M_G2_13S, not M_G2_05S; the latter is the
   plant stage. The banks contain 18 pieces versus 17 source fixtures.
4. Target plan -> MDX -> OPM VGM -> native OPM Segment comparison checks
   generated controls, pitch, volume, timing and unwanted Key edges against
   the plan. This does not prove cross-chip acoustic equivalence.
5. Source-to-target validation additionally checks all source part assignments,
   audible/mute transitions, trajectories, retained/dropped spectral components,
   and listening. PSG/SCC do not supply OPM-style KeyOn counts, so requiring
   equal raw Key counts across the chips would be the wrong oracle.
6. Expand to all 17 only after short cases. Measure text/binary capacity and
   preserve continuity through source loops before target compaction; do not
   sacrifice notes or rewrite Segments to fit MDX.

## References and qualifications

- User's local `assets/psg_scc_voice_by_fmchip/MS.X開発秘話-電子版-v1.0.pdf`,
  chapter 7, printed pp. 52-53: held-key/output muting, volume and noise advice.
- `field_notes/2026-10-04_opm_additive_harmonic_mapping.md`: constrained DFT
  approach and why it does not uniquely identify an arbitrary FM patch.
- [emu2149 implementation](https://github.com/digital-sound-antiques/emu2149/blob/master/emu2149.c):
  output mixer, volume variants and shape-write restarts, inspected as semantic
  reference only; no external implementation was copied.
- [ymfm OPM implementation](https://github.com/aaronsgiles/ymfm/blob/main/src/ymfm_opm.cpp):
  noise/operator association and independent noise clock behavior; reference
  only. Native source semantics and target approximation remain distinct.

Production code, tests and fixtures were not edited. No cross-chip MML/MDX/VGM
was generated and no new audio-likeness result is claimed by this investigation.
