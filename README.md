## msx_vgm2mml

VGMに記録されたレジスタ操作を解析し、音符・音価・音量・音色などの演奏情報を抽出して、MSX向けMML（MGSDRV用）を生成するツールです。対応する入力では、MGSも一括で生成できます。

変換途中の情報は、確認可能な中間表現（イベント／Segment）として保持します。元のVGMのレジスタ操作と生成結果の対応関係を追跡できる形で、音楽的に構造化されたMMLへ変換することを目指しています。Python 3.10以降が必要です。

### 使い方

#### VGMファイルを指定してMMLを生成

```bash
# MMLのみ生成
python vgm2mml.py INPUT.vgm --outdir OUTDIR
```

生成したMMLは、[MSXplayのエディタ](https://msxplay.com/editor.html) にコピー＆ペーストして再生できます。　また、MGSCでコンパイルすることでMGSを得ることができます。

もし、MMLの生成後、MGSの生成までを自動で行いたい場合は、scripts/export_mgs.pyを利用してください。


#### VGMファイルを含むディレクトリを指定して、mmlとmgsを一括変換

```bash
#MMLだけではなく.mgsまで一括自動変換。
python scripts/export_mgs.py INDIR --outdir OUTDIR
```

変換結果は `_diagnostics/results.csv` と各曲の診断ログで確認できます。

MGSの生成にはMGSC（mgsc-js）が必要です。また、生成結果のKey-On検証にはlibkss-jsを使用します。これらの環境構築については、[環境構築](docs/setup_mgs_tools.ja.md) を参照してください。

自動インストールのためのスクリプトは [外部ツール・自動インストールスクリプト](scripts/setup_mgs_tools.py) です

#### 出力構成

生成されたMML・MGS・診断情報は、共通のディレクトリ構成で出力されます。

各入力フォルダを1つの出力パッケージとして扱い、完成したMMLおよびMGSは `tracks/` 直下に出力します。

ログ・中間ファイル・往復VGMは `_diagnostics/<stem>/` に保存します。
入力ファイルのコピーは `_source_inputs/` に保存します。

再帰的に入力を処理する場合は、入力ディレクトリの相対構造を維持したまま出力します。

たとえば、

```text
INDIR/vgmrips.net/SALAMD/曲.vgm
```

は、

```text
OUTDIR/vgmrips.net/SALAMD/tracks/曲.mml
OUTDIR/vgmrips.net/SALAMD/tracks/曲.mgs
```

として出力されます。

`tracks/<曲名>/` のようなサブディレクトリは作成しません。

`--outdir` は省略可能です。その場合は各VGMファイルの親ディレクトリを出力先として使用します。

#### 主なオプション

| オプション | 説明 |
| --- | --- |
| --outdir OUTDIR | 入力の相対ディレクトリ構造を維持して出力 |
| --force | 未対応のレジスタ操作を診断付きで省略し、可能な範囲で変換を継続 |
| --timeout SECONDS | 各処理段階のタイムアウト（既定1200秒） |

`--force` を指定しても、すべての入力を変換できるわけではありません。未対応処理を一部省略しながら継続できる場合のみ有効です。省略内容についてはレポートを確認してください。

### 対応する音源

| VGMの音源 | 主なMGS向け出力 |
| --- | --- |
| PSG／SSG（AY系） | 演奏構造を抽出してMGSDRV用MMLへ変換 |
| OPLL（YM2413） | メロディ・リズムをMGSDRV用MMLへ変換 |
| SCC | 波形・音量変化などを解析してMGSDRV用MMLへ変換 |

PSG／SCCでは、音量変化からソフトウェアエンベロープを抽出し、反復部分のループ化やマクロ化も行います。

対応できる内容は、音源の組み合わせやVGM内で使用されている制御方法によって異なります。

### 変換と再生の注意点

VGMには音符そのものではなく、音源レジスタへの書き込みとそのタイミングが記録されています。

そのため本ツールでは、発音・音量・音色・音程などの変化を解析し、MGSDRVで再生できるMMLへ変換します。

ただし、VGMとMMLでは表現方法や制約が異なるため、元の演奏を完全に再現できるとは限りません。

また、MGSにはMGSDRVのバッファ制約があります。そのため、生成したMMLをコンパイルしても、データ量によってはMGSを生成できない場合があります。

その場合は、生成されたMMLを手動で編集または分割してください。

### 構成

- `vgm2mml.py` : 単体VGMの解析とMML生成
- `scripts/export_mgs.py` : MML・MGS・診断情報の一括出力
- `tests/script/` : 自動テスト
- `tests/fixtures/` : テスト用入力データおよび参照データ
- `py/` : 音源解析、中間表現、MML生成処理
- `scripts/` : 変換・検証・補助ツール

### ライセンス

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

本プロジェクトで利用または参照している第三者コンポーネントのライセンスおよび著作権表示については、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

### 謝辞

本プロジェクトの開発、検証、およびテスト生成では、以下のツールやプロジェクトを利用または参考にしています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 用途 |
| --- | --- |
| [MGSC／mgsc-js](https://github.com/digital-sound-antiques/mgsc) | MML→MGSコンパイル |
| [MGSDRV](https://www.gigamix.jp/mgsdrv/) | 出力MMLの対象ドライバ・再生検証 |
| [libkss-js／libkss](https://github.com/digital-sound-antiques/libkss-js) | MGS再生・Key-On数などの検証 |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | PSG→FMの音色・音量対応方式の参考 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) | 開発用MDX fixtureのコンパイル |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) | 開発用MDXのVGM再生・検査 |
| [mdxtools](https://github.com/vampirefrog/mdxtools) | MDXメタデータの独立検査 |

使用した第三者コンポーネントのバージョン、参照元、著作権表示、ライセンス条件、および再配布時の注意事項は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

解析とMML生成はPythonで実装しています。外部ツールは主にコンパイル、再生確認、比較、およびテスト生成に使用しています。