# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Siso remote execution, enabled by setting SISO_REAPI_ADDRESS."""

import os
import subprocess
import sys

from . import SOURCE_TREE


def enabled():
    return bool(os.environ.get('SISO_REAPI_ADDRESS'))


def set_environment():
    """Set what Siso needs at build time, including in resumed CI stages."""
    if enabled():
        os.environ['RBE_service_no_security'] = 'true'


def fetch_linux_clang():
    """Download the Linux compiler that remote workers run for Windows compiles."""
    subprocess.run([
        sys.executable, str(SOURCE_TREE / 'tools/clang/scripts/update.py'),
        '--host-os=linux',
        '--output-dir=' + str(SOURCE_TREE / 'third_party/llvm-build/Release+Asserts_linux'),
    ], check=True)


def configure():
    address = os.environ.get('SISO_REAPI_ADDRESS', '')
    instance = os.environ.get('SISO_REAPI_INSTANCE') or 'main'
    backend = ''

    if address:
        os.environ['SISO_REAPI_INSTANCE'] = instance
        backend = 'nativelink.star'

    subprocess.run([
        sys.executable, str(SOURCE_TREE / 'build/config/siso/configure_siso.py'),
        '--rbe_instance=projects/rbe-chrome-untrusted/instances/default_instance',
        f'--reapi_address={address}',
        f'--reapi_instance={instance if address else ""}',
        f'--reapi_backend_config_path={backend}',
    ], check=True)
