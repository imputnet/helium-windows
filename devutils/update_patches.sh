#!/bin/bash -eux

PLATFORM_ROOT=$(dirname $(dirname $(readlink -f ${BASH_SOURCE[0]})))
HELIUM_REPO=$PLATFORM_ROOT/helium-chromium

_command=$1

$HELIUM_REPO/devutils/update_platform_patches.py $_command $PLATFORM_ROOT/patches
