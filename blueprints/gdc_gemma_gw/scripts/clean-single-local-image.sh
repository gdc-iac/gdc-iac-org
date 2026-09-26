#!/bin/bash
# Purpose: Clean out a single specified local docker image.
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <image_id_or_name> [options]"
  echo "Example: $0 d166872034ad"
  echo "Example: $0 gemma-proxy:latest"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/clean_images.py" --image "$1" "${@:2}"
