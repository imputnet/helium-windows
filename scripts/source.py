# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Copyright (c) 2019 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Preparing the Chromium source tree for a Helium build."""

import os
import subprocess
import sys

import domain_substitution
import downloads
import generate_resources
import helium_version
import i18n_apply
import name_substitution
import patches
import prune_binaries
import replace_resources
from _common import ENCODING, get_logger

from . import DOWNLOAD_CACHE, HELIUM_REPO, ROOT_DIR, SOURCE_TREE

_PATCH_BIN = SOURCE_TREE / 'third_party/git/usr/bin/patch.exe'


def fetch(tarball, arm, extractors):
    """Download or clone Chromium and its dependencies into the source tree."""
    download_configs = [
        ROOT_DIR / 'downloads.ini',
        HELIUM_REPO / 'deps.ini',
    ]

    if tarball:
        download_configs = [
            HELIUM_REPO / 'downloads.ini',
            ROOT_DIR / 'downloads.x64.ini',
        ] + download_configs
    else:
        subprocess.run([
            sys.executable, str(HELIUM_REPO / 'utils' / 'clone.py'),
            '-o', str(SOURCE_TREE), '-p', 'win-arm64' if arm else 'win64',
        ], check=True)

    get_logger().info('Downloading required files...')
    download_info = downloads.DownloadInfo(download_configs)
    downloads.retrieve_downloads(download_info, DOWNLOAD_CACHE, None, True)

    try:
        downloads.check_downloads(download_info, DOWNLOAD_CACHE, None)
    except downloads.HashMismatchError as exc:
        get_logger().error('File checksum does not match: %s', exc)
        sys.exit(1)

    get_logger().info('Unpacking downloads...')
    downloads.unpack_downloads(download_info, DOWNLOAD_CACHE, None, SOURCE_TREE, extractors)


def prune():
    """Remove prebuilt binaries that the build does not need."""
    prune_binaries.prune_dirs(SOURCE_TREE, False, None, keep_build_dependencies=True)

    pruning_list = HELIUM_REPO / 'pruning.list'
    prune_list = tuple(filter(len, pruning_list.read_text(encoding=ENCODING).splitlines()))
    missing_files = prune_binaries.prune_files(
        SOURCE_TREE, prune_list, keep_build_dependencies=True)

    if missing_files:
        get_logger().info('Skipped %d pruning entries absent from this source tree',
                          len(missing_files))


def apply_patches():
    """Apply the shared helium-chromium patches, then the Windows ones."""
    for patches_dir in (HELIUM_REPO / 'patches', ROOT_DIR / 'patches'):
        patches.apply_patches(
            patches.generate_patches_from_series(patches_dir, resolve=True),
            SOURCE_TREE,
            patch_bin_path=_PATCH_BIN)


def substitute():
    """Substitute Google domains and Chromium names, then add translations."""
    domain_substitution.apply_substitution(
        HELIUM_REPO / 'domain_regex.list',
        HELIUM_REPO / 'domain_substitution.list',
        SOURCE_TREE,
        None)

    name_substitution.do_substitution(
        SOURCE_TREE,
        tarpath=None,
        workers=min(32, os.cpu_count()),
        dry_run=False)

    i18n_apply.apply_translations(SOURCE_TREE)


def set_version():
    """Append Helium's version components to chrome/VERSION."""
    version_parts = helium_version.get_version_parts(HELIUM_REPO, ROOT_DIR)
    chrome_version_path = SOURCE_TREE / 'chrome' / 'VERSION'
    helium_version.check_existing_version(chrome_version_path)

    with open(chrome_version_path, 'a') as version_file:
        for name, version in version_parts.items():
            helium_version.append_version(version_file, name, version)


def copy_resources():
    """Generate and copy the Windows resources, then the shared ones."""
    for resources, listing in ((ROOT_DIR / 'resources', 'platform_resources.txt'),
                               (HELIUM_REPO / 'resources', 'helium_resources.txt')):
        generate_resources.generate_resources(resources / 'generate_resources.txt', resources)
        replace_resources.copy_resources(resources / listing, resources, SOURCE_TREE)
