"""Target-only PSG audition masks retain time, controls and native evidence."""
import csv
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests')]
from psg_part_selection import select, dump
from psg_scc_performance import analyze, audible
from test_drum_inference import psg
from test_drum_enhancement import noise_vgm
from test_mml_envelopes import sounding_timeline
from mml_sync import analyze_mml


def mixed_vgm(extra=b''):
    raw=bytearray(noise_vgm(extra).replace(b'\xa0\x07\x37',
        b'\xa0\x07\x35\xa0\x02\xc8\xa0\x03\x00\xa0\x09\x0c'))
    raw[-1:] = b'\xa0\x09\x00\x66'
    struct.pack_into('<I',raw,4,len(raw)-4)
    return bytes(raw)


class PsgSelectionTests(unittest.TestCase):
    def native(self):
        return {0:[psg(0,735),psg(735,1470,volume=6),
                   psg(1470,2205,volume=0),psg(2205,4410,mode=1)],
                1:[psg(0,4410,ch=1,mode=1)]}

    def test_complementary_masks_preserve_every_source_row_and_duration(self):
        rows=self.native();before=repr(rows);performance=analyze(rows,'psg')
        melody,_,mreport,_,mm=select(performance,'melody')
        rhythm,items,rreport,_,rm=select(performance,'rhythm')
        self.assertTrue(items)
        for ch,source in rows.items():
            for i,row in enumerate(source):
                a,b=melody[ch][i],rhythm[ch][i]
                self.assertEqual((a.time,a.ticks,a.l,a.vgmticks,a.vgmticks_end),
                                 (row.time,row.ticks,row.l,row.vgmticks,row.vgmticks_end))
                self.assertEqual((b.ticks,b.l,b.vgmticks,b.vgmticks_end),
                                 (row.ticks,row.l,row.vgmticks,row.vgmticks_end))
                self.assertEqual(int(audible(a,'psg'))+int(audible(b,'psg')),int(audible(row,'psg')))
                if audible(row,'psg'):self.assertIn(row,(a,b))
        self.assertEqual(before,repr(rows));self.assertTrue(performance.validate(rows))
        self.assertEqual([r['classification'] for r in mm],[r['classification'] for r in rm])
        self.assertEqual(mreport['source_audible_intervals'],
                         mreport['selected_audible_intervals']+rreport['selected_audible_intervals'])

    def test_hw_envelope_overlap_abstains_even_on_a_different_channel(self):
        rows=self.native();rows[1]=[psg(0,4410,ch=1,mode=1,envelope_enabled=1,volume=0)]
        performance=analyze(rows,'psg')
        melody,_,summary,candidates,_=select(performance,'melody')
        rhythm,selected,_,_,_=select(performance,'rhythm')
        self.assertEqual(selected,());self.assertGreater(summary['hardware_phase_abstentions'],0)
        self.assertEqual(melody,rows)
        self.assertTrue(all(not audible(r,'psg') and r.envelope_enabled==0 and r.mode==0
                            for rs in rhythm.values() for r in rs))
        self.assertTrue(any(d['selection_reason']=='shared_hardware_envelope_phase_unverified' for d in candidates))

    def test_zero_controls_keep_lineage_and_uncertain_stays_melody(self):
        rows={0:[psg(0,0,ev_type='evS'),psg(0,2205),psg(2205,2940,volume=0),psg(2940,2940,volume=0),
                 psg(2940,29400,mode=1)]}
        performance=analyze(rows,'psg');melody,_,_,_,_=select(performance,'melody')
        rhythm,_,_,_,_=select(performance,'rhythm')
        self.assertEqual(len(rhythm[0]),len(rows[0]))
        self.assertEqual(rhythm[0][0],rows[0][0]);self.assertEqual(melody[0][-1],rows[0][-1])
        self.assertEqual(rhythm[0][-1].scale,'r')

    def test_unknown_timing_is_never_invented_or_classified(self):
        row=replace(psg(),vgmticks=None,vgmticks_end=None)
        rhythm,items,summary,_,members=select(analyze({0:[row]},'psg'),'rhythm')
        self.assertFalse(items);self.assertIsNone(rhythm[0][0].vgmticks)
        self.assertEqual(summary['eligible_rhythm_candidates'],0)
        self.assertEqual(members[0]['classification'],'melody')

    def test_catalog_and_target_mask_are_always_inspectable(self):
        result=select(analyze(self.native(),'psg'),'rhythm')
        with tempfile.TemporaryDirectory() as tmp:
            dump(tmp,'x',*result[2:]);folder=Path(tmp)
            self.assertTrue(json.loads((folder/'x.psg.selection.json').read_text())['source_segments_unchanged'])
            with (folder/'x.psg.selection.mask.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),sum(map(len,self.native().values())))
            self.assertTrue((folder/'x.psg.selection.candidates.csv').is_file())


class PsgSelectionCliTests(unittest.TestCase):
    def convert(self,source,out,*flags):
        proc=subprocess.run([sys.executable,str(ROOT/'vgm2mml.py'),str(source),'--outdir',str(out),
                             '--dump-passes','--vgmticks',*flags],capture_output=True,timeout=90)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        return (out/(source.stem+'.mml')).read_text(encoding='cp932')

    def test_solo_complement_native_segments_and_real_compiled_sound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'MIXED.vgm';source.write_bytes(mixed_vgm())
            default=self.convert(source,root/'all')
            melody=self.convert(source,root/'melody','--psg-melody_only')
            rhythm=self.convert(source,root/'rhythm','--psg-rhythm-only')
            from dataclasses import fields
            from chip_segments import PsgSegment
            def evidence(folder):
                with (root/folder/'MIXED.psg.segments.csv').open() as stream:
                    return [{f.name:r[f.name] for f in fields(PsgSegment)} for r in csv.DictReader(stream)]
            self.assertEqual(evidence('all'),evidence('melody'))
            self.assertEqual(evidence('all'),evidence('rhythm'))
            timelines=[sounding_timeline(text,raw=False) for text in (default,melody,rhythm)]
            for ch,states in timelines[0].items():
                for tick,original in enumerate(states):
                    chosen=[t.get(ch,[])[tick] if tick<len(t.get(ch,[])) else None for t in timelines[1:]]
                    self.assertEqual([s for s in chosen if s is not None],[original] if original is not None else [])
            self.assertEqual(set(analyze_mml(melody)[0]),{'2'})
            self.assertEqual(set(analyze_mml(rhythm)[0]),{'1'})
            if shutil.which('mgsc') and shutil.which('node'):
                for part in ('melody','rhythm'):
                    folder=root/part;mgs=folder/'MIXED.mgs'
                    compile_run=subprocess.run(['mgsc',str(folder/'MIXED.mml'),str(mgs)],capture_output=True)
                    self.assertEqual(compile_run.returncode,0,compile_run.stdout)
                    stats=folder/'audio.json'
                    run=subprocess.run(['node',str(ROOT/'scripts/probe_mgs_audio.mjs'),str(mgs),str(stats),'1000'],capture_output=True,timeout=45)
                    self.assertEqual(run.returncode,0,run.stderr)
                    self.assertGreater(json.loads(stats.read_text())['peak'],0)

    def test_solo_overlay_does_not_resurrect_excluded_rhythm_or_native_opll(self):
        # Source channel6 has a real melody key-on. It is excluded from both solo
        # targets, so it cannot consume or block target OPLL percussion lanes.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'mixed.vgm'
            source.write_bytes(mixed_vgm(b'\x51\x16\x80\x51\x26\x15\x51\x36\x10'))
            rhythm=self.convert(source,root/'rhythm','--psg-rhythm-only','--enhance-rhythm')
            melody=self.convert(source,root/'melody','--psg-melody-only','--enhance-rhythm')
            self.assertEqual(set(analyze_mml(rhythm)[0]),{'1','f'})
            self.assertEqual(set(analyze_mml(melody)[0]),{'2'})
            self.assertEqual(json.loads((root/'rhythm/mixed.drums.json').read_text())['added_hits'],3)
            self.assertEqual(json.loads((root/'melody/mixed.drums.json').read_text())['added_hits'],0)

    def test_no_psg_and_conflicting_modes_are_explicit_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'opll.vgm'
            raw=bytearray(noise_vgm()[:0x80]);raw.extend(b'\x51\x10\x80\x51\x20\x15\x62\x51\x20\x05\x66')
            struct.pack_into('<I',raw,0x74,0);struct.pack_into('<I',raw,0x10,3579545)
            struct.pack_into('<I',raw,4,len(raw)-4);struct.pack_into('<I',raw,0x18,735)
            fixture.write_bytes(raw)
            for flags in (['--psg-rhythm-only'],['--psg-rhythm-only','--psg-melody-only']):
                proc=subprocess.run([sys.executable,str(ROOT/'vgm2mml.py'),str(fixture),'--outdir',tmp,*flags],capture_output=True,timeout=30)
                self.assertNotEqual(proc.returncode,0)


if __name__=='__main__':unittest.main()
