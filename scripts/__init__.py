# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.
"""Build steps shared by the Windows build, packaging, and signing scripts."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
HELIUM_REPO = ROOT_DIR / 'helium-chromium'
BUILD_DIR = ROOT_DIR / 'build'
SOURCE_TREE = BUILD_DIR / 'src'
DOWNLOAD_CACHE = BUILD_DIR / 'download_cache'
OUT_DIR = SOURCE_TREE / 'out' / 'Default'

# Let the modules here import helium-chromium's utils directly.
sys.path.insert(0, str(HELIUM_REPO / 'utils'))
