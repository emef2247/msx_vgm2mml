# いろんなサウンドカートリッジで鳴らしてみる

`--vgm-variants` オプションを使うと、MSXのさまざまなサウンドカートリッジ向けにVGMを生成できます。

SFG-01（OPM）、Makoto（OPNA）、Misato（OPN3）、MSX-AUDIO（Y8950）、OPL3（YMF262）などを使って、同じ曲を異なる音源で楽しめます。

```bash
python scripts/export_mgs.py <入力.vgm> --outdir <出力先> --vgm-variants --force
```

生成したVGMは `vgm-variants/` 以下に、カートリッジの構成ごとに保存されます。

## 基本構成

1本のサウンドカートリッジを中心に演奏する構成です。

| プロファイル | 使用する音源 | 演奏内容 |
|---|---|---|
| `sfg01` | SFG-01（OPM / YM2151） | 各音源の演奏パートをOPMで再生 |
| `makoto` | Makoto（OPNA / YM2608） | FMパートとリズムをOPNAで、PCMをADPCM-Bで再生 |
| `misato` | Misato（OPN3） | FMパートとリズムをOPN3で再生（PCMなし） |
| `msxaudio` | MSX-AUDIO（Y8950） | OPLLなどの演奏パートをY8950で再生。PCMにも対応 |
| `opl3` | OPL3（YMF262） | OPLLなどの演奏パートをOPL3で再生（PCMなし） |

対応する入力音源やチャンネル数には制限があります。

## カートリッジを組み合わせる構成

2本以上のサウンドカートリッジを組み合わせ、FM、リズム、PCMを分担して演奏します。

### PCMを追加する組み合わせ

| プロファイル | FM・リズム | PCM |
|---|---|---|
| `sfg01/makoto` | SFG-01 | Makoto |
| `sfg01/msxaudio` | SFG-01 | MSX-AUDIO |
| `makoto/msxaudio` | Makoto | Makoto ＋ MSX-AUDIO |
| `makoto/msxaudio/msxaudio` | Makoto | Makoto ＋ MSX-AUDIO × 2 |
| `misato/msxaudio` | Misato | MSX-AUDIO |
| `msxaudio/msxaudio` | MSX-AUDIO（1台目） | MSX-AUDIO × 2 |
| `opl3/makoto` | OPL3 | Makoto |
| `opl3/msxaudio` | OPL3 | MSX-AUDIO |

PCMを複数のカートリッジに割り当てる構成では、同時に再生できるPCMの数も増えます。

### リズム音源を追加する組み合わせ

| プロファイル | メロディ | リズム |
|---|---|---|
| `sfg01/misato` | SFG-01（OPM） | Misato（OPN3） |
| `sfg01/opl3` | SFG-01（OPM） | OPL3（YMF262） |
| `sfg01/opllrhythm` | SFG-01（OPM） | OPLL（YM2413） |

`opllrhythm` は、OPLL本来のリズム音源をそのまま使用する構成です。

## 複数の音源を重ねて演奏する構成

### FM音源のレイヤー演奏

**`layered`**

同じ演奏パートを複数のFM音源で同時に鳴らします。

最大で以下の5種類の音源を重ねて演奏できます。

- SFG-01（OPM）
- Makoto（OPNA）またはMisato（OPN3）
- OPLL（YM2413）
- OPL3（YMF262）
- MSX-AUDIO（Y8950）

異なるFM音源の音色を重ね合わせる、MSXならではのお遊び機能です。

### SCC・PSGのレイヤー演奏

| プロファイル | 同時に鳴る音源 |
|---|---|
| `layered/scc` | SCC ＋ SFG-01（OPM）＋ Makoto（OPNA） |
| `layered/psg` | PSG ＋ SFG-01（OPM）＋ Makoto（OPNA） |

元のSCCやPSGの音を残しながら、同じ演奏パートをFM音源でも鳴らします。

なお、これらの構成ではOPLLへの変換は行いません。

## 再生方法

