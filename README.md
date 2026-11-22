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

MGSの生成にはMGSCまたはmgsc-jsが必要です。また、生成結果のKey-On検証にはlibkss-jsを使用します。

なお、バッファ制限回避のため、独自コンパイラMGSEXCも収録しています（`scripts/batch_vgm_to_mgs.py` の `--compiler mgsexc` で選択）。

これらの環境構築については、[環境構築](docs/setup_mgs_tools.ja.md)を参照してください。

外部ツールを自動でインストールしたい場合は、[scripts/setup_mgs_tools.py](scripts/setup_mgs_tools.py)を利用してください。

### Blueprintの出力

通常のMML/MGSとは別に、演奏情報を編集用のMMLおよびMIDI（SMF）として出力するBlueprint機能を搭載しています。

またndpサブフォルダ（`blueprint/ndp/`）には、MSX用PSGドライバ「NDP」形式のMMLが生成されます。

Blueprintでは、音色や音量の再現よりも、音符・音価・休符・繰り返しといった楽曲の構造を抽出することを重視しています。

生成したデータは、MMLの編集やDAWでのアレンジなどに利用できます。

Blueprintは通常のMML/MGS生成とは独立しており、MGSへの変換ができない場合でも生成できることがあります。

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

○：対応　△：近似変換　―：非対応

### MGS変換

PSG／SSG、OPLL、SCCの演奏情報をMGSDRV用MMLに変換します。

PSG／SCCでは、音量変化からソフトウェアエンベロープを抽出し、反復部分のループ化やマクロ化も行います。

HuC6280は、SCCを中心にPSGやOPLLを併用して近似変換します。波形や音源の使用状況によっては、再現できない演奏情報があります。

NES APUは、パルス波と三角波をSCC、ノイズをPSGへ割り当てて変換します。DPCMとFDSは、SCCの空きチャンネルでの波形スライス再生やOPLLへの割り当てで再現します。

## VGM出力

VGMから抽出した演奏情報をもとに、VGMファイルを生成できます。

VGMの生成はMMLのコンパイルとは独立しており、MMLやMGSを生成できない場合でも利用できることがあります。

生成されるVGMは音楽的な情報をもとに再構成したものであり、元のVGMのレジスタ操作を完全に再現するものではありません。

VGMのみを一括生成したい場合は、次のスクリプトも利用できます。

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

MML 生成用に構築した音楽情報を、MSX のサウンドカートリッジに搭載された別の音源へ割り当ててみる機能です。現在の対象は SFG-01（OPM）、Makoto（OPNA）、Misato（OPN3）、MSX-AUDIO（Y8950）、OPL3（YMF262）です。

    python scripts/export_mgs.py <入力.vgm> --outdir <出力先> --vgm-variants --force

生成物は `vgm-variants/<土台のプロファイル名>/<曲名>.vgm` に出力されます。組み合わせは土台の下に追加要素の名前のサブフォルダに入ります（例: `vgm-variants/sfg01/makoto/<曲名>.vgm`、`vgm-variants/sfg01/scc/<曲名>.vgm`）。土台と同一内容になる組み合わせは出力されません。生成できない構成は理由とともにスキップされ、診断が `_diagnostics` に残ります。

土台プロファイルが入力音源ごとに生成されるかの一覧です（○：生成される、△：制限あり・未変換部分あり、—：生成されない）。

| プロファイル | psg | psg_scc | opll | dcsg | dcsgx2 | apu | apu_fds | huc6280 | opna | opm | opn2 | opm_msm6258 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sfg01 | ○ | ○ | ○ | ○ | ○ | ○ | ○ | △ | ○ | ○ | △ | △ |
| makoto | ○ | ○ | ○ | ○ | ○ | ○ | ○ | △ | ○ | ○ | ○ | ○ |
| misato | ○ | ○ | ○ | ○ | ○ | △ | △ | △ | △ | ○ | △ | △ |
| msxaudio | ○ | — | ○ | ○ | ○ | ○ | △ | △ | — | — | — | — |
| opl3 | ○ | — | ○ | ○ | ○ | ○ | ○ | △ | — | — | — | — |

msxaudio / opl3 の apu_fds・huc6280 の △ は、波形音源の声数が上限を超えるためで、`--force` 指定時に上限を超えたレーンを省略して生成します。

組み合わせは原則として土台の行を引き継ぎますが、PCM を持つ入力では行き先を足す組み合わせの方が土台より広く対応します（例: opm_msm6258 では sfg01 は △、sfg01/makoto は ○）。

