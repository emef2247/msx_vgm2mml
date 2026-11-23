# いろんなサウンドカートリッジで鳴らしてみる

通常の出力に加えて、`--vgm-variants` を付けて実行すると、サウンドカートリッジの構成ごとの VGM を別途生成します。SFG-01（OPM）や Makoto（OPNA）といったカートリッジで、変換した曲をそのまま鳴らすための機能です。

MML 生成用に構築した音楽情報を、MSX のサウンドカートリッジに搭載された別の音源へ割り当ててみる機能です。現在の対象は SFG-01（OPM）、Makoto（OPNA）、Misato（OPN3）、MSX-AUDIO（Y8950）、OPL3（YMF262）です。

    python scripts/export_mgs.py <入力.vgm> --outdir <出力先> --vgm-variants --force

生成物は `vgm-variants/<1本目のプロファイル名>/<曲名>.vgm` に出力されます。組み合わせは1本目のフォルダの下に、追加要素の名前のサブフォルダに入ります（例: `vgm-variants/sfg01/makoto/<曲名>.vgm`、`vgm-variants/sfg01/scc/<曲名>.vgm`）。1本目と同一内容になる組み合わせは出力されません。生成できない構成は理由とともにスキップされ、診断が `_diagnostics` に残ります。

1本目のカートリッジのプロファイルが入力音源ごとに生成されるかの一覧です（○：生成される、△：制限あり・未変換部分あり、—：生成されない）。

| プロファイル | psg | psg_scc | opll | dcsg | dcsgx2 | apu | apu_fds | huc6280 | opna | opm | opn2 | opm_msm6258 | opm_segapcm | opn | opn_segapcm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sfg01 | ○ | ○ | ○ | ○ | ○ | ○ | ○ | △ | ○ | ○ | △ | △ | △ | ○ | △ |
| makoto | ○ | ○ | ○ | ○ | ○ | ○ | ○ | △ | ○ | ○ | ○ | ○ | △ | ○ | △ |
| misato | ○ | ○ | ○ | ○ | ○ | △ | △ | △ | △ | ○ | △ | △ | △ | ○ | △ |
| msxaudio | ○ | — | ○ | ○ | ○ | ○ | △ | △ | — | — | — | — | — | — | — |
| opl3 | ○ | — | ○ | ○ | ○ | ○ | ○ | △ | — | — | — | — | — | — | — |

msxaudio / opl3 の apu_fds・huc6280 の △ は、波形音源の声数が上限を超えるためで、`--force` 指定時に上限を超えたレーンを省略して生成します。

opm_segapcm の △ は、SegaPCM が最大16声の PCM で、1台の PCM では1声へのミックスや 256KiB 予算による省略が入るためです。PCM の行き先を足す組み合わせ（makoto/msxaudio、makoto/msxaudio/msxaudio）で声数と容量が広がります。

opn は YM2203（FM 3ch＋SSG）の入力で、FM は各プロファイルの FM 音源へ、SSG は AY へ変換されます。opn_segapcm の △ は opm_segapcm と同じ理由です（sfg01・misato では PCM の行き先が無いため、PCM は省略されます）。

組み合わせは原則として1本目の行を引き継ぎますが、PCM を持つ入力では行き先を足す組み合わせの方が1本目より広く対応します（例: opm_msm6258 では sfg01 は △、sfg01/makoto は ○）。

組み合わせと重ね系のプロファイルが生成される入力音源の種類は次の通りです（scc は SCC が鳴っている入力）。SCC・PSG を実チップのまま残す構成は layered の形（`layered/psg` / `layered/scc`）だけです。OPLL も実チップのまま残り、`layered` ではネイティブのレーンとして重なり、`sfg01/opllrhythm` ではリズムがネイティブのまま残ります。

| プロファイル | psg | scc | opna | opm | opn2 | opn |
|---|---|---|---|---|---|---|
| sfg01 | — | — | ○ | ○ | ○ | ○ |
| makoto | — | — | ○ | ○ | ○ | ○ |
| misato | — | — | ○ | ○ | ○ | ○ |
| msxaudio | — | — | — | — | — | — |
| opl3 | — | — | — | — | — | — |
| layered | — | — | ○ | ○ | ○ | ○ |
| layered/psg | ○ | — | — | — | — | — |
| layered/scc | — | ○ | — | — | — | — |

opna / opm / opn2 / opn 列は、2本目以降のカートリッジ（makoto / msxaudio / opl3 / misato）やリズム源（opllrhythm）を足す組み合わせの生成で、1本目のカートリッジ自体が受け付けない入力では生成されません。

### 各プロファイルの説明

