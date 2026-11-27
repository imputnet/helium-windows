# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Copyright (c) 2019 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Configuring and compiling the prepared source tree."""

import os
import shutil
import sys

from _common import ENCODING

from . import HELIUM_REPO, OUT_DIR, ROOT_DIR, SOURCE_TREE, remoteexec
from .toolchain import run_build_process

# Finish all release targets before signing. Siso can replace signed outputs
# if it is invoked again to build their dependents (the mini installer).
RELEASE_TARGETS = ('chrome', 'chromedriver', 'setup', 'mini_installer')


def args(arm, dev):
    """Return the contents of args.gn for this build."""
    gn_flags = (HELIUM_REPO / 'flags.gn').read_text(encoding=ENCODING)
    gn_flags += '\n'

    windows_flags = (ROOT_DIR / 'flags.windows.gn').read_text(encoding=ENCODING)
    if arm:
        windows_flags = windows_flags.replace('x64', 'arm64')

    if remoteexec.enabled():
        windows_flags += 'use_remoteexec = true\n'
        # Precompiled modules are not portable across Windows/Linux hosts.
        windows_flags += 'use_clang_modules = false\n'
    elif shutil.which('sccache'):
        windows_flags += 'cc_wrapper = "sccache"\n'

    gn_flags += windows_flags
    if dev:
        gn_flags += 'is_component_build=true\n'
    else:
        gn_flags += 'is_official_build=true\n'

    winsparkle_ed_key = os.environ.get('WINSPARKLE_ED_KEY', '')
    authenticode_org = os.environ.get('WINSPARKLE_AUTHENTICODE_ORG', '')
    if winsparkle_ed_key and authenticode_org:
        gn_flags += 'enable_winsparkle=true\n'
        gn_flags += f'winsparkle_ed_key="{winsparkle_ed_key}"\n'
        gn_flags += f'winsparkle_authenticode_org="{authenticode_org}"\n'

    return gn_flags


def write_args(arm, dev):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'args.gn').write_text(args(arm, dev), encoding=ENCODING)


def gen(*extra_args):
    run_build_process('buildtools\\win\\gn.exe', 'gen', 'out\\Default', '--fail-on-unused-args',
                      *extra_args, cwd=SOURCE_TREE)


def autoninja(targets, jobs=None, timeout=None):
    os.environ.setdefault('SISO_PATH', str(SOURCE_TREE / 'third_party/siso/cipd/siso.exe'))

    command = [sys.executable, 'third_party\\depot_tools\\autoninja.py']
    if jobs is not None:
        command += ['-j', jobs]
    command += ['-C', 'out\\Default', *targets]

    run_build_process(*command, cwd=SOURCE_TREE, timeout=timeout)
