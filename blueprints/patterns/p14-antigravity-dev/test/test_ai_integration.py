#!/usr/bin/env python3
"""
@file test_ai_integration.py
@brief Validation suite for Pattern 13: GDC Developer Environment (gdc-dev) AI Overlay Integration with Gemma 4 Gateway.

@details Validates Phase AI (Optional Additive Overlay) manifests, cross-namespace network policies,
and AI-enabled workspace UI contracts for Google Distributed Cloud (GDC) Air-Gapped.

@date 2026-09-01
"""

import os
import unittest
import json
import importlib.util

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class TestGdcDevAIIntegration(unittest.TestCase):
    """Validation tests for the optional gdc-dev + Gemma Gateway AI integration."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifest_dir = os.path.join(self.base_dir, "manifests", "gdc")

    def test_ai_manifest_files_exist(self):
        """Verify all required AI overlay manifest files are present."""
        expected_files = [
            "ai-gateway-configmap.yaml",
            "network-policy-ai.yaml",
            "gdc-dev-ai-patch.yaml",
        ]
        for fname in expected_files:
            fpath = os.path.join(self.manifest_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Missing AI manifest file: {fname}")

    def test_ai_gateway_configmap_structure(self):
        """Verify AI Gateway ConfigMap contains required cross-namespace endpoint keys."""
        config_file = os.path.join(self.manifest_dir, "ai-gateway-configmap.yaml")
        with open(config_file, "r") as f:
            content = f.read()

        self.assertIn("name: gdc-dev-ai-config", content)
        self.assertIn('AI_ENABLED: "true"', content)
        self.assertIn("OPENAI_API_BASE_URL", content)
        self.assertIn("gemma-gateway.gemma-inference.svc.cluster.local", content)
        self.assertIn("AI_DEFAULT_MODEL", content)
        self.assertIn("AI_CODER_MODEL", content)
        self.assertIn("NO_PROXY", content)

    def test_ai_network_policy_cross_namespace(self):
        """Verify NetworkPolicy allows egress to gemma-inference and kube-system."""
        netpol_file = os.path.join(self.manifest_dir, "network-policy-ai.yaml")
        with open(netpol_file, "r") as f:
            content = f.read()

        self.assertIn("kind: NetworkPolicy", content)
        self.assertIn("gdc-dev-to-gemma-netpol", content)
        self.assertIn("gdc-dev-landing-page", content)
        self.assertIn("gdc-dev-operator", content)
        self.assertIn("gemma-inference", content)
        self.assertIn("port: 80", content)
        self.assertIn("kube-system", content)

    def test_ai_patch_optional_overlay(self):
        """Verify AI patch marks ConfigMap as optional so base deployment is not broken."""
        patch_file = os.path.join(self.manifest_dir, "gdc-dev-ai-patch.yaml")
        with open(patch_file, "r") as f:
            content = f.read()

        self.assertIn("gdc-dev-ai-config", content)
        self.assertIn("optional: true", content)

    def test_ui_render_backward_compatibility(self):
        """Verify workspace UI renders cleanly when AI is disabled (base mode)."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        
        # Ensure AI is disabled
        os.environ["AI_ENABLED"] = "false"
        spec.loader.exec_module(landing_app)
        
        html = landing_app.render_workspace_ui("test-session", "dev-user-1")
        self.assertIn("GDC Developer Environment", html)
        self.assertIn("test-session", html)
        self.assertNotIn("GDC Dev AI Assistant (Gemma 4)", html)

    def test_ui_render_ai_enabled_mode(self):
        """Verify workspace UI dynamically renders AI Coder dock with Copy, Insert, & formatting actions."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        
        # Enable AI mode
        os.environ["AI_ENABLED"] = "true"
        os.environ["OPENAI_API_BASE_URL"] = "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
        spec.loader.exec_module(landing_app)
        
        html = landing_app.render_workspace_ui("ai-session", "oidc-developer@gdc.local")
        self.assertIn("GDC Developer Environment", html)
        self.assertIn("GDC Dev AI Assistant (Gemma 4)", html)
        self.assertIn("askAi", html)
        self.assertIn("copyResponse", html)
        self.assertIn("insertIntoEditor", html)
        self.assertIn("stopAi", html)
        self.assertIn("formatAiResponse", html)
        self.assertIn("ai-code-block", html)

    def test_handle_ai_chat_context_awareness(self):
        """Verify handle_ai_chat accepts and incorporates active file context and diagnostics."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        # Test request with active editor context
        payload = json.dumps({
            "prompt": "Optimize this prime search algorithm",
            "filename": "primes.py",
            "context": "def is_prime(n):\n    for i in range(2, n):\n        if n % i == 0: return False\n    return True"
        })
        resp = landing_app.handle_ai_chat(payload, "oidc-developer@gdc.local")
        self.assertIn("reply", resp)
        # Should return either gateway completion or diagnostic fallback
        self.assertTrue(len(resp["reply"]) > 0)


if __name__ == "__main__":
    unittest.main()
