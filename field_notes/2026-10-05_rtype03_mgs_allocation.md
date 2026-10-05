# Rtype03 MGSC allocation failure (2026-10-05)

## Scope and evidence

Investigated the user's `RTYPESMS/Rtype03.vgm compile_failed` in
`outputs/mgs/local_only/opll/www.smspower.org/`. No reconversion, source/Segment
changes, compression changes, or full regression were performed. The user's
`proportional_allocations(..., total=16000)` edit is retained.

The current native MGSC log fails at `#alloc` with `Can't allocate`. The saved
`outputs/mgs/hierarchical_loop/opll/` result for this input already failed with
`Track buffer full` on channel 9. This saved comparison is not a previously
successful conversion becoming unsuccessful; its failure stage changed.

The current saved GF2SMS02 native log reports Compile complete / Save complete,
consistent with the user's successful 16000-pool test.

## Allocation failure versus track shortage

The current Rtype03 allocation totals 16000 bytes. Controlled diagnostic
compiles reproduce the failure using the existing mgsc-js 2.0.0 adapter,
which runs MGSC 1.11. Native WSL execution was unavailable to this session;
the saved native log provides the original failure evidence.

With the actual title and custom voice setup retained but music reduced to
one note, the same allocation still fails. Removing the custom voice setup
allows the 16000 allocation to compile, including with the actual title.
Thus this allocation failure does not depend on the long musical stream.

In successful setup probes, MGSC reports an additional track-0 allocation of
903 bytes, of which the one custom voice uses 10. The 16000 music pool excludes
this definition allocation. This illustrates why raising the music pool alone
is not universally safe. Do not interpret these fixture-specific measurements
as a documented universal memory limit or a safe replacement pool size.

Setup probes with music allocations totaling 15000, 15200 and 15300 compile.
The 15400 probe reaches compilation but fails saving with `Object too big`.
The 16000 probe fails earlier with `Can't allocate`. These probes contain only
one musical note and are not successful full-song conversions.

## Full-song channel measurements

For each channel, a diagnostic copy preserves all headers, custom voices,
macro definitions, and that channel's entire original musical stream. Other
channels' musical lines are omitted only in these isolated diagnostic copies.
The measured channel receives 15000 bytes; each other explicitly allocated
channel receives 1 byte and produces zero bytes. All six isolated compiles
succeed. The compiler's used-byte column gives:

| Channel | Current allocation | Compiled music bytes | Shortage |
| --- | ---: | ---: | ---: |
| 9 | 1475 | 1861 | 386 |
| a | 1135 | 1412 | 277 |
| b | 9017 | 12991 | 3974 |
| c | 361 | 398 | 37 |
| d | 3923 | 6210 | 2287 |
| e | 89 | 85 | 0 |
| Total | 16000 | 22957 | 6957 net |

These are independently measured full-channel byte counts, not a successful
combined MGS or an audio-equivalence verdict. They show that redistribution
within the current music pool cannot fit the unchanged full musical streams.
Lowering the b allocation sufficiently to pass allocation likewise exposes
`Track buffer full` on channel 9 in the full-song diagnostic.

The current allocator uses estimated MML size, not measured MGSC output size.
Its estimates differ substantially from this song's compiled channel sizes.
Allocation estimation and target compression are separate issues; increasing
the pool does not repair either one by itself.

## Next work and constraints

Rtype03 needs target compression improvements if it must compile in full.
Investigate the long b/d streams and reversible loop/macro expression before
changing source notes, Key edges, timing, or native Segments. No successful
manual `--alloc` workaround was found or claimed.

Local diagnostic MML/MGS/logs and probe scripts are retained at
`C:/Users/ef110/Documents/Codex/2026-09-25/co/tmp/rtype_alloc/` outside fixtures
and the repository. They are private generated material, not commit candidates.

Only this note and the handoff were added/updated for the investigation.
