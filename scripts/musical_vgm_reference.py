"""Optional authored direct-VGM audio probe using local pinned libvgm cores.

Explicit --setup builds unchanged local cores under ignored .tools/. No core
source is copied into this repository and setup never downloads dependencies.
SCC uses its native clock/16 grid; mixed output uses nearest sample resampling.
This is an independent playback smoke/frequency oracle, not acoustic equality.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'py'))
from vgm_timing import command_times
COMMIT='bad50c571db45b872304bdcd0603dd2214f0663e'
TOOLS=ROOT/'.tools/musical-vgm-reference'
UPSTREAM=ROOT/'.tools/huc6280-reference/upstream'
WRAPPERS={
'psg':r'''
#include "emu/cores/emu2149.c"
void* probe_create(unsigned clock) { EPSG* p=EPSG_new(clock,44100); if(p){EPSG_reset(p);EPSG_setVolumeMode(p,2);} return p; }
void probe_close(void* p){EPSG_delete(p);}
void probe_write(void* p,unsigned port,unsigned reg,unsigned val){EPSG_writeReg(p,reg,val);}
void probe_render(void* p,unsigned count,int* l,int* r){DEV_SMPL* out[2]={l,r};EPSG_calc_stereo(p,count,out);}
''',
'opll':r'''
#include "emu/cores/emu2413.c"
void* probe_create(unsigned clock){EOPLL* p=EOPLL_new(clock,44100);if(p){EOPLL_reset(p);EOPLL_resetPatch(p,0);}return p;}
void probe_close(void* p){EOPLL_delete(p);}
void probe_write(void* p,unsigned port,unsigned reg,unsigned val){EOPLL_writeReg(p,reg,val);}
void probe_render(void* p,unsigned count,int* l,int* r){DEV_SMPL* out[2]={l,r};ym2413_update_emu(p,count,out);}
''',
'scc':r'''
#include "emu/cores/k051649.c"
void* probe_create(unsigned clock){DEV_GEN_CFG cfg={0};DEV_INFO out={0};cfg.clock=clock;if(device_start_k051649(&cfg,&out))return NULL;void*p=out.dataPtr->chipInf;device_reset_k051649(p);return p;}
void probe_close(void* p){device_stop_k051649(p);}
void probe_write(void* p,unsigned port,unsigned reg,unsigned val){k051649_w(p,port*2,reg);k051649_w(p,port*2+1,val);}
void probe_render(void* p,unsigned count,int* l,int* r){DEV_SMPL* out[2]={l,r};k051649_update(p,count,out);}
'''}
SOURCES=['emu/cores/emu2149.c','emu/cores/emu2149_private.h','emu/cores/emu2149.h',
 'emu/cores/emu2413.c','emu/cores/emu2413_private.h','emu/cores/emu2413.h',
 'emu/cores/k051649.c','emu/cores/k051649.h','emu/panning.c','emu/panning.h',
 'emu/cores/ayintf.h','emu/cores/emutypes.h','emu/cores/opll_vrc7tone.h','emu/SoundDevs.h','emu/EmuStructs.h','emu/EmuHelper.h',
 'emu/snddef.h','emu/EmuCores.h','stdtype.h']


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_metadata():
    if not (UPSTREAM/'.git').exists():raise RuntimeError('First setup the pinned huc6280_reference local checkout')
    revision=subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()
    if revision!=COMMIT:raise RuntimeError('Unexpected libvgm revision')
    hashes={}
    for name in SOURCES:
        expected=subprocess.check_output(['git','-C',str(UPSTREAM),'show',COMMIT+':'+name])
        hashes[name]=hashlib.sha256(expected).hexdigest()
        if digest(UPSTREAM/name)!=hashes[name]:raise RuntimeError('Modified reference dependency: '+name)
    return dict(upstream='https://github.com/ValleyBell/libvgm',commit=COMMIT,source_sha256=hashes,
        attributions=['EMU2149/EMU2413: Mitsutaka Okazaki (MIT upstream)','K051649: Bryan McPhail (BSD-3-Clause)',
                      'panning: Maxim; retain upstream checkout notices'],
        limitations=['Not hardware verification','Independent cores use their own amplitude profiles',
                     'Mixed SCC resampling is nearest sample; no acoustic equivalence assertion'])


def setup():
    record=source_metadata();TOOLS.mkdir(parents=True,exist_ok=True)
    (TOOLS/'.gitignore').write_text('*\n')
    record['wrappers']={};record['libraries']={}
    for chip,source in WRAPPERS.items():
        wrapper=TOOLS/(chip+'.c');wrapper.write_text(source)
        library=TOOLS/(chip+'.so')
        subprocess.run(['cc','-std=c99','-O2','-fPIC','-shared','-I',str(UPSTREAM),
            str(wrapper),str(UPSTREAM/'emu/panning.c'),'-lm','-o',str(library)],check=True)
        record['wrappers'][chip]=digest(wrapper);record['libraries'][chip]=digest(library)
    (TOOLS/'metadata.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


class Core:
    def __init__(self,chip,clock):
        record=json.loads((TOOLS/'metadata.json').read_text())
        if record['commit']!=COMMIT:raise RuntimeError('Unexpected reference build')
        path=TOOLS/(chip+'.so')
        if digest(path)!=record['libraries'][chip] or hashlib.sha256(WRAPPERS[chip].encode()).hexdigest()!=record['wrappers'][chip]:
            raise RuntimeError('Reference wrapper/library differs; rebuild explicitly')
        self.rate=clock//16 if chip=='scc' else 44100
        self.lib=ctypes.CDLL(str(path))
        self.lib.probe_create.argtypes=[ctypes.c_uint];self.lib.probe_create.restype=ctypes.c_void_p
        self.lib.probe_close.argtypes=[ctypes.c_void_p]
        self.lib.probe_write.argtypes=[ctypes.c_void_p]+[ctypes.c_uint]*3
        self.lib.probe_render.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int)]
        self.handle=self.lib.probe_create(clock)
        if not self.handle:raise RuntimeError('Reference allocation failed')
    def close(self):
        if self.handle:self.lib.probe_close(self.handle);self.handle=None
    def write(self,port,reg,value):self.lib.probe_write(self.handle,port,reg,value)
    def render(self,frames):
        left=(ctypes.c_int*frames)();right=(ctypes.c_int*frames)()
        self.lib.probe_render(self.handle,frames,left,right)
        return tuple(left),tuple(right)


def render_vgm(raw):
    """Return independently rendered per-chip native PCM and mixed44100 PCM."""
    import struct
    specs=(('psg',0x74),('scc',0x9c),('opll',0x10))
    cores={chip:Core(chip,struct.unpack_from('<I',raw,offset)[0]&0x3fffffff)
           for chip,offset in specs if struct.unpack_from('<I',raw,offset)[0]&0x3fffffff}
    audio={chip:([],[]) for chip in cores};positions={chip:0 for chip in cores};end=0
    try:
        for event in command_times(raw):
            at=event.address
            if event.command in (0xa0,0xd2,0x51):
                chip={0xa0:'psg',0xd2:'scc',0x51:'opll'}[event.command]
                if chip not in cores:raise ValueError('Register write without matching clock')
                port,reg,value=(raw[at+1],raw[at+2],raw[at+3]) if chip=='scc' else (0,raw[at+1],raw[at+2])
                cores[chip].write(port,reg,value)
            elif event.command not in (0x61,0x62,0x63,0x66) and not 0x70<=event.command<=0x7f:
                raise ValueError('Reference accepts only scoped PSG/SCC/OPLL VGM commands')
            if event.wait_samples:
                end=event.vgmticks+event.wait_samples
                for chip,core in cores.items():
                    wanted=(end*core.rate+44099)//44100
                    left,right=core.render(wanted-positions[chip]);positions[chip]=wanted
                    audio[chip][0].extend(left);audio[chip][1].extend(right)
        mixed=tuple(sum(audio[chip][0][min(len(audio[chip][0])-1,i*cores[chip].rate//44100)]
                        for chip in cores) for i in range(end))
        return dict(rate_hz=44100,mixed=mixed,chips={chip:dict(rate_hz=cores[chip].rate,left=tuple(value[0]),right=tuple(value[1]))
                                                  for chip,value in audio.items()})
    finally:
        for core in cores.values():core.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup',action='store_true')
    args=parser.parse_args()
    if args.setup:print('Local reference ready:',setup()['commit'])
    else:parser.print_help()


if __name__=='__main__':main()