生成したVGMは、MSX実機のVGMPlayや、Mami-VSIF Pro経由のMAmidiMEmoなどで再生できます。

実機がなくても、対応するVGMプレーヤーで楽しめます。

---

# Playing on Various Sound Cartridges

The `--vgm-variants` option generates VGM files for various MSX sound cartridge configurations.

Enjoy the same music on different sound chips, including SFG-01 (OPM), Makoto (OPNA), Misato (OPN3), MSX-AUDIO (Y8950), and OPL3 (YMF262).

```bash
python scripts/export_mgs.py <input.vgm> --outdir <output> --vgm-variants --force
```

Generated VGM files are saved under `vgm-variants/`, organized by sound cartridge configuration.

## Basic Configurations

These configurations use a single sound cartridge as the primary sound source.

| Profile | Sound Chip | Playback |
|---|---|---|
| `sfg01` | SFG-01 (OPM / YM2151) | Plays converted musical parts using OPM FM synthesis |
| `makoto` | Makoto (OPNA / YM2608) | Plays FM and rhythm parts using OPNA, and PCM using ADPCM-B |
| `misato` | Misato (OPN3) | Plays FM and rhythm parts using OPN3 (no PCM support) |
| `msxaudio` | MSX-AUDIO (Y8950) | Plays OPLL and other supported parts using Y8950, with PCM support |
| `opl3` | OPL3 (YMF262) | Plays OPLL and other supported parts using OPL3 (no PCM support) |

Supported input sound chips and available channels vary by configuration.

## Combined Cartridge Configurations

These configurations combine two or more sound cartridges to share FM, rhythm, and PCM playback.

### Adding PCM Playback

| Profile | FM / Rhythm | PCM |
|---|---|---|
| `sfg01/makoto` | SFG-01 | Makoto |
| `sfg01/msxaudio` | SFG-01 | MSX-AUDIO |
| `makoto/msxaudio` | Makoto | Makoto + MSX-AUDIO |
| `makoto/msxaudio/msxaudio` | Makoto | Makoto + MSX-AUDIO × 2 |
| `misato/msxaudio` | Misato | MSX-AUDIO |
| `msxaudio/msxaudio` | MSX-AUDIO (first cartridge) | MSX-AUDIO × 2 |
| `opl3/makoto` | OPL3 | Makoto |
| `opl3/msxaudio` | OPL3 | MSX-AUDIO |

Configurations with multiple PCM-capable cartridges can play more simultaneous PCM sounds.

### Adding Rhythm Playback

| Profile | Melody | Rhythm |
|---|---|---|
| `sfg01/misato` | SFG-01 (OPM) | Misato (OPN3) |
| `sfg01/opl3` | SFG-01 (OPM) | OPL3 (YMF262) |
| `sfg01/opllrhythm` | SFG-01 (OPM) | OPLL (YM2413) |

The `opllrhythm` configuration preserves the original OPLL rhythm sound rather than converting it to another FM sound chip.

## Layered Sound Configurations

### Layered FM Playback

**`layered`**

Plays the same musical parts simultaneously on multiple FM sound chips.

Up to five sound sources can be layered:

- SFG-01 (OPM)
- Makoto (OPNA) or Misato (OPN3)
- OPLL (YM2413)
- OPL3 (YMF262)
- MSX-AUDIO (Y8950)

Unlike simple detuning, this feature combines the distinct timbres of different FM sound chips — a unique way to enjoy music on the MSX.

### Layered SCC and PSG Playback

| Profile | Simultaneous Sound Sources |
|---|---|
| `layered/scc` | SCC + SFG-01 (OPM) + Makoto (OPNA) |
| `layered/psg` | PSG + SFG-01 (OPM) + Makoto (OPNA) |

These configurations preserve the original SCC or PSG sound while playing the same musical parts through additional FM sound chips.

OPLL is not used as a conversion target in these configurations.

## Playback

Generated VGM files can be played on real MSX hardware using VGMPlay, or through MAmidiMEmo with Mami-VSIF Pro.

You can also enjoy the generated VGM files using compatible software VGM players, even without real hardware.