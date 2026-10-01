# VGM loop-position decoding: bounded implementation plan

The user prefers the simple eseopl3patcher approach: compare the current
source-command address with the declared loop address before decoding the
command. No repetition discovery or loop unrolling is needed to locate it.

Current py/vgm_reader.py does not read the loop fields. Its existing pos cursor
can perform this comparison without changing chip writes or inserting attacks.

Header facts:

- 0x1C contains a relative loop offset. Zero means no declared loop.
- A nonzero value identifies absolute address 0x1C + relative_offset.
- 0x20 contains the declared loop sample count.

Primary implementation reference: libvgm/player/vgmplayer.cpp uses
ReadRelOfs(_hdrBuffer, 0x1C), whose helper adds the field address to a nonzero
offset:
https://github.com/ValleyBell/libvgm/blob/master/player/vgmplayer.cpp

The local eseopl3patcher main.c currently adds 0x04 to the value read at 0x1C.
Adopt its address-comparison algorithm, but do not copy that arithmetic or its
0xFFFFFFFF sentinel as the VGM header's no-loop convention.

First implementation scope proposed (not implemented in this review):

1. Decode the header offset and compare pos before consuming each command.
2. Retain the source loop address and observed loop-start sample/time, alongside
   declared loop samples; preserve the decoded chip state at the boundary.
3. Expose the boundary through dump metadata, then annotate Segment CSVs without
   turning the marker into a key-on or resetting a continuous note.
4. Handle MML loop notation separately after inspecting these intermediates.

Validation should cover no loop, a loop at data start, a loop on a wait command,
and invalid/non-command offsets. Unsupported commands must not be mistaken for
one-byte commands when determining a real command boundary. The current reader
does skip unsupported commands one byte at a time; that limits boundary claims.

The reader also has legacy zero-wait handling for 0x77/0x7A. Native source-sample
metadata must remain distinguishable from that compatibility timeline; do not
silently present legacy trace time as the exact VGM sample position.

No conversion behavior or loop emission changed during this planning review.

Implementation update: read-only loop metadata inspection and optional CSV dumps are implemented; see docs/vgm_loop.md. Segment annotations and MML loop emission remain future work. The source-boundary inspector has its own command-length cursor to avoid changing legacy trace decoding.
