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
import hashlib
import importlib.util
import platform
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

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


def load_chromium_tool(name):
    spec = importlib.util.spec_from_file_location(
        name, _BUILD_SRC / 'chrome/tools/build/win' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}


def extract(seven_zip, archive, directory):
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(seven_zip), 'x', str(archive), f'-o{directory}', '-y'], check=True)


def stage_build(build_outputs, seven_zip, arch=None):
    """Copy build outputs into a fresh directory before modifying them."""
    build_arch = get_target_cpu(build_outputs)
    if arch and arch != build_arch:
        raise ValueError(f'Build architecture {build_arch} does not match {arch}')
    # A new directory makes reruns independent of partially signed old releases.
    work = Path(tempfile.mkdtemp(prefix='signing-', dir=_ROOT_DIR / 'build'))
    portable = work / 'portable'
    portable.mkdir()
    for rel in portable_files(build_outputs):
        src, dst = build_outputs / rel, portable / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    for name in ('setup.exe', 'args.gn'):
        shutil.copy2(build_outputs / name, work / name)
    shutil.copy2(build_outputs / 'mini_installer.exe', work / 'unsigned-mini-installer.exe')
    extract(seven_zip, build_outputs / 'helium.7z', work / 'payload')
    version = load_chromium_tool('create_installer_archive').BuildVersion()
    for required in (portable / 'chrome.exe', portable / 'chrome.dll',
                     work / 'payload/Helium-bin/chrome.exe',
                     work / 'payload/Helium-bin' / version / 'chrome.dll'):
        if not required.is_file():
            raise FileNotFoundError(required)

    print(f'Signing staging directory: {work}')
    return work


def rebuild_mini_installer(work):
    """Replace compiled resources without relinking any signed executable."""
    import win32api
    editor = load_chromium_tool('resedit').ResourceEditor(
        str(work / 'unsigned-mini-installer.exe'), str(work / 'mini_installer.exe'))
    # Refuse layouts we do not support rather than leaving a stale payload in
    # the executable. The release build emits compressed archive + cabinet.
    if win32api.EnumResourceNames(editor.module, 'B7') != ['HELIUM.PACKED.7Z']:
        raise ValueError('Unexpected mini installer archive resources')
    if win32api.EnumResourceNames(editor.module, 'BL') != ['SETUP.EX_']:
        raise ValueError('Unexpected mini installer setup resources')
    for kind, name in (('B7', 'HELIUM.PACKED.7Z'), ('BL', 'SETUP.EX_')):
        if win32api.EnumResourceLanguages(editor.module, kind, name) != [1033]:
            raise ValueError('Unexpected mini installer resource language')
    editor.RemoveResource('BL', 1033, 'SETUP.EX_')
    # BN is upstream's supported uncompressed setup representation. The outer
    # installer is signed only after its resources have been replaced.
    editor.UpdateResource('BN', 1033, 'SETUP.EXE', str(work / 'setup.exe'))
    editor.UpdateResource('B7', 1033, 'HELIUM.PACKED.7Z', str(work / 'helium.packed.7z'))
    editor.Commit()


def build_packages(work, build_outputs, seven_zip):
    """Rebuild the installer payload, then create the release packages."""
    outputs = work / 'artifacts'
    if outputs.exists():
        raise FileExistsError(f'Release already packaged: {outputs}')
    subprocess.run([str(seven_zip), 'a', '-t7z', str(work / 'helium.7z'),
                    str(work / 'payload/Helium-bin'), '-mx0'], check=True)
    archive = load_chromium_tool('create_installer_archive')
    # Use upstream's BCJ2/LZMA settings: the mini installer's decoder does not
    # support arbitrary compression methods chosen by modern 7-Zip defaults.
    archive.GetLZMAExec = lambda _: str(seven_zip)
    archive.CompressUsingLZMA(str(build_outputs), str(work / 'helium.packed.7z'),
                             str(work / 'helium.7z'), True, False, strip_time=True)
    rebuild_mini_installer(work)
    return create_packages(work / 'portable', outputs, installer_inputs=work)


def check_equal(actual, expected, description):
    if actual != expected:
        raise ValueError(f'{description} differs from the signed staging files')


def verify_mini_installer(mini, temp, seven_zip, expected):
    editor = load_chromium_tool('resedit').ResourceEditor(str(mini), None)
    editor.ExtractResource('BN', 1033, 'SETUP.EXE', str(temp / 'setup.exe'))
    editor.ExtractResource('B7', 1033, 'HELIUM.PACKED.7Z', str(temp / 'helium.packed.7z'))
    check_equal(digest(temp / 'setup.exe'), expected['setup'], 'Mini installer setup')
    check_equal(digest(temp / 'helium.packed.7z'), expected['archive'], 'Mini installer archive')
    extract(seven_zip, temp / 'helium.packed.7z', temp / 'inner')
    extract(seven_zip, temp / 'inner/helium.7z', temp / 'payload')
    check_equal(inventory(temp / 'payload'), expected['payload'], 'Installer payload')


def verify_nsis_installer(nsis, temp, seven_zip, expected):
    extract(seven_zip, nsis, temp / 'nsis')
    for name, hash_value in (('setup.exe', expected['setup']),
                             ('helium.7z', expected['archive'])):
        extracted, = (temp / 'nsis').rglob(name)
        check_equal(digest(extracted), hash_value, f'NSIS {name}')


def verify_portable_zip(portable, expected):
    with zipfile.ZipFile(portable) as archive:
        actual = {}
        for name in archive.namelist():
            if name.endswith('/'):
                continue
            prefix, separator, relative = name.partition('/')
            if prefix != portable.stem or not separator or relative in actual:
                raise ValueError(f'Unexpected ZIP entry: {name}')
            with archive.open(name) as stream:
                actual[relative] = hashlib.file_digest(stream, 'sha256').hexdigest()
        check_equal(actual, expected['portable'], 'Portable ZIP')


def verify_packages(work, seven_zip, nsis, mini, portable, expected):
    """Check that each release package contains the signed staging files."""
    expected = {**expected, 'archive': digest(work / 'helium.packed.7z')}
    with tempfile.TemporaryDirectory(prefix='verify-', dir=work) as temp:
        temp = Path(temp)
        verify_mini_installer(mini, temp, seven_zip, expected)
        verify_nsis_installer(nsis, temp, seven_zip, expected)
        verify_portable_zip(portable, expected)
    print('Verified both installers and portable ZIP against the signed payloads.')


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