組み合わせと重ね系のプロファイルが生成される入力音源の種類は次の通りです（scc は SCC が鳴っている入力）。SCC・PSG を実チップのまま残す構成は layered の形（`psg_layered` / `scc_layered`）だけです。OPLL も実チップのまま残り、`layered` ではネイティブのレーンとして重なり、`sfg01_opllrhythm` ではリズムがネイティブのまま残ります。

| プロファイル | psg | scc | opna | opm | opn2 |
|---|---|---|---|---|---|
| sfg01 | — | — | ○ | ○ | ○ |
| makoto | — | — | ○ | ○ | ○ |
| misato | — | — | ○ | ○ | ○ |
| msxaudio | — | — | — | — | — |
| opl3 | — | — | — | — | — |
| layered | — | — | ○ | ○ | ○ |
| psg_layered | ○ | — | — | — | — |
| scc_layered | — | ○ | — | — | — |

opna / opm / opn2 列は、2台目のカートリッジ（makoto / msxaudio / opl3 / misato）やリズム源（rx21 / opllrhythm）を足す組み合わせの生成で、土台自体が受け付けない入力では生成されません。

### 各プロファイルの説明

各プロファイルでは、入力VGMから抽出した演奏情報を、対応するサウンドカートリッジの音源へ割り当てます。
複数の音源が混在する場合は、音源ごとの優先順位に従ってチャンネルを割り当てます。音源の仕様やチャンネル数の制約により、一部の演奏情報を再現できない場合があります。

#### 基本構成

- **`sfg01`**：SFG-01（OPM / YM2151）向け。各音源の演奏情報をOPMのFM音源へ変換します。
- **`makoto`**：Makoto（OPNA / YM2608）向け。各音源をOPNAのFM音源へ変換し、PCMはADPCM-Bへ割り当てます。
- **`misato`**：Misato（OPN3）向け。`makoto` と同様にFM音源へ変換しますが、ADPCM機能がないためPCMは再生できません。打楽器には搭載されたリズム音源を使用します。
- **`msxaudio`**：MSX-AUDIO（Y8950）向け。OPLLの演奏情報をY8950のFM音源へ変換します。OPLLのリズムはY8950のリズム音源へ、PCMはDelta-Tへ割り当てます。
- **`opl3`**：OPL3（YMF262）向け。OPLLの演奏情報をOPL3のFM音源へ変換し、リズムはOPL3のリズム音源へ割り当てます。PCMには対応しません。

#### 組み合わせ例： SFG-01と他の音源を組み合わせる構成

SFG-01によるFM演奏を基本とし、リズム音源やPCM再生に別の音源を併用する構成です。

- **`sfg01_opllrhythm`**：`sfg01` を基本とし、OPLLのリズムパートだけはFMへ変換せず、YM2413のリズム音源でそのまま再生します。
- **`sfg01_opl3`**：`sfg01` を基本とし、OPLLのリズムパートをOPL3（YMF262）のリズム音源で再生します。
- **`sfg01_makoto`**：SFG-01にMakotoを組み合わせ、PCM再生にOPNAのADPCM-Bを利用します。
- **`sfg01_msxaudio`**：SFG-01にMSX-AUDIOを組み合わせ、PCM再生にY8950のDelta-Tを利用します。
- **`sfg01_misato`**：SFG-01にMisatoを組み合わせ、OPLLやOPNAのリズムパートをMisatoのリズム音源で再生します。ADPCMは使用しません。

#### FM音源を重ねる構成

- **`layered`**：FMへ変換可能な演奏パートを各チップのFMユニットに割り当てます。最大でSFG-01,Makoto(or Misato), OPLL, OPL3, MSX-Audioで同じパートを重ねて演奏します。

単なるデチューンとは異なり、異なるFM音源チップの音色を重ね合わせる、MSXならではのお遊び機能です。

#### SCCを重ねる構成

SCCの演奏パートを元のSCCで再生しながら、同じパートを別のFM音源にも割り当てる構成です。

- **`scc_layered`**：SCC ＋ SFG-01（OPM）＋ Makoto（OPNA）の3重奏

SCC以外のパートは、対応する基本構成またはレイヤー構成と同じ方法で変換します。

#### PSGを重ねる構成

PSGの演奏パートを元のPSGで再生しながら、同じパートをFM音源にも割り当てる構成です。

- **`psg_layered`**：PSG ＋ SFG-01（OPM）＋ Makoto（OPNA）の3重奏

