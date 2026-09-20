#!/usr/bin/env python3
# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Stage, repack and verify Windows releases without modifying build outputs."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import package

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'build/src'


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def load_chromium_tool(name):
    spec = importlib.util.spec_from_file_location(
        name, SOURCE / 'chrome/tools/build/win' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pe_files(directory):
    return sorted(p for p in directory.rglob('*')
                  if p.is_file() and p.suffix.lower() in ('.exe', '.dll'))


def inventory(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}


def emit(name, value):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'{name}={value}\n')


def extract(seven_zip, archive, directory):
    directory.mkdir(parents=True, exist_ok=True)
    run(seven_zip, 'x', archive, f'-o{directory}', '-y')


def find_signtool():
    sdk = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))
    tools = list((sdk / 'Windows Kits/10/bin').glob('*/x64/signtool.exe'))
    if tools:
        return max(tools, key=lambda p: tuple(int(n) for n in p.parents[1].name.split('.')))
    tool = shutil.which('signtool')
    if tool:
        return tool
    raise FileNotFoundError('signtool.exe not found; install the Windows SDK or add x64 SignTool to PATH')


def verify_signatures(files, tool):
    if not files:
        raise ValueError('No binaries to verify')
    # /pa selects Authenticode policy; /tw warns on missing timestamps.
    # check=True rejects both failures (1) and warnings (2).
    for start in range(0, len(files), 32):
        run(tool, 'verify', '/pa', '/all', '/tw', *files[start:start + 32])


def sign(files, description, args, metadata):
    for start in range(0, len(files), 32):
        run(args.signtool, 'sign', '/fd', 'SHA256',
            '/tr', 'http://timestamp.acs.microsoft.com', '/td', 'SHA256',
            '/dlib', args.dlib, '/dmdf', metadata, '/d', description,
            '/du', 'https://github.com/imputnet/helium-windows',
            *files[start:start + 32])
    verify_signatures(files, args.signtool)


def stage_build(args):
    """Copy build outputs into a fresh directory before modifying them."""
    arch = package.get_target_cpu(args.build_outputs)
    if args.arch and args.arch != arch:
        raise ValueError(f'Build architecture {arch} does not match {args.arch}')
    # A new directory makes reruns independent of partially signed old releases.
    work = Path(tempfile.mkdtemp(prefix='signing-', dir=ROOT / 'build'))
    portable = work / 'portable'
    portable.mkdir()
    for rel in package.portable_files(args.build_outputs):
        src, dst = args.build_outputs / rel, portable / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    for name in ('setup.exe', 'args.gn'):
        shutil.copy2(args.build_outputs / name, work / name)
    shutil.copy2(args.build_outputs / 'mini_installer.exe', work / 'unsigned-mini-installer.exe')
    extract(args.seven_zip, args.build_outputs / 'helium.7z', work / 'payload')
    version = load_chromium_tool('create_installer_archive').BuildVersion()
    for required in (portable / 'chrome.exe', portable / 'chrome.dll',
                     work / 'payload/Helium-bin/chrome.exe',
                     work / 'payload/Helium-bin' / version / 'chrome.dll'):
        if not required.is_file():
            raise FileNotFoundError(required)

    print(f'Signing staging directory: {work}')
    return work


def sign_staged_binaries(work, args, metadata):
    """Sign identical binaries once and copy the result to every package layout."""
    groups = {}
    files = pe_files(work / 'portable') + pe_files(work / 'payload') + [work / 'setup.exe']
    for file in files:
        description = ('Helium Update Helper'
                       if file.name.lower() == 'helium_update_helper.exe' else 'Helium')
        groups.setdefault((description, digest(file)), []).append(file)
    if {description for description, _ in groups} != {'Helium', 'Helium Update Helper'}:
        raise ValueError('Expected browser and updater helper signing inputs')

    for description in ('Helium', 'Helium Update Helper'):
        originals = [paths[0] for (label, _), paths in groups.items() if label == description]
        sign(originals, description, args, metadata)
    for original, *copies in groups.values():
        for destination in copies:
            shutil.copy2(original, destination)


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


