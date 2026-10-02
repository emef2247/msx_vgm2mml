# Shared VGM source timing

All chips share sample zero at the start of the VGM command stream. The reader
accumulates integer wait samples and derives `time = samples / 44100`. It does
not subtract the time of each chip's first write. All waits count, including
0x77/0x7A, 0x80-0x8F and 0x64 wait overrides. Command payloads are skipped by
their declared lengths. Unknown/truncated commands fail instead of guessing.

The existing `ticks` field remains the derived 60 Hz value. It is not raw VGM
timing. Add `--vgmticks --dump-passes` to retain integer source evidence:

```sh
python vgm2mml.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm --outdir outputs/sample-vgmticks --dump-passes --vgmticks
```

Trace/pass/Segment CSVs carry `vgmticks` (absolute start sample); Segment and
interval pass CSVs also carry `vgmticks_end`. This end is the next contributing
source event boundary, not a synthesized musical gate or rhythm-hit length.
Terminal rows have an equal start/end. Multiple writes at the same sample
remain ordered. Old CSVs without these fields yield `None`; samples are never
reconstructed from rounded `time` or `ticks`. The command-level
`<stem>.vgm.timing.csv` retains addresses, commands, samples and wait lengths.

The shared clock correction applies with or without `--vgmticks`; that option
only adds evidence. It does not enable musical duration normalization. Files
previously affected by chip-relative origins or uncounted waits may produce
different timing because those bugs are corrected.

## Reference repetition audit

```sh
python scripts/compare_reference_vgmticks.py tests/fixtures/public/psg_opll/msxplay.com/sample/reference/sample.mml --segments outputs/sample-vgmticks/sample.opll.segments.csv --outdir outputs/sample-vgmticks/comparison
```

The audit expands reference loops, verifies note-order/pitch correspondence,
then compares source onset offsets, gate lengths, IOIs and register trajectories
between complete repetitions. It reports values separately, without a score.
Unclosed EOF notes and structurally different last-pass exits are excluded from
full repetition comparisons. Reference macros are not supported by this audit.

For OPLL pitch alignment only, one-sample FNUM intermediate states are ignored;
the raw trajectories retain them. An additional stable-state view ignores states
up to 44 samples; it never replaces the raw comparison. Rhythm alignment checks
instrument/volume groups. The sample PSG audit uses volume-reset candidates for
its decreasing software envelopes, verified against a shared clock inferred
from OPLL. This is a fixture-specific alignment method, not a general PSG KEYON
rule or production transformation.

Integer samples eliminate accumulation/rounding ambiguity, not real source
timing variation. A tolerant musical loop decision remains a separate stage.
