# OPLL rhythm Segment inspection

Run the usual converter with `--dump-passes`. The additional
`<stem>.opll.segments.csv` records all native Segment fields before target
voice assignment. Existing trace files and `.opll.pass0.csv` are preserved.
This change does not add rhythm MML or change segmentation.

Channels 9, 10, 11, 12 and 13 identify BD, SD, TOM, CYM (`tc`) and HH.
These are internal channels, not target MML track identifiers.

- `time` is the source event time in seconds; `ticks`, `tick_start` and
  `tick_end` use the existing 60 Hz analysis clock.
- For `rhythm_expand`, `keyon` is the rising-edge result for that channel.
  The five `bd/sd/tom/tc/hh` fields retain source flags, not five independent
  triggers. Only the instrument associated with the channel is emitted.
- PASS4 also contains non-trigger rows; rhythm Segment construction retains
  rhythm-mode-enabled rows with `keyon=1`.
- `tick_end` records the existing analysis interval, not measured acoustic
  decay. `vol` is native OPLL attenuation. Raw FNUM/BLOCK and channel state
  remain available; no common frequency/pan schema is introduced here.
- Unset native attributes are blank. Target voice identifiers have not yet
  been assigned in this dump.

`tests/test_opll_rhythm.py` compares freshly generated trace/register CSVs
and PASS1-4 against optional `reference/vgm2tx802` files. It also compares
the exported rhythm Segment timing, keyon, pitch registers, volume and flags
with reference PASS4 trigger rows. Missing reference fixtures are skipped.
Local-only fixture contents must not be committed.

Synthetic tests independently check held bits, same-tick off/on edges,
simultaneous instruments and volume-only writes at the expansion stage.
These do not establish full-pipeline behavior for every synthetic edge case,
mode transition or acoustic release. Reference parity likewise does not prove
the reference converter handles every chip behavior correctly.

Next stages are complete-pipeline edge-case coverage, explicit state/trigger
separation for a shared schema, and finally MGSDRV rhythm rendering.
