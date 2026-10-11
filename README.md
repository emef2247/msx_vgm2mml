# msx_vgm2mml

VGMから、検査可能な中間表現を経由してMGSDRV用MMLを生成するツールです。PSG／OPLL／SCCの入力に対応しています。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報を、MSXで扱えるMMLとして取り出すことです。

生成したMMLは、[MSXplayのエディタ](https://msxplay.com/editor.html)にコピー＆ペーストして再生できます。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

`--outdir`でMMLの出力先を指定します。省略した場合の出力例は`outputs/input/input.mml`です。fixtureの検証には入力と異なる出力先を指定してください。

### 入力と出力

| 入力 | 主な出力・変換経路 |
|---|---|
| PSG | イベントCSV・SegmentからMGSDRV用MMLを生成 |
| OPLL（MSX-MUSIC） | レジスタイベントの解析結果からMGSDRV用MMLを生成。リズムも処理 |
| SCC | イベントCSV・Segmentと波形情報からMGSDRV用MMLを生成 |

通常のPythonによるVGM→MML変換に、外部コンパイラ・再生ライブラリは不要です。MGSへのコンパイルや再生検証には、別途ツールを用意してください。

## 生成されるMMLの確からしさ

VGMには音符そのものではなく、音源への書き込みとその時刻が記録されています。したがって、VGMからMMLを作る際には、発音・停止・音程・音量・音色の変化を解釈し、MMLで表せる時間単位に変換する必要があります。

本プロジェクトでは、元VGMのイベント、中間の解析結果、ターゲットのMMLを区別します。PSG／SCCは次の段階に分けて処理します。

```text
VGM → イベントCSV → Segment → MGSDRV用MML
```

- **イベント・中間表現**：元VGMのレジスタ操作と解析結果を検査できる形で保存します。
- **ターゲットMML**：MGSDRVの音価・命令・データ量の制約に合わせて表現します。
- **検証結果**：音長補正の適用状況、コンパイル結果、OPLLメロディのKEYON数などを確認します。

PSG／SCCは休符だけのチャンネルと休符中の不要な設定を省き、一定音程の音量推移をソフトウェアエンベロープへ抽出します。反復部分のループ構造化とマクロ化も行います。

MMLの生成に成功したことは、元VGMと音が一致することを意味しません。コンパイルやKEYON数の比較に加え、再生して音程・音色・発音・タイミングを確認してください。

### 音長の補正

**`--normalize-lengths`は既定で無効です。** 有効にすると、OPLLの発音間隔から共通の音長基準を推定し、MML生成時に音長・ゲートを補正します。

```bash
python vgm2mml.py tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalize-lengths --dump-passes
```

曲ごとに音長基準の推定と安全性を自動判定し、適用できない場合は全パートを従来の出力のまま維持します。OPLLリズムも共通基準で処理します。

PSG／SCCはOPLLから推定した基準に合わせて音長を変換し、ソフトウェアエンベロープのフレーム指定は維持します。**現状、PSG／SCCだけの曲には補正効果がありません。** 元の`vgmticks`やSegment CSVは変更しません。

コンソールと`<stem>.normalization.json`に、`applied`（適用）または`unchanged`（未適用）とその理由を記録します。`--dump-passes`を併用すると、補正前MML、補正した音のCSV、ループ判定CSVも保存します。`--raw-ticks`との併用はできません。

詳細は[音長補正の仕様](docs/note_normalization.md)を参照してください。

## フォルダ指定による一括変換とMGS生成

`scripts/batch_vgm_to_mgs.py`は、入力ディレクトリ以下の`.vgm`／`.vgz`を再帰的に変換し、MGSへコンパイルします。

```bash
# 通常の変換
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/opll

# 音長補正を有効にして比較
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/normalize-lengths/opll --normalize-lengths
```

入力と出力は別フォルダにしてください。通常実行と補正実行も出力先を分けると、結果を比較できます。

MMLからMGSへのコンパイルには、PATH上のネイティブ`mgsc`を優先して使用します。実行ファイルは`--mgsc PATH`で指定できます。

```bash
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/opll --mgsc /path/to/mgsc
```

各曲のMMLと`convert.log`／`compile.log`を保存し、失敗しても次の曲へ進みます。全曲の結果は`results.csv`／`results.json`で確認できます。

コンパイル成功曲のOPLLメロディKEYON数の比較には、Node.jsとlibkss-jsが必要です。比較を省く場合は`--skip-keyon-counts`を指定してください。依存関係と詳細は[バッチ実行](docs/batch_mgs.md)を参照してください。

## 主なオプション

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

その他のオプションは`python vgm2mml.py --help`を参照してください。

### 同期コメント

統合MMLのstepコメントは、再生中の全チャンネルで音符・休符の境界が揃う位置に自動挿入します。表示間隔は`--sync-min-gap`で調整できます。

仕様と出力例は[同期ポイント](docs/mml_sync.md)を参照してください。

## 変換結果の見方

一括変換では、各曲のログと全曲の集計を使って結果を確認します。

| ファイル・項目 | 読み方 |
|---|---|
| `convert.log` | VGM→MML変換の結果と、音長補正の適用・未適用を確認 |
| `compile.log` | MML→MGSコンパイルの結果と、エラーの内容を確認 |
| `<stem>.normalization.json` | 音長補正の`applied`／`unchanged`と、その理由を確認 |
| `results.csv`／`results.json` | 全曲のコンパイル結果（`success`、`buffer_error`など）を確認 |
| OPLLメロディKEYON合計・不足数・超過数 | コンパイル成功曲の発音数を比較。未実施は空欄で、0とは扱わない |

KEYON数が一致していても、音程・音色・ゲート・タイミングの一致を保証するものではありません。コンパイルの成功、発音数の比較、聴感による確認は、それぞれ別の結果として扱ってください。

## MGSDRVのバッファ制限

MGSDRV用MMLは、**コンパイル後の全チャンネルのバッファサイズ合計を16KB以内**に収める必要があります。現状、本スクリプトはこの上限に収まることを保証しません。

`#alloc`にはチャンネルごとの文字数を設定していますが、MMLの文字数とコンパイル後のバッファサイズは異なります。コンパイル結果に応じて調整が必要になる場合があります。

生成したMMLが大きすぎる場合は、`#alloc`の値を手動で調整するか、反復部分のマクロ化などでデータ量を減らしてください。

## 中間結果と検証

```bash
python vgm2mml.py input.vgm --outdir OUTPUT --dump-passes --vgmticks
python -m unittest discover -s tests -v
```

イベントlog／trace、PASS0–3、PSG／SCC Segment、SCC波形CSVを保存し、元のデータと出力結果の対応を確認できます。

`--dump-passes`では、ソフトウェアエンベロープとして抽出した区間を`*.target_notes.csv`、適用後の音源別MMLを`*.target.mml`に保存します。構成と中間フォーマットは[PSG/SCC Segment pipeline](docs/psg_scc_segments.md)を参照してください。

## 構成

- `vgm2mml.py`：通常変換の入口。
- `py/vgm_reader.py`：VGMの読み込みと、入力のlog／trace出力。
- `scripts/batch_vgm_to_mgs.py`：一括変換、MGSコンパイル、OPLLメロディKEYON数の比較。
- [PSG/SCC Segment pipeline](docs/psg_scc_segments.md)：PSG／SCCの処理構成と中間フォーマット。
- [音長補正の仕様](docs/note_normalization.md)：音長基準の推定と補正の条件。
- [同期ポイント](docs/mml_sync.md)：統合MMLの同期コメント。
- [バッチ実行](docs/batch_mgs.md)：一括変換の依存関係と結果の確認方法。

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

