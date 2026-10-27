"""Ensure the selected Python has the contracts required by this checkout."""
from __future__ import annotations
import argparse
import subprocess
import sys

# Tested story-contract revision; reinstall even when an older build reused a version.
GITHUB_PACKAGE = ('git+https://github.com/whenigetout/manganarrator_contracts.git'
                  '@e26d418be3c06fcd2a66efc21b9e4448e7494881#subdirectory=python')
CHECK = 'from mn_contracts.story import StoryProject; from mn_contracts import __file__; print(__file__)'


def ensure_contracts(force=False):
    command = [sys.executable, '-c', CHECK]
    probe = subprocess.run(command, capture_output=True, text=True)
    if probe.returncode == 0 and not force:
        print('[contracts] Ready: ' + probe.stdout.strip())
        return 0
    print('[contracts] Installing Story Studio contracts into ' + sys.executable, flush=True)
    install = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade',
                              '--force-reinstall', '--no-deps', GITHUB_PACKAGE])
    if install.returncode:
        print('[contracts] Install failed. Check Git/network access and retry in the activated Conda environment.', file=sys.stderr)
        return install.returncode
    check = subprocess.run(command)
    if check.returncode:
        print('[contracts] Import still fails. Check for a local mn_contracts folder shadowing the installed package.', file=sys.stderr)
    return check.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Reinstall the tested contracts revision even if the import works')
    return ensure_contracts(parser.parse_args().force)


if __name__ == '__main__':
    raise SystemExit(main())
