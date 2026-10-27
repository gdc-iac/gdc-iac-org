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

# ==============================================================================
# GDC Air-Gap Release Bundle Ingestion & Harbor Sync Utility
#
# Turnkey utility for air-gapped platform administrators to verify cryptographic
# bundle integrity and seed packaged Helm charts and container images into a
# localized on-prem registry (e.g. Harbor, Quay, or Artifactory).
# ==============================================================================

set -euo pipefail

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Default values
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_BUNDLE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REGISTRY=""
PROJECT="charts"
USERNAME="${HARBOR_USER:-${REGISTRY_USER:-}}"
PASSWORD="${HARBOR_PASSWORD:-${REGISTRY_PASSWORD:-}}"
BUNDLE_DIR="${DEFAULT_BUNDLE_DIR}"
SKIP_CHECKSUM=false
INSECURE=false
DRY_RUN=false

usage() {
  echo -e "${BOLD}Usage:${NC} $(basename "$0") [OPTIONS]

${BOLD}Description:${NC}
  Verifies the cryptographic integrity of a GDC air-gap release bundle
  and pushes all packaged OCI Helm charts to a local air-gapped registry.

${BOLD}Options:${NC}
  -r, --registry <host>       Target registry hostname and optional port
                              (e.g., harbor.infra.gdc.example.com) [REQUIRED]
  -p, --project <project>     Target project / namespace in registry (default: \"charts\")
  -u, --user <username>       Registry username (default: \$HARBOR_USER or prompt)
  -P, --password <password>   Registry password (default: \$HARBOR_PASSWORD or prompt)
  -d, --bundle-dir <dir>      Path to extracted bundle directory (default: parent of script)
      --skip-checksum         Skip SHA256 checksum verification
      --insecure              Allow HTTP or self-signed/internal TLS certificates
      --dry-run               Simulate actions without pushing to the registry
  -h, --help                  Show this help message and exit

${BOLD}Examples:${NC}
  # Interactive ingestion into local Harbor registry:
  $(basename "$0") --registry harbor.infra.gdc.example.com --project gdc-iac

  # Automated ingestion via service robot credentials:
  $(basename "$0") \\
    --registry harbor.infra.gdc.example.com \\
    --project gdc-iac \\
    --user \"robot\$gdc-ci\" \\
    --password \"\$ROBOT_TOKEN\" \\
    --insecure
"
  exit 0
}

# Parse Command-Line Arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -r|--registry)
      REGISTRY="$2"
      shift 2
      ;;
    -p|--project)
      PROJECT="$2"
      shift 2
      ;;
    -u|--user)
      USERNAME="$2"
      shift 2
      ;;
    -P|--password)
      PASSWORD="$2"
      shift 2
      ;;
    -d|--bundle-dir)
      BUNDLE_DIR="$2"
      shift 2
      ;;
    --skip-checksum)
      SKIP_CHECKSUM=true
      shift
      ;;
    --insecure)
      INSECURE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo -e "${RED}Error: Unknown argument: $1${NC}" >&2
      echo "Use --help for usage instructions." >&2
      exit 1
      ;;
  esac
done

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BOLD}${CYAN}   GDC Air-Gap Release Bundle Ingestion Utility${NC}"
echo -e "${BLUE}====================================================================${NC}"

# Validation of Prerequisites
if ! command -v helm &>/dev/null; then
  echo -e "${RED}Error: 'helm' CLI is not found in PATH.${NC}" >&2
  echo "Please install Helm (v3.12+) on this administrative workstation." >&2
  exit 1
fi

if [[ -z "${REGISTRY}" ]]; then
  echo -n -e "${YELLOW}Enter Target Registry Host (e.g. harbor.infra.gdc.example.com): ${NC}"
  read -r REGISTRY
  if [[ -z "${REGISTRY}" ]]; then
    echo -e "${RED}Error: Target registry cannot be empty.${NC}" >&2
    exit 1
  fi
fi

# Strip trailing slash or protocol prefix if entered by user
REGISTRY="${REGISTRY#https://}"
REGISTRY="${REGISTRY#http://}"
REGISTRY="${REGISTRY%/}"

# Ensure Bundle Directory Exists
if [[ ! -d "${BUNDLE_DIR}" ]]; then
  echo -e "${RED}Error: Bundle directory '${BUNDLE_DIR}' does not exist.${NC}" >&2
  exit 1
