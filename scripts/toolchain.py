# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Copyright (c) 2019 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Running build tools inside the Visual Studio environment."""

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

from _common import ENCODING


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


def _interrupt(proc):
    print('Sending keyboard interrupt')
    for _ in range(3):
        ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, proc.pid)
        time.sleep(1)

    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_build_process(*args, cwd=None, timeout=None):
    """
    Runs the command with the Visual Studio environment variables set.

    With a timeout, the build is interrupted when it expires and the script exits
    with status 42, which CI takes to mean that another stage should continue it.
    """
    cmd_input = [
        'call "%s" >nul' % _get_vcvars_path(),
        'set DEPOT_TOOLS_WIN_TOOLCHAIN=0',
        ' '.join(map('"{}"'.format, args)),
        'exit\n',
    ]

    # A separate process group lets the timeout interrupt the build without
    # interrupting this script, but it also ignores Ctrl+C, so only use it in CI.
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if timeout is not None else 0
    with subprocess.Popen(('cmd.exe', '/k'), cwd=cwd, encoding=ENCODING,
                          stdin=subprocess.PIPE, creationflags=flags) as proc:
        proc.stdin.write('\n'.join(cmd_input))
        proc.stdin.close()
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            _interrupt(proc)
            sys.exit(42)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args)


def make_tmp_paths():
    """Creates TMP and TEMP variable dirs so ninja won't fail"""
    for name in ('TMP', 'TEMP'):
        Path(os.environ[name]).mkdir(exist_ok=True)
