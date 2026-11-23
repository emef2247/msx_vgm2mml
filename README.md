# msx_vgm2mml

VGMに記録されたレジスタ操作を解析し、音符・音価・音量・音色などの演奏情報を抽出して、MSX向けMML（MGSDRV用）を生成するツールです。

MML/MGSに加え、VGMの生成や、編集用のMML・MIDI（SMF）を出力するBlueprint機能にも対応しています。

Python 3.10以降が必要です。

## 使い方

### VGMファイルを指定して変換

MMLとVGMが生成されます。

```bash
python vgm2mml.py INPUT.vgm --outdir OUTDIR
```

### VGMファイルを含むディレクトリを指定して一括変換

```bash
python scripts/export_mgs.py INDIR --outdir OUTDIR
```

MMLの生成からMGSへのコンパイルまでを自動で行います。VGMやBlueprintも出力します。

### Blueprintの出力

通常のMML/MGSとは別に、演奏情報を編集用のMMLおよびMIDI（SMF）として出力するBlueprint機能を搭載しています。

またndpサブフォルダ（`blueprint/ndp/`）には、MSX用PSGドライバ「NDP」形式のMMLが生成されます。

Blueprintでは、音色や音量の再現よりも、音符・音価・休符・繰り返しといった楽曲の構造を抽出することを重視しています。

詳細は[Blueprintの仕様](docs/musical_blueprint.md)を参照してください。

### 主なオプション

| オプション | 説明 |
| --- | --- |
| `--outdir OUTDIR` | 入力の相対ディレクトリ構造を維持して出力 |
| `--output-format {mml,vgm,both}` | MML・VGMの出力形式を指定 |
| `--force` | 未対応のレジスタ操作を診断付きで省略し、可能な範囲で変換を継続 |
| `--timeout SECONDS` | 各処理段階のタイムアウト（既定1200秒） |

`--force`を指定しても、すべての入力を変換できるわけではありません。未対応処理を一部省略しながら継続できる場合のみ有効です。省略内容についてはレポートを確認してください。

## 対応する音源

| VGMの音源 | MGS変換 | Blueprint | vgm-variants |
| --- | :---: | :---: | :---: |
| PSG／SSG（AY系） | ○ | ○ | ○ |
| OPLL（YM2413） | ○ | ○ | ○ |
| SCC | ○ | ○ | ○ |
| DCSG（SN76489） | ― | ○ | ○ |
| DCSGx2 | ― | ○ | ○ |
| HuC6280 | △ | ○ | △ |
| NES APU | ○ | ○ | ○ |
| FDS | ○ | ○ | ○ |
| OPM（YM2151） | ― | ○ | ○ |
| OPM＋MSM6258 | ― | ― | ○ |
| OPNA（YM2608） | ― | ○ | ○ |
| OPN2（YM2612） | ― | ○ | ○ |
| OPN（YM2203） | ― | ○ | ○ |
| OPN＋SegaPCM | ― | ― | ○ |

○：対応　△：近似変換　―：非対応

### MGS変換

PSG／SSG、OPLL、SCCの演奏情報をMGSDRV用MMLに変換します。

## VGM出力

VGMから抽出した演奏情報をもとに、VGMファイルを生成できます。

```bash
python scripts/export_vgm.py INDIR --outdir OUTDIR
```

## 変換と再生の注意点

VGMとMMLでは表現方法や制約が異なるため、元の演奏を完全に再現できるとは限りません。

また、MGSにはMGSDRVのバッファ制約があります。そのため、生成したMMLをコンパイルしても、データ量によってはMGSを生成できない場合があります。

その場合は、生成されたMMLを手動で編集または分割してください。

Blueprintについても、音源固有の制御やPCMなど、楽譜として表現できない情報があります。

## トラブルシューティング

### コンパイルがバッファ上限（Track buffer full）で失敗する

既定のコンパイラMGSCには、演奏データ全体で約16KBの作成上限があります。`--compiler mgsexc` を指定すると、上限のない同梱コンパイラMGSEXCでコンパイルできます（MGSCでコンパイル可能なデータでは、生成されるMGSはMGSCとバイト単位で一致します）。

