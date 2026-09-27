# Current handoff

Date: 2026-09-27
Status: ready to resume

## Last completed
- Added --sync-min-gap (default 700 target-MML steps, 0 for all shared points).
  Select the first shared boundary at least that far from the previous marker;
  start and final end are always retained. No note splitting or retiming.
- Fixed blank-line accumulation when sync annotation extracts track bodies:
  final header now keeps at most one blank separator. Regenerated outputs/check/giselle.mml;
  all nonblank lines (including music and sync comments) match the previous output.
- Added shared step comments to final merged MML via py/mml_sync.py. Common
  boundaries are calculated across all still-playing channels in target MML time.
- Preserved expanded note/command timelines; loops crossing a marker are expanded
  only as needed. Event/PASS/Segment generation remains unchanged.
- Verified all 20 existing/current unittest methods (including 134 conversion
  scenarios), then all 10 sync tests after adding a two-mode mixed-VGM CLI test.
- Verified all 12 mixed public VGMs in standard and raw modes (24 conversions).
- Documented sync semantics and time units in docs/mml_sync.md.
- Refactored PSG/SCC into event CSV -> analysis -> immutable chip-specific Segment -> MML.
- Added py/psg.py, py/scc.py and py/chip_segments.py; renderers consume named fields.
- Retained PASS0-3 and added Segment/waveform CSVs. --dump-passes now keeps input event CSVs.
- Initial 134-case comparison preserved an existing SCC-header bug. Corrected
  the clock offset from 0xCC (ES5503) to 0x9C (K051649), added header-boundary
  checking and clock-flag masking. Regression expectations now come from the
  old non-Segment converter plus only that header fix.
- Verified SCC note output from an unmodified public VGM; header tests added.
- Header correction validation: all 11 unittest methods passed, including 134
  conversion scenarios against the header-corrected pre-refactor reference.
- Inspected PSG zero-length/envelope fields and SCC waveform/Segment CSVs.
- Documented the architecture and preserved legacy heuristics in docs/psg_scc_segments.md.

## Unfinished
- No required implementation remains for automatic shared sync comments.
- Private gra2_002 converted successfully but differs from its expected MML:
  current SCC processing has four channels; the expected file uses five. Envelope
  output and duration differences also remain. Do not treat conversion success
  or sync annotation as proof that this fixture matches its expected output.
- Hardware playback and WSL execution have not been checked.
- Changes are local and uncommitted; existing user-generated/untracked data was left intact.

## Next allowed action
- Review the local diff and run `python -m unittest discover -s tests -v`.
- Treat any changes to timing, waveform reconstruction or note-boundary heuristics as separate work.

## Do not do next
- Do not discard event/PASS evidence or replace chip-specific fields with OPLL defaults.
- Do not mistake 0xCC for SCC or infer valid conversion from old-output equality alone.
- Do not overwrite private fixtures or regenerate regression hashes to hide a mismatch.
