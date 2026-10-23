#!/usr/bin/env python3
"""
@file test_phase1.py
@brief Validation suite for Pattern 13: GDC Developer Environment (gdc-dev) (Phase 1).

@details Executes Phase A (Structural & Lint Validation) and Phase B (Functional & Routing Verification)
for the gdc-dev blueprint on Google Distributed Cloud (GDC) Air-Gapped.

@date 2026-07-03
"""

import os
import unittest

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class TestGdcDevPhase1Structural(unittest.TestCase):
    """Phase A Structural and Manifest Validation Tests."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifest_dir = os.path.join(self.base_dir, "manifests", "gdc")

    def test_manifest_files_exist(self):
        """Verify all required Phase 1 manifest files are present."""
        expected_files = [
            "namespace.yaml",
            "gateway.yaml",
            "loadbalancer.yaml",
            "mock-auth-configmap.yaml",
            "gdc-dev-operator.yaml",
            "values-gdc-phase1.yaml",
        ]
        for fname in expected_files:
            fpath = os.path.join(self.manifest_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Missing manifest file: {fname}")

    def test_loadbalancer_configuration(self):
        """Verify standalone LoadBalancer Service configuration for developer entry point."""
        lb_file = os.path.join(self.manifest_dir, "loadbalancer.yaml")
        with open(lb_file, "r") as f:
            content = f.read()

        self.assertIn("kind: Service", content)
        self.assertIn("type: LoadBalancer", content)
        self.assertIn("gdc-dev-loadbalancer", content)
        self.assertIn("networking.gke.io/load-balancer-type: \"Internal\"", content)
        self.assertNotIn("kind: Ingress", content, "Legacy Ingress should not be used")

    def test_gateway_api_configuration(self):
        """Verify Gateway API specs replace legacy NGINX Ingress."""
        gateway_file = os.path.join(self.manifest_dir, "gateway.yaml")
        with open(gateway_file, "r") as f:
            content = f.read()

        self.assertIn("kind: GatewayClass", content)
        self.assertIn("kind: Gateway", content)
        self.assertIn("kind: HTTPRoute", content)
        self.assertNotIn("kind: Ingress", content, "Legacy Ingress should not be used")
        self.assertIn("gdc-dev-gateway", content)
        self.assertIn("dev.gdc.local", content)

    def test_mock_auth_configmap(self):
        """Verify Phase 1 Mock Identity ConfigMap contains required keys."""
        config_file = os.path.join(self.manifest_dir, "mock-auth-configmap.yaml")
        with open(config_file, "r") as f:
            content = f.read()

        self.assertIn('AUTH_MODE: "mock"', content)
        self.assertIn('HEADER_USER_KEY: "X-User-ID"', content)
        self.assertIn("MOCK_USER_ID", content)

    def test_values_override_phase1(self):
        """Verify Phase 1 Helm values disable NGINX and enable self-signed TLS."""
        values_file = os.path.join(self.manifest_dir, "values-gdc-phase1.yaml")
        with open(values_file, "r") as f:
            content = f.read()

        self.assertIn("enabled: false", content) # Ingress disabled
        self.assertIn("gatewayClassName: \"gdc-dev-gateway-class\"", content)
        self.assertIn("type: \"mock\"", content)
        self.assertIn("create: true", content) # self-signed issuer enabled in Phase 1

    def test_session_service_selector(self):
        """Verify gdc-dev-session-service targets operator on port 3000."""
        operator_file = os.path.join(self.manifest_dir, "gdc-dev-operator.yaml")
        with open(operator_file, "r") as f:
            content = f.read()

        session_service_block = content.split("name: gdc-dev-session-service")[1]
        self.assertIn("app: gdc-dev-operator", session_service_block)
        self.assertIn("port: 3000", session_service_block)

    def test_interactive_session_endpoints(self):
        """Verify operator and landing page implement interactive POST exec endpoint and textarea UI."""
        operator_app = os.path.join(self.base_dir, "example-app", "operator", "app.py")
        landing_app = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        
        for fpath in [operator_app, landing_app]:
            with open(fpath, "r") as f:
                content = f.read()
            self.assertIn("do_POST", content, f"Missing do_POST handler in {fpath}")
            self.assertIn("/exec", content, f"Missing /exec endpoint handling in {fpath}")
            self.assertIn("<textarea", content, f"Missing interactive textarea editor in {fpath}")

    def test_terminal_history_and_autocomplete_features(self):
        """Verify operator and landing page implement terminal command history, autocomplete, and history command."""
        operator_app = os.path.join(self.base_dir, "example-app", "operator", "app.py")
        landing_app = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        
        for fpath in [operator_app, landing_app]:
            with open(fpath, "r") as f:
                content = f.read()
            self.assertIn("handleTermKeydown", content, f"Missing handleTermKeydown in {fpath}")
            self.assertIn("commandHistory", content, f"Missing commandHistory in {fpath}")
            self.assertIn("autoCompleteCommand", content, f"Missing autoCompleteCommand in {fpath}")
            self.assertIn("ArrowUp", content, f"Missing ArrowUp history navigation in {fpath}")
            self.assertIn('trimmed === "history"', content, f"Missing client history command in {fpath}")

    def test_render_workspace_ui_execution(self):
        """Verify render_workspace_ui executes cleanly without f-string or NameError."""
        import importlib.util
        for subapp in ["operator", "landing-page"]:
            fpath = os.path.join(self.base_dir, "example-app", subapp, "app.py")
            spec = importlib.util.spec_from_file_location(f"{subapp}_app", fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            
            html = mod.render_workspace_ui("test-session", "dev-user-1")
            self.assertTrue(html.startswith("<!DOCTYPE html>"), f"render_workspace_ui in {subapp} did not return valid HTML")
            self.assertIn("test-session", html)
            self.assertIn("dev-user-1", html)

    def test_operator_entrypoint_symbols(self):
        """Verify operator app defines all required symbols for __main__ startup."""
        import importlib.util
        fpath = os.path.join(self.base_dir, "example-app", "operator", "app.py")
        spec = importlib.util.spec_from_file_location("operator_app_entrypoint", fpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "Thread") or hasattr(mod.threading, "Thread"))
        self.assertTrue(callable(getattr(mod, "run_health_server", None)))
        self.assertTrue(callable(getattr(mod, "run_session_server", None)))
        self.assertTrue(callable(getattr(mod, "control_loop", None)))


if __name__ == "__main__":
    unittest.main()
