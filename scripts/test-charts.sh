#!/bin/bash
set -e

# Change straight to directory of this script, then go up one level to repo root
cd "$(dirname "$0")/.."

echo "================================================="
echo "Starting CI/CD pre-deployment checks..."
echo "================================================="

# Loop through all subdirectories in chars/
for chart in charts/*; do
  if [ -d "$chart" ] && [ -f "$chart/Chart.yaml" ]; then
    echo ""
    echo "================================================="
    echo "Testing Chart: $chart"
    echo "================================================="

    echo "1. Validating Helm syntax and structural best practices (helm lint)..."
    helm lint "$chart"
    echo "✅ Linting passed."

    echo ""
    echo "2. Validating Go templating logic via unit tests (helm-unittest)..."
    helm unittest "$chart"
    echo "✅ Unit tests passed."

    echo ""
    echo "3. Structural & Schema Validation (kubeconform)..."
    # Note: Skipping custom GDC resource ProjectNetworkPolicy for now until OpenAPI schemas are supplied.
    helm template test-release "$chart" | kubeconform -strict -summary -skip ProjectNetworkPolicy
    echo "✅ Kubeconform structural validation passed."

    echo ""
    echo "4. Policy & Security Compliance (conftest)..."
    # Check if a policy directory exists for this chart, or fall back to a global policy
    if [ -d "$chart/policy" ]; then
      helm template test-release "$chart" | conftest test -p "$chart/policy/" -
      echo "✅ Local chart security policies passed."
    elif [ -d "policy" ]; then
      helm template test-release "$chart" | conftest test -p policy/ -
      echo "✅ Global security policies passed."
    else
      echo "⚠️ No conftest policies found to evaluate."
    fi

    echo "================================================="
    echo "✅ ALL CHECKS PASSED FOR $chart"
    echo "================================================="
  fi
done