### 16KBを超えるMGSが実機で正しく再生されない

MGSDRV本体は16KBを超える演奏データも処理できますが、プレーヤーによっては再生できるサイズに上限があります。実機で確認した例（2026-10-31）:

- MGSEL 3.01v: 16,384バイトまで
- MultiPlay-X V1.13: おそらく20,480バイト（0x5000）まで

上限を超えると、途中で音がおかしくなったり、曲が終了しなくなったり、無言で再生されなかったりします。実機再生が前提の場合は、MGSが16,384バイト以下に収まるようMMLを編集または分割してください。

## いろんなサウンドカートリッジで鳴らしてみる

通常の出力に加えて、`--vgm-variants` を付けて実行すると、サウンドカートリッジの構成ごとの VGM を別途生成します。SFG-01（OPM）や Makoto（OPNA）といったカートリッジで、変換した曲をそのまま鳴らすための機能です。

    python scripts/export_mgs.py <入力.vgm> --outdir <出力先> --vgm-variants --force

生成物は `vgm-variants/<1本目のプロファイル名>/<曲名>.vgm` に出力されます。組み合わせは1本目のフォルダの下に、追加要素の名前のサブフォルダに入ります（例: `vgm-variants/sfg01/makoto/<曲名>.vgm`、`vgm-variants/sfg01/scc/<曲名>.vgm`）。

1本目のカートリッジのプロファイルが入力音源ごとに生成されるかの一覧です（○：生成される、△：制限あり・未変換部分あり、—：生成されない）。

| プロファイル | psg | psg_scc | opll | dcsg | dcsgx2 | apu | apu_fds | huc6280 | opna | opm | opn2 | opm_msm6258 | opm_segapcm | opn | opn_segapcm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sfg01 | ○ | ○ | ○ | ○ | ○ | ○ | ○ | △ | ○ | ○ | △ | △ | △ | ○ | △ |
| makoto | ○ | ○ | ○ | ○ | ○ | ○ | ○ | △ | ○ | ○ | ○ | ○ | △ | ○ | △ |
| misato | ○ | ○ | ○ | ○ | ○ | △ | △ | △ | △ | ○ | △ | △ | △ | ○ | △ |
| msxaudio | ○ | — | ○ | ○ | ○ | ○ | △ | △ | — | — | — | — | — | — | — |
| opl3 | ○ | — | ○ | ○ | ○ | ○ | ○ | △ | — | — | — | — | — | — | — |

各プロファイルでは、入力VGMから抽出した演奏情報を、対応するサウンドカートリッジの音源へ割り当てます。
複数の音源が混在する場合は、音源ごとの優先順位に従ってチャンネルを割り当てます。音源の仕様やチャンネル数の制約により、一部の演奏情報を再現できない場合があります。

各プロファイルの詳細については、[--vgm-variantsの詳細](README.vgm-variants.md)を参照してください

## 構成

- `vgm2mml.py`：単体VGMの解析とMML・VGM生成
- `scripts/export_mgs.py`：MML・MGS・VGM・Blueprint・診断情報の一括出力
- `scripts/export_vgm.py`：VGMの一括出力
- `tests/script/`：自動テスト
- `tests/fixtures/`：テスト用入力データおよび参照データ
- `py/`：音源解析、中間表現、出力生成処理
- `scripts/`：変換・検証・補助ツール

## ライセンス

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

本プロジェクトで利用または参照している第三者コンポーネントのライセンスおよび著作権表示については、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

## 謝辞