各プロファイルでは、入力VGMから抽出した演奏情報を、対応するサウンドカートリッジの音源へ割り当てます。
複数の音源が混在する場合は、音源ごとの優先順位に従ってチャンネルを割り当てます。音源の仕様やチャンネル数の制約により、一部の演奏情報を再現できない場合があります。

#### 基本構成

- **`sfg01`**：SFG-01（OPM / YM2151）向け。各音源の演奏情報をOPMのFM音源へ変換します。
- **`makoto`**：Makoto（OPNA / YM2608）向け。各音源をOPNAのFM音源へ変換し、PCMはADPCM-Bへ割り当てます。
- **`misato`**：Misato（OPN3）向け。`makoto` と同様にFM音源へ変換しますが、ADPCM機能がないためPCMは再生できません。打楽器には搭載されたリズム音源を使用します。
- **`msxaudio`**：MSX-AUDIO（Y8950）向け。OPLLの演奏情報をY8950のFM音源へ変換します。OPLLのリズムはY8950のリズム音源へ、PCMはDelta-Tへ割り当てます。
- **`opl3`**：OPL3（YMF262）向け。OPLLの演奏情報をOPL3のFM音源へ変換し、リズムはOPL3のリズム音源へ割り当てます。PCMには対応しません。

#### 2本目以降のカートリッジでPCMを補完する構成

1本目のカートリッジだけではPCMを再生できない構成に、2本目以降のカートリッジのPCM再生機能を組み合わせます。

- **`sfg01/makoto/`**：SFG-01にMakotoを組み合わせ、PCM再生にOPNAのADPCM-Bを利用します。
- **`sfg01/msxaudio/`**：SFG-01にMSX-AUDIOを組み合わせ、PCM再生にY8950のDelta-Tを利用します。
- **`makoto/msxaudio/`**：MakotoにMSX-AUDIOを組み合わせ、PCMをADPCM-BとDelta-Tの2チャンネルで再生します（各256KiB）。重なって鳴るPCMは2台に振り分けられます。
- **`makoto/msxaudio/msxaudio/`**：MSX-AUDIOをもう1台重ね、PCMをADPCM-BとDelta-T 2台の3チャンネルで再生します（各256KiB）。
- **`misato/msxaudio/`**：MisatoにMSX-AUDIOを組み合わせ、PCM再生にY8950のDelta-Tを利用します。リズムはMisatoのリズム音源で再生します。
- **`msxaudio/msxaudio/`**：MSX-AUDIOを2台使います。1台目のFM演奏に加え、PCMをDelta-T 2チャンネルで再生します（各256KiB、2台目のFM部は使いません）。
- **`opl3/makoto/`**：OPL3にMakotoを組み合わせ、PCM再生にOPNAのADPCM-Bを利用します。
- **`opl3/msxaudio/`**：OPL3にMSX-AUDIOを組み合わせ、PCM再生にY8950のDelta-Tを利用します。

#### 2本目以降のカートリッジでリズム音源を補完する構成

- **`sfg01/misato/`**：SFG-01にMisatoを組み合わせ、OPLLやOPNAのリズムパートをMisatoのリズム音源で再生します。ADPCMは使用しません。
- **`sfg01/opl3/`**：`sfg01` を基本とし、OPLLのリズムパートをOPL3（YMF262）のリズム音源で再生します。

#### 実チップのリズムを残す構成

- **`sfg01/opllrhythm/`**：`sfg01` を基本とし、OPLLのリズムパートだけはFMへ変換せず、YM2413のリズム音源でそのまま再生します。

#### FM音源を重ねる構成

- **`layered`**：FMへ変換可能な演奏パートを各チップのFMユニットに割り当てます。最大でSFG-01,Makoto(or Misato), OPLL, OPL3, MSX-Audioで同じパートを重ねて演奏します。

単なるデチューンとは異なり、異なるFM音源チップの音色を重ね合わせる、MSXならではのお遊び機能です。

#### SCCを重ねる構成

SCCの演奏パートを元のSCCで再生しながら、同じパートを別のFM音源にも割り当てる構成です。

- **`layered/scc/`**：SCC ＋ SFG-01（OPM）＋ Makoto（OPNA）の3重奏

SCC以外のパートは、対応する基本構成またはレイヤー構成と同じ方法で変換します。

#### PSGを重ねる構成

PSGの演奏パートを元のPSGで再生しながら、同じパートをFM音源にも割り当てる構成です。

- **`layered/psg/`**：PSG ＋ SFG-01（OPM）＋ Makoto（OPNA）の3重奏

これらはPSGのみを使用する入力VGMを対象とします。

なお、SCC・PSGのレイヤー構成ではOPLLへの変換は行いません。OPLLはユーザー定義音色を同時に1種類しか使用できないため、複数パートの独立した音色を再現する用途には適していません。

#### PCMの取り扱い

