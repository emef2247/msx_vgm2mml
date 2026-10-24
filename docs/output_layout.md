# MGS export package layout

Both `scripts/batch_vgm_to_mgs.py` and `scripts/export_mgs.py` use this layout.
Each original input parent directory becomes a package, retaining its path
relative to INDIR. Final listening/editable files are directly in `tracks/`;
there is no `tracks/<stem>/` directory.

```text
OUTDIR/
  vgmrips.net/
    SALAMD/
      tracks/
        SONG01.mml
        SONG01.mgs
        SONG02.mml
        SONG02.mgs
      _diagnostics/
        SONG01/
          report.txt
          report.json
          convert.log
          compile.log
          SONG01.roundtrip.vgm
          ... source, intermediate, normalization and verification artifacts
        SONG02/
      _source_inputs/
        SONG01.vgm
        SONG02.vgm
      listening_manifest.json
      results.csv
      results.json
  _diagnostics/
    results.csv
    results.json
    keyon_setup.log
```

For example, `INDIR/vgmrips.net/SALAMD/SONG01.vgm` produces
`OUTDIR/vgmrips.net/SALAMD/tracks/SONG01.mml` and `.mgs`. A single-file input,
or files directly inside INDIR, places the package directly at OUTDIR.
Package result paths are relative to that package. Aggregate progress under
OUTDIR/_diagnostics uses paths relative to OUTDIR. Package results retain other
songs when only one source is rerun; aggregate progress describes the current run.

Source filenames are preserved, including existing 8.3 names. Same-package stem
collisions (case differences or a VGM/VGZ pair) are rejected before conversion;
identical stems in separate packages are allowed. No source filename is silently
renamed. Staged inputs are byte-identical copies, with source/staged SHA256 hashes
recorded separately. They are inputs to conversion; originals remain unchanged.

`listening_manifest.json` uses schema version 1 and entries keyed by the original
filename within each package. It records source path/hash, staged path/hash,
diagnostic directory, publication status, published package-relative paths and
SHA256 hashes. Unchanged owned files can be replaced; unowned or edited final
files and modified staged inputs stop the run with an explicit error.

A fresh conversion may publish valid MML even when compilation fails. MGS is
published only after successful compilation. A failed rerun preserves the previous
owned listening products; manifest `latest_attempt_status` and package results
record the new failure, while `status` describes the retained publication.
Latest failed result rows do not claim that retained files belong to that attempt.
Playback comparison errors remain separate from compilation status and affect
process exit status. Successful compilation does not prove equivalent playback.

Both entry points accept omitted `--outdir`. The source parent then becomes the
package root (or INDIR-relative package roots for recursive input), so `tracks/`
is beside the source. Adjacent reruns skip generated `tracks/`, `_source_inputs/`,
`_diagnostics/`, `psg_melody/` and `psg_rhythm/` directories. An explicitly supplied
output root must remain separate from the input tree.

PSG solo invocations retain their independent namespace before the relative
parent: `OUTDIR/psg_melody/<relative-parent>/` or
`OUTDIR/psg_rhythm/<relative-parent>/`, each containing the same package children.
Aggregate progress for these modes remains in OUTDIR/_diagnostics/psg_melody or
psg_rhythm. This does not change the experimental classification rules.

Older output layouts are not deleted or migrated automatically. Use a fresh
output directory to avoid mixing prior products. This package contract is shared
with X68000 MDX/PDX and MUCOM MUC/MUB exporters; target-specific naming rules and
required bank files remain target-specific.

The export entry still requests FM state 24ms / timing normalization 8ms.
The historical batch entry retains opt-in normalization and its existing defaults.
This layout change does not alter chip interpretation, MML structure or timing.