これらはPSGのみを使用する入力VGMを対象とします。

なお、SCC・PSGのレイヤー構成ではOPLLへの変換は行いません。OPLLはユーザー定義音色を同時に1種類しか使用できないため、複数パートの独立した音色を再現する用途には適していません。

#### PCMの取り扱い

PCMデータは256KiBの容量制限に収まるよう、重複サンプルの共有や代表サンプルへの置き換えによって自動調整します。

PCMの再生可否や割り当て先は、プロファイルと搭載音源の構成によって異なります。

#### 再生方法

生成したVGMは、MSX実機のVGMPlayや、Mami-VSIF Pro経由のMAmidiMEmoなどで再生できます。

実機をお持ちでない場合も、対応するVGMプレーヤーで演奏を楽しめます。

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

MGSC or mgsc-js is required to generate MGS files. libkss-js is used to verify Key-On events in the generated output.

A bundled compiler, MGSEXC, is also included to avoid the buffer limit (select it with `--compiler mgsexc` in `scripts/batch_vgm_to_mgs.py`).

For instructions on setting up these tools, see [Tool Setup](docs/setup_mgs_tools.md).

To install the external tools automatically, use [scripts/setup_mgs_tools.py](scripts/setup_mgs_tools.py).

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

### MGS Conversion

Musical information from PSG/SSG, OPLL, and SCC is converted into MGSDRV-compatible MML.

For PSG and SCC, the tool extracts software envelopes from volume changes and applies loop and macro optimizations to repeated passages.

HuC6280 is approximately mapped to SCC, with PSG and OPLL used where applicable. Some musical information may not be reproduced accurately, depending on waveform characteristics and sound chip usage.

The NES APU is converted by assigning its pulse and triangle channels to SCC and its noise channel to PSG. DPCM and FDS are reproduced with waveform slices on a free SCC channel or by assignment to OPLL.

## VGM Output

The tool can generate VGM files from musical information extracted from the source VGM.

VGM generation is independent of MML compilation and may be available even when MML or MGS generation is unsuccessful.

Generated VGM files are musical reconstructions and are not guaranteed to reproduce the original register operations exactly.

For batch VGM generation without MML/MGS compilation, the following script is also available:

```bash
python scripts/export_vgm.py INDIR --outdir OUTDIR
```

## Conversion and Playback Limitations

Because VGM and MML have different representations and constraints, the original performance may not always be reproduced accurately.

MGS files are also subject to MGSDRV buffer limitations. As a result, some generated MML files may exceed the available capacity and fail to compile into MGS files.

In such cases, manually edit or split the generated MML files.

Blueprint also has limitations: sound chip-specific controls, PCM data, and other information that cannot be represented as musical notation may not be included.


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

Output goes to `vgm-variants/<base profile>/<song>.vgm`. Compositions are placed under their base in a subfolder named by the added element (e.g. `vgm-variants/sfg01/makoto/<song>.vgm`, `vgm-variants/sfg01/scc/<song>.vgm`). A composition identical to its base is not written. Configurations that cannot be generated are skipped with a reason, and diagnostics remain in `_diagnostics`.

Base profiles generated for each source type (Yes: generated, Approximate: generated with limitations or unconverted parts, No: not generated).

| Profile | psg | psg_scc | opll | dcsg | dcsgx2 | apu | apu_fds | huc6280 | opna | opm | opn2 | opm_msm6258 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sfg01 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Approximate | Yes | Yes | Approximate | Approximate |
| makoto | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Approximate | Yes | Yes | Yes | Yes |
| misato | Yes | Yes | Yes | Yes | Yes | Approximate | Approximate | Approximate | Approximate | Yes | Approximate | Approximate |
| msxaudio | Yes | No | Yes | Yes | Yes | Yes | Approximate | Approximate | No | No | No | No |
| opl3 | Yes | No | Yes | Yes | Yes | Yes | Yes | Approximate | No | No | No | No |

The Approximate cells for apu_fds / huc6280 on msxaudio and opl3 are due to waveform-voice capacity: with `--force`, lanes beyond capacity are omitted.

Compositions generally inherit their base profile's row, but for sources with PCM, a composition that adds a PCM destination covers more than its base (e.g. for opm_msm6258, sfg01 is Approximate but sfg01/makoto is Yes).

The source types for which the composition and layered profiles are generated are (scc: sources where SCC sounds). The only compositions that keep a real SCC or PSG are the layered forms, `psg_layered` / `scc_layered`. OPLL also stays on the real chip: it joins `layered` as a native lane, and `sfg01_opllrhythm` keeps its rhythm native.

