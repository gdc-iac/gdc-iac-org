#!/bin/bash
# Purpose: Clean out the repo of all images.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/clean_images.py" --repo-all "$@"
