# vgm2mml
PSG／OPLL／SCCのVGMからMGSDRV用MMLを生成します。
MGSDRV用MMLは https://msxplay.com/editor.html にコピー＆ペーストして再生できます。

## 機能概要
- VGM（MSX-Music / SCC）を解析し、MGSDRV 形式の MML を自動生成  
- レジスタアクセスに忠実な MML を出力

## コマンド一覧

| コマンド | 対応音源 | 概要 |
|----------|----------|------|
| `vgm2mml.py` | PSG, OPLL, SCC | MGSDRV用MMLを出力 |
| `py/vgm_reader.py` | PSG, OPLL, SCC | 入力のlog/traceを出力 |

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
| `--legacy-loops` | PSG/SCC/OPLLの可逆なループ構造化を無効にし、従来のループ・エンベロープ処理を使用 |
| `--legacy-macros` | ループ内部を探索する既定のマクロ強化を無効にし、従来のマクロ処理を使用 |
| `--enhance-macros` | マクロ強化を明示的に有効化（現在は既定）。`--dump-passes`で採用マクロCSVと候補案の文字数を保存 |

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

Copyright (c) 2026 emef2247. Licensed under the [MIT License](LICENSE).

## 謝辞

本プロジェクトのコンパイル・再生検証と開発では、以下のプロジェクトを利用・参照しています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 用途 | 確認した利用条件 |
|---|---|---|
| [MGSC／mgsc-js](https://github.com/digital-sound-antiques/mgsc)（Digital Sound Antiques／Mitsutaka Okazaki） | MML→MGSコンパイル | ラッパーはISC。内包MGSC.COMは別条件 |
| [MGSDRV](https://www.gigamix.jp/mgsdrv/)（Ain／GIGAMIX） | 出力MMLの対象ドライバ・再生検証 | 配布自由・アーカイブ内容の変更不可（公式文書） |
| [libkss-js／libkss](https://github.com/digital-sound-antiques/libkss-js)（Mitsutaka Okazaki・貢献者） | MGS→VGMの再生検証 | ISC。内包ドライバは対象外 |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)（Mitsutaka Okazaki and Contributors） | 開発用PSG FM投影のAY→OPM音色・音量→TL対応を参考にし、外部変換との比較にも利用 | ISC |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) 0.2.0（h1romas4） | 開発用MDX fixtureのコンパイル | MIT |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) 0.15.0（h1romas4） | 開発用MDXのVGM再生・検査 | MIT |
| [mdxtools](https://github.com/vampirefrog/mdxtools)（任意導入） | 開発用MDXメタデータの独立検査 | GPL v3（上流LICENSE） |

使用版・確認元・著作権表示・ライセンス全文・内包ドライバの例外は[第三者の表示](THIRD_PARTY_NOTICES.md)に記録しています。本プロジェクトのMITライセンスと併せて、この表示も配布物に含めてください。外部ツールやJS/WASMパッケージ、Rust helperのバイナリを同梱して配布する場合は、内包ドライバや推移的依存の条件も確認する必要があります。

通常のPythonによるVGM→MML変換に外部コンパイラ・再生ライブラリは不要です。PSG FM投影のSegment処理とターゲット生成は本プロジェクトで実装し、vgm-convを実行時のライブラリ依存にはしていません。

