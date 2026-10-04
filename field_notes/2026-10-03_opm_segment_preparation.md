# OPM input preparation

Initial review: 2026-10-03. OPM reader dispatch and native state Segments were
implemented on 2026-10-04. The user supplied public migrated fixtures.
This note retains the initial design proposal; current fields and limits are
documented in [OPM analysis](../docs/opm_segments.md), with results in
[native Segment validation](2026-10-04_opm_native_segments.md).

## Scope

The project centers on an independent Segment-based engine for obtaining
musical information for real sound hardware. OPM input is the next candidate;
MGSDRV composite voices, MS2 and TX802 are separate output decisions. The
mml2vgm compiler is only a potential external validation-data generator,
particularly for the otherwise missing YM2612 fixtures. No upstream compiler
code is to be incorporated.

## Sources and certainty

The VGM specification is the source for file commands and header flags.
Register meanings were cross-checked against the X16 project's YM2151
programming reference and the independent ymfm implementation. These are
implementation/developer references, not a newly obtained Yamaha datasheet.
A Yamaha manual scan located during research was inaccessible. No external
implementation was copied or translated into project code.

- [VGM specification](https://github.com/vgmrips/vgmplay-legacy/blob/master/VGMPlay/vgmspec171.txt)
- [X16 sound programming reference](https://github.com/X16Community/x16-docs/blob/master/X16%20Reference%20-%2011%20-%20Sound%20Programming.md)
- [ymfm OPM register reference](https://github.com/aaronsgiles/ymfm/blob/main/src/ymfm_opm.h)
- [ymfm OPM state handling](https://github.com/aaronsgiles/ymfm/blob/main/src/ymfm_opm.cpp)
- [ymfm envelope/key handling](https://github.com/aaronsgiles/ymfm/blob/main/src/ymfm_fm.ipp)

### VGM facts

YM2151 writes use command `0x54`; the second instance uses `0xA4` when the
dual-chip flag is present. The clock field is at `0x30`, with bit30 indicating
two instances and bit31 indicating YM2164 for applicable versions. Old
versions through 1.01 use the YM2413 clock field. Preserve the raw clock flags,
instance and variant instead of silently treating every stream as one YM2151.

Use existing `read_vgm_bytes` for gzip detection and `command_times` for the
global integer 44100 Hz sample clock. The existing timing iterator already
recognizes the lengths of both OPM commands. `parse_vgm` now dispatches their
payloads in that same stream loop. Do not create an independent wait-clock
implementation.

### Channel/operator register groups

OPM has eight channels and four operators per channel. Register groups:

| Address | Meaning |
|---|---|
| `08` | Channel selection and operator key mask |
| `20-27` | Left/right enable, feedback, algorithm |
| `28-2F` | KC |
| `30-37` | KF, upper six bits |
| `38-3F` | PMS, AMS |
| `40-5F` | DT1, MUL |
| `60-7F` | TL |
| `80-9F` | KS, AR |
| `A0-BF` | AM enable, D1R |
| `C0-DF` | DT2, D2R |
| `E0-FF` | D1L, RR |

Channel addresses use low three bits; operator register banks are spaced by
eight. Do not impose OPLL's FNUM, preset-instrument or single-volume model.

### Mapping and state traps

The operator register-bank order is M1, M2, C1, C2; key-control bits3..6 are
M1, C1, M2, C2. Store named operators or an explicit mapping, not an ambiguous
`op1..4` convention. Names denote hardware positions, not a guarantee that an
operator acts as a carrier under every algorithm.

KC is not a linear semitone code. Its low nibble uses
`0,1,2,4,5,6,8,9,A,C,D,E` for C-sharp through the following C. Keep raw KC and
KF bytes, including unused bits; decode the fraction separately. Do not lose
the upper-C octave distinction. Noncanonical encodings remain raw evidence;
their derived pitch needs a defined policy rather than rejection on sight.

AMD and PMD are independent values selected by bit7 of writes to `0x19`.
Keeping only the last byte at that address loses one depth. An emulator's
internal `0x1A` PMD shadow is not a source hardware register to invent in CSV.

Hardware key state is operator-specific. Repeated asserted key bits do not
by themselves imply a new attack. Preserve every source key write and derive
rising/falling masks from previous state; partial transitions must not restart
all four operators. Key-off indicates release, not proven acoustic silence.
Same-time writes can be sampled differently by an emulator or real chip:
record their order without claiming that every zero-duration pulse was heard.

## Proposed Segment contents (not finalized)

| Group | Candidate fields |
|---|---|
| Identity/evidence | segment_id, chip_instance, channel, source_event_id, command_address, register/data, change_kind |
| Native timing | vgmticks, vgmticks_end, same-time order, time; derived ticks/l for compatibility |
| Pitch | kc_raw, kf_raw, decoded KC/KF; optional derived note and base_frequency_hz |
| Key/continuity | key_mask, rising_mask, falling_mask, key-write evidence, continuity_id |
| Channel | algorithm, feedback, left_enabled, right_enabled, PMS, AMS |
| Each named operator | DT1, MUL, TL, KS, AR, AM_enable, D1R, DT2, D2R, D1L, RR |
| Shared effective state | LFO rate/wave/reset, AMD, PMD, noise enable/rate, CSM/timer state |
| Optional analysis | patch_state_id, later pattern_id/occurrence_id; no target voice assignment |

The proposed evidence field identifies the write causing this state boundary;
the raw event table retains all writes, including nonchanges. A patch ID is
an analysis identifier for a state snapshot, not an instrument number observed
in VGM. Keep effective operator parameters in Segment CSV so human review
does not require joining a separate patch table. Flatten them into named
columns; nested objects may still be useful inside Python.

There is no observed channel-wide scalar volume to fill with a guessed
0..15 value. Preserve all TL values. Any carrier-level summary is derived
analysis and cannot replace TL or algorithm state. Likewise, a derived base
frequency is not each operator's instantaneous frequency after DT, MUL and
LFO, nor the complete perceived pitch of the resulting FM sound.

Shared control writes should retain one global source event and the affected
channels' effective state. Noise is relevant to channel7 C2. Preserve timers,
CSM and test writes in trace; ordinary key-register edges alone cannot account
for timer-generated CSM attacks. Flag that interpretation as incomplete until
timer behavior is explicitly modeled, rather than report perfect coverage.

## Processing proposal

Follow OPLL's conceptual stages, not its target-coupled field layout:

```text
VGM -> ordered raw OPM writes -> reconstructed state trace
    -> source-timed Segments -> later note/phrase analysis -> target projection
```

1. Receive OPM commands in the existing `py/vgm_reader.py` stream loop, beside
   OPLL and SCC, as explicitly requested by the user. Reuse input/timing
   utilities and keep current eight-result `parse_vgm` callers compatible.
   Chip-specific state analysis will consume the resulting ordered trace;
   it must not introduce a separate VGM decoding loop.
2. Reconstruct chip-wide, channel and named-operator state. Distinguish
   unobserved initial values from observed writes and any assumed reset model.
3. Create intervals at relevant state transitions, with event identity retained
   for same-time transitions. Pitch/TL/patch/pan/LFO changes split state
   intervals without creating additional attacks.
4. Derive higher musical units from those intervals. Do not normalize timing,
   compress loops or map OPM patches to MSX voices during native decoding.

`OpmSegment` should be a chip-specific type. The current PSG/SCC base requires
tone-period and volume fields and is not a suitable forced parent. Sharing
source timing and evidence helpers is sufficient initially; no broad rewrite
of existing OPLL behavior is required.

## First validation checklist

Use synthetic, independently specified register sequences before public song
fixtures. Check partial keys and their operator mapping, repeated key writes,
same-sample off/on order, held-note KC/KF and TL changes, patch changes during
sustain, AMD/PMD interleaving, shared-control changes, noise, two instances,
nondefault clocks and final interval closure.

For public migrated fixtures, compare the ordered source writes with trace,
then check effective state reconstructed from Segments at each boundary.
Report source key writes, operator rising/falling counts and channel note
counts separately: OPLL's single-key count is not an interchangeable metric.
Before any source-to-source replay claim, clarify what is reconstructed from
Segments and what requires raw events. No audio fidelity or roundtrip result
has yet been measured.

## Implemented reader entry (2026-10-04)

The existing `parse_vgm` command loop dispatches `0x54` and `0xA4` to a raw
OPM collector. A nonzero declared OPM clock produces
`<stem>_trace.opm_regs.csv`. Commands for an absent chip or an undeclared second
instance are ignored according to the source header. Versions before 1.10
use the old shared clock location; dual/variant flags are interpreted from
1.51 onward.

CSV columns: `event_id,address,command,vgmticks,time,chip_instance,chip_type,
clock_hz,clock_raw,register,data`. Integers are decimal. `event_id` is the
zero-based ordinal of the command in the whole stream, including waits and
other chips, rather than an ordinal among OPM writes. Together with byte
address it preserves ordering even at the same sample. Repeated writes and
zero-time key pulses are retained, with no key/patch interpretation yet.
`vgmticks` is always present, independent of the legacy optional timing flag.

The eight returned PSG/SCC/OPLL paths are unchanged. Optional `opm_metadata`
receives the OPM CSV path, raw clock, effective clock, instance/variant facts,
write count and absolute source end in samples. `vgm2mml.py --dump-passes`
retains this trace; normal output still contains only the merged MML. No OPM
MML rendering is implemented, so this is input evidence support, not a claim
of OPM-to-MGSDRV conversion.

Validation: six new synthetic tests passed, including shared timing, same-time
write fidelity, AMD/PMD raw bytes, dual/variant and old-header handling, gzip,
unchanged eight legacy CSVs and main-CLI retention/cleanup. An emitted smoke
CSV was also inspected: three key writes shared sample735 in original order,
the second chip also used sample735, and two depth writes used sample743.
The timing, loop and SCC-header suites passed (18 tests), as did two input
tests. One input test failed on the obsolete GD3 expectation without the
space after `[SMS]`; the exact same failure was confirmed with the HEAD
reader. It is unrelated to this dispatch change and was left untouched.
No public OPM playback or Segment roundtrip has been tested yet.