fi

BUNDLE_DIR="$(cd "${BUNDLE_DIR}" && pwd)"
echo -e "Target Registry:     ${BOLD}${CYAN}oci://${REGISTRY}/${PROJECT}${NC}"
echo -e "Bundle Directory:    ${BOLD}${BUNDLE_DIR}${NC}"
echo -e "Insecure TLS:        ${BOLD}${INSECURE}${NC}"
echo -e "Dry Run Mode:        ${BOLD}${DRY_RUN}${NC}"
echo -e "--------------------------------------------------------------------"

# Step 1: Cryptographic Integrity Verification
echo -e "\n${BOLD}[Step 1/3] Cryptographic Integrity Verification...${NC}"
if [[ "${SKIP_CHECKSUM}" == "true" ]]; then
  echo -e "${YELLOW}⚠️  Skipping checksum verification (--skip-checksum specified).${NC}"
else
  SHA_FILE=""
  if [[ -f "${BUNDLE_DIR}/SHA256SUMS" ]]; then
    SHA_FILE="${BUNDLE_DIR}/SHA256SUMS"
  elif [[ -f "${BUNDLE_DIR}/sha256sums.txt" ]]; then
    SHA_FILE="${BUNDLE_DIR}/sha256sums.txt"
  fi

  if [[ -n "${SHA_FILE}" ]]; then
    echo "Verifying SHA256 checksums from $(basename "${SHA_FILE}")..."
    cd "${BUNDLE_DIR}"
    if command -v sha256sum &>/dev/null; then
      if sha256sum -c "${SHA_FILE}" --status 2>/dev/null || sha256sum -c "${SHA_FILE}"; then
        echo -e "${GREEN}✅ Checksum verification passed! All bundle contents are authentic.${NC}"
      else
        echo -e "${RED}❌ Checksum verification FAILED! Bundle files may be corrupted or altered.${NC}" >&2
        exit 1
      fi
    elif command -v shasum &>/dev/null; then
      if shasum -a 256 -c "${SHA_FILE}"; then
        echo -e "${GREEN}✅ Checksum verification passed! All bundle contents are authentic.${NC}"
      else
        echo -e "${RED}❌ Checksum verification FAILED! Bundle files may be corrupted or altered.${NC}" >&2
        exit 1
      fi
    else
      echo -e "${YELLOW}Warning: Neither 'sha256sum' nor 'shasum' available; skipping checksum verification.${NC}"
    fi
  else
    echo -e "${YELLOW}Note: No SHA256SUMS file found in '${BUNDLE_DIR}'. Proceeding with unverified bundle.${NC}"
  fi
fi

# Step 2: Registry Authentication
echo -e "\n${BOLD}[Step 2/3] Authenticating to Local OCI Registry...${NC}"
if [[ -z "${USERNAME}" ]]; then
  echo -n -e "${YELLOW}Enter Registry Username: ${NC}"
  read -r USERNAME
fi

if [[ -z "${PASSWORD}" ]]; then
  echo -n -e "${YELLOW}Enter Registry Password for '${USERNAME}': ${NC}"
  read -r -s PASSWORD
  echo ""
fi

LOGIN_EXTRA_ARGS=()
if [[ "${INSECURE}" == "true" ]]; then
  LOGIN_EXTRA_ARGS+=(--insecure)
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  echo -e "${CYAN}[DRY-RUN] helm registry login \"${REGISTRY}\" -u \"${USERNAME}\" ${LOGIN_EXTRA_ARGS[*]}${NC}"
else
  if echo "${PASSWORD}" | helm registry login "${REGISTRY}" -u "${USERNAME}" --password-stdin "${LOGIN_EXTRA_ARGS[@]}"; then
    echo -e "${GREEN}✅ Authenticated successfully to ${REGISTRY}${NC}"
  else
    echo -e "${RED}❌ Registry authentication failed. Check credentials and TLS settings.${NC}" >&2
    exit 1
  fi
fi

# Step 3: Ingesting Helm Charts
echo -e "\n${BOLD}[Step 3/3] Synchronizing Helm Charts to oci://${REGISTRY}/${PROJECT}...${NC}"

# Find all packaged chart tarballs
CHART_PACKAGES=()
while IFS= read -r -d $'\0' pkg; do
  CHART_PACKAGES+=("$pkg")
