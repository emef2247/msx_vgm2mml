#!/usr/bin/env python3
"""Install/check repository-local JavaScript MGSC and libkss dependencies."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ('mgsc-js@2.0.0', 'libkss-js')


def run(args, *, cwd=ROOT, timeout=180):
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return False
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description='Set up mgsc-js and libkss-js for MGS exports')
    parser.add_argument('--check', action='store_true', help='Only verify existing dependencies')
    args = parser.parse_args()
    print(f'Repository: {ROOT}', flush=True)
    if not shutil.which('node') or not shutil.which('npm'):
        print('ERROR: Node.js and npm must be installed and on PATH.', file=sys.stderr)
        return 1
    if not run(['node', '--version']) or not run(['npm', '--version']):
        return 1
    if not args.check:
        print('Installing JavaScript dependencies locally...', flush=True)
        # No global install and no package-lock modifications.
        if not run(['npm', 'install', '--no-save', '--package-lock=false', *PACKAGES], timeout=600):
            return 1
    print('Checking MGSC initialization...', flush=True)
    if not run(['node', str(ROOT / 'scripts' / 'compile_mgs.mjs'), '--check']):
        print('ERROR: MGSC initialization failed.', file=sys.stderr)
        return 1
    print('Checking libkss-js module availability...', flush=True)
    # Resolve from the repository, not a globally installed package.
    js = "import('libkss-js').then(m => { if (!m) process.exit(1); console.log('libkss-js import OK'); }).catch(e => { console.error(e); process.exit(1); });"
    if not run(['node', '--input-type=module', '-e', js]):
        print('ERROR: libkss-js import failed.', file=sys.stderr)
        return 1
    print('Setup checks passed. (Playback functionality is not verified by this check.)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
