# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Staging build outputs for signing, and repackaging and verifying them after."""

import hashlib
import importlib.util
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from . import BUILD_DIR, SOURCE_TREE
from .installer import create_packages, get_target_cpu, portable_files


def load_chromium_tool(name):
    spec = importlib.util.spec_from_file_location(
        name, SOURCE_TREE / 'chrome/tools/build/win' / (name + '.py'))
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
    work = Path(tempfile.mkdtemp(prefix='signing-', dir=BUILD_DIR))
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
