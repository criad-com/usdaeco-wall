#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLCHAIN_DIR="${TOOLCHAIN_DIR:-$HERE/../usdaeco-toolchain}"
CORE_DIR="${AECO_CORE_ROOT:-${CORE_DIR:-$HERE/../usdaeco-core}}"
BUILDUP_DIR="${AECO_BUILDUP_ROOT:-$HERE/../usdaeco-buildup}"
AXIS_DIR="${AECO_AXIS_ROOT:-$HERE/../usdaeco-axis}"
BUILDUP_PLUGIN="${BUILDUP_PLUGIN_DIR:-$BUILDUP_DIR/out/plugins/usdAecoBuildUp/resources}"
if [[ ! -f "$BUILDUP_PLUGIN/plugInfo.json" ]]; then
    BUILDUP_PLUGIN="$BUILDUP_DIR/plugins/usdAecoBuildUp/resources"
fi
bash "$TOOLCHAIN_DIR/build.sh" usdAecoWall "$HERE" \
    --dep "${CORE_PLUGIN_DIR:-$CORE_DIR/out/plugins/usdAeco/resources}" \
    --dep "${AXIS_PLUGIN_DIR:-$AXIS_DIR/out/plugins/usdAecoAxis/resources}" \
    --dep "$BUILDUP_PLUGIN" "$@"
while (( $# )); do
    if [[ "$1" == "--install-root" ]]; then
        mkdir -p "$2/python"
        cp -RL "$HERE/tools/usdaeco_wall" "$2/python/"
        break
    fi
    shift
done
