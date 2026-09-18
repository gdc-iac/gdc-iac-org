#!/bin/bash
# Purpose: Clean out all local docker images relevant to this project.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/clean_images.py" --all "$@"
