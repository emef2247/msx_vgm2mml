# Third-party attribution and notices

The project source is licensed under MIT: Copyright (c) 2026 emef2247.
This file distinguishes referenced mapping material, optional compilation/
playback dependencies and development-only inspection tools. Their own notices
and conditions remain applicable. External packages and driver binaries are
not vendored by this project; a source release is not a complete distribution
of those tools.

## vgm-conv

Project: [digital-sound-antiques/vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)

Reference revision: `780a20ed505e23eb21aa9c6ce3f349029718b5a0`

Reference source:
[src/converter/ay8910-to-opm-coverter.ts](https://github.com/digital-sound-antiques/vgm-conv/blob/780a20ed505e23eb21aa9c6ce3f349029718b5a0/src/converter/ay8910-to-opm-coverter.ts)

The PSG FM projection in `py/psg_opm_fm.py` uses the published AY8910-to-OPM
voice parameters and volume-to-TL mapping as a reference. This includes
AL4/FB7, the MUL2/TL27 modulator, MUL1 carrier, fixed-level TL table and eight
attenuation steps of headroom. Segment processing and target generation are
implemented in this project; the external converter is not a runtime dependency.
The upstream notice is retained for these referenced mapping materials.

Upstream [LICENSE.md](https://github.com/digital-sound-antiques/vgm-conv/blob/780a20ed505e23eb21aa9c6ce3f349029718b5a0/LICENSE.md):

```text
ISC License

Copyright (c) 2023 Mitsutaka Okazaki and Contributors

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

## MGSC / mgsc-js / MGSDRV

Projects: [mgsc](https://github.com/digital-sound-antiques/mgsc),
[mgsc-js](https://github.com/digital-sound-antiques/mgsc-js),
[MGSDRV](https://www.gigamix.jp/mgsdrv/).

Use: native `mgsc` is invoked as a separate compiler command. The optional
`mgsc-js` fallback is imported by the Node helper `scripts/compile_mgs.mjs`;
`scripts/mml_to_vgm.mjs` also imports it for roundtrip checks.
The documented npm version is `mgsc-js` 2.0.0, whose registry metadata declares
ISC and records source revision `0f749e5c20912821744f965c7be2ccc6d04170fe`.
Its `modules/mgsc` gitlink is `079de8c3ef24189d0b12f14151a3af71658ae6b5`.
No separate license file is listed in that wrapper source/package manifest;
this entry records the package declaration rather than inventing a wrapper notice.
The revision of the locally installed native executable was not established.

The underlying emulator wrapper's
[LICENSE](https://github.com/digital-sound-antiques/mgsc/blob/079de8c3ef24189d0b12f14151a3af71658ae6b5/LICENSE)
is retained below. Its
[README](https://github.com/digital-sound-antiques/mgsc/blob/079de8c3ef24189d0b12f14151a3af71658ae6b5/README.md)
separately attributes the embedded MSX `MGSC.COM` dump to Ain/GIGAMIX and the
KMZ80 emulator to Mamiya (public-domain declaration).

```text
Copyright (c) 2015, Digital Sound Antiques

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

The official [MGSC 1.11 document](https://p.gigamix.jp/mgsdrv/MGSC111.TXT)
identifies `Copyright(c) 1992-93 by Ain` and permits copying/distribution:

```text
★ 転載、配布は自由に行なって下さい。
```

The official [MGSDRV 3.20 document](https://p.gigamix.jp/mgsdrv/MGSDR320.TXT)
identifies:

```text
Copyright(c) 1991-94 by Ain
Copyright(c) 1997-2001 GIGAMIX
Modified by Goripon & Influenza (GIGAMIX)
```

Its distribution condition is:

```text
転載、配布は自由に行なって構いませんが、アーカイブの内容は変更しないでください。
```

These historical freeware terms are separate from the emulator wrapper's ISC
license; they do not establish an MIT/ISC license for MGSC.COM or MGSDRV.
Use original driver/compiler distributions and retain their accompanying
notices when redistributing them. Do not describe every embedded MSX driver as
ISC merely because the npm wrapper declares ISC.

## libkss-js / libkss

Projects: [libkss-js](https://github.com/digital-sound-antiques/libkss-js),
[libkss](https://github.com/digital-sound-antiques/libkss).

Use: the optional Node helpers `scripts/mgs_to_vgm.mjs` and
`scripts/mml_to_vgm.mjs` import libkss-js to export compiled MGS into VGM for
validation. It is not required for the Python VGM-to-MML converter.
The installed package inspected for this check is `libkss-js` 3.1.0; earlier
roundtrip documentation records 3.0.0 and is not relabeled as a 3.1.0 measurement.

The 3.1.0 package metadata declares ISC. Its `LICENSE.md` refers to libkss's
license, rather than supplying an independent copyright text.
Registry `gitHead`: `30c8c14c50e3b639c17a8ecc4f3ac432ac22b9b3`;
`modules/libkss` gitlink: `15fb77fbb949d9d679df7e9652723b2c41b9f46e`.
The corresponding libkss
[LICENSE.md](https://github.com/digital-sound-antiques/libkss/blob/15fb77fbb949d9d679df7e9652723b2c41b9f46e/LICENSE.md)
is copied in full below, including its driver exception:

```text
## Caveat
[kss-drivers] submodule that libkss depends on are not compliant with this license.

[kss-drivers]: https://github.com/digital-sound-antiques/kss-drivers

## libkss License 

Copyright (c) 2015 Mitsutaka Okazaki

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

The matching `modules/drivers` gitlink is
`e8032da38ea8439caca699954fce82b5050bf86f` in
[kss-drivers](https://github.com/digital-sound-antiques/kss-drivers/tree/e8032da38ea8439caca699954fce82b5050bf86f).
Its README attributes `mgsdrv.h` to Ain/GIGAMIX and lists other copyrighted
MSX driver materials. The official MGSDRV terms above concern MGSDRV, not all
of those other drivers. Redistributing the JS/WASM playback package requires
checking its bundled drivers and other components as well as the ISC notice;
this direct-dependency check is not a complete package redistribution audit.

## Distribution scope

### Optional HuC6280 reference core

`scripts/huc6280_reference.py --setup` obtains a pinned
[libvgm](https://github.com/ValleyBell/libvgm) checkout, commit
`bad50c571db45b872304bdcd0603dd2214f0663e`, into ignored local tool storage.
It builds a local validation wrapper around the unchanged
`emu/cores/c6280_mame.c` core, attributed to Charles MacDonald and marked
BSD-3-Clause. The wrapper records source, wrapper and library hashes. No
upstream core or compiled reference binary is redistributed in this repository.
The converter's native source profile is behaviorally checked against that
reference; this does not establish hardware accuracy for all core behavior.
If redistributing the optional checkout or binary, retain upstream copyright,
license and dependency notices from that pinned distribution.

`scripts/musical_vgm_reference.py` additionally builds optional local wrappers
around the same pinned checkout's EMU2149/EMU2413 (Mitsutaka Okazaki; upstream
MIT notices), K051649 (Bryan McPhail; BSD-3-Clause) and panning support. Source,
wrapper and binary hashes are retained in local metadata. These cores and
binaries remain outside tracked source. Preserve their exact pinned upstream
notices if separately redistributing the optional reference installation.

Include this notice and the project LICENSE with source distributions.
Referenced vgm-conv mapping material retains its ISC notice. Optional compiler,
player and inspector executables/packages and copyrighted driver dumps are
not copied into the tracked converter source by this change.

If bundling npm/WASM packages, preserve their own and their embedded
components' notices and terms.
The direct-tool notices above are not a complete binary bundle license manifest.
Source fixture/music rights are separate from software licenses; this file
provides no permission to redistribute private or third-party song data.
