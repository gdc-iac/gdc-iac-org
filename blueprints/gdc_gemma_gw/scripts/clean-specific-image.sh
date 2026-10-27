#!/bin/bash
# Purpose: Clean out a specific image.
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <image_name_or_tag> [options]"
  echo "Example: $0 gemma-proxy"
  echo "Example: $0 gemma-proxy:latest"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/clean_images.py" --specific "$1" "${@:2}"
