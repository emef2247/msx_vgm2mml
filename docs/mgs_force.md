# Scoped forced MGSDRV projection

`vgm2mml.py` and `scripts/batch_vgm_to_mgs.py` accept `--force` for the MGS
target. A validated source-command inventory precedes target rendering. Clock
fields alone do not indicate active unsupported source material. Existing
undeclared, muted SCC initialization compatibility remains separate from a
forced omission.

The current finite omission list covers register writes for OPM, OPNA, DCSG,
MSM6258, SegaPCM and a second OPLL instance. Strict conversion rejects these
unrepresented writes; `--force` permits their omission while converting the
remaining primary AY/PSG, SCC and OPLL material. No supported source writes
remaining is an error rather than a successful empty song.

This is a target projection loss; the input VGM and native source evidence are
not rewritten. It is not a new chip converter. The flag does not grant permission
to ignore malformed/unknown commands, invalid loop offsets, unsupported
AY/SCC variants or test controls, PCM data blocks/transfers/DAC stream controls,
compiler source/track buffer limits or timeouts. Those remain explicit failures.
Unsupported native-decoder variants require their own source implementation;
removing a guard is not such an implementation.

Every attempted inventory emits:

- `<stem>.mgs.source.json`: command offsets, original sample times, header facts,
  usage counts and validation/projection decisions.
- `<stem>.mgs.force.json`: enabled state, omissions, blockers and CSV location.
- `<stem>.mgs.force.csv`: one row per applied omission, including source command,
  byte offset, sample time, chip/instance, port/register/data, action and reason.

Console output identifies the omitted-write count and details path when force
is requested. Batch reports retain the same records separately from conversion,
compilation and optional key-on comparison results. Empty applied-omission lists
are not proof all source semantics have been acoustically reproduced.

```sh
python scripts/batch_vgm_to_mgs.py INPUT_DIR --outdir outputs/mgs --force
```

See [batch diagnostics](batch_mgs.md) and [optional normalization](note_normalization.md).