| Profile | psg | scc | opna | opm | opn2 |
|---|---|---|---|---|---|
| sfg01 | No | No | Yes | Yes | Yes |
| makoto | No | No | Yes | Yes | Yes |
| misato | No | No | Yes | Yes | Yes |
| msxaudio | No | No | No | No | No |
| opl3 | No | No | No | No | No |
| layered | No | No | Yes | Yes | Yes |
| psg_layered | Yes | No | No | No | No |
| scc_layered | No | Yes | No | No | No |

The opna / opm / opn2 columns are compositions that add a second cartridge (makoto / msxaudio / opl3 / misato) or a rhythm source (rx21 / opllrhythm); they are not generated for sources the base itself does not accept.

### Profile Descriptions

Each profile maps the musical information extracted from the input VGM to the sound chips available in the corresponding MSX sound cartridge configuration.

When multiple sound sources are present, channels are allocated according to source priorities. Some performance details may not be reproduced due to hardware limitations or the number of available channels.

#### Basic Configurations

- **`sfg01`**: For SFG-01 (OPM / YM2151). Converts performance data from various sound sources to the OPM FM sound generator.
- **`makoto`**: For Makoto (OPNA / YM2608). Converts performance data to the OPNA FM sound generator and maps PCM samples to ADPCM-B.
- **`misato`**: For Misato (OPN3). Performs FM conversion similarly to `makoto`, but PCM playback is unavailable because the cartridge has no ADPCM functionality. Percussion is played using its built-in rhythm sound generator.
- **`msxaudio`**: For MSX-AUDIO (Y8950). Converts OPLL performance data to Y8950 FM, maps OPLL rhythm parts to the Y8950 rhythm sound generator, and plays PCM through Delta-T.
- **`opl3`**: For OPL3 (YMF262). Converts OPLL performance data to OPL3 FM and maps OPLL rhythm parts to the OPL3 rhythm sound generator. PCM playback is not supported.

#### Combination Examples: SFG-01 with Additional Sound Chips

These configurations use SFG-01 for FM playback while combining it with other sound chips for rhythm or PCM playback.

- **`sfg01_opllrhythm`**: Based on `sfg01`, but preserves the original OPLL rhythm parts and plays them directly through the YM2413 rhythm sound generator instead of converting them to FM.
- **`sfg01_opl3`**: Based on `sfg01`, but plays OPLL rhythm parts through the OPL3 (YMF262) rhythm sound generator.
- **`sfg01_makoto`**: Combines SFG-01 with Makoto, using OPNA ADPCM-B for PCM playback.
- **`sfg01_msxaudio`**: Combines SFG-01 with MSX-AUDIO, using Y8950 Delta-T for PCM playback.
- **`sfg01_misato`**: Combines SFG-01 with Misato, playing OPLL and OPNA rhythm parts through Misato's rhythm sound generator. ADPCM is not used.

#### Layered FM Configurations

- **`layered`**: Assigns FM-convertible performance parts to the FM units of multiple sound chips. The same parts can be played simultaneously on up to five sound sources: SFG-01, Makoto (or Misato), OPLL, OPL3, and MSX-AUDIO.

Unlike simple detuning, this feature layers the distinct timbres of different FM sound chips, offering a unique kind of musical experimentation made possible by the MSX platform.

#### Layered SCC Configurations

These configurations preserve the original SCC performance while simultaneously playing the same parts through additional FM sound chips.

- **`scc_layered`**: SCC + SFG-01 (OPM) + Makoto (OPNA), three-layer playback

Parts other than SCC are converted using the same methods as their corresponding basic or layered configurations.

#### Layered PSG Configurations

These configurations preserve the original PSG performance while simultaneously playing the same parts through additional FM sound chips.

- **`psg_layered`**: PSG + SFG-01 (OPM) + Makoto (OPNA), three-layer playback

These profiles are intended for input VGM files containing only PSG sound data.

Note that OPLL is not used as a conversion target in the layered SCC and PSG configurations. Since OPLL supports only one user-defined instrument at a time, it is not well suited to reproducing multiple independent parts with different custom timbres.

#### PCM Handling

PCM data is automatically optimized to fit within the 256 KiB capacity limit by sharing duplicate samples and substituting representative samples where necessary.

PCM playback availability and destination depend on the selected profile and the sound chips included in the configuration.

#### Playback

The generated VGM files can be played using

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