PCMデータは256KiBの容量制限に収まるよう、重複サンプルの共有や代表サンプルへの置き換えによって自動調整します。

PCMの再生可否や割り当て先は、プロファイルと搭載音源の構成によって異なります。

#### 再生方法

生成したVGMは、MSX実機のVGMPlayや、Mami-VSIF Pro経由のMAmidiMEmoなどで再生できます。

実機をお持ちでない場合も、対応するVGMプレーヤーで演奏を楽しめます。

# Playing on Various Sound Cartridges

In addition to the standard output, adding `--vgm-variants` also generates VGM files for each sound cartridge configuration. This feature lets you play converted songs as they are on cartridges such as SFG-01 (OPM) and Makoto (OPNA).

The musical information built for MML generation is assigned to other sound chips mounted on MSX sound cartridges. The current targets are SFG-01 (OPM), Makoto (OPNA), Misato (OPN3), MSX-AUDIO (Y8950), and OPL3 (YMF262).

    python scripts/export_mgs.py <input.vgm> --outdir <output> --vgm-variants --force

Output goes to `vgm-variants/<first cartridge profile>/<song>.vgm`. Compositions are placed under the first cartridge's folder in a subfolder named by the added element (e.g. `vgm-variants/sfg01/makoto/<song>.vgm`, `vgm-variants/sfg01/scc/<song>.vgm`). A composition identical to the first cartridge alone is not written. Configurations that cannot be generated are skipped with a reason, and diagnostics remain in `_diagnostics`.

Base profiles generated for each source type (Yes: generated, Approximate: generated with limitations or unconverted parts, No: not generated).

| Profile | psg | psg_scc | opll | dcsg | dcsgx2 | apu | apu_fds | huc6280 | opna | opm | opn2 | opm_msm6258 | opm_segapcm | opn | opn_segapcm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sfg01 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Approximate | Yes | Yes | Approximate | Approximate | Approximate | Yes | Approximate |
| makoto | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Approximate | Yes | Yes | Yes | Yes | Approximate | Yes | Approximate |
| misato | Yes | Yes | Yes | Yes | Yes | Approximate | Approximate | Approximate | Approximate | Yes | Approximate | Approximate | Approximate | Yes | Approximate |
| msxaudio | Yes | No | Yes | Yes | Yes | Yes | Approximate | Approximate | No | No | No | No | No | No | No |
| opl3 | Yes | No | Yes | Yes | Yes | Yes | Yes | Approximate | No | No | No | No | No | No | No |

The Approximate cells for apu_fds / huc6280 on msxaudio and opl3 are due to waveform-voice capacity: with `--force`, lanes beyond capacity are omitted.

The Approximate cells for opm_segapcm are because SegaPCM carries up to 16 PCM voices: a single PCM unit mixes them down to one voice and may omit content over its 256 KiB budget. The compositions that add PCM destinations (makoto/msxaudio, makoto/msxaudio/msxaudio) widen both the voice count and the capacity.

opn is YM2203 input (3 FM channels + SSG): the FM is converted to each profile's FM generator and the SSG to AY. The Approximate cells for opn_segapcm are for the same reason as opm_segapcm (on sfg01 and misato the PCM has no destination and is omitted).

Compositions generally inherit the first cartridge's row, but for sources with PCM, a composition that adds a PCM destination covers more than the first cartridge alone (e.g. for opm_msm6258, sfg01 is Approximate but sfg01/makoto is Yes).

The source types for which the composition and layered profiles are generated are (scc: sources where SCC sounds). The only compositions that keep a real SCC or PSG are the layered forms, `layered/psg` / `layered/scc`. OPLL also stays on the real chip: it joins `layered` as a native lane, and `sfg01/opllrhythm` keeps its rhythm native.

| Profile | psg | scc | opna | opm | opn2 | opn |
|---|---|---|---|---|---|---|
| sfg01 | No | No | Yes | Yes | Yes | Yes |
| makoto | No | No | Yes | Yes | Yes | Yes |
| misato | No | No | Yes | Yes | Yes | Yes |
| msxaudio | No | No | No | No | No | No |
| opl3 | No | No | No | No | No | No |
| layered | No | No | Yes | Yes | Yes | Yes |
| layered/psg | Yes | No | No | No | No | No |
| layered/scc | No | Yes | No | No | No | No |

The opna / opm / opn2 / opn columns are compositions that add a second or later cartridge (makoto / msxaudio / opl3 / misato) or a rhythm source (opllrhythm); they are not generated for sources the first cartridge itself does not accept.

### Profile Descriptions

Each profile maps the musical information extracted from the input VGM to the sound chips available in the corresponding MSX sound cartridge configuration.

When multiple sound sources are present, channels are allocated according to source priorities. Some performance details may not be reproduced due to hardware limitations or the number of available channels.

