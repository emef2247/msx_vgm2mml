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
| `vgm2mml_grid.py` | OPLL | ステップグリッドで量子化した MML を出力。ユーザ定義音色・リズム音源に対応 |

---

## vgm2mml.py

### 使い方
```bash
python vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug] vgm
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
| `--dump-passes` | 中間ファイル（intermediate files）を出力 |
| `--debug` | デバッグ用ファイルを出力 |

---

## vgm2mml_grid.py

OPLL（YM2413）専用のコマンドです。音符をステップグリッドに量子化して MML を生成します。  
**ユーザ定義音色**および**リズム音源**に対応しています。

### 使い方
```bash
python vgm2mml_grid.py [-h] [--outdir OUTDIR] [--bpm BPM] [--video {ntsc,pal}]
                       [--ticks-per-step N] [--base-ms2 PATH] [--debug]
                       vgm
```

### 基本例
```
python vgm2mml_grid.py stem.vgm
```

出力例：
```
stem.opll.mml
```

### オプション
| オプション | 説明 |
|-----------|------|
| `--outdir OUTDIR` | MML ファイルの出力先ディレクトリを指定 |
| `--bpm BPM` | テンポを BPM で指定（デフォルト: VGM から自動検出） |
| `--video {ntsc,pal}` | ビデオ方式の指定（デフォルト: `ntsc`） |
| `--ticks-per-step N` | ステップグリッドのティック数を手動で指定（最小値: 2） |
| `--base-ms2 PATH` | ベースプリセット楽器ライブラリとして使用する MS2 ファイルのパスを指定 |
| `--debug` | デバッグ情報を追加出力 |

### 対応機能
- **ユーザ定義音色**: VGM に含まれる OPLL ユーザパッチを MML の `@` 定義として出力
- **リズム音源**: バスドラム (b)・スネア (s)・タム (m)・シンバル (c)・ハイハット (h) をリズムトラックとして出力
- **ステップグリッド量子化**: 音符を 16 分音符単位のグリッドに配置。付点音符・タイによる延長にも対応

---

## 制限事項
- `#alloc` に設定されている値はチャンネルごとの文字数です。コンパイル後のバッファサイズに合うよう調整が必要な場合があります
- `vgm2mml_grid.py` は現状 **OPLL のみ**対応です

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
| `vgm2mml_grid.py` | OPLL | Outputs step-grid quantized MML. Supports user-defined patches and rhythm instruments |

---

## vgm2mml.py

### Usage
```bash
python vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug] vgm
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

---

## vgm2mml_grid.py

A dedicated command for OPLL (YM2413). Notes are quantized to a step grid and output as MML.  
Supports **user-defined patches** and **rhythm instruments**.

### Usage
```bash
python vgm2mml_grid.py [-h] [--outdir OUTDIR] [--bpm BPM] [--video {ntsc,pal}]
                       [--ticks-per-step N] [--base-ms2 PATH] [--debug]
                       vgm
```

### Example
```
python vgm2mml_grid.py stem.vgm
```
Output: `stem.opll.mml`

### Options
| Option | Description |
|--------|-------------|
| `--outdir OUTDIR` | Specify the output directory for the MML file |
| `--bpm BPM` | Song tempo in BPM (default: auto-detected from VGM) |
| `--video {ntsc,pal}` | Video system: `ntsc` (default) or `pal` |
| `--ticks-per-step N` | Override ticks per step for grid quantization (minimum: 2) |
| `--base-ms2 PATH` | Path to an MS2 file to use as the base preset instrument library |
| `--debug` | Print extra debug information |

### Supported Features
- **User-defined patches**: OPLL user patches found in the VGM are exported as `@` instrument definitions in the MML
- **Rhythm instruments**: Bass drum (b), snare (s), tom (m), cymbal (c), and hi-hat (h) are output as a rhythm track
- **Step-grid quantization**: Notes are placed on a 16th-note step grid, with support for dotted notes and ties

---

## Limitations
- The value set in `#alloc` is the character count per channel. You may need to adjust it to fit the buffer size after compilation.
- `vgm2mml_grid.py` currently supports **OPLL only**.

## Notes
MGSDRV MML must satisfy the constraint that the total buffer size of all channels after compilation is within 16 KB.
However, this script does not take that limitation into account.

If the generated MML is too large, you may need to:
- Manually adjust the `#alloc` values
- Use macros to reduce data size

## License
MIT License
