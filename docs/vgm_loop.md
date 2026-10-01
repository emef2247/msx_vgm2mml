# Declared VGM loop metadata

The first implementation records the VGM header's loop boundary. It does not
infer repetitions, replay the stream, reset registers or emit infinite MML loops.
Existing conversion traces and Segment interpretation remain unchanged.

With `--dump-passes` or `--debug`, `<stem>.vgm.loop.csv` contains one row:

- `loop_offset`: raw unsigned relative value at header offset 0x1C; zero means no loop.
- `loop_address`: absolute source byte address, 0x1C + nonzero offset.
- `header_loop_samples`: declared sample count at 0x20.
- `status`: `no_loop`, `valid`, or a reason inspection could not validate the stream.
- `loop_start_samples`, `loop_start_seconds`: source time before consuming the loop command.
- `loop_start_trace_seconds`: global compatibility wait clock, not chip-relative
  CSV time. Legacy 0x77/0x7A waits count zero here; source samples retain them.
- `decoded_end_samples`, `decoded_loop_samples`: observed duration through 0x66;
  these may differ from the declared header count.

The address comparison happens before consuming each command, including waits.
A loop in a command operand or data-block payload is rejected as `inside_command`.
Unsupported or truncated commands stop inspection rather than inventing a boundary.
If inspection stops after finding the start, retain its observed time but do not
claim a validated loop (`status` changes to the failure reason).

A separate read-only cursor checks command lengths because the legacy trace
decoder skips some unsupported commands as single bytes. Changing that trace
decoder is outside this patch. Metadata validation does not certify the accuracy
of unrelated-chip traces. The compatibility clock is a wait sum; it cannot fix
misdecoded payloads in those traces. Standard source waits, including stream/DAC
waits and wait overrides, are counted for source metadata only.

Normal conversion still emits only `<stem>.mml`. The eight-path `parse_vgm`
return tuple is unchanged; callers can request metadata via the optional
`loop_metadata` dictionary and `dump_loop=True` keyword arguments.

Next stage: annotate boundaries in Segment CSVs, including a marker falling
inside a sustained note, before implementing target-specific MML loop handling.
Do not synthesize a KEYON merely because playback has a declared loop boundary.
