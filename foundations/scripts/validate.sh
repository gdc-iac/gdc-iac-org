#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# GDC AG Foundations IaC Pipeline Validation Script
# Automates local static checks, schema enforcement, and template rendering checks.
#
# Usage:
#   ./foundations/scripts/validate.sh [ENV] [--env-dir PATH]
#   FOUNDATIONS_ENV_DIR=/path/to/environments ./foundations/scripts/validate.sh [ENV]

set -euo pipefail

CALLER_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FOUNDATIONS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV=""
ENV_DIR_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: --env-dir requires a directory argument." >&2
        exit 1
      fi
      ENV_DIR_ARG="$2"
      shift 2
      ;;
    --env-dir=*)
      ENV_DIR_ARG="${1#*=}"
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [ENV] [--env-dir PATH]"
      echo "  ENV             Target Helmfile environment name (default: dev)"
      echo "  --env-dir PATH  External environments directory (sets FOUNDATIONS_ENV_DIR)"
      exit 0
      ;;
    -*)
      echo "Error: Unknown option '$1'" >&2
      exit 1
      ;;
    *)
      if [[ -z "${ENV}" ]]; then
        ENV="$1"
      else
        echo "Error: Unexpected positional argument '$1'" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

ENV="${ENV:-dev}"

if [[ -n "${ENV_DIR_ARG}" ]]; then
  export FOUNDATIONS_ENV_DIR="${ENV_DIR_ARG}"
fi

# Canonicalize relative FOUNDATIONS_ENV_DIR against the caller's working directory
# before switching into FOUNDATIONS_DIR.
if [[ -n "${FOUNDATIONS_ENV_DIR:-}" ]]; then
  if [[ "${FOUNDATIONS_ENV_DIR}" != /* ]]; then
    FOUNDATIONS_ENV_DIR="${CALLER_PWD}/${FOUNDATIONS_ENV_DIR}"
  fi
  if [[ ! -d "${FOUNDATIONS_ENV_DIR}" ]]; then
    echo "Error: FOUNDATIONS_ENV_DIR directory does not exist: ${FOUNDATIONS_ENV_DIR}" >&2
    exit 1
  fi
  FOUNDATIONS_ENV_DIR="$(cd "${FOUNDATIONS_ENV_DIR}" && pwd)"
  export FOUNDATIONS_ENV_DIR
fi

cd "${FOUNDATIONS_DIR}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0;0m'

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   GDC AG IaC Foundations Validation Harness (${ENV})${NC}"
if [[ -n "${FOUNDATIONS_ENV_DIR:-}" ]]; then
  echo -e "${BLUE}   Config Source: ${FOUNDATIONS_ENV_DIR}${NC}"
else
  echo -e "${BLUE}   Config Source: ${FOUNDATIONS_DIR}/bases/environments (in-tree)${NC}"
fi
echo -e "${BLUE}====================================================${NC}"

# Step 1: Helm Chart Linting
echo -e "\n${YELLOW}[Step 1/3] Linting Local Custom & Blueprint Charts...${NC}"
for chart_dir in "${REPO_ROOT}/charts"/* "${REPO_ROOT}/blueprints/patterns"/*/chart "${REPO_ROOT}/blueprints/gdc_gemma_gw"/*/chart "${REPO_ROOT}/blueprints/gdc_gemma_gw/blueprints"/*; do
  if [ -d "$chart_dir" ] && [ -f "$chart_dir/Chart.yaml" ]; then
    echo -n "Linting ${chart_dir#${REPO_ROOT}/}... "
    if helm lint "$chart_dir" >/dev/null 2>&1; then
      echo -e "${GREEN}PASSED${NC}"
    else
      echo -e "${RED}FAILED${NC}"
      helm lint "$chart_dir"
      exit 1
    fi
  fi
done

# Step 2: Helmfile Linting
echo -e "\n${YELLOW}[Step 2/3] Performing Helmfile Environment Linting...${NC}"
if helmfile -e "${ENV}" lint; then
  echo -e "${GREEN}Helmfile configuration lint successful.${NC}"
else
  echo -e "${RED}Helmfile lint failed.${NC}"
  exit 1
fi


# Step 3: Rendering & Dry-Run Compilation Checks
echo -e "\n${YELLOW}[Step 3/3] Validating Dynamic Go Templates & Schema Rules...${NC}"
if helmfile -e "$ENV" template > /dev/null; then
  echo -e "${GREEN}Template validation succeeded. All schemas and dynamic Go configurations are 100% valid!${NC}"
else
  echo -e "${RED}Template validation failed. Check for syntax errors or JSON Schema violations above.${NC}"
  exit 1
fi

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN} ✅ VALIDATION SUCCESS: Pipeline is release-ready!   ${NC}"
echo -e "${GREEN}====================================================${NC}"