done < <(find "${BUNDLE_DIR}" -maxdepth 3 -name "*.tgz" -print0 2>/dev/null || true)

if [[ ${#CHART_PACKAGES[@]} -eq 0 ]]; then
  echo -e "${YELLOW}No pre-packaged *.tgz chart archives found in ${BUNDLE_DIR}.${NC}"
  echo "Checking for uncompressed charts directory..."
  if [[ -d "${BUNDLE_DIR}/charts" ]]; then
    echo "Found uncompressed charts under ${BUNDLE_DIR}/charts. Packaging charts into temporary cache..."
    TEMP_PKG_DIR=$(mktemp -d)
    trap 'rm -rf "${TEMP_PKG_DIR}"' EXIT
    for chart_dir in "${BUNDLE_DIR}/charts"/*; do
      if [[ -d "${chart_dir}" ]] && [[ -f "${chart_dir}/Chart.yaml" ]]; then
        helm package "${chart_dir}" -d "${TEMP_PKG_DIR}" >/dev/null
      fi
    done
    while IFS= read -r -d $'\0' pkg; do
      CHART_PACKAGES+=("$pkg")
    done < <(find "${TEMP_PKG_DIR}" -name "*.tgz" -print0)
  fi
fi

if [[ ${#CHART_PACKAGES[@]} -eq 0 ]]; then
  echo -e "${RED}Error: No Helm charts found to ingest in '${BUNDLE_DIR}'.${NC}" >&2
  exit 1
fi

echo -e "Found ${BOLD}${#CHART_PACKAGES[@]}${NC} chart packages to ingest."

PUSH_EXTRA_ARGS=()
if [[ "${INSECURE}" == "true" ]]; then
  PUSH_EXTRA_ARGS+=(--insecure-skip-tls-verify)
fi

SUCCESS_COUNT=0
FAILURE_COUNT=0
INGESTED_CHARTS=()

for pkg in "${CHART_PACKAGES[@]}"; do
  pkg_name="$(basename "$pkg")"
  echo -n -e "  • Pushing ${BOLD}${pkg_name}${NC} ... "

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo -e "${CYAN}[DRY-RUN] helm push \"$pkg\" \"oci://${REGISTRY}/${PROJECT}\"${NC}"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    INGESTED_CHARTS+=("${pkg_name}")
  else
    if helm push "$pkg" "oci://${REGISTRY}/${PROJECT}" "${PUSH_EXTRA_ARGS[@]}" >/dev/null 2>&1; then
      echo -e "${GREEN}SUCCESS${NC}"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
      INGESTED_CHARTS+=("${pkg_name}")
    else
      echo -e "${RED}FAILED${NC}"
      echo -e "${YELLOW}Retrying with verbose output:${NC}"
      helm push "$pkg" "oci://${REGISTRY}/${PROJECT}" "${PUSH_EXTRA_ARGS[@]}" || true
      FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi
  fi
done

echo -e "\n${BLUE}====================================================================${NC}"
if [[ ${FAILURE_COUNT} -eq 0 ]]; then
  echo -e "${GREEN}${BOLD} ✅ INGESTION COMPLETE: All ${SUCCESS_COUNT} charts successfully pushed!${NC}"
else
  echo -e "${YELLOW}⚠️  INGESTION FINISHED WITH WARNINGS: ${SUCCESS_COUNT} succeeded, ${FAILURE_COUNT} failed.${NC}"
fi
echo -e "${BLUE}====================================================================${NC}"

# Downstream Configuration Instructions
echo -e "\n${BOLD}${CYAN}Downstream Helmfile Configuration Example:${NC}"
echo -e "To consume these ingested charts in downstream tenant environments, update"
echo -e "${BOLD}foundations/bases/environments/<env>/charts.yaml${NC} with:"
echo -e ""
echo -e "  ${YELLOW}# Pinned OCI charts in local Harbor${NC}"
echo -e "  gdc_clusters_chart_path: ${GREEN}\"oci://${REGISTRY}/${PROJECT}/gdc-clusters\"${NC}"
echo -e "  gdc_clusters_chart_version: ${GREEN}\"0.1.3\"${NC}"
echo -e ""
echo -e "  gdc_projects_chart_path: ${GREEN}\"oci://${REGISTRY}/${PROJECT}/gdc-projects\"${NC}"
echo -e "  gdc_projects_chart_version: ${GREEN}\"0.1.1\"${NC}"
echo -e ""
