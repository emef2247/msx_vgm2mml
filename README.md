# msx_vgm2mml

VGMに記録されたレジスタ操作から音符・音価・音量・音色などの演奏情報を抽出し、MSX向けの構造化されたMML（MGSDRV用）を生成するツールです。対応する入力ではMGSも一括出力できます。

元のVGMのレジスタ操作を、検査可能な中間表現（イベント／Segment）として保持し、音楽的に構造化されたMMLへ変換することを目指しています。Python 3.10以降を使用します。

## 使い方

VGMファイルを置いたディレクトリを指定して、一括変換します。

```bash
python scripts/batch_vgm_to_mgs.py INDIR --outdir OUTDIR
```

既定の設定で、MML・MGS・変換レポートを生成します。出力先の `results.csv` と各曲のログで、成功・失敗の内容を確認できます。

生成したMMLは、[MSXplayのエディタ](https://msxplay.com/editor.html)にコピー＆ペーストして再生することもできます。

MGSへのコンパイルにはMGSCが必要です。環境構築や検証ツールの準備については、[バッチ実行](docs/batch_mgs.md)を参照してください。

### 主なオプション

| オプション | 説明 |
|---|---|
| `--outdir OUTDIR` | 変換結果の出力先ディレクトリ（必須） |
| `--force` | 対応可能な範囲で未対応のレジスタ操作を診断付きで省略して続行 |
| `--timeout SECONDS` | 各処理段階のタイムアウト（既定1200秒） |

`--force` を指定しても、すべての入力が変換できるわけではありません。省略が発生した場合はレポートを確認してください。

その他のオプションは `python scripts/batch_vgm_to_mgs.py --help` を参照してください。

## 対応する音源

| VGMの音源 | 主なMGS向け出力 |
|---|---|
| PSG／SSG（AY系） | 演奏構造を抽出してMGSDRV用MMLへ変換 |
| OPLL（YM2413） | メロディ・リズムをMGSDRV用MMLへ変換 |
| SCC | 波形・音量変化などを解析してMGSDRV用MMLへ変換 |

PSG／SCCでは、音量変化からソフトウェアエンベロープを抽出し、反復部分のループ構造化やマクロ化も行います。

音源の組み合わせやVGM内の制御内容によって対応範囲は異なります。

## 変換と再生の注意点

VGMには音符ではなく音源レジスタへの書き込みが記録されているため、MML生成時には発音・音量・音色・音程などを解釈します。元の演奏をMMLとして表現する過程で、時間分解能や音源仕様による制約が生じます。

**MML生成、MGSへのコンパイル、MSXでの再生確認は別の検証段階です。** コンパイルに成功しても、元の音声との一致や実機・エミュレータでの再生成功を保証するものではありません。

MGSにはMGSDRVのバッファ制約があり、データ量によってはコンパイルできない場合があります。

また、OPLLメロディのKey-On数比較は検証の一部であり、音程・音色・タイミングなどの完全な一致を保証するものではありません。

変換結果の検証方法や既知の制約については、[バッチ実行](docs/batch_mgs.md)および[MGS定義領域](docs/mgs_definition_storage.md)を参照してください。

## 構成

- `vgm2mml.py`：単体VGMの解析・MML生成
- `scripts/batch_vgm_to_mgs.py`：MML・MGSの一括生成と検証
- `py/`：音源解析、中間表現、ターゲット生成
- `scripts/`：検証・比較・補助ツール

## ライセンス

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

本プロジェクトで参照・利用する第三者コンポーネントのライセンスおよび著作権表示については、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

## 謝辞

本プロジェクトの開発、検証、比較、およびテスト生成では、以下のツールやプロジェクトを利用または参考にしています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 |
|---|---|
| [MGSC／mgsc-js](https://github.com/digital-sound-antiques/mgsc) | MML→MGSコンパイル |
| [MGSDRV](https://www.gigamix.jp/mgsdrv/) | 出力MMLの対象ドライバ・再生検証 |
| [libkss-js／libkss](https://github.com/digital-sound-antiques/libkss-js) | MGS再生・Key-On数などの検証 |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | PSG→FMの音色・音量対応方式の参考 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) | 開発用MDX fixtureのコンパイル |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) | 開発用MDXのVGM再生・検査 |
| [mdxtools](https://github.com/vampirefrog/mdxtools) | MDXメタデータの独立検査 |

使用した第三者コンポーネントのバージョン、参照元、著作権表示、ライセンス条件、および再配布時の注意事項は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

解析とMML生成はPythonで実装しています。外部ツールは主にコンパイル、再生確認、比較、およびテスト生成に使用します。
