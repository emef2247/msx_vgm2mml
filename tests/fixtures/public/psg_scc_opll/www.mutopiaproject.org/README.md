# Public MGSDRV Test Data derived from Mutopia Project MIDI files

This directory contains public test data used by `msx_vgm2mml`.

The original MIDI files were obtained from the **Mutopia Project** and converted to MGSDRV MML using **MIDI_MGSDRV_Converter**.

These files are used as test material containing a mixture of PSG, SCC, and OPLL parts.

## Data flow

The test data in this directory was prepared using the following process:

```text
Mutopia Project MIDI
        |
        v
MIDI_MGSDRV_Converter
        |
        v
MGSDRV MML
        |
        v
msx_vgm2mml test fixtures
```

The generated MGSDRV data is intended primarily for testing and regression analysis. It should not be considered a manually optimized MGSDRV arrangement of the original music.

## Converter

The MIDI files were converted using:

**MIDI_MGSDRV_Converter**

https://mdpc.dousetsu.com/utility/msx/mu/mgsdrv/top.htm

The converter translates Standard MIDI File data into MML suitable for use with MGSDRV.

## Source

Original MIDI data was obtained from:

**Mutopia Project**

https://www.mutopiaproject.org/

Mutopia Project distributes freely usable sheet music and associated files. Copyright and licensing information should be checked on the corresponding Mutopia Project entry for each work.

The individual MIDI source files used for these fixtures are listed below so that the origin of every test case can be traced.

### Classical

* `cpe-bach-rondo`
  https://www.mutopiaproject.org/ftp/BachCPE/cpe-bach-rondo/cpe-bach-rondo.mid

* `giselle`
  https://www.mutopiaproject.org/ftp/AdamA/giselle/giselle.mid

### Hymn

* `ellacombe`
  https://www.mutopiaproject.org/ftp/Anonymous/ellacombe/ellacombe.mid

* `more_love_to_Thee_o_Christ`
  https://www.mutopiaproject.org/ftp/DoaneWH/more_love_to_Thee_o_Christ/more_love_to_Thee_o_Christ.mid

### Jazz

* `enchanted-island`
  https://www.mutopiaproject.org/ftp/DoonanSC/enchanted-island/enchanted-island.mid

* `turpinhar`
  https://www.mutopiaproject.org/ftp/TurpinT/turpinhar/turpinhar.mid

### Modern

* `bridge`
  https://www.mutopiaproject.org/ftp/BrownCJ/bridge/bridge.mid

* `wedding`
  https://www.mutopiaproject.org/ftp/BrownCJ/wedding/wedding.mid

### Romantic

* `aguado-op03n01`
  https://www.mutopiaproject.org/ftp/AguadoD/O3/aguado-op03n01/aguado-op03n01.mid

* `alkan-op31-1`
  https://www.mutopiaproject.org/ftp/AlkanCV/O31/alkan-op31-1/alkan-op31-1.mid

### Song

* `bluemtns`
  https://www.mutopiaproject.org/ftp/AdamsS/bluemtns/bluemtns.mid

* `MusAirCh`
  https://www.mutopiaproject.org/ftp/RootGF/MusAirCh/MusAirCh.mid
