#!/usr/bin/env python3
# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Helium development commands for Windows. Load dev.ps1 and run them as `he`."""

import inspect
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from scripts import (BUILD_DIR, DOWNLOAD_CACHE, HELIUM_REPO, OUT_DIR, ROOT_DIR, SOURCE_TREE,
                     gn, remoteexec, source, worktree)
from scripts.toolchain import make_tmp_paths
import i18n_apply
from _common import USE_REGISTRY, ExtractorEnum

PATCHES_DIR = ROOT_DIR / 'patches'
SUBS_CACHE = BUILD_DIR / 'subs.tar.gz'
NAMESUBS_CACHE = BUILD_DIR / 'namesubs.tar'
ARM = platform.machine().lower() in ('arm64', 'aarch64')


class Abort(Exception):
    pass


def gnu_tools():
    """
    Find GNU diff and patch, which q runs: preferably the copies in Chromium's
    bundled Git, which build.py also patches with, or else Git for Windows'.
    """
    exec_path = subprocess.run(['git', '--exec-path'], check=True, text=True,
                               stdout=subprocess.PIPE).stdout.strip()

    for tools in (SOURCE_TREE / 'third_party/git/usr/bin',
                  Path(exec_path).parents[2] / 'usr' / 'bin'):
        if (tools / 'diff.exe').is_file() and (tools / 'patch.exe').is_file():
            return tools

    return None


def environment():
    """Variables for q, shared with the other platforms through set_quilt_vars.sh."""
    shared = (HELIUM_REPO / 'devutils/set_quilt_vars.sh').read_text(encoding='utf-8')
    env = dict(re.findall(r'^export (\w+)="?(.*?)"?$', shared, re.M))
    env['QUILT_PATCHES'] = str(PATCHES_DIR)
    env['QUILT_SERIES'] = 'series.merged'

    # Append rather than prepend, so that these don't shadow Windows tools
    # of the same name, such as find.exe.
    env['PATH'] = os.environ['PATH']
    tools = gnu_tools()
    if tools and str(tools) not in env['PATH'].split(os.pathsep):
        env['PATH'] += os.pathsep + str(tools)

    return env


def check_requirements():
    for repo in (ROOT_DIR, HELIUM_REPO):
        autocrlf = subprocess.run(['git', '-C', str(repo), 'config', 'core.autocrlf'],
                                  text=True, stdout=subprocess.PIPE).stdout.strip()
        if autocrlf not in ('', 'false'):
            raise Abort(f'{repo} has core.autocrlf={autocrlf}, which rewrites line endings in '
                        'patches and sources\nset it to false and check the repository out again')

    if not quilt_program():
        raise Abort('neither q nor quilt is on PATH; q is at '
                    'https://github.com/imputnet/q/releases/latest')


def quilt_program():
    """q, or else quilt: they take the same commands and share the .pc state."""
    return shutil.which('q') or shutil.which('quilt')


def q(*args, check=True):
    # Setup fetches the bundled tools only just before it first runs q.
    os.environ.update(environment())

    if not (shutil.which('diff') and shutil.which('patch')):
        raise Abort("q and quilt need GNU diff and patch, but they aren't on PATH, in the "
                    'source tree, or in Git for Windows')

    return subprocess.run([quilt_program(), '--quiltrc', '-', *args], cwd=SOURCE_TREE,
                          check=check)


def python(script, *args, check=True):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=check)


def patches_op(command, check=True):
    python(HELIUM_REPO / 'devutils/update_platform_patches.py', command, PATCHES_DIR,
           check=check)


def setup(*args):
    """[-c] - sets up the dev environment, optionally cloning chromium"""
    if args not in ((), ('-c',)):
        raise Abort('usage: he setup [-c]')

    if OUT_DIR.parent.exists():
        raise Abort(f'{OUT_DIR.parent} already exists')

    if SOURCE_TREE.exists():
        shutil.rmtree(SOURCE_TREE)

    SOURCE_TREE.mkdir(parents=True)
    DOWNLOAD_CACHE.mkdir(parents=True, exist_ok=True)
    make_tmp_paths()

    source.fetch(args != ('-c',) and not ARM, ARM, {
        ExtractorEnum.SEVENZIP: USE_REGISTRY,
        ExtractorEnum.WINRAR: USE_REGISTRY,
    })
    source.prune()
    source.copy_resources()
    gn.write_args(ARM, dev=True)

    patches_op('merge')
    source.set_version()
    q('push', '-a')

    # The Linux compiler's extraction patch has to be applied before this.
    if remoteexec.enabled():
        remoteexec.fetch_linux_clang()
    remoteexec.configure()
    gn.gen()


def configure():
    """- regenerates build files in out/Default"""
    gn.gen()


def build(*args):
    """[args] - prepares a development build binary"""
    remoteexec.set_environment()
    gn.autoninja(['-k', '0', 'chrome', *args])


def run(*args):
    """[args] - runs a development build of helium with dev data dir & ui devtools enabled"""
    profile = Path(os.environ['LOCALAPPDATA']) / 'net.imput.helium.dev'

    # .git is a file in linked worktrees, and a directory in the main checkout.
    # Name a worktree's profile by its whole path under the .wt folder, since
    # worktrees like feature/foo and bug/foo share their last component.
    if (ROOT_DIR / '.git').is_file():
        worktrees = worktree.path('')
        name = (ROOT_DIR.relative_to(worktrees) if ROOT_DIR.is_relative_to(worktrees)
                else Path(*ROOT_DIR.parts[1:]))
        profile = profile.with_name(profile.name + '.wt') / name

    subprocess.run([str(OUT_DIR / 'chrome.exe'), f'--user-data-dir={profile}',
                    '--enable-ui-devtools', *args], check=True)


