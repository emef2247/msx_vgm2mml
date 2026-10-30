"""HW-envelope pitch partitions stay adjacent untied notes, never ties."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(Path(__file__).parent)]
from test_psg_scc_performance import psg
from psg_scc_performance import analyze
from psg_hw_envelope_mml import continuation_starts
from vgm_io import read_vgm_bytes
from vgm_timing import command_times


def source():
    return {0:[psg(tick,1,ev_type='evS' if tick in (0,3) else 'fCA',
                   envelope_enabled=1,amplitude_register=16,envelope_period=416,
                   tone_period=400-tick*10,scale=('c','d','e')[tick%3])
               for tick in range(6)]}


class HardwareEnvelopePlaybackTests(unittest.TestCase):
    def test_pitch_partitions_are_not_tied_continuations(self):
        performance=analyze(source(),'psg')
        self.assertEqual(continuation_starts(performance),set())

    @unittest.skipUnless(shutil.which('mgsc') and shutil.which('node'),'requires MGSC and Node')
    def test_actual_driver_restarts_envelope_on_each_adjacent_partition(self):
        from pre_envelope_loops import LoopFirstEnvelopeBank,ScoreGuidedEnvelopeBank
        from production_v110.pre_envelope_loops import LoopFirstEnvelopeBank as HistoricalBank
        for kind in (LoopFirstEnvelopeBank,ScoreGuidedEnvelopeBank,HistoricalBank):
            with self.subTest(bank=kind.__module__+kind.__name__),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);mml=root/'probe.mml';mgs=root/'probe.mgs';vgm=root/'probe.vgm'
                bank=kind(deferred=True)
                bank.submit(source(),'psg',mml,performance=analyze(source(),'psg'))
                bank.flush()
                text=mml.read_text()
                text='\n'.join(line for line in text.splitlines() if not line.startswith('#alloc'))
                mml.write_text('#opll_mode 0\n'+text+'\n')
                compiled=subprocess.run(['mgsc',str(mml),str(mgs)],capture_output=True)
                self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
                played=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'1000'],capture_output=True)
                self.assertEqual(played.returncode,0,played.stderr)
                raw=read_vgm_bytes(vgm)
                resets=[raw[e.address+2] for e in command_times(raw)
                        if e.command==0xa0 and raw[e.address+1]==13]
                self.assertEqual(resets,[9,9,9,9,9,9])