#### Basic Configurations

- **`sfg01`**: For SFG-01 (OPM / YM2151). Converts performance data from various sound sources to the OPM FM sound generator.
- **`makoto`**: For Makoto (OPNA / YM2608). Converts performance data to the OPNA FM sound generator and maps PCM samples to ADPCM-B.
- **`misato`**: For Misato (OPN3). Performs FM conversion similarly to `makoto`, but PCM playback is unavailable because the cartridge has no ADPCM functionality. Percussion is played using its built-in rhythm sound generator.
- **`msxaudio`**: For MSX-AUDIO (Y8950). Converts OPLL performance data to Y8950 FM, maps OPLL rhythm parts to the Y8950 rhythm sound generator, and plays PCM through Delta-T.
- **`opl3`**: For OPL3 (YMF262). Converts OPLL performance data to OPL3 FM and maps OPLL rhythm parts to the OPL3 rhythm sound generator. PCM playback is not supported.

#### Compositions That Add PCM Playback via a Second or Later Cartridge

These pair a first cartridge that cannot play PCM on its own with the PCM playback of a second or later cartridge.

- **`sfg01/makoto/`**: Combines SFG-01 with Makoto, using OPNA ADPCM-B for PCM playback.
- **`sfg01/msxaudio/`**: Combines SFG-01 with MSX-AUDIO, using Y8950 Delta-T for PCM playback.
- **`makoto/msxaudio/`**: Combines Makoto with MSX-AUDIO, playing PCM on two channels, ADPCM-B and Delta-T (256 KiB each). PCM content that sounds together is split across the two units.
- **`makoto/msxaudio/msxaudio/`**: Stacks a second MSX-AUDIO, playing PCM on three channels, ADPCM-B and two Delta-T units (256 KiB each).
- **`misato/msxaudio/`**: Combines Misato with MSX-AUDIO, using Y8950 Delta-T for PCM playback. Rhythm plays on Misato's rhythm sound generator.
- **`msxaudio/msxaudio/`**: Uses two MSX-AUDIO cartridges. On top of the first unit's FM playback, PCM plays on two Delta-T channels (256 KiB each; the second unit's FM section is not used).
- **`opl3/makoto/`**: Combines OPL3 with Makoto, using OPNA ADPCM-B for PCM playback.
- **`opl3/msxaudio/`**: Combines OPL3 with MSX-AUDIO, using Y8950 Delta-T for PCM playback.

#### Compositions That Add a Rhythm Sound Generator via a Second or Later Cartridge

- **`sfg01/misato/`**: Combines SFG-01 with Misato, playing OPLL and OPNA rhythm parts through Misato's rhythm sound generator. ADPCM is not used.
- **`sfg01/opl3/`**: Based on `sfg01`, but plays OPLL rhythm parts through the OPL3 (YMF262) rhythm sound generator.

#### Compositions That Keep the Rhythm on the Real Chip

- **`sfg01/opllrhythm/`**: Based on `sfg01`, but preserves the original OPLL rhythm parts and plays them directly through the YM2413 rhythm sound generator instead of converting them to FM.

#### Layered FM Configurations

- **`layered`**: Assigns FM-convertible performance parts to the FM units of multiple sound chips. The same parts can be played simultaneously on up to five sound sources: SFG-01, Makoto (or Misato), OPLL, OPL3, and MSX-AUDIO.

Unlike simple detuning, this feature layers the distinct timbres of different FM sound chips, offering a unique kind of musical experimentation made possible by the MSX platform.

#### Layered SCC Configurations

These configurations preserve the original SCC performance while simultaneously playing the same parts through additional FM sound chips.

- **`layered/scc/`**: SCC + SFG-01 (OPM) + Makoto (OPNA), three-layer playback

Parts other than SCC are converted using the same methods as their corresponding basic or layered configurations.

#### Layered PSG Configurations

These configurations preserve the original PSG performance while simultaneously playing the same parts through additional FM sound chips.

- **`layered/psg/`**: PSG + SFG-01 (OPM) + Makoto (OPNA), three-layer playback

These profiles are intended for input VGM files containing only PSG sound data.

Note that OPLL is not used as a conversion target in the layered SCC and PSG configurations. Since OPLL supports only one user-defined instrument at a time, it is not well suited to reproducing multiple independent parts with different custom timbres.

#### PCM Handling

PCM data is automatically optimized to fit within the 256 KiB capacity limit by sharing duplicate samples and substituting representative samples where necessary.

PCM playback availability and destination depend on the selected profile and the sound chips included in the configuration.

#### Playback

The generated VGM files can be played with VGMPlay on real MSX hardware, or with MAmidiMEmo via Mami-VSIF Pro.

Even without real hardware, you can enjoy them on any compatible VGM player.
