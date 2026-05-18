#!/usr/bin/env bash

# GDC AG Foundations IaC Pipeline Validation Script
# Automates local static checks, schema enforcement, and template rendering checks.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0;0m'

ENV="${1:-dev}"

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   GDC AG IaC Foundations Validation Harness (${ENV})${NC}"
echo -e "${BLUE}====================================================${NC}"

# Step 1: Helm Chart Linting
echo -e "\n${YELLOW}[Step 1/3] Linting Local Custom Charts...${NC}"
for chart_dir in charts/*; do
  if [ -d "$chart_dir" ]; then
    echo -n "Linting $chart_dir... "
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
if helmfile -e "$ENV" lint; then
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
