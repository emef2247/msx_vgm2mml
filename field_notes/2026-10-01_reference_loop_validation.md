# Reference loops and generated-MGS roundtrip inspection

## Scope

Inspected the paired reference MML and exported VGM for sample, grider and
sx01v. gra2_001 was excluded at the user's request. This is a bounded validation
of the current note-unit work, not a change to the converter or loop matcher.

The question is whether repeated reference MML instructions survive export as
the same musical state trajectory. Relative-volume accumulation and last-pass
loop exits are separate cases; they must not obscure the ordinary repeat test.

## Observations

- sample reference line 20, tracks 9/a: the first four repetitions have the
  same native pitch, block, volume, sustain and instrument/voice identifier
  sequence, and the same relative tick intervals. Each repetition spans 120
  source ticks. Keyed intervals were checked against the source CSV as well
  as the suggested reference windows.
- sample line 22 repeats the same state sequence, but some boundaries differ
  by one tick in the second repetition. For example, a keyed interval starting
  at relative tick 90 in one repetition starts at 91 in the next. Equal adjacent
  states must also be coalesced for comparison: an extra register write can
  partition an otherwise unchanged state interval.
- grider line 69, rhythm track f: the first two repetitions match in state
  sequence and relative tick intervals.
- sx01v line 190, rhythm track f: its four repetitions match in state sequence
  and relative tick intervals under the declared reference-window mapping.
  Other windows include fractional tick lengths, exits and relative controls;
  a window mismatch alone is not evidence of a changed musical instruction.

These observations support using performed notes and state trajectories rather
than literal Segment row boundaries. They do not justify ignoring pitch,
volume or instrument differences. Nor do they prove every loop in every song
is identical: suggested time windows use an approximate first-note anchor.

## MGS to VGM to Segment

Reused the current generated MGS files, exported them with libkss-js, and parsed
the resulting VGM into OPLL/PSG/SCC Segment CSVs. No second MML conversion was
used for this comparison. All three generated MGS files compiled successfully.

| Input | Source KEYON | Exported KEYON | Count shortage | Count excess | Source positive keyed units | Exported positive keyed units |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sample | 609 | 604 | 5 | 0 | 604 | 603 |
| grider | 2596 | 2558 | 38 | 0 | 2558 | 2555 |
| sx01v | 1615 | 1604 | 11 | 0 | 1604 | 1603 |

KEYON shortages/excesses are summed per-channel inventory differences, not
time-matched missing/added event counts. Positive keyed units are continuous
keyed periods delimited by observed key edges, not individual Segment rows.
The sources also contain respectively 5, 38 and 11 zero-duration keyed units;
the exports contain 1, 3 and 1. Thus it would be incorrect to claim that every
count shortage represents a lost audible note, or that all positive intervals
were preserved exactly. The five positive-unit shortages have source duration
one tick. Their absence from this inventory does not by itself identify a
lost attack: the exported state may instead occupy zero ticks.

A first-positive-state comparison also found isolated initial pitch/volume
differences. This compares only the first retained positive state per keyed
unit; it is not a complete pitch/volume trajectory or acoustic quality verdict.
These details are retained in the local report for further inspection rather
than converted into a score or used to change rendering in this task.

## Artifacts and limitations

Local outputs are under `outputs/reference-loop-audit` in the Codex workspace,
outside the source fixture tree. Each song has a loop-window CSV with reference
MML line numbers, source CSV lines, state sequences and relative intervals,
plus actual exported Segment CSVs. `note_inventory.json` and
`note_sequence_differences.json` describe the roundtrip inventory.

`scripts/audit_reference_loop_windows.py` is intentionally a bounded fixture
audit parser. MGSC remains the authority for compilation. Its window mapping
assumes nominal 60 Hz and anchors the first audible note/first rhythm trigger;
it is not an exact mapping between MML commands and VGM byte addresses. Window
mismatches require inspecting actual attacks and boundaries. The audit does not
certify complete user-patch bytes, PSG noise/envelope equivalence or WAV identity.
Native dumps remain unchanged. No timing tolerance or relaxed equality has been
introduced into production loop compression.
