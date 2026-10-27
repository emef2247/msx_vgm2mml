"""Actual driver-frame comparison; raw dispatch transients are not hidden."""
from bisect import bisect_right
import contextlib
import io
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'py')]
import vgm2mml
from vgm_io import read_vgm_bytes
from vgm_timing import command_times
from mml_envelopes import EnvelopeBank


def authored(path,offset):
    raw=bytearray(256);raw[:4]=b'Vgm '
    for position,value in ((8,0x171),(0x34,256-0x34),(0x74,1789773)):
        struct.pack_into('<I',raw,position,value)
    raw+=bytes.fromhex('a0 07 3c a0 00 90 a0 01 01 a0 02 90 a0 03 01')
    if offset:raw+=b'\x61'+struct.pack('<H',offset)
    for left,right in zip((15,15,11,10,6),(15,15,10,10,6)):
        raw+=bytes((0xa0,8,left,0xa0,9,right,0x62))
    raw+=bytes.fromhex('a0 08 00 a0 09 00 62 66')
    struct.pack_into('<I',raw,4,len(raw)-4);struct.pack_into('<I',raw,0x18,4410+offset)
    path.write_bytes(raw)


def trace(path):
    raw=read_vgm_bytes(path);events=list(command_times(raw))
    registers={reg:[] for reg in range(14)}
    for event in events:
        if event.command==0xa0:
            registers[raw[event.address+1]].append((event.vgmticks,raw[event.address+2]))
    return registers,events[-1].vgmticks


def level(rows,at):
    position=bisect_right([t for t,_ in rows],at)-1
    return rows[position][1] if position>=0 else 0


@unittest.skipUnless(shutil.which('mgsc') and shutil.which('node'),'MGSC and libkss Node runtime required')
class CurveApproxPlaybackTests(unittest.TestCase):
    def check_case(self,offset,capacity):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'song.vgm';authored(source,offset)
            traces=[]
            for mode in ('baseline','approx'):
                folder=root/mode
                args=['vgm2mml.py',str(source),'--outdir',str(folder),'--software-volume-curves']
                if mode=='approx':
                    args+=['--score-guided-loops','--psg-state-ms','24',
                           '--curve-volume-error','1','--curve-mean-error','.25']
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(sys,'argv',args))
                    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    if capacity:stack.enter_context(patch.object(EnvelopeBank,'register',return_value=None))
                    self.assertEqual(vgm2mml.main(),0)
                mgs=folder/'song.mgs';vgm=folder/'song.played.vgm'
                compiled=subprocess.run(['mgsc',str(folder/'song.mml'),str(mgs)],capture_output=True,timeout=30)
                self.assertEqual(compiled.returncode,0,compiled.stdout)
                played=subprocess.run(['node',str(ROOT/'scripts/mgs_to_vgm.mjs'),str(mgs),str(vgm),'2000'],
                                      capture_output=True,timeout=45)
                self.assertEqual(played.returncode,0,played.stderr)
                traces.append(trace(vgm))
            (before,end),(after,new_end)=traces
            # Inspect a settled point in every output frame; preserve raw events
            # separately because instruction dispatch can shift a write by 1 sample.
            times=range(300,min(end,new_end),735)
            main=[abs(level(before[8],at)-level(after[8],at)) for at in times]
            other=[abs(level(before[9],at)-level(after[9],at)) for at in times]
            self.assertEqual(max(main),1)
            self.assertEqual(sum(value>0 for value in main),1)
            self.assertFalse(any(other))
            for reg in (0,1,2,3,7):
                def changes(rows):
                    result=[]
                    for at,value in rows:
                        if not result or result[-1][1]!=value:result.append((at,value))
                    return result
                left,right=changes(before[reg]),changes(after[reg])
                self.assertEqual([v for _,v in left],[v for _,v in right])
                self.assertLessEqual(max((abs(a[0]-b[0]) for a,b in zip(left,right)),default=0),8)
            # Deliberately do not assert raw samplewise error<=1: a dispatch
            # transient at a large step can exceed the logical curve budget.
            raw_times=sorted({t for reg in (8,9) for t,_ in before[reg]+after[reg]})
            raw_peak=max(abs(level(before[8],at)-level(after[8],at)) for at in raw_times)
            self.assertGreaterEqual(raw_peak,1)

    def test_observed_curve_at_zero_and_nonzero_frame_phase(self):
        for offset in (0,1000):
            with self.subTest(offset=offset):self.check_case(offset,False)

    def test_full_envelope_bank_uses_same_bounded_inline_curve(self):
        for offset in (0,1000):
            with self.subTest(offset=offset):self.check_case(offset,True)


if __name__=='__main__':unittest.main()
