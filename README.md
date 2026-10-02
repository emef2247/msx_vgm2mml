# vgm2mml
MSX-Music（PSG, OPLL）および SCC の VGM ファイルから、MGSDRV 用 MML を生成するスクリプトです。  
生成した MML は https://msxplay.com/editor.html にコピー＆ペーストすることで、そのまま再生できます。

## 機能概要
- VGM（MSX-Music / SCC）を解析し、MGSDRV 形式の MML を自動生成  
- レジスタアクセスに忠実な MML を出力  

## コマンド一覧

| コマンド | 対応音源 | 概要 |
|----------|----------|------|
| `vgm2mml.py` | PSG, OPLL, SCC | レジスタアクセスに忠実な MML を出力 |

---

## vgm2mml.py

### 使い方
```bash
python vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug] [--raw-ticks] vgm
```

### 基本例
```
python vgm2mml.py stem.vgm
```

出力例：
```
outputs/stem/stem.mml
```

### オプション
| オプション | 説明 |
|-----------|------|
| `--outdir OUTDIR` | MML ファイルの出力先ディレクトリを指定 |
| `--sync-min-gap N` | 同期コメントの最小間隔（出力MMLのstep、既定1000）。0でループ・マクロを分割しない全同期点を表示。開始・終端は常に表示 |
| `--dump-passes` | イベントlog/trace、PASS0-3、PSG/SCC Segment、SCC波形CSVを保存 |
| `--vgmticks` | trace/pass/Segmentに丸め前のVGMサンプル時刻を併記。Segment保存には`--dump-passes`も指定 |
| `--debug` | デバッグ用ファイルを出力 |
| `--raw-ticks` | 音長を `%` tick 形式（例: `c%%N`）で出力（デフォルトは音価形式） |
| `--normalize-lengths` | OPLLの発音間隔から共通の音長基準を推定し、音長・ゲートを補正。既定は無効。適用できない曲は従来出力を維持。`--raw-ticks`との併用不可 |

PSG/SCCは、イベントCSV → Segment → MMLの段階に分けて処理します。
構成と中間フォーマットは [PSG/SCC Segment pipeline](docs/psg_scc_segments.md) を参照してください。
統合MMLのstepコメントは、再生中の全チャンネルで音符・休符の境界が揃う位置に自動挿入します。
PSG/SCCは休符だけのチャンネルと休符中の不要な設定を省き、一定音程の音量推移をソフトウェアエンベロープへ抽出します。
`--dump-passes` では抽出した区間を `*.target_notes.csv`、適用後の音源別MMLを `*.target.mml` に保存します。
仕様と出力例は [同期ポイント](docs/mml_sync.md) を参照してください。
テストはリポジトリのルートで `python -m unittest discover -s tests -v` を実行します。

### 音長の補正

```bash
python vgm2mml.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalize-lengths --dump-passes
```

補正は元の`vgmticks`やSegment CSVを書き換えず、MML生成時に行います。
曲ごとに音長基準の推定と安全性を自動判定し、適用できない場合は全パートを
従来の出力のまま維持します。OPLLリズムも共通基準で処理します。
PSG/SCCはOPLLから推定した基準に合わせて音長を変換し、SWエンベロープの
フレーム指定は維持します。**現状、PSG/SCCだけの曲には補正効果がありません。**

コンソールと`<stem>.normalization.json`に、`applied`（適用）または
`unchanged`（未適用）とその理由を記録します。`--dump-passes`を併用すると、
補正前MML、補正した音のCSV、ループ判定CSVも保存します。
詳細は[音長補正の仕様](docs/note_normalization.md)を参照してください。

### バッチ変換・MGSコンパイル

```bash
# 通常の変換
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/opll

# 音長補正を有効にして比較
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/normalize-lengths/opll --normalize-lengths
```

入力ディレクトリ以下のVGM/VGZを再帰的に変換し、PATH上のネイティブ`mgsc`を
優先してMGSへコンパイルします。実行ファイルは`--mgsc PATH`で指定できます。
各曲のMMLと`convert.log`／`compile.log`を残し、失敗しても次の曲へ進みます。
補正の適用・未適用は各曲の`convert.log`と`<stem>.normalization.json`で確認できます。

`results.csv`／`results.json`にコンパイル結果（`success`、`buffer_error`など）と、
コンパイル成功曲のOPLLメロディKEYON合計・不足数・超過数を記録します。
KEYON比較にはNode.jsとlibkss-jsが必要です。比較を省く場合は
`--skip-keyon-counts`を指定してください。未実施の比較は空欄で、0とは扱いません。
通常実行と補正実行は出力先を分けると結果を比較できます。
依存関係と詳細は[バッチ実行](docs/batch_mgs.md)を参照してください。

---

## 制限事項
- `#alloc` に設定されている値はチャンネルごとの文字数です。コンパイル後のバッファサイズに合うよう調整が必要な場合があります

## 注意事項
MGSDRV の MML は **コンパイル後、全チャンネルのバッファサイズ合計が 16KB 以内**である必要があります。しかし**本スクリプトはこの制限を考慮していません**。  
そのため、生成された MML が大きすぎる場合は、以下のような調整が必要です：
- `#alloc` の値を手動で調整  
- マクロ化してデータ量を削減  

