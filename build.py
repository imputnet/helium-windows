#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Copyright (c) 2019 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
Helium build script for Windows
"""

import sys
import time
import argparse
import os
import shutil
import subprocess
import ctypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'helium-chromium' / 'utils'))
import downloads
import domain_substitution
import i18n_apply
import name_substitution
import helium_version
import generate_resources
import replace_resources
import prune_binaries
import patches
from _common import ENCODING, USE_REGISTRY, ExtractorEnum, get_logger
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent
_PATCH_BIN_RELPATH = Path('third_party/git/usr/bin/patch.exe')


def _get_vcvars_path(name='64'):
    """
    Returns the path to the corresponding vcvars*.bat path

    As of VS 2017, name can be one of: 32, 64, all, amd64_x86, x86_amd64
    """
    vswhere_exe = '%ProgramFiles(x86)%\\Microsoft Visual Studio\\Installer\\vswhere.exe'
    result = subprocess.run(
        '"{}" -products * -prerelease -latest -property installationPath'.format(vswhere_exe),
        shell=True,
        check=True,
        stdout=subprocess.PIPE,
        universal_newlines=True)
    vcvars_path = Path(result.stdout.strip(), 'VC/Auxiliary/Build/vcvars{}.bat'.format(name))
    if not vcvars_path.exists():
        raise RuntimeError(
            'Could not find vcvars batch script in expected location: {}'.format(vcvars_path))
    return vcvars_path


def _run_build_process(*args, **kwargs):
    """
    Runs the subprocess with the correct environment variables for building
    """
    # Add call to set VC variables
    cmd_input = ['call "%s" >nul' % _get_vcvars_path()]
    cmd_input.append('set DEPOT_TOOLS_WIN_TOOLCHAIN=0')
    cmd_input.append(' '.join(map('"{}"'.format, args)))
    cmd_input.append('exit\n')
    subprocess.run(('cmd.exe', '/k'),
                   input='\n'.join(cmd_input),
                   check=True,
                   encoding=ENCODING,
                   **kwargs)


def _run_build_process_timeout(*args, timeout):
    """
    Runs the subprocess with the correct environment variables for building
    """
    # Add call to set VC variables
    cmd_input = ['call "%s" >nul' % _get_vcvars_path()]
    cmd_input.append('set DEPOT_TOOLS_WIN_TOOLCHAIN=0')
    cmd_input.append(' '.join(map('"{}"'.format, args)))
    cmd_input.append('exit\n')
    with subprocess.Popen(('cmd.exe', '/k'), encoding=ENCODING, stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) as proc:
        proc.stdin.write('\n'.join(cmd_input))
        proc.stdin.close()
        try:
            proc.wait(timeout)
            if proc.returncode != 0:
                raise RuntimeError('Build failed!')
        except subprocess.TimeoutExpired:
            print('Sending keyboard interrupt')
            for _ in range(3):
                ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, proc.pid)
                time.sleep(1)
            try:
                proc.wait(10)
            except:
                proc.kill()
            sys.exit(42)


def _make_tmp_paths():
    """Creates TMP and TEMP variable dirs so ninja won't fail"""
    tmp_path = Path(os.environ['TMP'])
    if not tmp_path.exists():
        tmp_path.mkdir()
    tmp_path = Path(os.environ['TEMP'])
    if not tmp_path.exists():
        tmp_path.mkdir()


def _configure_remoteexec(source_tree):
    address = os.environ.get('SISO_REAPI_ADDRESS', '')
    instance = os.environ.get('SISO_REAPI_INSTANCE') or 'main'
    backend = ''
    if address:
        os.environ['SISO_REAPI_INSTANCE'] = instance
        backend = 'nativelink.star'

    subprocess.run([
        sys.executable, str(source_tree / 'build/config/siso/configure_siso.py'),
        '--rbe_instance=projects/rbe-chrome-untrusted/instances/default_instance',
        f'--reapi_address={address}',
        f'--reapi_instance={instance if address else ""}',
        f'--reapi_backend_config_path={backend}',
    ], check=True)


