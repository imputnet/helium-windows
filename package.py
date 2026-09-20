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
import platform
import re
from pathlib import Path
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent / 'helium-chromium' / 'utils'))
import helium_version
import filescfg
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent
_BUILD_SRC = _ROOT_DIR / 'build' / 'src'
_ICON_PATH = _BUILD_SRC / 'chrome' / 'app' / 'theme' / 'chromium' / 'win' / 'chromium.ico'
_PORTABLE_EXCLUSIONS = {Path(name) for name in (
    'mini_installer.exe', 'mini_installer_exe_version.rc', 'setup.exe',
    'helium.packed.7z')}


def get_target_cpu(build_outputs):
    args_gn_text = (build_outputs / 'args.gn').read_text()
    match = re.search(r'^\s*target_cpu\s*=\s*"(x64|arm64)"', args_gn_text, re.M)
    if not match:
        raise ValueError('Expected target_cpu x64 or arm64 in args.gn')
    return match[1]


def portable_files(build_outputs, cpu_arch='64bit'):
    return filescfg.filescfg_generator(
        _BUILD_SRC / 'chrome/tools/build/win/FILES.cfg',
        build_outputs, cpu_arch, _PORTABLE_EXCLUSIONS)


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


def create_packages(build_outputs, output_dir, cpu_arch='64bit', *, installer_inputs=None):
    build_outputs = build_outputs.resolve()
    installer_inputs = (installer_inputs or build_outputs).resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    version_parts = helium_version.get_version_parts(_ROOT_DIR / 'helium-chromium', _ROOT_DIR)
    version = f"{version_parts['HELIUM_MAJOR']}.{version_parts['HELIUM_MINOR']}." + \
              f"{version_parts['HELIUM_PATCH']}.{version_parts['HELIUM_PLATFORM']}"

    target_cpu = get_target_cpu(installer_inputs)

    installer_output = output_dir / f'helium_{version}_{target_cpu}-installer.exe'
    _build_nsis_installer(version, target_cpu, installer_inputs, installer_output)

    mini_installer_output = output_dir / f'helium_{version}_{target_cpu}-mini-installer.exe'
    shutil.copy2(installer_inputs / 'mini_installer.exe', mini_installer_output)

    timestamp = None
    try:
        with open(_BUILD_SRC / 'build/util/LASTCHANGE.committime', 'r') as ct:
            timestamp = int(ct.read())
    except FileNotFoundError:
        pass

    output = output_dir / f'helium_{version}_{target_cpu}-windows.zip'

    filescfg.create_archive(
        portable_files(build_outputs, cpu_arch), tuple(), build_outputs, output, timestamp)
    return installer_output, mini_installer_output, output


def main():
    """Entrypoint for local unsigned packaging."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-outputs', type=Path,
                        default=_BUILD_SRC / 'out/Default')
    parser.add_argument('--output-dir', type=Path, default=_ROOT_DIR / 'build')
    parser.add_argument(
        '--cpu-arch', metavar='ARCH', default=platform.architecture()[0],
        choices=('64bit', '32bit'),
        help='Target CPU filter in FILES.cfg. Default: %(default)s')
    args = parser.parse_args()
    create_packages(args.build_outputs, args.output_dir, args.cpu_arch)

if __name__ == '__main__':
    main()
