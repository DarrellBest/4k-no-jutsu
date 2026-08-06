#!/usr/bin/env bash
# One-time environment setup: conda env, the jutsu package itself, and the
# vendored AI upscale backends. Safe to re-run (every step is idempotent).
#
# Usage:
#   ./scripts/setup.sh
#
# After this completes, use `jutsu run` / `jutsu compare` to actually
# process a video -- running is a separate step from setup, see README.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="4k-no-jutsu"

if ! conda env list | grep -q "^${ENV_NAME} "; then
  echo "Creating conda env '${ENV_NAME}'..."
  conda create -n "$ENV_NAME" python=3.12 -y
else
  echo "conda env '${ENV_NAME}' already exists, skipping creation."
fi

echo "Installing jutsu (editable) + dev dependencies..."
conda run -n "$ENV_NAME" pip install -e "${ROOT}[dev]"

echo "Installing AI upscale backends (realesrgan / realcugan)..."
"${ROOT}/scripts/install_backends.sh"

echo
echo "Setup complete. Next: conda activate ${ENV_NAME}, then 'jutsu run <config.yaml> <workdir>'."
