#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT/vendor"
mkdir -p "$VENDOR_DIR"

if [ ! -x "$VENDOR_DIR/realesrgan/realesrgan-ncnn-vulkan" ]; then
  echo "Installing realesrgan-ncnn-vulkan..."
  TMP=$(mktemp -d)
  curl -L -o "$TMP/realesrgan.zip" \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip
  mkdir -p "$VENDOR_DIR/realesrgan"
  unzip -o -q "$TMP/realesrgan.zip" -d "$VENDOR_DIR/realesrgan"
  chmod +x "$VENDOR_DIR/realesrgan/realesrgan-ncnn-vulkan"
  rm -rf "$TMP"
fi

if [ ! -x "$VENDOR_DIR/realcugan/realcugan-ncnn-vulkan" ]; then
  echo "Installing realcugan-ncnn-vulkan..."
  TMP=$(mktemp -d)
  curl -L -o "$TMP/realcugan.zip" \
    https://github.com/nihui/realcugan-ncnn-vulkan/releases/download/20220728/realcugan-ncnn-vulkan-20220728-ubuntu.zip
  unzip -o -q "$TMP/realcugan.zip" -d "$TMP/extracted"
  mkdir -p "$VENDOR_DIR/realcugan"
  mv "$TMP"/extracted/realcugan-ncnn-vulkan-20220728-ubuntu/* "$VENDOR_DIR/realcugan/"
  chmod +x "$VENDOR_DIR/realcugan/realcugan-ncnn-vulkan"
  rm -rf "$TMP"
fi

echo "Backends installed in $VENDOR_DIR"
