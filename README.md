## msx_vgm2mml

VGMに記録されたレジスタ操作を解析し、音符・音価・音量・音色などの演奏情報を抽出して、MSX向けMML（MGSDRV用）を生成するツールです。　Python 3.10以降が必要です。

### 使い方

#### VGMファイルを指定してMMLを生成

```bash
# MMLのみ生成
python vgm2mml.py INPUT.vgm --outdir OUTDIR
```

もし、MMLの生成からMGSの生成までを自動で行いたい場合は、`scripts/export_mgs.py`(後述）を利用してください。


#### VGMファイルを含むディレクトリを指定して、mmlとmgsを一括変換

```bash
#MMLだけではなく.mgsまで一括自動変換。
python scripts/export_mgs.py INDIR --outdir OUTDIR
```

MGSの生成にはMGSC又はmgsc-jsが必要です。また、生成結果のKey-On検証にはlibkss-jsを使用します。これらの環境構築については、[環境構築](docs/setup_mgs_tools.ja.md) を参照してください。

これら外部ツールを自動でインストールしたい場合は [scripts/setup_mgs_tools.py](scripts/setup_mgs_tools.py) を利用してください。

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

VGMとMMLでは表現方法や制約が異なるため、元の演奏を完全に再現できるとは限りません。

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

使用した第三者コンポーネントのバージョン、参照元、著作権表示、ライセンス条件、および再配布時の注意事項は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

解析とMML生成はPythonで実装しています。外部ツールは主にコンパイル、再生確認、比較、およびテスト生成に使用しています。