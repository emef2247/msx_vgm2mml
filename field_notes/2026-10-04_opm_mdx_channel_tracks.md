# OPM MDX channel separation (2026-10-04)

## Purpose and scope

The user prioritized channel separation before MDX loop reconstruction.
Native OpmSegment already has physical ch0..7 and a self-contained effective
channel/operator snapshot. The missing information was explicit ownership in
the ordered raw register CSV; the initial target also placed all controls on A.

Work checkout: `I:/wsl/repositories/emef2247/test/msx_vgm2mml`.
The damaged original checkout was not changed. README remains unchanged;
OPM is still not announced there.

## Changes

- Raw OPM CSV appends `ch` and `register_scope`, retaining one row per source
  write and its event ID/address/absolute samples. New ch annotations are
  validated; legacy traces without the column remain readable.
- Effective channel, pitch, pan, modulation sensitivity, four-operator and
  Key-mask states remain separate per chip/channel. LFO/test/timers are
  chip-wide state, not inferred channel controls or an external patch table.
- Noise register 0x0f is scoped to ch7. It no longer creates noise-only
  Segment boundaries or irrelevant noise fields on ch0..6.
- MDX register replay defaults to A..H for ch0..7, including individual
  operator controls and partial Keys. Chip-wide writes occur once on A;
  ch7 noise is emitted on H. Each used track shares global source zero and
  advances independently to the real projected source end.
- Controls CSV adds physical `ch` and scheduling `mdx_track`; timing JSON
  reports `track_layout`. Shared controls have blank physical ch even on A.
- `--track-layout conductor` explicitly retains the previous source-ordered
  A-only replay. No automatic fallback, note quantization, voice conversion,
  loops, macros or discarded zero-duration events were introduced.

## Independent validation

Used the existing external mmlx 0.2.0 / soundlog 0.15.0 fixture helper, without
copying its implementation into the Python engine. The validation path was:

```text
source VGM -> native Segments -> channel MDX MML -> MDX -> returned VGM
           -> native Segments -> control/state/key/timing comparison
```

| Measurement | Public OPM set | Two short local MSXGRA2S inputs |
|---|---:|---:|
| Cases passed | 38/38 | 2/2 |
| Retained controls, source = returned | 8,572 | 2,625 |
| Channel attack events, source = returned | 357 | 125 |
| Operator KeyOns, source = returned | 1,377 | 440 |
| Operator KeyOffs, source = returned | 1,208 | 424 |
| Missing/extra channel or operator Key edges | 0/0 | 0/0 |
| Source-known state mismatches | 0 | 0 |
| Maximum source timing delta (44100 Hz samples) | 6 | 0 |
| Maximum projected timing/end delta (samples) | 0 | 0 |
| Cases whose cross-channel source write order changed | 10 | 2 |

Private smoke inputs were M_G2_17S and M_G2_18S. This is not a repeat of the
full private catalog; earlier clock/MDX capacity limits are still unresolved.

MDX processes A..H sequentially within one tick. The source CSV/projection is
never reordered; a separate target scheduling projection predicts that order.
Roundtrip comparison checks every retained register/data control and all
source-known states against that prediction, without relaxing Key counts,
state checks or target times. Cross-channel equal-tick ordering may change;
this does not assert waveform/phase equality or that every possible coupled
shared-control stream is representable. Such discrepancies remain detectable
in the external comparison; conductor layout remains available explicitly.

A proposed pre-export replay gate starting from unknown registers falsely
rejected native MDX initialization: the real external player already initializes
channel defaults before track playback. That extra gate was removed rather than
inventing a reset table or weakening the independent roundtrip comparisons.
The actual initializer continues to be measured separately and its exact
zero-time prefix checked before exclusion, as in the previous verifier.

42 OPM unit tests pass. Added coverage for all eight channels/operator banks,
common timing origin/tails, partial same-time Keys, raw ownership, channel-7
noise scope, legacy conductor rendering, explicit target scheduling, and
rejection of corrupt raw/Segment channel annotations. Existing independent
roundtrip negative tests still check wrong pitch/state/Keys/timing.

## Artifacts and next step

`outputs/opm/channel_tracks_20261004/` retains:

- `public_all/results.csv` and `results.json`: all 38 public inputs.
- `local/M_G2_17S/` and `local/M_G2_18S/`: private two-case evidence.
- `summary.json`: aggregate measurements above.
- Per case: MML, compiled MDX, returned VGM, raw/state/Segment CSVs,
  control projection, timing report, compiler log and comparison JSON.

Source fixtures and reference MML/MDX were not changed. These output artifacts
remain outside git. The converter's normal output remains MML only;
`--dump-passes` retains inspection CSVs.

Next: develop musical note/voice notation and per-channel reversible loop
structure. Current output is still explicit `y<register>,<data>` control replay,
so channel separation alone is not a claim of completed musical structuring.
