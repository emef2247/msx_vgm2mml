# Native OPM analysis

OPM/YM2151 input follows the existing `py/vgm_reader.py` command loop:

```text
VGM -> ordered raw OPM writes -> effective channel/operator state -> OpmSegment
```

`py/opm.py` performs state interpretation after source decoding. It does not
have a separate VGM parser and does not import a target renderer. OPM patches
are not converted to OPLL, PSG or SCC voices yet. MGSDRV MML generation remains
limited to the existing source chips.

## Generate inspectable CSVs

From the repository root:

```bash
python py/vgm_reader.py \
  tests/fixtures/public/opm/from_fm/legato_patch_mix/legato_patch_mix.vgm \
  outputs/opm/from_fm/legato_patch_mix
```

The reader writes its existing chip CSVs plus these OPM artifacts:

| File | Meaning |
|---|---|
| `<stem>_trace.opm_regs.csv` | Every accepted OPM write, in source order, with ch and register_scope |
| `<stem>_trace.opm.csv` | Effective state after every write, including nonchanges |
| `<stem>.opm.segments.csv` | State intervals with exact start/end samples |

`vgm2mml.py --dump-passes` and `--debug` also retain this OPM analysis when an
OPM clock is declared. This does not make an OPM-only input produce playable
MGSDRV MML: use the reader command above for native OPM inspection.

Programmatic callers keep the eight existing `parse_vgm` return paths. Pass
`opm_metadata={}` and `dump_opm_segments=True` to obtain the additional paths,
clock facts, source end and Key counts. `opm.build_segments(trace_csv,
end_vgmticks=...)` requires the real VGM end; using the final register write
as the end would lose the last sustained/released interval.

## Timing and source evidence

One `vgmtick` is one 44100 Hz sample. `vgmticks` and `vgmticks_end` are absolute
and share the existing source origin with all chips. `duration_samples` is
their difference. No conversion to 60 Hz, musical normalization, loop
compression or target allocation occurs here. `time` is a derived value in
seconds and is not used to recover integer boundaries.

`source_event_id` is the zero-based ordinal among all VGM commands, including
other chips and waits. `address`, `command`, `register` and `data` retain the
write causing an interval. CSV integers are decimal. Initial intervals use
blank source identifiers because they are assumptions, not source writes.
State CSV remains in source order; Segment CSV is grouped by instance/channel,
then sample and `segment_id`, so same-time changes keep their original order.

Changed state splits an interval. Repeated unchanged writes stay in raw/state
CSV, without creating spurious attacks. Test and timer-control writes also
preserve interval boundaries because their side effects cannot be represented
only by a register's final value. Same-time transitions produce zero-duration
Segments and are retained; they are not invented musical notes or proof of
audible pulses.

## Register channel ownership

Raw trace rows now include `ch` and `register_scope`. Key register 0x08 derives
its channel from data bits 0..2. Channel and operator registers derive it from
register bits 0..2. Noise register 0x0f belongs to ch7. Other low-register
controls are chip-wide: `ch` is blank, with `register_scope=shared`.
The other scopes are `key`, `noise`, `channel` and `operator`.

A shared source write remains one raw row and updates the effective shared
state in each channel snapshot. Native Key state, pitch, pan, modulation
sensitivity and four-operator state remain independent per chip/channel.
Noise changes split only ch7's intervals; they no longer create unrelated
noise transitions on ch0..6. Its register still appears in ch7's raw snapshot.
No separate patch lookup is required to understand a Segment's current state.

When a raw CSV contains the new `ch` column, the native builder validates it
against the register/data address. Older traces lacking this column remain
readable, deriving ownership from register/data rather than guessing a channel.

## Native fields

Each Segment contains the complete effective channel and shared state;
reviewing a patch does not require joining a separate table:

- Raw KC/KF, decoded KF and canonical KC note/octave. Noncanonical KC codes
  remain raw evidence with blank derived note/octave.
- Algorithm, feedback, left/right enables, PMS and AMS.
- Four named operators `m1`, `m2`, `c1`, `c2`, each with DT1, MUL, TL, KS, AR,
  AM enable, D1R, DT2, D2R, D1L and RR. CSV columns use names such as `m1_tl`.
- Shared LFO/test/timer controls, separately latched AMD and PMD, and
  CT/LFO waveform selection. Noise state is present only on ch7.
