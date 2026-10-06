# PSG/SCC -> OPM conversion audit and WAV comparison (2026-10-06)

## Scope

Priority returned to sound-chip conversion at the user's request. This audit
used existing source Segment CSVs and target artifacts, inspected both mapping
implementations, and rendered two local songs with the same external VGMPlay
cores. It did not change native Segments or the MDX renderer.

The goal is deterministic use of source musical data on real sound hardware.
Spectral similarity, target behavior, notation/display and real-hardware
listening are separate observations. No aggregate sound-quality score is used.

## Existing conversion results and blockers

These are the saved **register-control/additive** `results.csv` inventories,
not the user's later note-MDX regression. They include split files and are not
counts of unique songs. Classifying the first reported failure yields:

| First outcome | PSG (82 inputs) | PSG/SCC (255 inputs) |
| --- | ---: | ---: |
| Verified target controls | 43 | 16 |
| Noise or hardware EG unsupported | 20 | 141 |
| KC/KF range rejected | 17 | 26 |
| External MDX offset failure | 2 | 7 |
| Dual-chip/SCC-variant target guard | 0 | 65 |

Do not add the categories as estimates of independent unsupported features:
conversion stops at the first failure. Saved source CSVs from 272 inputs were
also examined to expose later noise/EG states, independently of that first error.
The other inputs lack the saved source CSVs needed for this audit.

NEMESIS2 has 17 GRA2 songs: only GRA2_07 and GRA2_17 currently verify. Twelve
first fail at noise/EG; GRA2_01, GRA2_09 and GRA2_13 first fail at pitch range.
Source PSG inspection nevertheless finds noise in 15 songs, mixed tone/noise
in 14, and hardware EG in 12. GRA2_07/17 have tonal PSG only. Range handling
alone therefore will not complete all the remaining songs.

Examples, preserving source channel-time durations (summing channels, not a
unique elapsed interval):

| Source | Tone rows | Noise-only rows | Mixed rows | EG rows |
| --- | ---: | ---: | ---: | ---: |
| GRA2_02 | 441 | 22 | 9 | 0 |
| GRA2_03 | 2,316 | 716 | 20 | 604 |
| GRA2_09 | 2,537 | 819 | 36 | 867 |

GRA2_02 noise-only spans total 38,209 samples; mixed spans total 5,879 samples.
These are positive-duration behavior, not merely chip initialization writes.
GRA2_03 EG spans total 327,283 channel-samples. Their omission would remove
source behavior rather than just make compilation more permissive.

## A concrete pitch rejection: GRA1_03

PSG ch0 changes period 256 -> 0 -> 228 twice. Each period-zero intermediate
state lasts two native samples, about 45.35 microseconds, with nonzero volume.
The target currently treats period zero like period one, giving 111,860.8125 Hz.

| Source interval (samples) | MDX tick interval | Current handling |
| --- | --- | --- |
| 582928..582930 | 51634..51634 | Explicit zero-target-duration omission |
| 630032..630034 | 55806..55807 | Range exception |

Both states arise on a high-byte frequency write followed by the low-byte write.
Identical physical durations receive different treatment because their absolute
phase relative to the MDX tick grid differs. The rejection therefore does not
prove a sustained musical note outside OPM range. Source evidence must remain
intact, including these two-sample intervals.

A target-only sample/hold projection or a documented transient policy can avoid
this tick-phase dependency. It must expose which source intervals were omitted
or replaced; do not erase them in PSG Segment construction. Genuine sustained
out-of-range tones need a separate response. Scaling KC down and operator MULs
up can preserve selected partial frequencies when all required MULs fit; it
cannot generally preserve all four odd harmonics of arbitrarily high input.
Clamping KC would silently change pitch and should not be called exact conversion.

## Mapping differences inspected

| Property | Current additive target | vgm-conv AY -> OPM |
| --- | --- | --- |
| PSG tone | AL7 / FB0; four independent sine carriers at 1,3,5,7 with 1/n weights | AL4 / FB7, modulator MUL2 TL27, carrier MUL1 |
| High partials | Finite selected set; higher odd partials omitted | FM/feedback generates a richer set of partials |
| Source level | Approximate 3 dB per volume level; current gain 0.125 | Fixed volume-to-TL table plus default tone attenuation 8 |
| Key behavior | Held oscillator; level/pan updates | Held tone/noise operators; level updates |
| Noise | Rejected | Dedicated channel 7 C2 hardware noise; maximum enabled source-channel volume |
| Hardware EG | Rejected | Tone volume forced to zero when EG flag is set; full EG is not reconstructed |
| SCC | Four strongest DFT bins per 32-sample wave, phases recorded but not reproduced | The AY converter does not convert SCC; retained SCC in a mixed output is not all-OPM playback |

