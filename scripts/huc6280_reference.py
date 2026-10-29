"""Optional authored HuC6280 reference checks using unchanged pinned libvgm.

Explicit setup installs the external core and local wrapper under ignored
.tools/huc6280-reference. No private fixtures are read by this tool.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'bad50c571db45b872304bdcd0603dd2214f0663e'
SOURCE_HASHES = {
    'emu/cores/c6280_mame.c': 'f342dd818a7b4bf0afe15f12320e62d85ff38f5ebf78ba2cc4d49b8e6f02eb4b',
    'emu/cores/c6280_mame.h': 'fcadacee436b4b8665f271122adc65f3ccb0f8f66b8efaf4c8efb410f01eca23',
    'stdtype.h': 'a7a8c9f8c6cf92e3820d5b986b5701ddc8d36784f3120127db8562c4ca58576c',
    'emu/EmuStructs.h': 'e606f8c183143d9bf83b4d0208fc11465c7c51c79e28e5d667954e29b6b16472',
    'emu/EmuHelper.h': '454342af628ee8ea09a48a0e2c471eed3fbf4555bcdb6e405176f8aeb8f7925b',
    'emu/snddef.h': '5d0b2ef05df3ad9145124ebca448c03e9c49305697fefe087f7e7085ca9265b1',
    'emu/EmuCores.h': '10b442e590ac9e309816c340171feb40e838c8b19aca4fa834b67d7709732f6b',
}
TOOLS = ROOT / '.tools/huc6280-reference'
UPSTREAM = TOOLS / 'upstream'
LIBRARY = TOOLS / 'libhuc6280_reference.so'
WRAPPER = r"""
#include "upstream/emu/cores/c6280_mame.c"
void* ref_create(unsigned clock, unsigned rate) {
    void* chip=device_start_c6280mame(clock,rate ? rate : clock/16);
    if(chip) device_reset_c6280mame(chip);
    return chip;
}
void ref_destroy(void* chip) { device_stop_c6280mame(chip); }
void ref_write(void* chip,unsigned reg,unsigned value) { c6280mame_w(chip,reg,value); }
void ref_render(void* chip,unsigned frames,int* left,int* right) {
    DEV_SMPL* output[2]={left,right}; c6280mame_update(chip,frames,output);
}
void ref_state(void* chip,unsigned channel,int* out) {
    c6280_t* p=chip; t_channel* c=&p->channel[channel];
    out[0]=p->select; out[1]=p->balance; out[2]=p->lfo_frequency; out[3]=p->lfo_control;
    out[4]=c->frequency; out[5]=c->control; out[6]=c->balance; out[7]=c->index;
    out[8]=c->counter; out[9]=c->dda; out[10]=c->noise_control;
    out[11]=c->noise_counter; out[12]=c->noise_seed;
    for(unsigned i=0;i<32;i++) out[13+i]=c->waveform[i];
}
void ref_volume(void* chip,int* out) {
    c6280_t* p=chip; for(unsigned i=0;i<32;i++) out[i]=p->volume_table[i];
}
"""


def metadata():
    if not (UPSTREAM / '.git').exists():
        raise RuntimeError('HuC6280 oracle is not installed; explicitly run --setup')
    revision = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != COMMIT:
        raise RuntimeError('Pinned HuC6280 reference revision differs')
    for name, digest in SOURCE_HASHES.items():
        if hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Pinned HuC6280 source hash differs: ' + name)
    return dict(upstream='https://github.com/ValleyBell/libvgm', commit=COMMIT,
        source_sha256=dict(SOURCE_HASHES), source_license='BSD-3-Clause',
        attribution='Charles MacDonald', sample_grid='clock_hz // 16',
        comparison='authored native waveform RAM/register/counter/index/gain and periodic audio',
        limitations=['Reference core is not a hardware specification',
                    'Upstream notes shared write/play index and LFO hardware uncertainty',
                    'Noise pseudo-random bits are not a verified hardware sequence',
                    'No cross-chip acoustic-equivalence assertion'])


def setup():
    TOOLS.mkdir(parents=True, exist_ok=True)
    (TOOLS / '.gitignore').write_text('*\n')
    if not (UPSTREAM / '.git').exists():
        local = ROOT.parent / 'x68k_vgm2mml/.tools/msm6295-reference/upstream'
        if (local / '.git').exists() and subprocess.check_output(
                ['git', '-C', str(local), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT:
            subprocess.run(['git', 'clone', '--no-checkout', '--no-hardlinks', str(local), str(UPSTREAM)], check=True)
        else:
            subprocess.run(['git', 'init', str(UPSTREAM)], check=True)
            subprocess.run(['git', '-C', str(UPSTREAM), 'remote', 'add', 'origin',
                            'https://github.com/ValleyBell/libvgm.git'], check=True)
            subprocess.run(['git', '-C', str(UPSTREAM), 'fetch', '--depth', '1', 'origin', COMMIT], check=True)
        subprocess.run(['git', '-C', str(UPSTREAM), 'checkout', '--detach', COMMIT], check=True)
    if subprocess.run(['git', '-C', str(UPSTREAM), 'diff', '--quiet', 'HEAD', '--']).returncode:
        raise RuntimeError('Pinned HuC6280 worktree has modified dependencies')
    record = metadata()
    wrapper = TOOLS / 'wrapper.c'
    wrapper.write_text(WRAPPER)
    subprocess.run(['cc', '-std=c99', '-O2', '-fPIC', '-shared', str(wrapper), '-lm', '-o', str(LIBRARY)], check=True)
    record.update(wrapper_sha256=hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                  library_sha256=hashlib.sha256(LIBRARY.read_bytes()).hexdigest())
    (TOOLS / 'metadata.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


class Reference:
    def __init__(self, clock=3579545, rate=None):
        metadata()
        record = json.loads((TOOLS / 'metadata.json').read_text())
        if record.get('wrapper_sha256') != hashlib.sha256(WRAPPER.encode()).hexdigest():
            raise RuntimeError('HuC6280 wrapper differs; explicitly rebuild with --setup')
        if record.get('library_sha256') != hashlib.sha256(LIBRARY.read_bytes()).hexdigest():
            raise RuntimeError('HuC6280 oracle library differs; explicitly rebuild with --setup')
        self.lib = ctypes.CDLL(str(LIBRARY))
        self.lib.ref_create.argtypes = [ctypes.c_uint, ctypes.c_uint]
        self.lib.ref_create.restype = ctypes.c_void_p
        self.lib.ref_destroy.argtypes = [ctypes.c_void_p]
        self.lib.ref_write.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        self.lib.ref_render.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        self.lib.ref_state.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
        self.lib.ref_volume.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.clock_hz = clock
        self.rate_hz = clock // 16 if rate is None else rate
        self.native_frame = 0
        self.handle = self.lib.ref_create(clock, self.rate_hz)
        if not self.handle:
            raise RuntimeError('HuC6280 reference allocation failed')

    def close(self):
        if self.handle:
            self.lib.ref_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def write(self, register, value):
        self.lib.ref_write(self.handle, register, value)

    def render(self, frames):
        if frames < 0:
            raise ValueError('Negative frame count')
        if not frames:
            return (), ()
        left = (ctypes.c_int * frames)()
        right = (ctypes.c_int * frames)()
        self.lib.ref_render(self.handle, frames, left, right)
        self.native_frame += frames
        return tuple(left), tuple(right)

    def advance(self, frames):
        self.render(frames)

    def snapshot(self):
        channels = []
        for ch in range(8):
            row = (ctypes.c_int * 45)()
            self.lib.ref_state(self.handle, ch, row)
            channels.append(dict(frequency=row[4], control=row[5], balance=row[6], index=row[7],
                counter=row[8], dda=row[9], noise_control=row[10], noise_counter=row[11],
                noise_seed=row[12], waveform=tuple(row[13:])))
        return dict(selected_channel=row[0], global_balance=row[1], lfo_frequency=row[2],
                    lfo_control=row[3], channels=channels, native_frame=self.native_frame)

    def volume_table(self):
        row = (ctypes.c_int * 32)()
        self.lib.ref_volume(self.handle, row)
        return tuple(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', action='store_true', help='Fetch/reuse pinned libvgm and build optional reference')
    parser.add_argument('--self-test', action='store_true', help='Run authored reference tests, never private fixtures')
    args = parser.parse_args()
    if args.setup:
        details = setup()
        print('Pinned HuC6280 reference ready:', details['commit'])
    if args.self_test:
        import unittest
        sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/script')]
        suite = unittest.defaultTestLoader.loadTestsFromName('test_huc6280_reference')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
    if not args.setup and not args.self_test:
        parser.print_help()


if __name__ == '__main__':
    main()
