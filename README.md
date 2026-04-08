# vgm2mml
MSX-Music（OPLL）および SCC の VGM ファイルから、MGSDRV 用 MML を生成するスクリプトです。  
生成した MML は https://msxplay.com/editor.html にコピー＆ペーストすることで、そのまま再生できます。

---

## 機能概要
- VGM（MSX-Music / SCC）を解析し、MGSDRV 形式の MML を自動生成  
- レジスタアクセスに忠実な MML を出力  
---

## 使い方

### コマンド
usage: vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug] [--scc-input {trace,log}] [--psg-input {trace,log}] vgm
vgm2mml.py: error: the following arguments are required: vgm

### 基本例
python vgm2mml.py 02_StartingPoint.vgm

出力例：
outputs/02_StartingPoint/02_StartingPoint.mml

---

## オプション

| オプション | 説明 |
|-----------|------|
| `--outdir OUTDIR` | MML ファイルの出力先ディレクトリを指定 |
| `--dump-passes` | 中間ファイル（intermediate files）を出力 |
| `--debug` | デバッグ用ファイルを出力 |
| `--scc-input {trace,log}` | SCC の入力形式を指定 |
| `--psg-input {trace,log}` | PSG の入力形式を指定 |

---
## 制限事項 
- `#alloc` に設定されている値はchごとの文字数です。コンパイル後のバッファサイズに合うよう調整が必要な場合があります
- OPLLは現状ノートの展開のみに対応しています。音色指定は現状未対応です

## 注意事項 
MGSDRV の MML は **コンパイル後、全チャンネルのバッファサイズ合計が 16KB 以内**である必要があります。 しかし **本スクリプトはこの制限を考慮しません**。
そのため、生成されたMMLが大きすぎる場合は、以下のような調整が必要です
- `#alloc` の値を手動で調整  
- マクロ化してデータ量を削減  

---

## ライセンス
MIT License