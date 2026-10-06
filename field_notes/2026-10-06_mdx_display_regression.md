# Additive note-MDX regression and MMDSP display (2026-10-06)

## Scope and decision

The user ran `scripts/render_additive_mdx_notes.py` on the existing additive
projection outputs and listened with MMDSP. Screenshots identify MMDSP 0.30 beta
and the MADRV driver. This investigation inspected the generated MML, mappings,
MDX sizes and public MMDSP source. It did not run the user's MMDSP installation.

**Further MDX MML renderer changes are on hold at the user's request.** Native
Segments, projection code, compiler and fixtures were not changed in this audit.
The current MDX route remains useful for target-plan roundtrip verification.
A complete, structured musical MDX output comparable with the local reference
MMLs is a separate unfinished objective, relevant to a future x68k project.

## User regression versus saved artifacts

These counts come from the supplied terminal transcript, not the earlier
register-control renderer's `results.csv`:

| Note-rendering input | Attempts | Verified | MDX offset failures |
| --- | ---: | ---: | ---: |
| `outputs/opm/local_only/psg` | 45 | 42 | 3 |
| `outputs/opm/local_only/psg_scc` | 23 | 15 | 8 |
| Total | 68 | 57 | 11 |

PSG offset failures: DSLY4_02, DSLY4_11 and XANADU14 (track 7).
PSG/SCC offset failures: gra2_008 and gra2_008_with_sync_mark01 (track 7),
MG2_04 and MG2_05 (track 3), MG2_18 (track 5), and MG2_25, MG2_30 and MG2_36
(track 4). These are the compiler's track indices as printed, not a claim
that any ADPCM note was generated.

`verified` checks the projected OPM audible states, Key edges and end time
under the external roundtrip's semantics. It does not certify MMDSP display,
MADRV work-area behavior, acoustic equivalence or capacity on every player.

## Listening/display observations supplied by the user

All the following files still produce music according to the user.

| Files | Observed MMDSP behavior |
| --- | --- |
| GRA1_01 | Volume meter does not move |
| GRA1_02; DSLY4_04, DSLY4_07, DSLY4_13, DSLY4_18 | Player reports insufficient track buffer |
| GRA1_05 and other GRA1 files in the report | Meter moves initially, then only peak line; keyboard continues moving |
| DSLY4_01, DSLY4_03, DSLY4_06, DSLY4_09, DSLY4_19, DSLY4_20 | Keyboard highlight only, reported static |
| DSLY4_08 | No moving display |

Do not reinterpret these reports as loss of audio, or infer a player-buffer
limit from the external compiler's separate 16-bit offset limit.

## Generated notation inspected

The renderer emits one sustained, tied note stream per used target channel.
Silence is represented by pan/volume control; there are no rests. It does not
infer musical attacks from PSG amplitude rises. Each snapshot repeats voice,
volume, pan, detune and octave setters, even when only one state value changed.
Long intervals are split into chunks of at most 256 MDX ticks and tied.

| File | MML characters | Note chunks | Ties | Rests | Volume range by used track | MDX bytes | Largest FM track bytes |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| DSLY4_01 | 34,183 | 1,318 | 1,315 | 0 | F/G/H: 0..106 | 16,000 | 5,415 |
| DSLY4_04 | 93,843 | 4,271 | 4,268 | 0 | F: 0..94; G/H: 0..90 | 43,183 | 20,865 |
| DSLY4_08 | 60,926 | 3,171 | 3,168 | 0 | F/G/H: 0..106 | 27,526 | 16,710 |
| GRA1_01 | 68,017 | 2,970 | 2,967 | 0 | F/H: 0..102; G: 0..106 | 31,071 | 12,882 |
| GRA1_02 | 79,232 | 3,484 | 3,481 | 0 | F/G: 0..102; H: 0..94 | 36,195 | 19,677 |
| GRA1_05 | 44,985 | 1,899 | 1,897 | 0 | F/G: 0..106 | 21,089 | 10,545 |

These six files each use two defined voices. Volume-setter counts equal
snapshot counts: 1,318 / 3,354 / 1,981 / 2,442 / 2,840 / 1,690 respectively.
Therefore a static meter is not evidence that the generated file lacks volume
changes. A note chunk is also not a new musical attack.

The complete 68-file notation inventory is in
`outputs/opm/diagnostics_2026-10-06/mdx_notation.csv`. It is a local artifact,
not a fixture or a reference score.

## What the public MMDSP code explains

Inspected primary sources (no code was copied into this project):

- [MADRV adapter](https://github.com/gaolay/MMDSP/blob/master/src/MACTRL.s),
  approximately lines 697..728: obtains KeyOn notifications from driver work
  fields, and velocity from current volume/LFO/fade work fields.
- [Level display](https://github.com/gaolay/MMDSP/blob/master/src/_LEVEL.s),
  `put_velocity` / `put_keyon`, approximately lines 363..403: volume updates
  change the peak marker, while an increased filled bar is refreshed through
  a new KeyOn notification; level decay is reset there.
- [Spectrum display](https://github.com/gaolay/MMDSP/blob/master/src/_SPEANA.s),
  approximately lines 496..520: new KeyOn notifications, keycodes and velocities
  feed the display bins. This is not a measurement of the output WAV spectrum.

The current continuous ties provide very few new KeyOns. The public code thus
explains why the filled bar can appear initially, decay away and subsequently
leave only a changing peak marker, despite ongoing audio and volume changes.
This is an evidence-based explanation for that particular observation. It is
not a reproduction of the user's installed MADRV build or a complete diagnosis
of every static keyboard/pan display.

## Could a small MDX adjustment help later?

Suppressing repeated identical setters is a reversible target compaction and
should be evaluated first if MDX work resumes. It could reduce player-buffer
pressure; it cannot by itself create the missing KeyOn notifications.

Replacing silent tied spans with rests, followed by actual notes, could create
musical/display attacks. That changes target Key edges and oscillator/envelope
phase, so it is not a cosmetic fix or a proven safe replacement for the held-key
plan. Arbitrary periodic KeyOns solely to animate MMDSP would be inappropriate.
A correct musical-note projection needs an inspectable distinction between
source-derived onsets and continuing parameter changes, with its own validation.

Conclusion: a modest compaction may improve capacity; a reliable display fix
requires musical onset semantics, not just fewer commands. No such change was
made. Remaining unexplained display cases require driver/work-area evidence if
the user later chooses to resume that investigation.
