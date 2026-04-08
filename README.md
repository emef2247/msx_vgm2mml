# vgm2mml
MSX-Music（PSG, OPLL）および SCC の VGM ファイルから、MGSDRV 用 MML を生成するスクリプトです。  
生成した MML は https://msxplay.com/editor.html にコピー＆ペーストすることで、そのまま再生できます。

## 機能概要
- VGM（MSX-Music / SCC）を解析し、MGSDRV 形式の MML を自動生成  
- レジスタアクセスに忠実な MML を出力  h

## 使い方
x`x
### コマンド
```bash
python vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug]  vgm
```

### 基本例
```
python vgm2mml.py stem.vgm
```

出力例：
outputs/stem/stem.mml

## オプション
| オプション | 説明 |
|-----------|------|
| `--outdir OUTDIR` | MML ファイルの出力先ディレクトリを指定 |
| `--dump-passes` | 中間ファイル（intermediate files）を出力 |
| `--debug` | デバッグ用ファイルを出力 |

## 制限事項 
- `#alloc` に設定されている値はchごとの文字数です。コンパイル後のバッファサイズに合うよう調整が必要な場合があります
- OPLLは現状ノートの展開のみに対応しています。音色指定は現状未対応です

## 注意事項 
MGSDRV の MML は **コンパイル後、全チャンネルのバッファサイズ合計が 16KB 以内**である必要があります。 しかし **本スクリプトはこの制限を考慮しません**。
そのため、生成されたMMLが大きすぎる場合は、以下のような調整が必要です
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

## Usage
To convert a VGM file to MML, use the following command:
```bash
python vgm2mml.py [-h] [--outdir OUTDIR] [--dump-passes] [--debug] vgm
```

### Example
To convert a stem file:
```
python vgm2mml stem.vgm
```
The output will be saved in `outputs/<stem>/<stem>.mml`.

## Options
| Option | Description |
|--------|-------------|
| `--outdir OUTDIR` | Specify the output directory for the MML file |
| `--dump-passes` | Output intermediate files |
| `--debug` | Output debug files |

## Limitations
- The value set in `#alloc` is the character count per channel. You may need to adjust it to fit the buffer size after compilation.
- OPLL support is currently limited to note expansion only. Tone (instrument) assignment is not yet supported.

## Notes
MGSDRV MML must satisfy the constraint that the total buffer size of all channels after compilation is within 16 KB.
However, this script does not take that limitation into account.

If the generated MML is too large, you may need to:
- Manually adjust the `#alloc` values
- Use macros to reduce data size

## License
MIT License