本プロジェクトの開発、検証、およびテスト生成では、以下のツールやプロジェクトを利用または参考にしています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 用途 |
| --- | --- |
| [MGSC／mgsc-js](https://github.com/digital-sound-antiques/mgsc) | MML→MGSコンパイル |
| [MGSDRV](https://www.gigamix.jp/mgsdrv/) | 出力MMLの対象ドライバ・再生検証 |
| [libkss-js／libkss](https://github.com/digital-sound-antiques/libkss-js) | MGS再生・Key-On数などの検証 |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | PSG→FMの音色・音量対応方式の参考 |

使用した第三者コンポーネントのバージョン、参照元、著作権表示、ライセンス条件、および再配布時の注意事項は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に記録しています。

解析とMML生成はPythonで実装しています。外部ツールは主にコンパイル、再生確認、比較、およびテスト生成に使用しています。

---

# msx_vgm2mml

A tool that analyzes register operations recorded in VGM files, extracts musical information such as notes, durations, volumes, and timbres, and generates MML for MSX systems (MGSDRV).

In addition to MML/MGS output, it supports VGM generation and a Blueprint feature that produces editable MML and MIDI (SMF) files.

Requires Python 3.10 or later.

## Usage

### Convert a VGM file
By default, both MML and VGM files are generated.
```bash
python vgm2mml.py INPUT.vgm --outdir OUTDIR
```

### Batch conversion of a directory containing VGM files

```bash
python scripts/export_mgs.py INDIR --outdir OUTDIR
```

This script automatically generates MML files and compiles them into MGS files. It also produces VGM and Blueprint output.

### Blueprint Output

In addition to the standard MML/MGS output, the Blueprint feature generates editable MML and MIDI (SMF) files from the extracted musical information.

The ndp subfolder (`blueprint/ndp/`) also receives MML in the format of "NDP," a PSG driver for MSX.

Blueprint focuses on extracting musical structure, such as notes, durations, rests, and repetitions, rather than reproducing the original timbres and volume characteristics.

The generated files can be used for MML editing, arrangement, and further processing in DAWs.

Blueprint generation is independent of the standard MML/MGS conversion process and may succeed even when MGS conversion is unavailable.

For details, see the [Blueprint Specification](docs/musical_blueprint.md).

### Main Options

| Option | Description |
| --- | --- |
| `--outdir OUTDIR` | Preserve the input's relative directory structure in the output |
| `--output-format {mml,vgm,both}` | Select MML, VGM, or both output formats |
| `--force` | Continue conversion where possible by omitting unsupported register operations with diagnostic reporting |
| `--timeout SECONDS` | Timeout for each processing stage (default: 1200 seconds) |

The `--force` option does not guarantee successful conversion of every input. It only allows conversion to continue when unsupported operations can be safely omitted. Check the diagnostic reports for details about omitted operations.

## Supported Sound Chips

| VGM Sound Chip | MGS Conversion | Blueprint | VGM Variants |
| --- | :---: | :---: | :---: |
| PSG / SSG (AY family) | Yes | Yes | Yes |
| OPLL (YM2413) | Yes | Yes | Yes |
| SCC | Yes | Yes | Yes |
| DCSG (SN76489) | No | Yes | Yes |
| DCSGx2 | No | Yes | Yes |
| HuC6280 | Approximate | Yes | Approximate |
| NES APU | Yes | Yes | Yes |
| FDS | Yes | Yes | Yes |
| OPM (YM2151) | No | Yes | Yes |
| OPM + MSM6258 | No | No | Yes |
| OPNA (YM2608) | No | Yes | Yes |
| OPN2 (YM2612) | No | Yes | Yes |
| OPN (YM2203) | No | Yes | Yes |
| OPN + SegaPCM | No | No | Yes |

### MGS Conversion

Musical information from PSG/SSG, OPLL, and SCC is converted into MGSDRV-compatible MML.

## VGM Output

The tool can generate VGM files from musical information extracted from the source VGM.

```bash
python scripts/export_vgm.py INDIR --outdir OUTDIR
```

## Conversion and Playback Limitations

Because VGM and MML have different representations and constraints, the original performance may not always be reproduced accurately.


## Troubleshooting

### Compilation fails with a buffer limit (Track buffer full)

The default compiler, MGSC, can create at most about 16 KB of performance data in total. Specifying `--compiler mgsexc` uses the bundled MGSEXC compiler, which has no such limit (for data MGSC can compile, its MGS output is byte-identical to MGSC's).

### MGS data over 16 KB does not play correctly on real hardware

MGSDRV itself handles performance data over 16 KB, but some players have their own size limits. Observed on real hardware (2026-10-31):

- MGSEL 3.01v: up to 16,384 bytes
- MultiPlay-X V1.13: probably up to 20,480 bytes (0x5000)

Beyond a player's limit, playback may glitch partway through, never terminate, or silently refuse to play. If real-hardware playback matters, edit or split the MML so the MGS stays within 16,384 bytes.

## Playing on Various Sound Cartridges

In addition to the standard output, adding `--vgm-variants` also generates VGM files for each sound cartridge configuration. This feature lets you play converted songs as they are on cartridges such as SFG-01 (OPM) and Makoto (OPNA).

The musical information built for MML generation is assigned to other sound chips mounted on MSX sound cartridges. The current targets are SFG-01 (OPM), Makoto (OPNA), Misato (OPN3), MSX-AUDIO (Y8950), and OPL3 (YMF262).

    python scripts/export_mgs.py <input.vgm> --outdir <output> --vgm-variants --force

Output goes to `vgm-variants/<first cartridge profile>/<song>.vgm`. Compositions are placed under the first cartridge's folder in a subfolder named by the added element (e.g. `vgm-variants/sfg01/makoto/<song>.vgm`, `vgm-variants/sfg01/scc/<song>.vgm`). A composition identical to the first cartridge alone is not written. Configurations that cannot be generated are skipped with a reason, and diagnostics remain in `_diagnostics`.

Base profiles generated for each source type (Yes: generated, Approximate: generated with limitations or unconverted parts, No: not generated).

| Profile | psg | psg_scc | opll | dcsg | dcsgx2 | apu | apu_fds | huc6280 | opna | opm | opn2 | opm_msm6258 | opm_segapcm | opn | opn_segapcm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sfg01 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Approximate | Yes | Yes | Approximate | Approximate | Approximate | Yes | Approximate |
| makoto | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Approximate | Yes | Yes | Yes | Yes | Approximate | Yes | Approximate |
| misato | Yes | Yes | Yes | Yes | Yes | Approximate | Approximate | Approximate | Approximate | Yes | Approximate | Approximate | Approximate | Yes | Approximate |
| msxaudio | Yes | No | Yes | Yes | Yes | Yes | Approximate | Approximate | No | No | No | No | No | No | No |
| opl3 | Yes | No | Yes | Yes | Yes | Yes | Yes | Approximate | No | No | No | No | No | No | No |

Each profile maps the musical information extracted from the input VGM to the sound chips available in the corresponding MSX sound cartridge configuration.
When multiple sound sources are present, channels are allocated according to source priorities. Some performance details may not be reproduced due to hardware limitations or the number of available channels.

For details on each profile, see the [--vgm-variants details](README.vgm-variants.md).

## Project Structure

- `vgm2mml.py`: Analyze individual VGM files and generate MML and VGM output
- `scripts/export_mgs.py`: Batch generation of MML, MGS, VGM, Blueprint, and diagnostic information
- `scripts/export_vgm.py`: Batch VGM generation
- `tests/script/`: Automated tests
- `tests/fixtures/`: Test inputs and reference data
- `py/`: Sound chip analysis, intermediate representations, and output generation
- `scripts/`: Conversion, validation, and utility scripts

## License

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

For licenses and copyright notices of third-party components used or referenced by this project, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Acknowledgments

The following tools and projects have been used or referenced during development, validation, and test generation.

Special thanks to their developers, maintainers, and contributors.

| Project | Purpose |
| --- | --- |
| [MGSC / mgsc-js](https://github.com/digital-sound-antiques/mgsc) | MML-to-MGS compilation |
| [MGSDRV](https://www.gigamix.jp/mgsdrv/) | Target driver for generated MML and playback validation |
| [libkss-js / libkss](https://github.com/digital-sound-antiques/libkss-js) | MGS playback and validation, including Key-On event counts |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | Reference for PSG-to-FM timbre and volume mapping approaches |

Versions, upstream references, copyright notices, license terms, and redistribution requirements for third-party components are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

VGM analysis and MML generation are implemented in Python. External tools are primarily used for compilation, playback verification, comparison, and test generation.