def build_packages(work, args):
    """Rebuild the installer payload, then create the release packages."""
    outputs = work / 'artifacts'
    if outputs.exists():
        raise FileExistsError(f'Release already packaged: {outputs}')
    run(args.seven_zip, 'a', '-t7z', work / 'helium.7z',
        work / 'payload/Helium-bin', '-mx0')
    archive = load_chromium_tool('create_installer_archive')
    # Use upstream's BCJ2/LZMA settings: the mini installer's decoder does not
    # support arbitrary compression methods chosen by modern 7-Zip defaults.
    archive.GetLZMAExec = lambda _: str(args.seven_zip)
    archive.CompressUsingLZMA(str(args.build_outputs), str(work / 'helium.packed.7z'),
                             str(work / 'helium.7z'), True, False, strip_time=True)
    rebuild_mini_installer(work)
    return package.create_packages(work / 'portable', outputs, installer_inputs=work)


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


def verify_packages(work, args, nsis, mini, portable, expected):
    """Check that each release package contains the signed staging files."""
    expected = {**expected, 'archive': digest(work / 'helium.packed.7z')}
    with tempfile.TemporaryDirectory(prefix='verify-', dir=work) as temp:
        temp = Path(temp)
        verify_mini_installer(mini, temp, args.seven_zip, expected)
        verify_nsis_installer(nsis, temp, args.seven_zip, expected)
        verify_portable_zip(portable, expected)
    print('Verified both installers and portable ZIP against the signed payloads.')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-outputs', type=Path, default=SOURCE / 'out/Default')
    parser.add_argument('--dlib', type=Path, required=True,
                        help="Path to the x64 Azure.CodeSigning.Dlib.dll")
    parser.add_argument('--signtool', type=Path, help='Path to x64 signtool.exe')
    parser.add_argument('--arch', choices=('x64', 'arm64'))
    parser.add_argument('--seven-zip', type=Path,
                        default=Path(shutil.which('7z') or 'C:/Program Files/7-Zip/7z.exe'))
    args = parser.parse_args()
    args.build_outputs = args.build_outputs.resolve()
    args.seven_zip = args.seven_zip.resolve()
    args.dlib = args.dlib.resolve()
    if not args.dlib.is_file():
        parser.error(f'Signing plugin not found: {args.dlib}')
    args.signtool = args.signtool.resolve() if args.signtool else find_signtool()
    required = ('AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET',
                'AZURE_SIGNING_ENDPOINT', 'AZURE_SIGNING_ACCOUNT',
                'AZURE_SIGNING_CERTIFICATE_NAME')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        parser.error('Missing environment variables: ' + ', '.join(missing))

    return args


def write_signing_metadata(work):
    metadata = work / 'metadata.json'
    metadata.write_text(json.dumps({
        'Endpoint': os.environ['AZURE_SIGNING_ENDPOINT'],
        'CodeSigningAccountName': os.environ['AZURE_SIGNING_ACCOUNT'],
        'CertificateProfileName': os.environ['AZURE_SIGNING_CERTIFICATE_NAME'],
        # Use only EnvironmentCredential, never a runner's cached login.
        'ExcludeCredentials': [
            'ManagedIdentityCredential', 'WorkloadIdentityCredential',
            'SharedTokenCacheCredential', 'VisualStudioCredential',
            'VisualStudioCodeCredential', 'AzureCliCredential',
            'AzurePowerShellCredential', 'AzureDeveloperCliCredential',
            'InteractiveBrowserCredential',
        ],
    }), encoding='utf-8')
    return metadata


def main():
    args = parse_args()
    work = stage_build(args)
    metadata = write_signing_metadata(work)
    sign_staged_binaries(work, args, metadata)

    # Snapshot the signed inputs before packaging so verification can detect changes.
    expected = {'payload': inventory(work / 'payload'),
                'portable': inventory(work / 'portable'),
                'setup': digest(work / 'setup.exe')}
    nsis, mini, portable = build_packages(work, args)
    verify_packages(work, args, nsis, mini, portable, expected)
    sign([nsis, mini], 'Helium Installer', args, metadata)
    emit('artifacts', work / 'artifacts')


if __name__ == '__main__':
    main()