def sub():
    """- apply google domain and name substitutions"""
    if SUBS_CACHE.exists():
        raise Abort(f'{SUBS_CACHE} exists, are you sure you want to do this?\n'
                    f'if yes, then delete the {SUBS_CACHE} file')

    namesub()
    python(HELIUM_REPO / 'utils/domain_substitution.py', 'apply',
           '-r', HELIUM_REPO / 'domain_regex.list',
           '-f', HELIUM_REPO / 'domain_substitution.list',
           '-c', SUBS_CACHE, SOURCE_TREE)


def unsub():
    """- undo google domain and name substitutions"""
    python(HELIUM_REPO / 'utils/domain_substitution.py', 'revert', '-c', SUBS_CACHE,
           SOURCE_TREE)

    nameunsub()


def namesub():
    """- apply only name substitutions"""
    if NAMESUBS_CACHE.exists():
        raise Abort(f'{NAMESUBS_CACHE} exists, are you sure you want to do this?\n'
                    f'if yes, then delete the {NAMESUBS_CACHE} file')

    python(HELIUM_REPO / 'utils/name_substitution.py', '--sub', '-t', SOURCE_TREE,
           '--backup-path', NAMESUBS_CACHE)


def nameunsub():
    """- undo name substitutions"""
    python(HELIUM_REPO / 'utils/name_substitution.py', '--unsub', '-t', SOURCE_TREE,
           '--backup-path', NAMESUBS_CACHE)


def merge():
    """- merges all patches"""
    patches_op('merge')


def unmerge():
    """- unmerges all patches"""
    patches_op('unmerge')


def push():
    """- applies all patches"""
    q('push', '-a', '--refresh')


def pop():
    """- undoes all patches"""
    q('pop', '-a')


def pull():
    """- undoes all patches, pulls, redoes all patches"""
    if SUBS_CACHE.exists():
        raise Abort("source files are substituted, please run 'he unsub' first")

    # quilt exits with 2 when nothing is applied. Anything else means that a
    # patch couldn't be removed, such as one with unrefreshed changes, and
    # updating the patches underneath it would leave .pc inconsistent.
    if q('pop', '-a', check=False).returncode not in (0, 2):
        raise Abort("couldn't remove the applied patches; refresh or revert the changes "
                    "reported above, then run 'he pull' again")

    patches_op('unmerge', check=False)

    # Stop at the first failure, such as a conflicting rebase, rather than
    # updating the other checkout or applying patches to an unfinished one.
    for repo in (ROOT_DIR, HELIUM_REPO):
        for command in (['fetch'], ['rebase', '--autostash', 'origin/main']):
            if subprocess.run(['git', '-C', str(repo), *command]).returncode != 0:
                raise Abort(f'git {command[0]} failed in {repo}\n'
                            "once it's resolved, run 'he pull' again, or 'he merge' and "
                            "'he push' to continue")

    patches_op('merge')
    q('push', '-a', '--refresh')


def resources():
    """- copies helium resources (such as icons)"""
    source.copy_resources()


def translate():
    """- apply translations from i18n folder"""
    i18n_apply.apply_translations(SOURCE_TREE)


def reset():
    """- nukes everything"""
    patches_op('unmerge', check=False)
    SUBS_CACHE.unlink(missing_ok=True)
    NAMESUBS_CACHE.unlink(missing_ok=True)

    if SOURCE_TREE.exists():
        doomed = SOURCE_TREE.with_name(f'src.deleting-{os.getpid()}')
        SOURCE_TREE.rename(doomed)
        subprocess.Popen(['cmd', '/c', 'rd', '/s', '/q', str(doomed)],
                         creationflags=subprocess.DETACHED_PROCESS)


def wt(*args):
    """new [--copy] <name> | rm [-f] <name> | ls - manages worktrees with block-cloned source trees"""
    match args:
        case ('ls',):
            worktree.list_all()
        case ('new', name) if not name.startswith('-'):
            worktree.new(name)
        case ('new', '--copy', name):
            worktree.new(name, copy=True)
        case ('rm', name) if not name.startswith('-'):
            worktree.remove(name)
        case ('rm', '-f', name):
            worktree.remove(name, force=True)
        case _:
            raise Abort(f'usage: he wt {wt.__doc__}')


def env():
    """- prints the environment for q, used by dev.ps1"""
    for name, value in environment().items():
        print(f'{name}={value}')


COMMANDS = {function.__name__: function for function in (
    setup, configure, build, run, sub, unsub, namesub, nameunsub, merge, unmerge, push, pop,
    pull, resources, translate, reset, wt, env)}


def usage():
    lines = [f'usage: he ({" | ".join(COMMANDS)})']
    lines += [f'\t{name} {function.__doc__}' for name, function in COMMANDS.items()]
    return '\n'.join(lines)


def main(argv):
    command = COMMANDS.get(argv[0]) if argv else None
    if command is None:
        print(usage(), file=sys.stderr)
        return 1

    takes_args = any(parameter.kind is parameter.VAR_POSITIONAL
                     for parameter in inspect.signature(command).parameters.values())
    if argv[1:] and not takes_args:
        print(f'usage: he {argv[0]}', file=sys.stderr)
        return 1

    try:
        check_requirements()
        os.environ.update(environment())
        command(*argv[1:])
    except (Abort, worktree.WorktreeError) as error:
        print(error, file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f'he {argv[0]}: {error}', file=sys.stderr)
        return error.returncode or 1

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
