# Definition storage and actual MGS playback

Generated setup data needs its own MGSC allocation (`#alloc 0`). The estimate
includes generated PSG tuning tables, SCC waveforms, software envelopes and OPLL
user voices. It also reserves one terminating byte for the nonempty definition
stream. An empty stream does not create an allocation just for a terminator.
The fixed 16,000-byte shared allocation budget includes this reservation; music
track shares decrease accordingly. Native source Segments and target note timing
are unaffected.

The local MGSC 1.11/libkss reproduction established a playback failure that
compilation alone did not detect:

- A generated 84-byte setup allocation compiled successfully but produced no OPLL
  Key-On events. Increasing that allocation to 85 while reducing a music track
  by one byte restored playback without increasing the total budget.
- The resulting MGS files had the same packed size. Their only differing byte
  in the controlled probe was at offset 152: `2c` in the broken file versus `ff`
  in the working file, the definition-stream terminator.
- Separate PSG tuning, software-envelope and OPLL user-voice cases reproduced
  the missing termination; some other definition estimates already had slack.

This is observed behavior of the available compiler/player. The compiler source
revision is not available locally. Individual body-size estimates remain
conservative implementation estimates, not a formal specification for every
MGSC release or arbitrary hand-written definition syntax.

## Regression checks

`tests/script/test_mgs_playback.py` compiles and actually plays generated MGS through
MGSC/libkss. It checks nonempty definition classes individually and together,
expected note counts/intervals, and the ordinary public OPLL export path. It also
reproduces the old successful-compile/zero-Key-On case and verifies its repair.
`probe_mgs_audio.mjs` measures rendered PCM peak/RMS/nonzero sample counts from
an already compiled MGS; a positive compile result is not its soundness oracle.

```sh
python -m unittest discover -s tests/script -p test_mgs_playback.py -v
node scripts/probe_mgs_audio.mjs song.mgs audio.json 5000
```

Actual-playback tests explicitly skip when the optional compiler/runtime is
unavailable. Such a skip is not playback validation.

## Batch comparison results

Compilation and roundtrip verification remain separate. A compiled output can
retain `status=success` but receive `keyon_status=mismatch` if melodic OPLL
Key-On counts differ. Export then exits unsuccessfully and prints the shortages
and excesses. `compared` means the checked counts match; it does not prove timing,
pitch, volume, patch, rhythm or audio equivalence. `--skip-keyon-counts` explicitly
omits this check. `--enhance-drums` does not affect definition termination rules.
