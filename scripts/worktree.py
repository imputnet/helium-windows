# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Git worktrees that share the set-up source tree through block cloning."""

import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import BUILD_DIR, DOWNLOAD_CACHE, HELIUM_REPO, ROOT_DIR, SOURCE_TREE


class WorktreeError(Exception):
    pass


def _git(*args, **kwargs):
    return subprocess.run(['git', *map(str, args)], check=True, **kwargs)


def _git_output(*args):
    return _git(*args, stdout=subprocess.PIPE, text=True).stdout.strip()


def path(name):
    common = Path(_git_output('-C', ROOT_DIR, 'rev-parse', '--path-format=absolute',
                              '--git-common-dir'))
    return common.parent.with_name(common.parent.name + '.wt') / name


def _filesystem(directory):
    name = ctypes.create_unicode_buffer(32)
    root = os.path.splitdrive(directory.resolve())[0] + '\\'

    if not ctypes.windll.kernel32.GetVolumeInformationW(
            root, None, 0, None, None, None, name, len(name)):
        raise ctypes.WinError()

    return name.value


def _can_block_clone(dest_parent):
    """ReFS, as used by Dev Drives, clones files within a volume instead of copying them."""
    same_volume = os.path.splitdrive(dest_parent.resolve())[0].lower() == \
        os.path.splitdrive(SOURCE_TREE.resolve())[0].lower()

    return same_volume and _filesystem(dest_parent) == 'ReFS'


def _robocopy(src, dst):
    # Windows clones blocks for copies within a ReFS volume, so this is quick there.
    result = subprocess.run([
        'robocopy', str(src), str(dst), '/E', '/MT:32', '/COPY:DAT', '/DCOPY:DAT', '/SL',
        '/R:0', '/W:0', '/NFL', '/NDL', '/NP', '/NJH', '/NJS'])

    # robocopy uses exit codes below 8 for success.
    if result.returncode >= 8:
        raise subprocess.CalledProcessError(result.returncode, result.args)


def _remove_tree(directory):
    # rd is much faster than shutil.rmtree on a Chromium tree.
    subprocess.run(['cmd', '/c', 'rd', '/s', '/q', str(directory)], check=True)


def _copy_uncommitted(repo, dest, *excludes):
    diff = _git('-C', repo, 'diff', '--binary', 'HEAD', '--', '.',
                *(f':!{exclude}' for exclude in excludes), stdout=subprocess.PIPE).stdout
    _git('-C', dest, 'apply', '--allow-empty', input=diff)


def new(name, copy=False):
    dest = path(name)

    if not (ROOT_DIR / 'patches/series.merged').is_file() or not (SOURCE_TREE / '.pc').is_dir():
        raise WorktreeError(f'{SOURCE_TREE} must be set up with merged patches applied')

    for repo in (ROOT_DIR, HELIUM_REPO):
        exists = subprocess.run(['git', '-C', str(repo), 'rev-parse', '-q', '--verify',
                                 f'refs/heads/{name}'], stdout=subprocess.DEVNULL)
        if exists.returncode == 0:
            raise WorktreeError(f'branch {name} already exists')

    dest.parent.mkdir(parents=True, exist_ok=True)
    if not copy and not _can_block_clone(dest.parent):
        raise WorktreeError(
            f"{dest.parent} isn't on the ReFS volume holding {SOURCE_TREE}, "
            f'so the source tree would be copied in full\n'
            f"use 'he wt new --copy {name}' to do that anyway")

    _git('-C', ROOT_DIR, 'worktree', 'add', '-b', name, dest, 'HEAD')
    _git('-C', HELIUM_REPO, 'worktree', 'add', '-b', name, dest / 'helium-chromium', 'HEAD')
    _copy_uncommitted(ROOT_DIR, dest, 'patches', 'helium-chromium')
    _copy_uncommitted(HELIUM_REPO, dest / 'helium-chromium', 'patches')

    shutil.rmtree(dest / 'patches')
    _robocopy(ROOT_DIR / 'patches', dest / 'patches')

    (dest / 'build').mkdir()
    DOWNLOAD_CACHE.mkdir(exist_ok=True)

    # A junction, unlike a symbolic link, needs neither Developer Mode nor elevation.
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(dest / 'build/download_cache'),
                    str(DOWNLOAD_CACHE.resolve())], check=True, stdout=subprocess.DEVNULL)

    _robocopy(SOURCE_TREE, dest / 'build/src')

    for cache in ('subs.tar.gz', 'namesubs.tar'):
        if (BUILD_DIR / cache).is_file():
            shutil.copy2(BUILD_DIR / cache, dest / 'build' / cache)

    (dest / 'build/src/.pc/.quilt_patches').write_text(f'{dest / "patches"}\n')

    subprocess.run([sys.executable, str(dest / 'dev.py'), 'configure'], check=True)
    print(f'created {dest}')


def remove(name, force=False):
    dest = path(name)

    if not (dest / '.git').is_file():
        raise WorktreeError(f'{dest} is not a worktree')

    if not force:
        # Shared patch edits are untracked while the patches are merged.

        if (dest / 'patches/series.merged').exists():
            raise WorktreeError(f"patches in {dest} are merged; run 'he unmerge' there first")

        for repo in (dest, dest / 'helium-chromium'):
            if repo.exists() and _git_output('-C', repo, 'status', '--porcelain'):
                raise WorktreeError(f'{repo} has uncommitted changes')

    build = dest / 'build'
    if (build / 'download_cache').exists():
        # Remove the junction itself so that nothing deletes the shared cache.
        os.rmdir(build / 'download_cache')

    if build.exists():
        _remove_tree(build)

    if (dest / 'helium-chromium/.git').is_file():
        _git('-C', HELIUM_REPO, 'worktree', 'remove', '--force', dest / 'helium-chromium')

    _git('-C', ROOT_DIR, 'worktree', 'remove', '--force', dest)


def list_all():
    _git('-C', ROOT_DIR, 'worktree', 'list')
