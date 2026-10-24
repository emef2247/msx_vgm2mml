"""Inferred target percussion preserves source parts, native rhythm and clocks."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests')]
from drum_inference import DrumCandidate
from drum_enhancement import project, apply
from note_normalization import TimingPlan
from test_rhythm_mml import attacks
from test_rhythm_patterns import segment
from test_mml_envelopes import sounding_timeline


def candidate(tick=2,instrument='HH',volume=8,**kwargs):
    values=dict(candidate_id=f'psg:0:{tick}',chip='psg',channel=0,segment_indices=(0,),
                source_sample=tick*735,source_end=(tick+2)*735,tick_start=tick,
                tick_end=tick+2,instrument=instrument,volume=volume,
                reasons=('authored_hypothesis',),features=())
    values.update(kwargs)
    return DrumCandidate(**values)


def noise_vgm(extra=b''):
    raw=bytearray(0x80);raw[:4]=b'Vgm '
    struct.pack_into('<I',raw,8,0x161);struct.pack_into('<I',raw,0x34,0x80-0x34)
    struct.pack_into('<I',raw,0x74,3579545)
    if extra:struct.pack_into('<I',raw,0x10,3579545)
    raw+=extra+b'\xa0\x00\x64\xa0\x01\x00\xa0\x06\x08\xa0\x07\x37'
    for i in range(3):
        raw+=b'\xa0\x08\x0f\x62\xa0\x08\x08\x62\xa0\x08\x00\x62'
    raw+=b'\x66';struct.pack_into('<I',raw,4,len(raw)-4)
    struct.pack_into('<I',raw,0x18,9*735)
    return bytes(raw)


class DrumProjectionTests(unittest.TestCase):
    def test_native_priority_and_inferred_duplicates_have_lineage(self):
        native={9:[segment(2,volume=1)]}
        items=[candidate(2,'BD'),candidate(4,volume=3),candidate(4,volume=10,candidate_id='strong')]
        text,report,decisions=project(items,native,[])
        self.assertEqual(report['added_hits'],1)
        self.assertEqual(report['omitted_hits'],2)
        self.assertEqual(attacks('#opll_mode 1\n'+text),[(6,'b',14),(12,'h',10)])
        self.assertIn('native_rhythm_priority',[r['reason'] for r in decisions])
        self.assertIn('duplicate_inferred_instrument_tick',[r['reason'] for r in decisions])
        self.assertEqual(native[9][0].vol,1)

    def test_nine_voice_native_melody_blocks_overlay_even_zero_length(self):
        native={6:[SimpleNamespace(keyon=1,fnum=200,tick_end=0)]}
        text,report,decisions=project([candidate()],native,[])
        self.assertEqual(text,'');self.assertEqual(report['added_hits'],0)
        self.assertEqual(decisions[0]['status'],'blocked')

    def test_minimum_gap_and_same_tick_chords(self):
        timing=TimingPlan(150,12,1200,0,1,50)
        items=[candidate(source_sample=200,tick=0,instrument='BD'),
               candidate(source_sample=300,tick=0,instrument='HH',candidate_id='near'),
               candidate(source_sample=200,tick=0,instrument='SD',candidate_id='chord')]
        text,report,decisions=project(items,{},[],timing=timing)
        self.assertEqual(report['added_hits'],2)
        self.assertEqual(attacks('#opll_mode 1\n'+text),[(2,'b',8),(2,'s',8)])
        self.assertIn('target_minimum_interval',[r['reason'] for r in decisions])

    def test_normalized_overlay_follows_control_boundary_not_beat_snap(self):
        timing=TimingPlan(120,12,1200,0,1,500)
        item=candidate(source_sample=1000,tick=1)
        self.assertNotEqual(timing.onset(1000),10)
        text,report,rows=project([item],{},[],timing=timing,target_boundaries={('psg',0,1):10})
        self.assertEqual(rows[0]['target_tick'],10)
        self.assertEqual(rows[0]['target_reference'],'projected_control_boundary')
        self.assertEqual(attacks('#opll_mode 1\n'+text),[(10,'h',8)])
        missing=project([item],{},[],timing=timing,target_boundaries={})
        self.assertEqual(missing[1]['added_hits'],0)

    def test_all_rejected_keeps_exact_target_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original='#tempo 225\n#alloc 9=0\n9 @0 o4 c4\n'
            target=root/'x.opll.target.mml';target.write_text(original)
            mode,report=apply([candidate(instrument=None)],{},[],root,'x',native_mode=0,normalization={})
            self.assertEqual(mode,0);self.assertEqual(target.read_text(),original)
            self.assertEqual(report['status'],'unchanged')
            self.assertTrue((root/'x.drums.candidates.csv').exists())

    def test_apply_reads_actual_normalized_control_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'x.opll.target.mml').write_text('#tempo 120\n#alloc 9=0\n')
            (root/'x.psg.before.normalize.mml').write_text('#tempo 225\n1 r64 c64\n')
            (root/'x.psg.target.mml').write_text('#tempo 120\n1 r%10 c%2\n')
            timing=TimingPlan(120,12,1200,0,1,500)
            mode,report=apply([candidate(tick=1,source_sample=1000)],{},[],root,'x',native_mode=0,
                              normalization=dict(applied=True,timing=timing.__dict__))
            self.assertEqual(mode,1)
            rows=(root/'x.drums.projection.csv').read_text()
            self.assertIn('projected_control_boundary',rows)
            self.assertEqual(attacks('#opll_mode 1\n'+(root/'x.opll.target.mml').read_text()),[(10,'h',8)])


class DrumCliTests(unittest.TestCase):
    def run_cli(self,source,out,*flags,dump=True):
        p=subprocess.run([sys.executable,str(ROOT/'vgm2mml.py'),str(source),'--outdir',str(out),
                          *(['--dump-passes'] if dump else []),*flags],capture_output=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'))
        return (out/(source.stem+'.mml')).read_text(encoding='cp932')

    def test_plain_raw_and_export_defaults_compile_and_preserve_psg(self):
        for flags in [(),('--raw-ticks',),('--fm-state-ms','24','--normalization-ms','8')]:
            with self.subTest(flags=flags),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=root/'drums.vgm';source.write_bytes(noise_vgm())
                before=self.run_cli(source,root/'base','--vgmticks',*flags)
                after=self.run_cli(source,root/'added','--enhance-drums',*flags)
                self.assertEqual(sounding_timeline(before,raw='--raw-ticks' in flags),
                                 sounding_timeline(after,raw='--raw-ticks' in flags))
                self.assertIn('#opll_mode 1',after)
                report=json.loads((root/'added/drums.drums.json').read_text())
                self.assertEqual(report['added_hits'],3)
                expected=[(t if '--raw-ticks' in flags else t*3,'h',10) for t in (0,3,6)]
                self.assertEqual(attacks(after),expected)
                self.assertEqual((root/'base/drums.psg.segments.csv').read_bytes(),
                                 (root/'added/drums.psg.segments.csv').read_bytes())
                compiled=subprocess.run(['mgsc',str(root/'added/drums.mml'),str(root/'added/drums.mgs')],capture_output=True)
                self.assertEqual(compiled.returncode,0,compiled.stdout)
                self.assertGreater((root/'added/drums.mgs').stat().st_size,0)
                self.run_cli(source,root/'added',*flags)
                self.assertFalse((root/'added/drums.drums.json').exists())

    def test_actual_shared_clock_keeps_added_hits_on_projected_control_boundaries(self):
        events=[(0,b'\x51\x30\x10\x51\x10\xc3\xa0\x00\x64\xa0\x01\x00\xa0\x06\x08\xa0\x07\x37')]
        for i in range(24):
            start=i*5512
            events.extend([(start,b'\x51\x20\x19'),(start+2756,b'\x51\x20\x09')])
            if i%4==0:
                events.extend([(start,b'\xa0\x08\x0f'),(start+735,b'\xa0\x08\x08'),
                               (start+1470,b'\xa0\x08\x00')])
        raw=bytearray(0x80);raw[:4]=b'Vgm '
        for offset,value in [(8,0x161),(0x34,0x80-0x34),(0x74,3579545),(0x10,3579545),(0x18,24*5512)]:
            struct.pack_into('<I',raw,offset,value)
        previous=0
        for sample,writes in sorted(events,key=lambda e:e[0]):
            if sample>previous:raw+=b'\x61'+struct.pack('<H',sample-previous)
            raw+=writes;previous=sample
        raw+=b'\x61'+struct.pack('<H',24*5512-previous)+b'\x66'
        struct.pack_into('<I',raw,4,len(raw)-4)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'clock.vgm';source.write_bytes(raw)
            flags=('--fm-state-ms','24','--normalization-ms','16')
            before=self.run_cli(source,root/'base',*flags)
            after=self.run_cli(source,root/'added','--enhance-drums',*flags)
            norm=json.loads((root/'added/clock.normalization.json').read_text())
            self.assertTrue(norm['applied'],norm)
            report=json.loads((root/'added/clock.drums.json').read_text())
            self.assertEqual(report['added_hits'],6,report)
            self.assertTrue(report['normalized_clock'])
            self.assertEqual(sounding_timeline(before,raw=True),sounding_timeline(after,raw=True))
            from mml_sync import analyze_mml,_leaves,_NOTE
            psg=(root/'added/clock.psg.target.mml').read_text()
            positions={n.start for n in _leaves(analyze_mml(psg)[0]['1']) if _NOTE.fullmatch(n.text.lower())}
            self.assertTrue(all(t in positions for t,_,_ in attacks(after)))
            plain=self.run_cli(source,root/'added','--enhance-drums',*flags,dump=False)
            self.assertEqual(plain,after)
            report=json.loads((root/'added/clock.drums.json').read_text())
            self.assertEqual(report['added_hits'],6)
            self.assertFalse((root/'added/clock.psg.before.normalize.mml').exists())

    def test_export_entry_forwards_feature_and_records_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'drums.vgm';source.write_bytes(noise_vgm())
            run=subprocess.run([sys.executable,str(ROOT/'scripts/export_mgs.py'),str(source),
                                '--outdir',str(root/'export'),'--enhance-drums','--skip-keyon-counts'],
                               capture_output=True,timeout=90)
            self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
            report=json.loads((root/'export/_diagnostics/tracks/drums.vgm/report.json').read_text())
            self.assertTrue(report['options']['enhance_drums'])
            self.assertEqual(report['summaries']['drums']['added_hits'],3)
            self.assertIn(b'Rhythm enhancement: 3 added hits',run.stdout)

    def test_high_native_melody_leaves_original_mml(self):
        extra=b'\x51\x36\x10\x51\x16\x80\x51\x26\x19'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'mixed.vgm';source.write_bytes(noise_vgm(extra))
            before=self.run_cli(source,root/'base')
            after=self.run_cli(source,root/'added','--enhance-drums')
            self.assertEqual(before,after)
            report=json.loads((root/'added/mixed.drums.json').read_text())
            self.assertEqual(report['reason'],'native_opll_melody_channels_6_8')


if __name__=='__main__':unittest.main()
