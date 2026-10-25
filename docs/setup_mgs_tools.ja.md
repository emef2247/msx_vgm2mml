# MGS一括生成用ツールのセットアップ

`msx_vgm2mml`でVGM/VGZからMMLとMGSを一括生成するために、JavaScript版MGSC（`mgsc-js`）と再生検証用`libkss-js`を準備します。MSX実機版MGSCのインストールは不要です。ネイティブ実行ファイル版`mgsc`がPATHにある場合、既存のバッチ処理はそちらを優先します（本スクリプトはその設定を変更しません）。

## 前提条件

- Python 3
- Node.jsとnpm（どちらもコマンドとして実行できること）
- `msx_vgm2mml`のリポジトリ一式
- 初回インストール時のインターネット接続

WindowsではPowerShell、Linux/WSLではシェルから、**リポジトリのルート**で以下を実行します。WSLで利用する場合はWSL内にNode.js/npmを導入してください。

## インストール

```sh
python scripts/setup_mgs_tools.py
```

このコマンドは、リポジトリ内で次のnpmパッケージをインストールします。

- `mgsc-js@2.0.0`：MMLをMGSにコンパイル
- `libkss-js`：MGSの再生・Key-On検証

`npm install --no-save --package-lock=false`を使うため、グローバルインストールや`package-lock.json`の生成は行いません。既存のnpm依存関係に影響する可能性はあるため、必要に応じて作業ツリーの状態を確認してください。`libkss-js`はバージョンを固定していません。

## 環境確認のみ

```sh
python scripts/setup_mgs_tools.py --check
```

インストールは行わず、Node.js/npm、MGSCの初期化、libkss-jsの読み込みを確認します。**この確認はlibkssによる実際の再生結果の正しさまでは保証しません。**

## MGSを一括生成する

```sh
python scripts/export_mgs.py INPUT_DIR --outdir OUTPUT_DIR --force
```

単一の`.vgm`/`.vgz`ファイルも入力できます。出力先には楽曲ごとの`tracks/`（MML/MGS）と`_diagnostics/`（レポート・ログ）が作られます。Key-On検証を省略する場合は`--skip-keyon-counts`を付けてください。

```sh
python scripts/export_mgs.py INPUT_DIR --outdir OUTPUT_DIR --force --skip-keyon-counts
```

`export_mgs.py`の既定の正規化設定、`--force`の制限、エラー判定については[一括変換の説明](batch_mgs.ja.md)を参照してください。MGSのコンパイル成功だけで、元VGMと同等の再生が保証されるわけではありません。

## よくある問題

- **`node`または`npm`が見つからない**：Node.js/npmをインストールし、PATHを確認してください。
- **`mgsc-js`を読み込めない**：リポジトリのルートでセットアップを再実行してください。WSLとWindowsのnpm環境は別です。
- **`libkss-js`を読み込めない**：同様にセットアップを再実行してください。検証不要なら変換時に`--skip-keyon-counts`を使用できます。
- **npmの権限・ネットワークエラー**：npmのログとネットワーク設定を確認してください。`sudo npm install`を安易に実行しないでください。
- **ネイティブ版mgscが優先される**：既存のバッチ仕様です。JS版を明示する場合は`--mgsc-module`の利用を検討してください。詳細は[一括変換の説明](batch_mgs.ja.md)を参照してください。

本スクリプトはPython、Node.js、npm自体をインストールしません。MGSCおよびlibkssの配布条件についてはリポジトリの`THIRD_PARTY_NOTICES.md`を確認してください。
