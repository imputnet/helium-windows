#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2025 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Copyright (c) 2018 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
ungoogled-chromium packaging script for Microsoft Windows
"""

import argparse
import platform
from pathlib import Path

from scripts import BUILD_DIR, OUT_DIR
from scripts.installer import create_packages


def main():
    """Entrypoint for local unsigned packaging."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-outputs', type=Path, default=OUT_DIR)
    parser.add_argument('--output-dir', type=Path, default=BUILD_DIR)
    parser.add_argument(
        '--cpu-arch', metavar='ARCH', default=platform.architecture()[0],
        choices=('64bit', '32bit'),
        help='Target CPU filter in FILES.cfg. Default: %(default)s')

    args = parser.parse_args()

    create_packages(args.build_outputs, args.output_dir, args.cpu_arch)


if __name__ == '__main__':
    main()