Primary implementation inspected:
[AY -> OPM converter](https://github.com/digital-sound-antiques/vgm-conv/blob/main/src/converter/ay8910-to-opm-coverter.ts)
and its pitch helper. Local source was inspected at
`I:/wsl/repositories/test/vgm-conv`; listening comparison used the external npm
vgm-conv 0.14.1 package. No implementation was copied into this repository.
Its pitch helper caps the octave and handles zero frequency by selecting KC0.
Successful external conversion is therefore not proof that every source pitch,
EG or source-channel noise amplitude was preserved.

The supplied VGMPlay AY core (`chips/ay8910.c`) models tone/noise mixer output
as a logical gate combination, not independent tone-plus-noise addition. It also
keeps a shared noise generator and shared envelope phase. Writing envelope
shape resets that phase, including a repeated same-value shape write. Existing
PSG Segments retain `evS` events and envelope fields; do not turn each Segment
into a new envelope attack. AY/YM variants need their own rate/level profile.

## Same-renderer WAV measurements

Inputs: native `GRA1_05` and `DSLY4_04`, the existing additive returned VGM,
and each matching `*.vgm-conv.vgm`. Used the externally built VGMPlay renderer
at 44,100 Hz, stereo, integer 16-bit PCM, one stored traversal, no fade or
normalization. Renderer and external GPL sources remain outside this repository.

Analysis uses the shared 0.1..5.0 second interval, Hann FFT4096, hop1024,
Welch mean power, frame DC removal, and mean channel power. No automatic
alignment, resampling, gain matching or perceptual score was applied.
The source has substantial DC; AC RMS is reported separately from raw RMS.

| Song / version | AC RMS dBFS | Spectral centroid Hz | 95% rolloff Hz | Energy at/above 4 kHz |
| --- | ---: | ---: | ---: | ---: |
| GRA1_05 source | -20.24 | 563.0 | 1,970.3 | 2.021% |
| GRA1_05 additive | -28.54 | 551.6 | 1,755.0 | 0.411% |
| GRA1_05 vgm-conv | -18.77 | 780.4 | 2,960.8 | 3.474% |
| DSLY4_04 source | -25.69 | 738.5 | 2,271.8 | 2.666% |
| DSLY4_04 additive | -32.47 | 523.6 | 1,862.6 | 0.452% |
| DSLY4_04 vgm-conv | -22.71 | 749.6 | 2,971.6 | 3.332% |

Both additive outputs have markedly less high-frequency energy. The measured
levels are also lower under the current gain; this is not evidence of missing
source channels. vgm-conv retains/generates more high partials, but it exceeds
the source high-frequency energy in both measured intervals. These numerical
observations are compatible with the user's less-bright/additive and brighter/FM
listening reports; they do not rank overall reproduction quality.

Entire rendered durations match for GRA1_05 (20.845283 s). DSLY4_04 source and
vgm-conv are 38.683492 s; additive is 38.683356 s (six rendered samples shorter).
These two cases show no large tempo difference. This does not resolve earlier
public-fixture timing reports or certify every track's timing.

Local artifacts, deliberately outside tracked source:

- `outputs/opm/diagnostics_2026-10-06/first_failure_classes.json`
- `outputs/opm/diagnostics_2026-10-06/psg_source_modes.csv`
- `outputs/opm/diagnostics_2026-10-06/wav/<stem>/{source,additive,vgm-conv}.wav`
- `outputs/opm/diagnostics_2026-10-06/wav/<stem>/report/{metrics.json,metrics.csv,spectra.csv,comparison.png}`
- `outputs/opm/diagnostics_2026-10-06/wav/durations.json`

Reproduce analysis after rendering with the existing external renderer:

```bash
python scripts/analyze_wav.py \
  <wav-dir>/source.wav <wav-dir>/additive.wav <wav-dir>/vgm-conv.wav \
  --start 0.1 --end 5 --outdir <wav-dir>/report --plot
```

## Countermeasures and next bounded experiments

1. **Separate range failures into transient and sustained cases.** Start with
   GRA1_03's two-sample writes and retain a source-to-target mapping. Validate
   boundaries independently of absolute tick phase. Do not globally widen a
   tolerance or clamp musical pitch to obtain a success count.
2. **Noise-only PSG first.** Preserve all three source-channel identities and
   the shared noise period, and add an explicit hardware-OPM-noise target plan.
   PSG-only inputs have spare OPM channels, allowing a clean first experiment
   such as XANADU01. Use measured noise-rate/spectral behavior to choose the
   mapping; vgm-conv's reversed period and maximum-volume rule are comparison
   points, not a specification to copy.
3. **Mixed tone/noise separately.** Logical AY mixing is not faithfully modeled
   by summing independent sine and noise outputs. If that approximation is used,
   identify it in the target mapping and assess it on public mixer fixtures.
4. **PSG+SCC channel allocation.** Five SCC plus three PSG parts already occupy
   eight OPM channels. Adding a dedicated noise channel without an explicit
   operator/channel-sharing plan loses a part. Investigate sharing ch7 C2 noise
   with three remaining sine carriers, or a measured allocation across available
   parts; label any reduction from four to three harmonics. GRA2_02 is a short
   noise/mixed fixture without EG, useful before GRA2_03.
5. **Hardware EG.** Reconstruct shared envelope phase, period changes, repeated
   shape-write restarts, hold/alternate/attack and variant rate from preserved
   source events. Project that amplitude trajectory to OPM TL updates. Keep this
   derived trajectory in a target diagnostic, not rewritten native volume fields.
   vgm-conv does not supply a full-EG baseline.
6. **Tone character and gain.** Keep finite additive synthesis as an explicit
   choice. Compare an independently designed feedback/FM profile or increased
   harmonic resources separately. Calibrate gain/volume curves with the public
   volume sweep, not a subjective adjustment on a single game track. Record
   spectral changes, level, clipping and resource costs independently.

These are investigated countermeasures, **not implemented fixes**. MDX notation
work remains paused. The current checkout has the shared VGM header changes on
`codex/mdx_vgm_header_parsing`, not this branch: `scripts/psg_scc_to_mdx.py` imports
`read_vgm_header`, which this branch's `py/vgm_io.py` does not yet define.
Saved artifacts sufficed for this audit. Integrate the user's header branch
before a fresh conversion regression; do not create another input decoder.