## ライセンス
MIT License

---


# vgm2mml
A script that converts VGM files for MSX-Music (PSG, OPLL) and SCC into MML for MGSDRV.
The generated MML can be copied and pasted directly into https://msxplay.com/editor.html for playback.

## Overview
- Automatic conversion: Parses VGM (MSX-Music / SCC) and generates MGSDRV-style MML
- Register-accurate output: Produces MML that closely reflects the original register writes

## Command Overview

| Command | Supported Chips | Description |
|---------|-----------------|-------------|
| `vgm2mml.py` | PSG, OPLL, SCC | Outputs register-accurate MML |

---

## vgm2mml.py

### Usage
```bash
python vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug] [--raw-ticks] vgm
```

### Example
```
python vgm2mml.py stem.vgm
```
The output will be saved in `outputs/<stem>/<stem>.mml`.

### Options
| Option | Description |
|--------|-------------|
| `--outdir OUTDIR` | Specify the output directory for the MML file |
| `--dump-passes` | Output intermediate files |
| `--debug` | Output debug files |
| `--raw-ticks` | Output note lengths as raw `%` ticks (e.g. `c%%N`) instead of note-value notation |
| `--normalize-lengths` | Infer a shared musical clock from OPLL attacks and correct target lengths/gates. Disabled by default; uncertain/unsafe songs retain conventional output. Incompatible with `--raw-ticks` |

---

## Limitations
- The value set in `#alloc` is the character count per channel. You may need to adjust it to fit the buffer size after compilation.

## Notes
MGSDRV MML must satisfy the constraint that the total buffer size of all channels after compilation is within 16 KB.
However, this script does not take that limitation into account.

If the generated MML is too large, you may need to:
- Manually adjust the `#alloc` values
- Use macros to reduce data size

## License
MIT License

### Declared VGM loop inspection

`--dump-passes` (or `--debug`) writes `<stem>.vgm.loop.csv` with the
header loop address, declared sample count, observed start/end samples and
validation status. This records the source loop without repeating playback,
resetting chip state or adding KEYONs. Infinite MML loops and Segment loop
annotations are not emitted yet. See [VGM loop metadata](docs/vgm_loop.md).

### OPLL Segment inspection

`--dump-passes` also writes `<stem>.opll.segments.csv`, including melody and
rhythm channels before target voice assignment. See `docs/opll_rhythm.md`.

The same option writes `.opll.rhythm.groups.csv`, `.opll.rhythm.patterns.csv`
and `.opll.rhythm.occurrences.csv` for lossless tick grouping and exact repeats.
These analysis tables do not yet change the generated MML.

The main converter now renders OPLL rhythm on track `f`, including simultaneous
hits, per-instrument volumes and exact finite repeats. Rhythm participates in
shared sync marks and the 15000 allocation pool. Source timing still uses the
existing 60 Hz analysis; no libkss timing correction is applied.

Main OPLL target output uses MGSDRV ROM voices @0..@14 and explicit user
voice definitions starting at @16. Long notes use exact lengths and tied
continuations when split. --dump-passes includes `.opll.target_notes.csv`
with the selected target voice and source patch bytes for each sounding Segment.

## Rhythm notation optimization

Final rhythm MML omits redundant instrument-volume commands and selects a
single default length when it reduces text size. Exact patterns still come
from Segment analysis; this pass does not discover new loops or macros.
`--dump-passes` retains `.opll.rhythm.before.target.mml`,
`.opll.rhythm.after.target.mml`, and `.opll.rhythm.optimization.csv`.
See docs/opll_rhythm.md for scope and validation.

## Melody pattern analysis

`--dump-passes` also writes per-chip `.melody.patterns.csv`,
`.melody.occurrences.csv` and `.melody.markings.csv`. These describe exact
adjacent Segment repeats and retain source-row references. Eligible candidates become finite MML loops without changing expanded commands; see [melody pattern analysis](docs/melody_patterns.md) for equality
rules, reconstruction and the limits of these loop candidates.

### Output metadata and default artifacts

By default, `vgm2mml.py` produces only `<stem>.mml`. Both the player metadata
`;[name=<stem> lpf=1]` and `#title` use the input filename without its extension.
Use `--name "Player name"` and `--title "Song title"` to override them independently;
These options do not rename the output.
`--dump-passes` retains analysis artifacts; `--debug` retains legacy MML variants.

```sh
python vgm2mml.py song.vgm --outdir outputs/song --name song --title "Song Title"
```

With `--dump-passes`, `.performed.units.csv` and `.performed.loops.csv` expose
complete-note/percussion candidates and nested loops. Segment CSVs also carry
performed-unit IDs and hierarchy paths. PSG percussion grouping is conservative:
noise-containing intervals with a trailing rest are candidates, not inferred
original driver macros. Exact command-preserving nested loops support PSG/SCC
and OPLL melody; see `docs/melody_patterns.md` for limits.
# Automatic MML macros

