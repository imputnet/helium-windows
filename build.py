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

import argparse
import time

from scripts import DOWNLOAD_CACHE, OUT_DIR, SOURCE_TREE, gn, remoteexec, source
from scripts.toolchain import make_tmp_paths
from _common import USE_REGISTRY, ExtractorEnum

# CI jobs are stopped after 6 hours. Leave time to save the build tree.
_CI_STAGE_SECONDS = 5.5 * 60 * 60


def parse_args():
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

    return args


def prepare_source(args):
    SOURCE_TREE.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_CACHE.mkdir(parents=True, exist_ok=True)
    make_tmp_paths()

    source.fetch(args.tarball, args.arm, {
        ExtractorEnum.SEVENZIP: args.sevenz_path,
        ExtractorEnum.WINRAR: args.winrar_path,
    })
    source.prune()

    if args.dev:
        print("Apply patches using quilt, then press Enter")
        input()
    else:
        source.apply_patches()

    # Remote Windows compiles use a separate Linux compiler on workers.
    # Apply its extraction patch before downloading, and substitute domains after.
    if remoteexec.enabled():
        remoteexec.fetch_linux_clang()

    if not args.dev:
        source.substitute()

    source.set_version()
    source.copy_resources()
    remoteexec.configure()


def main():
    """CLI Entrypoint"""
    args = parse_args()
    remoteexec.set_environment()

    # In CI, later stages resume from the previous stage's build tree.
    if not args.ci or not (SOURCE_TREE / 'BUILD.gn').exists():
        prepare_source(args)

    if not args.ci or not OUT_DIR.exists():
        gn.write_args(args.arm, args.dev)

    if not args.ci or not (OUT_DIR / 'build.ninja').exists():
        gn.gen()

    timeout = None
    if args.ci:
        timeout = int(_CI_STAGE_SECONDS - (int(time.time()) - args.ci))
        print(f"{timeout} seconds left for build")

    gn.autoninja(gn.RELEASE_TARGETS, args.thread_count, timeout)


if __name__ == '__main__':
    main()