- Raw channel and shared register snapshots as quoted JSON arrays, preserving
  unused bits and writes whose semantics have not been modeled.

Unwritten parameters are `None` in Python and blank in CSV. No assumed patch
or volume is silently substituted. Gates initially start cleared, with
`key_reset_assumed=True` and `key_observed=False` until that channel receives a
Key write. The reset baseline is explicit; a recording beginning mid-note
cannot reveal its prior internal state.

`key_mask`, `rising_mask` and `falling_mask` use the four Key register bits
shifted down by three: M1=1, C1=2, M2=4, C2=8. This differs from register-bank
order M1/M2/C1/C2. Named `*_key_on`, `*_key_on_edge` and `*_key_off_edge`
columns make both orders inspectable. `continuity_id` increments when at least
one operator has a rising edge; a partial edge does not assert that every
operator or the whole acoustic note restarted. These register/key meanings
follow the [X16 YM2151 reference](https://github.com/X16Community/x16-docs/blob/master/X16%20Reference%20-%2011%20-%20Sound%20Programming.md).

`gate_state=released` describes cleared gates, not a silent rest. Key-off
does not erase a release envelope. Effective frequency in Hz, internal
envelope level, acoustic silence, LFO phase, timer expiry and CSM-generated
attacks are not yet simulated. `csm_enabled` preserves control state and
`csm_edges_modeled=False` makes this limitation explicit. There is no invented
channel-wide scalar volume or OPLL-like FNUM/BLOCK.

## Validation and fixture limits

Run:

```bash
python -m unittest discover -s tests -p 'test_opm*.py' -v
```

Synthetic tests cover multiple channels/instances, partial keys, operator
mapping, redundant writes, zero-time off/on, held-note parameter changes,
independent modulation depths, shared controls, unknown values and ordering.
The public fixture test checks all 16 retained migrated patterns against their actual
OPM source commands, not against the pre-conversion OPLL MML. The checked-in
reference MML is context for the original composition, not an OPM oracle.

These migrated inputs currently exercise Key writes only on OPM channel0.
Three migrated `rhythm_only_test0*` cases had no OPM Key writes and were
removed at the user's request: vgm-conv did not convert their rhythm data. Native noise,
partial-Key and multi-instance tests require synthetic cases or later native
OPM fixtures. No OPM audio roundtrip is claimed by the state/edge checks.


## Original MDX/MML public fixtures

`tests/fixtures/public/opm/from_mdx/` adds nine newly authored synthetic
cases with matching MDX MML, compiled MDX and generated OPM VGM. They fill
the migrated set's multi-channel, partial-Key, held-control, hardware LFO,
channel-7 noise and register-bank gaps. A finite nested-loop example and
same-sample/release retriggers are also included. The case README records
provenance, licensing, expectations and regeneration commands.

The native fixture tests assert authored attack counts and actual raw
source evidence independently of musical quantization or target rendering.
The generator is a development-only external Rust utility; neither Rust,
mmlx nor soundlog is needed to run the Python reader or committed-fixture
tests. The separate [MDX target](opm_mdx.md) now reuses these source patterns
for Segment -> MDX MML register controls -> MDX -> VGM -> Segment validation.
Ordinary note/voice notation is now available in the separate MDX target;
acoustic equivalence remains outside these native-state tests.

## Integrated CSV inspection

All channels remain together in the existing state/Segment CSVs. Every row
retains the complete effective channel/operator and shared state, so sorting
by ch or absolute `vgmticks` is sufficient for inspection. No separate stream
CSV or channel CSV is produced. Appended `stream_scope`, `target_ch`,
`logical_track` and `event_role` are ownership labels only; they do not split
or rebuild the confirmed native Segment engine. Logical track labels are not
MDX playback tracks. Shared state remains visible on the channel snapshots.

The separate Segment-to-MDX structural stage appends `opm_phrase_unit_id` and
`opm_source_loop_path` to the same Segment CSV when its dumps are requested.
Source-loop paths include phrase/Segment level, pattern/occurrence/parent IDs,
depth and repeat position. Existing cells/intervals are unchanged. Target
unit/voice IDs and boundary-mapping status are also appended for projection
inspection. Source candidate detection and emitted MDX brackets are distinct.
See [MDX output](opm_mdx.md) for that later stage.
