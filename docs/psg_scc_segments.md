# PSG / SCC Segment pipeline

The register-oriented converter now follows:

```text
VGM
  -> vgm_reader.parse_vgm: chip log / chronological trace CSV
  -> psg.build_segments / scc.build_segments: existing PASS0-3 analysis
  -> PsgSegment / SccSegment (before target repeat compression)
  -> psg_mml.write_psg_mml / scc_mml.write_scc_mml
  -> MGSDRV MML variants and merged MML
```

`process_psg_csv` and `process_scc_csv` retain their existing signatures and
return paths. The CLI options and MML filenames remain compatible.

## Inspecting a conversion

```sh
python vgm2mml.py input.vgm --outdir outputs/check --dump-passes
```

This keeps the parser's event log/trace CSVs, the existing PASS0-3 CSVs, and adds:

- `<stem>.psg.segments.csv`
- `<stem>.scc.segments.csv`
- `<stem>.scc.waveforms.csv` (waveform ID and all 32 bytes as hex)

`--debug` additionally keeps all MML variants, as before. Without either option,
temporary source log/trace CSVs are still cleaned up. Parser CSVs represent the
existing reconstructed chip events, not a new lossless dump of every VGM opcode.

## Segment semantics

The OPLL pipeline is the architectural example, not a universal chip schema.
PSG and SCC have their own dataclasses rather than populating OPLL-only fields
with invented values. This change does not alter OPLL analysis or grid conversion.

Common fields:

| Field | Meaning |
| --- | --- |
| `ev_type`, `time`, `ch` | Analyzed event type, source CSV timestamp in seconds, zero-based source channel |
| `ticks`, `l` | Existing PASS start tick and interpreted duration; retain the existing `get_ticks` convention |
| `tick_start`, `tick_end` | Convenience view of `ticks` and `ticks + l`; no additional quantization |
| `tone_period` | Source-derived period counter; not Hz |
| `volume` | Existing interpreted 0-15 volume |
| `octave`, `scale` | Existing pitch/rest interpretation retained from PASS analysis |
| `volume_delta` | Existing PASS volume difference, including its look-ahead semantics |
| `pass3_row` | Exact analyzed row as an immutable tuple; dumped as a quoted JSON array |

These are intervals/state changes produced by the existing interpretation, not
newly inferred full note-on/note-off objects. Zero-length rows are retained where
the existing passes retain them. The source `time` is the parser's CSV time, which
may be relative to the chip's first write rather than absolute VGM time.
In particular, SCC PASS2 can attach dropped waveform-event durations to another
row. Consequently `tick_end` is the interpreted end (`ticks + l`), not a claim
about an independently observed source key-off. Raw source evidence remains in
the log/trace and PASS CSVs.

PSG adds `mode`, `mixer`, `noise_period`, `amplitude_register`, and hardware
envelope enabled/period/shape. `envelope_period` is the original 16-bit register
period. The legacy `int(143.03493 * period)` MGSDRV conversion occurs only in the
renderer, not in this field.

SCC adds `enabled`, `enable_register`, `previous_tone_period`,
`volume_run_count`, `waveform_id`, and `waveform_hex`. `SccAnalysis` carries the
entire waveform bank, including definitions not selected by a sounding Segment.
An unavailable waveform is represented by an empty hex string; no waveform is
invented. `pass3_row` also preserves the existing envelope-analysis columns.

Segments are frozen. MML repeat compression produces separate
`(Segment, repeat_count)` pairs and never modifies or removes entries from the
analysis result. Renderers use named fields only, not `pass3_row`. Keeping the
legacy row provides a lossless migration boundary for fields whose full semantics
have not yet been redesigned; it is not a replacement for source event CSVs.

## Programmatic use

With `py/` on the Python import path:

```python
from psg import build_segments
from psg_mml import write_psg_mml

segments = build_segments('song_trace.psg.csv', 'outputs/check', stem='song')
write_psg_mml(segments, 'outputs/check', 'song')
```

The SCC equivalent returns an `SccAnalysis` carrying `segments` and `waveforms`;
pass that object to `write_scc_mml`.

## Validation and limits

```sh
python -m unittest discover -s tests -v
```

The regression manifest records output hashes from base commit
`6b9d5656781da9e8379df5ec6aa76e2404dd10a3` with only SCC header detection corrected
(offset 0x9C, header-boundary check, clock-flag masking). The reference does not
include the Segment refactor. See `reference_correction` in the manifest. It covers all 41 public VGMs in
standard and raw-tick modes, including all debug MML and existing intermediate
files. These hashes characterize existing behavior, not a proof of sound-chip
or MGSDRV correctness. Do not regenerate them merely to accept a mismatch.

Correction: the original converter read 0xCC (ES5503 clock) as K051649,
silently skipping valid SCC commands. The correct K051649/K052539 field is
0x9C-0x9F, a little-endian 32-bit value with chip flags in the high bits.
Of the 13 current public SCC VGMs, 12 contain 1789773 Hz there; only
`short_pulses` contains zero. The previous claim that all 13 have zero SCC clock
was incorrect and resulted from trusting the erroneous implementation.

Tests run all unmodified fixtures and also explicit temporary copies with
0x9C set to 1789773 Hz in trace/log and standard/raw-tick modes. Originals are
not rewritten. Independent header tests check that 0x9C enables SCC, 0xCC does
not, short extended headers work, and flags alone do not declare a clock.
An integration test verifies SCC notes in merged MML from an unmodified VGM.

Specification: https://raw.githubusercontent.com/vgmrips/vgmplay-legacy/master/VGMPlay/vgmspec171.txt

Unit checks cover PSG noise/envelope and zero-length events, SCC waveforms,
rendering without legacy rows, immutable repeat projection, and diagnostic-file
retention. Hardware playback, private fixtures, and WSL execution are not part
of these checks. This refactor deliberately preserves existing note-boundary,
waveform reconstruction, volume and timing heuristics; fixing their known or
suspected limitations is separate work.