def main():
    """CLI Entrypoint"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--7z-path',
        dest='sevenz_path',
        default=USE_REGISTRY,
        help=('Command or path to 7-Zip\'s "7z" binary. If "_use_registry" is '
              'specified, determine the path from the registry. Default: %(default)s'))
    parser.add_argument(
        '--winrar-path',
        dest='winrar_path',
        default=USE_REGISTRY,
        help=('Command or path to WinRAR\'s "winrar.exe" binary. If "_use_registry" is '
              'specified, determine the path from the registry. Default: %(default)s'))
    parser.add_argument(
        '-j',
        type=int,
        dest='thread_count',
        help=('Number of CPU threads to use for compiling'))
    parser.add_argument(
        '--ci',
        type=int,
    )
    parser.add_argument(
        '--arm',
        action='store_true'
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        '--tarball', dest='tarball', action='store_true',
        help='Download prepared Chromium archives (default for x64)')
    sources.add_argument(
        '--clone', dest='tarball', action='store_false',
        help='Clone Chromium and prepare dependencies with gclient (default for ARM64)')
    parser.set_defaults(tarball=None)
    parser.add_argument(
        '--dev',
        action='store_true'
    )
    args = parser.parse_args()
    if args.tarball is None:
        args.tarball = not args.arm
    if args.tarball and args.arm:
        parser.error('the prepared Windows archive targets x64; use --clone for ARM64')

    # Set common variables
    source_tree = _ROOT_DIR / 'build' / 'src'
    downloads_cache = _ROOT_DIR / 'build' / 'download_cache'
    if os.environ.get('SISO_REAPI_ADDRESS'):
        os.environ['RBE_service_no_security'] = 'true'

    if not args.ci or not (source_tree / 'BUILD.gn').exists():
        # Setup environment
        source_tree.mkdir(parents=True, exist_ok=True)
        downloads_cache.mkdir(parents=True, exist_ok=True)
        _make_tmp_paths()

        # Extractors
        extractors = {
            ExtractorEnum.SEVENZIP: args.sevenz_path,
            ExtractorEnum.WINRAR: args.winrar_path,
        }

        download_configs = [
            _ROOT_DIR / 'downloads.ini',
            _ROOT_DIR / 'helium-chromium' / 'deps.ini',
        ]
        if args.tarball:
            download_configs = [
                _ROOT_DIR / 'helium-chromium' / 'downloads.ini',
                _ROOT_DIR / 'downloads.x64.ini',
            ] + download_configs
        else:
            subprocess.run([
                sys.executable, str(_ROOT_DIR / 'helium-chromium' / 'utils' / 'clone.py'),
                '-o', str(source_tree), '-p', 'win-arm64' if args.arm else 'win64',
            ], check=True)

        get_logger().info('Downloading required files...')
        download_info = downloads.DownloadInfo(download_configs)
        downloads.retrieve_downloads(download_info, downloads_cache, None, True)
        try:
            downloads.check_downloads(download_info, downloads_cache, None)
        except downloads.HashMismatchError as exc:
            get_logger().error('File checksum does not match: %s', exc)
            parser.exit(1)
        get_logger().info('Unpacking downloads...')
        downloads.unpack_downloads(download_info, downloads_cache, None, source_tree, extractors)

        prune_binaries.prune_dirs(source_tree, False, None, keep_build_dependencies=True)
        pruning_list = _ROOT_DIR / 'helium-chromium' / 'pruning.list'
        prune_list = tuple(filter(len, pruning_list.read_text(encoding=ENCODING).splitlines()))
        missing_files = prune_binaries.prune_files(
            source_tree, prune_list, keep_build_dependencies=True)
        if missing_files:
            get_logger().info('Skipped %d pruning entries absent from this source tree',
                              len(missing_files))

        if not args.dev:
            # Apply patches
            # First, ungoogled-chromium-patches
            patches.apply_patches(
                patches.generate_patches_from_series(_ROOT_DIR / 'helium-chromium' / 'patches', resolve=True),
                source_tree,
                patch_bin_path=(source_tree / _PATCH_BIN_RELPATH)
            )
            # Then Windows-specific patches
            patches.apply_patches(
                patches.generate_patches_from_series(_ROOT_DIR / 'patches', resolve=True),
                source_tree,
                patch_bin_path=(source_tree / _PATCH_BIN_RELPATH)
            )

        else:
            print("Apply patches using quilt, then press Enter")
            input()

        # Remote Windows compiles use a separate Linux compiler on workers.
        # Apply its extraction patch before downloading, and substitute domains after.
        if os.environ.get('SISO_REAPI_ADDRESS'):
            subprocess.run([
                sys.executable, str(source_tree / 'tools/clang/scripts/update.py'),
                '--host-os=linux',
                '--output-dir=' + str(source_tree / 'third_party/llvm-build/Release+Asserts_linux'),
            ], check=True)

        if not args.dev:
            # Substitute domains
            domain_substitution_list = _ROOT_DIR / 'helium-chromium' / 'domain_substitution.list'
            domain_substitution.apply_substitution(
                _ROOT_DIR / 'helium-chromium' / 'domain_regex.list',
                domain_substitution_list,
                source_tree,
                None
            )

            # Substitute names
            name_substitution.do_substitution(
                source_tree,
                tarpath=None,
                workers=min(32, os.cpu_count()),
                dry_run=False
            )

            # Append translations
            i18n_apply.apply_translations(source_tree)

        # Set version
        version_parts = helium_version.get_version_parts(_ROOT_DIR / 'helium-chromium', _ROOT_DIR)
        chrome_version_path = source_tree / "chrome" / "VERSION"
        helium_version.check_existing_version(chrome_version_path)
        with open(chrome_version_path, "a") as f:
            for name, version in version_parts.items():
                helium_version.append_version(f, name, version)

        # Copy resources
        # First, generate and copy Windows-specific resources
        generate_resources.generate_resources(
            _ROOT_DIR / 'resources' / 'generate_resources.txt',
            _ROOT_DIR / 'resources'
        )

        replace_resources.copy_resources(
            _ROOT_DIR / 'resources' / 'platform_resources.txt',
            _ROOT_DIR / 'resources',
            source_tree
        )

        # Then common helium-chromium resources
        generate_resources.generate_resources(
            _ROOT_DIR / 'helium-chromium' / 'resources' / 'generate_resources.txt',
            _ROOT_DIR / 'helium-chromium' / 'resources'
        )

        replace_resources.copy_resources(
            _ROOT_DIR / 'helium-chromium' / 'resources' / 'helium_resources.txt',
            _ROOT_DIR / 'helium-chromium' / 'resources',
            source_tree
        )

        _configure_remoteexec(source_tree)

    if not args.ci or not (source_tree / 'out/Default').exists():
        # Output args.gn
        (source_tree / 'out/Default').mkdir(parents=True, exist_ok=True)
        gn_flags = (_ROOT_DIR / 'helium-chromium' / 'flags.gn').read_text(encoding=ENCODING)
        gn_flags += '\n'
        windows_flags = (_ROOT_DIR / 'flags.windows.gn').read_text(encoding=ENCODING)
        if args.arm:
            windows_flags = windows_flags.replace('x64', 'arm64')
        if args.dev:
            windows_flags += '\nchrome_pgo_phase=0\n'

        if os.environ.get('SISO_REAPI_ADDRESS'):
            windows_flags += 'use_remoteexec = true\n'
            # Precompiled modules are not portable across Windows/Linux hosts.
            windows_flags += 'use_clang_modules = false\n'
        elif shutil.which('sccache'):
            windows_flags += 'cc_wrapper = "sccache"\n'

        gn_flags += windows_flags
        if args.dev:
            gn_flags += 'is_component_build=true\n'
        else:
            gn_flags += 'is_official_build=true\n'

        winsparkle_ed_key = os.environ.get('WINSPARKLE_ED_KEY', '')
        authenticode_org = os.environ.get('WINSPARKLE_AUTHENTICODE_ORG', '')
        if winsparkle_ed_key and authenticode_org:
            gn_flags += 'enable_winsparkle=true\n'
            gn_flags += f'winsparkle_ed_key="{winsparkle_ed_key}"\n'
            gn_flags += f'winsparkle_authenticode_org="{authenticode_org}"\n'

        (source_tree / 'out/Default/args.gn').write_text(gn_flags, encoding=ENCODING)

    # Enter source tree to run build commands
    os.chdir(source_tree)

    if not args.ci or not os.path.exists('out\\Default\\build.ninja'):
        # Run gn gen
        _run_build_process(
            'buildtools\\win\\gn.exe', 'gen', 'out\\Default', '--fail-on-unused-args')

    # Ninja commandline
    os.environ.setdefault('SISO_PATH', str(source_tree / 'third_party/siso/cipd/siso.exe'))
    ninja_commandline = [sys.executable, 'third_party\\depot_tools\\autoninja.py']
    if args.thread_count is not None:
        ninja_commandline.append('-j')
        ninja_commandline.append(args.thread_count)
    ninja_commandline.append('-C')
    ninja_commandline.append('out\\Default')

    # Finish all release targets before signing. Siso can replace signed outputs
    # if it is invoked again to build their dependents (the mini installer).
    ninja_commandline.extend(['chrome', 'chromedriver', 'setup', 'mini_installer'])

    # Run ninja
    if args.ci:
        max_time = 5.5 * 60 * 60
        secs_spent = int(time.time()) - args.ci
        timeout = int(max_time - secs_spent)
        print(f"{timeout} seconds left for build")

        _run_build_process_timeout(*ninja_commandline, timeout=timeout)
    else:
        _run_build_process(*ninja_commandline)


if __name__ == '__main__':
    main()
