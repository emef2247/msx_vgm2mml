# gra2_005: Segment validation after removing loop-depth caps

## Scope

Input: optional local fixture
`tests/fixtures/local_only/psg_scc/msxplay.com/gra2_msx/gra2_005/gra2_005.vgm`.
Compared legacy performed compression with explicit depth2, explicit depth6,
and unrestricted depth, plus the current default structural conversion.
All use enhanced macros, `--dump-passes --vgmticks`, and no normalization.
Only the legacy depth changes within the three legacy runs; their envelope
order and all other options remain identical. The default run has its own
source-loop-first envelope bank, so its smaller size is not a depth-removal gain.

## Results

| Variant | MML characters | Maximum applied performed depth | MGSC1.11 |
| --- | ---: | ---: | --- |
| Legacy depth2 | 8749 | 2 | Success |
| Legacy depth6 | 8749 | 2 | Success |
| Legacy unrestricted | 8749 | 2 | Success |
| Default structural | 8313 | Not used | Success |

- Each run retains 5029 PSG and10369 SCC Segment rows. Every native dataclass
  field, including source time/sample bounds, tone period, volume, chip state,
  waveform evidence and the original pass row, agrees across all four runs.
  Derived tick start/end fields also agree. Target annotations are not included
  in this source comparison because their representation may legitimately differ.
- All14 trace/pass CSV files are byte-identical across the four runs.
- Each final MML agrees with its own Segment-derived effective state at every
  60Hz tick: pitch name/octave, volume, PSG mode/noise/hardware-envelope
  configuration, SCC waveform ID and silence. All four state timelines agree.
- Before/after target loop projection expands to identical timed command
  sequences for both PSG and SCC, in every run. This checks retained controls
  and ties as well as effective sounding states.
- The three legacy final MML files are byte-identical. Each invokes the
  performed compressor six times, so the changed code path was actually tested.
  This input produces no applied legacy nesting beyond two levels.
- Default structural final MML is byte-identical to the earlier gra2_005
  structural benchmark. It never calls the legacy performed compressor.
- All four outputs compile using MGSC1.11 via mgsc-js without buffer errors.

This is a source/target-state and command-expansion check, not an audio or
MGS-to-VGM roundtrip. It establishes no sample-exact waveform equivalence.
For this fixture, removing the depth cap changes neither source Segments nor
the legacy generated MML; unrestricted deeper-loop behavior is covered by
the separate seven-level synthetic regressions.

## Local artifacts

Codex workspace `outputs/gra2-unrestricted-depth/comparison.json` records the
four runs. Each variant directory retains conversion/compiler logs, traces,
pass/Segment CSVs, projection dumps, final MML and MGS. The local runner is
`check_gra2_unrestricted_depth.py`. No fixture input was modified.
