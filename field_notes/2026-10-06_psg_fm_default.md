# Default FM/feedback PSG target (2026-10-06)

## Requested change and boundaries

The user asked to make the richer FM/feedback PSG tone approach the OPM default
while retaining finite additive synthesis for future multi-OPM/6OP experiments.
MDX musical-notation redesign remains paused; local OPM reference MMLs remain
its future quality target. No display-specific KeyOns or note-renderer changes
were introduced. MGSDRV remains the top-level default output target.

The user's goal is hardware playback of deterministic source-derived musical
data. A target roundtrip proves that the selected projection survives compilation,
not that a PSG waveform is reproduced without acoustic loss.

## Implementation

- `py/psg_opm_fm.py` declares an independently written AL4/FB7 PSG profile:
  register-bank M1 MUL2/TL27, C1 MUL1 with fixed source-level attenuation and
  eight TL steps of headroom; unused operators muted. Gain changes affect C1,
  not the modulator's timbre. No external converter code/runtime was imported.
- `scripts/psg_scc_to_mdx.py` defaults to FM. The main command exposes
  `--target opm`, with `--psg-model fm|additive`. Old `--target opm-additive`
  explicitly selects the previous model.
- SCC remains waveform-derived additive synthesis. Arbitrary SCC waves are
  not replaced with the AY square-tone patch.
- `--opm-pitch-policy clamp|error` is independent of the voice model. FM defaults
  to clamp; additive to the old error policy with zero-target-duration omissions.
  Clamp selects the nearest legal KC/KF boundary, rather than wrapping the
  note within a capped octave. It can permit compilation by changing pitch;
  it does not extend hardware frequency range. This policy also applies to SCC.
- Source frequency, projected frequency, signed error, range-limiting reason,
  native timestamps, source channel and row stay in the target CSV. Model/clock/
  gains/policy/clamped count are saved in target JSON. Separate source CSVs
  remain integrated per chip and unchanged.
- The existing `read_vgm_header` helper from the user's committed
  `codex/mdx_vgm_header_parsing` was reused verbatim in this checkout to satisfy
  the converter's existing dependency. No new VGM decoder was introduced.

Parameter reference inspected locally:
`I:/wsl/repositories/test/vgm-conv/src/converter/ay8910-to-opm-coverter.ts`.
[Published primary source](https://github.com/digital-sound-antiques/vgm-conv/blob/main/src/converter/ay8910-to-opm-coverter.ts).
Compatible mapping parameters do not imply byte-identical VGM conversion:
this project consumes native Segments, rounds corrected pitch to the nearest
KC/KF step, projects timing onto MDX ticks and uses explicit pan muting.

Noise/hardware EG are not implemented by this tonal switch. It is not the entire
vgm-conv converter transplanted into this project. Unsupported states continue
failing explicitly rather than being silently discarded. The existing additive
note renderer intentionally rejects non-AL7 plans.

## Verification

- Nine existing additive projection checks, six new FM/range/CLI checks and four
  additive note-renderer checks passed (19 total).
- `test_vgm_io.py`: two tests passed, one existing title assertion failed:
  expectation `[SMS]ゲーム...`, actual `[SMS] ゲーム...`. The space is already
  required by the user's previous title change. GD3 code/tests were not modified
  as part of this tonal change; this unrelated expectation remains to reconcile.
- Public PSG directory: 11/13 inputs verified for each model. legato_patch_mix
  and patch_change_midnote retain explicit noise/EG rejection.
- Local FM: GRA1_03, GRA1_05, DSLY4_04 and PSG/SCC GRA2_17 all verified against
  exact generated target writes, Key commands and end time. Additive verifies
  the latter three; GRA1_03 still rejects out-of-range under its old policy.
- Source PSG/SCC Segment CSVs agree byte-for-byte in all 34 comparisons across
  these 17 inputs. Blank/unused-chip evidence is included in that count.
- GRA1_03 exposes three clamped rows and completes 2,450 exact target controls.
  The two-source-sample period-zero states are retained rather than deleted.

| Local song | FM MML characters | Additive MML characters | FM MDX bytes | Additive MDX bytes |
| --- | ---: | ---: | ---: | ---: |
| GRA1_03 | 38,328 | range-rejected | 9,876 | - |
| GRA1_05 | 32,794 | 79,911 | 8,713 | 22,795 |
| DSLY4_04 | 64,456 | 97,122 | 18,303 | 28,137 |
| GRA2_17 | 25,940 | 27,893 | 8,098 | 8,689 |

These are register-control MMLs, not the previously generated tied-note MMLs.
Reduced command count is a consequence of controlling fewer tonal operators;
no new structural compression is claimed.

Artifacts: `outputs/opm/fm_default_2026-10-06/benchmark_results.csv`,
`benchmark_results.json`, `native_comparisons.json`, and per-input `fm/` and
`additive/` folders with MML/MDX/VGM, native passes and target plans.
No private fixture content is copied into tracked documentation.

## Same-renderer WAV evidence

VGMPlay 44.1 kHz stereo 16-bit, one traversal, no fade/normalization. Same shared
0.1..5 second interval, Hann4096 / hop1024 Welch power with per-frame DC removal;
no quality score, automatic alignment or gain matching. Source/external vgm-conv
WAVs from the previous audit were reused; new FM/additive returned VGMs were
rendered with that same external executable. No clipped full-scale samples were
found in these intervals.

| Song / version | AC RMS dBFS | Centroid Hz | 95% rolloff Hz | Energy >=4 kHz |
| --- | ---: | ---: | ---: | ---: |
| GRA1_05 source | -20.24 | 563.0 | 1970.3 | 2.021% |
| GRA1_05 new FM | -18.80 | 786.1 | 3046.9 | 3.523% |
| GRA1_05 additive | -28.54 | 551.6 | 1755.0 | 0.411% |
| GRA1_05 external vgm-conv | -18.77 | 780.4 | 2960.8 | 3.474% |
| DSLY4_04 source | -25.69 | 738.5 | 2271.8 | 2.666% |
| DSLY4_04 new FM | -22.73 | 751.0 | 2928.5 | 3.289% |
| DSLY4_04 additive | -32.47 | 523.6 | 1862.6 | 0.452% |
| DSLY4_04 external vgm-conv | -22.71 | 749.6 | 2971.6 | 3.332% |

The new FM target is close to the external converter in these descriptive level
and spectral measurements. Both FM results have more high-frequency energy than
the source in these intervals. No general acoustic superiority or exact equivalence
is inferred. Current default FM gain is 1 relative to its declared headroom;
additive retains 0.125. Compare shape and level separately.

WAVs and plots: `outputs/opm/fm_default_2026-10-06/wav/<stem>/`.
This output remains local/ignored and is not committed.

## Next scope

Continue source-derived PSG noise/mixer/EG targets independently of this voice
choice. For future multi-OPM/6OP/OPL3 mapping, use the preserved requested pitch,
range-loss flags and operator resources to decide allocation. Do not fake source
KeyOn edges to animate MMDSP. Musical MDX notation should later be designed
against the existing local OPM reference MMLs with its own inspectable note model.
