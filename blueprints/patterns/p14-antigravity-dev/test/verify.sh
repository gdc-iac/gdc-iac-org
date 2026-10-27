#!/bin/bash
# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Running Pattern 14 Phase 1 (Structural & Gateway) Test Suite ==="
python3 "${SCRIPT_DIR}/test_phase1.py"

echo "=== Running Pattern 14 Phase 2 (Keycloak OIDC & Session Isolation) Test Suite ==="
python3 "${SCRIPT_DIR}/test_phase2.py"

echo "=== Running Pattern 14 Phase 3 (Enterprise PKI & NetworkPolicy) Test Suite ==="
python3 "${SCRIPT_DIR}/test_phase3.py"

echo "=== Running Pattern 14 Phase 3 Agentic AI & PoLP Test Suite ==="
python3 "${SCRIPT_DIR}/test_phase3_agentic.py"

echo "=== Running Pattern 14 AI Gateway Integration Test Suite ==="
python3 "${SCRIPT_DIR}/test_ai_integration.py"

echo "=== Running Pattern 14 Phase 4 Multi-Agent Swarm & Shared Git Promotion Test Suite ==="
python3 "${SCRIPT_DIR}/test_phase4_swarm.py"

echo "=== Running Pattern 14 Sovereign Admin Telemetry & Port 8081 Isolation Test Suite ==="
python3 "${SCRIPT_DIR}/test_telemetry.py"

echo "=== Running Pattern 14 Phase 5 Antigravity SDK & Integrated JupyterLab 4 Test Suite ==="
python3 "${SCRIPT_DIR}/test_phase5_antigravity_notebooks.py"

echo "========================================================================"
echo "✅ ALL PATTERN 14 (p14-antigravity-dev) VALIDATION SUITES PASSED"
echo "========================================================================"
