#!/usr/bin/env python3
"""
@file test_phase3_agentic.py
@brief Validation suite for Pattern 13: Phase 3 In-Pod Agentic AI Platform on GDC Air-Gapped.

@details Validates:
1. Phase 3 Agentic ConfigMap & Deployment manifests.
2. Helm values-gdc-phase3.yaml agent configuration block.
3. OpenAI-compatible Function Calling tool schemas (read_file, write_file, apply_diff, run_terminal_command, list_directory).
4. In-pod co-located tool execution engine (surgical diff patching, safe sandboxed execution).
5. Selective Auto-Approval security policy (read-only auto-approved, mutations/commands require human confirmation).
6. Workspace UI rendering in Phase 3 Agentic mode.

@date 2026-09-01
"""

import os
import sys
import unittest
import json
import importlib.util

class TestGdcDevPhase3Agentic(unittest.TestCase):
    """Phase 3 In-Pod Agentic AI Engine & Security Tests."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifest_dir = os.path.join(self.base_dir, "manifests", "gdc")

    def test_phase3_agent_configmap_structure(self):
        """Verify gdc-dev-agent-config ConfigMap exists with required agentic keys."""
        config_file = os.path.join(self.manifest_dir, "gdc-dev-agent-configmap.yaml")
        self.assertTrue(os.path.isfile(config_file), f"Missing manifest: {config_file}")
        with open(config_file, "r") as f:
            content = f.read()

        self.assertIn("name: gdc-dev-agent-config", content)
        self.assertIn('AI_AGENT_MODE: "agentic"', content)
        self.assertIn('AI_APPROVAL_POLICY: "selective"', content)
        self.assertIn('AI_MAX_TURNS: "10"', content)
        self.assertIn('AI_REQUEST_TIMEOUT: "300"', content)
        self.assertIn('AI_TIER1_MODEL: "gemma4:26b"', content)
        self.assertIn('AI_CODER_MODEL: "gemma4:31b"', content)

    def test_phase3_deployment_manifest(self):
        """Verify Phase 3 Deployment references gdc-dev-agent-config and gdc-dev-oidc-auth-config."""
        dep_file = os.path.join(self.manifest_dir, "gdc-dev-phase3-deployment.yaml")
        self.assertTrue(os.path.isfile(dep_file), f"Missing manifest: {dep_file}")
        with open(dep_file, "r") as f:
            content = f.read()

        self.assertIn("name: gdc-dev-operator", content)
        self.assertIn("name: gdc-dev-landing-page", content)
        self.assertIn("gdc-dev-agent-config", content)
        self.assertIn("gdc-dev-oidc-auth-config", content)

    def test_values_override_phase3_agentic(self):
        """Verify values-gdc-phase3.yaml includes agent block with in-pod mode and selective approval."""
        values_file = os.path.join(self.manifest_dir, "values-gdc-phase3.yaml")
        with open(values_file, "r") as f:
            content = f.read()

        self.assertIn("agent:", content)
        self.assertIn('mode: "in-pod"', content)
        self.assertIn('approvalPolicy: "selective"', content)
        self.assertIn("maxTurns: 10", content)
        self.assertIn("timeout: 300", content)
        self.assertIn('tier1Model: "gemma4:26b"', content)
        self.assertIn('tier2Model: "gemma4:31b"', content)

    def test_agentic_tool_schema_conformance(self):
        """Verify the agentic tool schema conforms to OpenAI function calling standards."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        tools = getattr(landing_app, "AGENT_TOOLS", [])
        tool_names = [t["function"]["name"] for t in tools]
        expected_tools = ["read_file", "write_file", "apply_diff", "run_terminal_command", "list_directory", "create_directory"]
        for expected in expected_tools:
            self.assertIn(expected, tool_names, f"Missing tool in schema: {expected}")

    def test_in_pod_tool_execution_engine(self):
        """Verify in-pod tool execution for read_file, apply_diff, run_terminal_command, and create_directory."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        mock_files = {
            "primes.py": "def is_prime(n):\n    if n < 1: return False\n    return True\n"
        }

        # 1. Test read_file
        ok, content = landing_app.execute_tool("read_file", {"path": "primes.py"}, mock_files)
        self.assertTrue(ok)
        self.assertIn("is_prime", content)

        # 2. Test apply_diff
        ok, msg = landing_app.execute_tool("apply_diff", {
            "path": "primes.py",
            "target_block": "if n < 1: return False",
            "replacement_block": "if n <= 1: return False"
        }, mock_files)
        self.assertTrue(ok)
        self.assertIn("if n <= 1:", mock_files["primes.py"])

        # 3. Test run_terminal_command
        ok, out = landing_app.execute_tool("run_terminal_command", {"command": "echo 'Agentic Verified'"}, mock_files)
        self.assertTrue(ok)
        self.assertIn("Agentic Verified", out)

        # 4. Test create_directory
        ok, dir_msg = landing_app.execute_tool("create_directory", {"path": "src/utils"}, mock_files)
        self.assertTrue(ok)
        self.assertIn("src/utils", dir_msg)

    def test_selective_auto_approval_security_gate(self):
        """Verify selective auto-approval policy correctly segments read vs mutation permissions."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        # Read-only and safe scaffolding tools must be AUTO_APPROVED
        self.assertEqual(landing_app.classify_tool_permission("read_file"), "AUTO_APPROVED")
        self.assertEqual(landing_app.classify_tool_permission("list_directory"), "AUTO_APPROVED")
        self.assertEqual(landing_app.classify_tool_permission("create_directory"), "AUTO_APPROVED")

        # Mutating tools must require DIFF or COMMAND approval
        self.assertEqual(landing_app.classify_tool_permission("apply_diff"), "REQUIRES_DIFF_APPROVAL")
        self.assertEqual(landing_app.classify_tool_permission("write_file"), "REQUIRES_DIFF_APPROVAL")
        self.assertEqual(landing_app.classify_tool_permission("run_terminal_command"), "REQUIRES_COMMAND_APPROVAL")


if __name__ == "__main__":
    unittest.main()
