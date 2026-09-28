# MGSDRV / libkss playback timing: sample investigation

Date: 2026-09-28

Status: measured observation for the supplied msxplay.com sample and an
external libkss-based playback implementation. This is not a universal
MGSDRV interrupt-frequency specification or a change to converter behavior.

## External evidence

Repository: https://github.com/hsk/oplldrv

Inspected commit: `9c040acaddfeb90b2a95ff0b9868d157cbc8f6ed`.

[bin/msxplay/mgs2log.mjs](https://github.com/hsk/oplldrv/blob/9c040acaddfeb90b2a95ff0b9868d157cbc8f6ed/bin/msxplay/mgs2log.mjs#L1-L58)
uses mgsc-js and libkss-js to compile/play MML. Its comments describe the
same playback components as msxplay.com and an approximately 59.94 Hz
MGSDRV interrupt rate under libkss. The script uses the empirically measured
constant `FRAME = 735.77` samples at 44100 samples/second:

```text
44100 / 735.77 = 59.93720863856912 frames/second
```

Treat 735.77 as the script's measured approximation, not an exact hardware
constant. Its comment explains that dividing by 735 (exactly 60 Hz) introduces
roughly one frame of drift per thousand frames. It also groups register
writes into interrupt batches using a gap greater than 300 samples before
rounding a batch's start to a frame. That batching rule is a heuristic, not a
chip specification; this investigation did not import it into the converter.

## Fixture and comparison method

Input and original MML:

- `tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm`
- `tests/fixtures/public/psg_opll/msxplay.com/sample/reference/sample.mml`

The user identifies this VGM as generated from the sample MML. The supplied
`reference/vgm2tx802/sample_trace.opll_regs.csv` contains source-derived
register times; an earlier comparison found it identical to the current
converter's regenerated register trace. Reference files are optional local
data and may not be present in a fresh checkout.

The investigation expanded the specific rhythm-track syntax used in this
fixture, including the four-repeat loop with a last-iteration exit and the
outer repeating sequence. This was a fixture-specific comparison, not a
general MGSDRV parser.

At tempo 120, a sixteenth note has an ideal duration of 7.5 nominal driver
frames and an eighth note 15. One expanded rhythm sequence has 53 hit groups
and 480 ideal frames. The recorded VGM contains 213 rising-edge groups.
Instrument combinations and per-instrument volumes matched that sequence
through all 213 groups.

For register 0x0E, the comparison used bits transitioning from zero to one
while rhythm mode was enabled. Per-instrument attenuation was read from
0x36-0x38 and converted to the MML volume convention as `15 - attenuation`.

Recalculation used unrounded source times, not Segment tick integers:

```text
samples_i = source_time_seconds_i * 44100
frame_60_i = samples_i / 735
frame_libkss_i = samples_i / 735.77

absolute_error_i = calculated_frame_i - ideal_MML_frame_i
aligned_error_i = absolute_error_i - absolute_error_0
```

Alignment removes the initial playback offset only; it does not fit a tempo,
retime individual hits, or alter VGM timestamps.

## Results

| Quantity | Exact 60 Hz | 735.77 samples/frame |
| --- | ---: | ---: |
| Initial absolute offset (frames) | 1.510204 | 1.508624 |
| Absolute error range (frames) | 1.165986 to 3.603401 | 1.066026 to 1.709128 |
| First-hit-aligned error range (frames) | -0.344218 to +2.093197 | -0.442598 to +0.200504 |
| Final aligned error (frames) | +1.956463 | -0.054908 |

As a separate check, matching phase positions 53 groups / 480 ideal frames
apart yielded a median of 735.750 samples per frame (range 735.498 to
735.998). This is consistent with the external script's approximation.

The previously reported 2 to 4.5 tick difference was calculated with the
existing 60 Hz integer tick conversion and included the initial offset.
It is not the same metric as the aligned, unrounded errors above. In
particular, current `get_ticks()` applies `ceil(time * 60)` with an additional
legacy special case mapping tick 1 to 0.

## Interpretation and limits

The results strongly support the playback-period mismatch as the main source
of cumulative drift in this sample. They do not prove the origin of every
remaining sub-frame difference or validate 735.77 for every playback system.
Register writes within an interrupt occur at different times; exact duration,
startup phase, frame scheduling and rounding need separate consideration.

The user considers the previously observed small timing differences acceptable.
This observation is useful for interpreting and reproducing MML timing, not
justification for silently correcting source events.

## Guidance for future work

- Preserve VGM time in its original 44100-sample time base. VGM does not acquire
  a new time base because the originating player uses a different interrupt rate.
- Distinguish source timestamps, inferred playback frames and MML musical steps.
  The existing target convention of 48 MML steps per quarter is another unit.
- Apply playback-period knowledge when relating MML lengths/tempo to elapsed
  time, or when explicitly reconstructing the originating driver's frames.
- Do not replace every converter `60` with `59.94`, or universally apply the
  measured 735.77 constant to unrelated VGM sources or targets.
- If a source/target timing profile is implemented, make its provenance and
  conversion explicit and preserve the original observations in dumps.
- Current Segment grouping and exact pattern matching still use the existing
  60 Hz ticks. Slight drift can therefore split otherwise similar patterns.
  No timing-profile or pattern-tolerance change was implemented in this work.

The arithmetic was checked against all 213 groups. No MGSDRV replay or audio
comparison was performed as part of this recalculation.
