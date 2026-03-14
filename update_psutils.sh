#!/bin/bash

PLATFORMS=("win_amd64" "manylinux2014_x86_64" "macosx_11_0_arm64" "macosx_10_9_x86_64")

for PLATFORM in "${PLATFORMS[@]}"; do
    DEST="./lib/$PLATFORM"
    mkdir -p "$DEST"
    pip download psutil --only-binary=:all: --platform "$PLATFORM" --dest "$DEST"
    unzip "$DEST"/*.whl "psutil/*" -d "$DEST"
    rm "$DEST"/*.whl
done
