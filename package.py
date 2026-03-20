#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Copyright (c) 2018 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
ungoogled-chromium packaging script for Microsoft Windows
"""

import sys
if sys.version_info.major < 3:
    raise RuntimeError('Python 3 is required for this script.')

import argparse
import os
import platform
from pathlib import Path
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent / 'helium-chromium' / 'utils'))
import helium_version
import filescfg
from _common import ENCODING, get_chromium_version
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent
_BUILD_SRC = _ROOT_DIR / 'build' / 'src'
_ICON_PATH = _BUILD_SRC / 'chrome' / 'app' / 'theme' / 'chromium' / 'win' / 'chromium.ico'

_cached_target_cpu = None

def _get_target_cpu(build_outputs):
    global _cached_target_cpu
    if not _cached_target_cpu:
        with open(build_outputs / 'args.gn', 'r') as f:
            args_gn_text = f.read()
            for cpu in ('x64', 'arm64'):
                if f'target_cpu="{cpu}"' in args_gn_text:
                    _cached_target_cpu = cpu
                    break
    assert _cached_target_cpu
    return _cached_target_cpu

def _build_nsis_installer(version, arch, build_outputs, output_file):
    cmd = [
        str(_BUILD_SRC / 'third_party' / 'nsis' / 'makensis.exe'),
        '-NOCD',
        f'-DVERSION={version}',
        f'-DARCH={arch}',
        f'-DSETUP_EXE={build_outputs / "setup.exe"}',
        f'-DHELIUM_7Z={build_outputs / "helium.packed.7z"}',
        f'-DICON_FILE={_ICON_PATH}',
        f'-DOUTPUT_FILE={output_file}',
        f'-DLICENSE_FILE={_ROOT_DIR / "LICENSE"}',
        str(_ROOT_DIR / 'installer' / 'helium.nsi'),
    ]
    subprocess.run(cmd, check=True)


def main():
    """Entrypoint"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--cpu-arch',
        metavar='ARCH',
        default=platform.architecture()[0],
        choices=('64bit', '32bit'),
        help=('Filter build outputs by a target CPU. '
              'This is the same as the "arch" key in FILES.cfg. '
              'Default (from platform.architecture()): %(default)s'))
    args = parser.parse_args()

    build_outputs = Path('build/src/out/Default')

    version_parts = helium_version.get_version_parts(_ROOT_DIR / 'helium-chromium', _ROOT_DIR)
    version = f"{version_parts['HELIUM_MAJOR']}.{version_parts['HELIUM_MINOR']}." + \
              f"{version_parts['HELIUM_PATCH']}.{version_parts['HELIUM_PLATFORM']}"

    target_cpu = _get_target_cpu(build_outputs)

    installer_output = _ROOT_DIR / 'build' / f'helium_{version}_{target_cpu}-installer.exe'
    _build_nsis_installer(version, target_cpu, build_outputs, installer_output)

    timestamp = None
    try:
        with open('build/src/build/util/LASTCHANGE.committime', 'r') as ct:
            timestamp = int(ct.read())
    except FileNotFoundError:
        pass

    output = Path('build/helium_{}_{}-windows.zip'.format(
        version, target_cpu))

    excluded_files = set([
        Path('mini_installer.exe'),
        Path('mini_installer_exe_version.rc'),
        Path('setup.exe'),
        Path('helium.packed.7z'),
    ])
    files_generator = filescfg.filescfg_generator(
        Path('build/src/chrome/tools/build/win/FILES.cfg'),
        build_outputs, args.cpu_arch, excluded_files)
    filescfg.create_archive(
        files_generator, tuple(), build_outputs, output, timestamp)

if __name__ == '__main__':
    main()
