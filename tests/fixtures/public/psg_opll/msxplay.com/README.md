# Test fixture derived from MSXplay.com demo data

This directory contains a public PSG/OPLL test fixture derived from demo MML data distributed with **MSXplay.com / msxplay-js**.

## Source

Original demo data:

https://github.com/digital-sound-antiques/msxplay-js/tree/main/public/demo

MSXplay.com:

https://msxplay.com/

The MML file stored under the `reference/` directory is based on the corresponding demo MML file from the upstream `msxplay-js` repository.

The VGM file was prepared from that reference MML and is used as an input fixture for `msx_vgm2mml`.

The purpose of this fixture is to compare:

```
reference MGSDRV MML
        ↓
      VGM
        ↓
   msx_vgm2mml
        ↓
 generated MML
```

This provides a real MGSDRV PSG/OPLL test case for checking the conversion pipeline and generated MML.

## Source mapping

* `sample/reference/sample.mml`

  * upstream: `public/demo/psg_fm.mml`

Upstream source:

https://github.com/digital-sound-antiques/msxplay-js/blob/main/public/demo/psg_fm.mml

## Copyright

The upstream `COPYRIGHT.md` explicitly identifies `psg_fm.mgs/mml` as **Public Domain**.

https://github.com/digital-sound-antiques/msxplay-js/blob/main/public/demo/COPYRIGHT.md

The local filename `sample.mml` corresponds to the upstream `psg_fm.mml`.