Normal target output now shares repeated PSG, SCC and OPLL melodic command
sequences, including OPLL rhythm, through MGSDRV macros. Candidates are ranked by source-character
savings across tracks (no fixed chip priority). Existing synchronization marks,
loops and allocation remain intact. Up to 32 non-recursive definitions are
emitted, only when the resulting file is smaller. Rhythm and melody use separate
candidate pools to retain their distinct syntax. Macros reduce source length, not
necessarily compiled track memory. `--dump-passes` retains the pre-macro chip
outputs; the merged MML contains the final definitions and calls.
# Batch MGS compilation

Batch regression also exports each compiled MGS through libkss and reports
OPLL melodic KEYON totals, shortages and excesses in `results.csv`/`results.json`.
Use `--skip-keyon-counts` to compile without playback comparison, or
`--libkss-module` to select the installed playback module. See
[batch dependency setup](docs/batch_mgs.md).

Use `python scripts/batch_vgm_to_mgs.py INPUT_DIR --outdir OUTPUT_DIR` to
recursively convert VGM/VGZ and compile MGS. Native `mgsc` on PATH is preferred;
use `--mgsc PATH` to select it explicitly. The mgsc-js fallback is also available.
Intermediate MML and per-file conversion/compiler logs are retained on failure,
and later inputs continue. Results are recorded in `results.csv`/`results.json`;
buffer allocations are not adjusted automatically after compiler failures.

```bash
# Conventional conversion
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/opll

# Opt-in musical normalization; use a separate output tree for comparison
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/normalize-lengths/opll --normalize-lengths
```

Each song's `convert.log` and `<stem>.normalization.json` report whether correction
was applied. Successful compilations also report source/export OPLL melodic
KEYON totals and per-channel count shortages/excesses summed over the song.
Unperformed comparisons have blank counts, not zeros. Compare conventional and
normalized `results.csv` files to inspect changes in `buffer_error` and counts.
See [setup and usage](docs/batch_mgs.md).
# GD3 titles

Without `--title`, the converter reads VGM GD3 metadata and generates
`[System]Name(Release date) Title Author`. `--gd3-language ja` (default) prefers
Japanese with English fallback for each field; `--gd3-language en` reverses
that preference for track, game and author. System always uses the English
field (omitted if absent). Release date is language-independent. Full-width
ASCII in System and Release date is normalized to half-width. Missing fields omit their
delimiters; absent, empty or malformed GD3 falls back to the input stem.
Explicit `--title` always wins. Metadata name (`--name`) and filenames do not
change. Merged MML is UTF-8.

Generated titles are sanitized for MML syntax and limited to 240 CP932 bytes
(whole characters), with a warning on truncation. This is a conservative MGSC
physical-line safeguard, not a fixed MGS title-field size. MGS stores its title
as a variable-length CRLF-terminated text field. MGSC 1.11 probes accepted a
240-byte title and rejected 250 bytes with the emitted header syntax. The
explicit `--title` override is not automatically truncated.
# Manual allocation overrides

Use `--alloc "9=1800, a=3780, b=1480, c=2850, d=4750, f=600"` to override
selected channels in the final merged `#alloc`. Unspecified channels retain
their automatic allocations. Channel letters are case-insensitive; duplicate
channels and invalid/non-integer values are rejected. Overrides are applied
after formatting/macros and are not redistributed to enforce the default total
budget. Actual compiler capacity is still checked by MGSC.

`scripts/batch_vgm_to_mgs.py` also accepts `--alloc`, applying the same overrides
to every input in that batch. Per-chip intermediate MML remains unchanged.

## OPLL key-on count checks

Compare source and exported VGM key-on counts, or supply a CSV of VGM pairs
for regression. Reports contain per-VGM totals and per-channel count shortages/
excesses summed over the song, without a quality score or timing comparison.
See [OPLL key-on counts](docs/opll_keyon_counts.md).

### Compressed VGM input

Input is detected by its contents: gzip-compressed VGM is accepted even with a
`.vgm` extension, as well as `.vgz`. GD3 metadata uses the same decompressed bytes.

## Optional musical duration normalization

`--normalize-lengths` estimates a shared clock from native OPLL attacks and
projects note lengths/gates before loop extraction. Raw sample times and Segment
CSV evidence stay unchanged. Uncertain or unsafe material keeps conventional
output. Use `--dump-passes` to inspect correction and normalized loop CSVs.
Batch conversion accepts the same flag. It is disabled by default and cannot be
combined with `--raw-ticks`. OPLL rhythm uses the shared clock; PSG/SCC durations
are retimed using that OPLL-derived clock while software envelope frame lengths
stay unchanged. **PSG/SCC-only songs currently receive no normalization.**

```bash
python vgm2mml.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalize-lengths --dump-passes
```

Each song is checked automatically. `<stem>.normalization.json` reports `applied`
or `unchanged`, with the reason for abstaining; the console reports the same.
With `--dump-passes`, conventional target MML, corrected-note evidence and loop
decision CSVs are retained alongside native Segment dumps.
See [usage and limits](docs/note_normalization.md)
and [sample/grider/sx01v measurements](field_notes/2026-10-02_note_normalization_benchmark.md).
