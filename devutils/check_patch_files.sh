#!/bin/bash -eux

PLATFORM_ROOT=$(dirname $(dirname $(readlink -f ${BASH_SOURCE[0]})))
HELIUM_REPO=$PLATFORM_ROOT/helium-chromium

$HELIUM_REPO/devutils/check_patch_files.py -p $PLATFORM_ROOT/patches
