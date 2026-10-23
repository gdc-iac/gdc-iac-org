#!/usr/bin/env python3
"""
@file test_phase2.py
@brief Validation suite for Pattern 13: GDC Developer Environment (gdc-dev) (Phase 2 Keycloak OIDC Integration).

@details Executes structural manifest checks for OIDC configuration and unit tests
application handling of OIDC authentication flows (Login portal vs Authenticated IDE sessions)
on Google Distributed Cloud (GDC) Air-Gapped.

@date 2026-07-07
"""

import os
import unittest
import importlib.util

class TestGdcDevPhase2OIDCStructural(unittest.TestCase):
    """Phase 2 Keycloak OIDC Structural and Manifest Validation Tests."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifest_dir = os.path.join(self.base_dir, "manifests", "gdc")

    def test_phase2_manifest_files_exist(self):
        """Verify required Phase 2 Keycloak OIDC manifest files are present."""
        expected_files = [
            "oidc-auth-configmap.yaml",
            "values-gdc-phase2.yaml",
            "gdc-dev-phase2-deployment.yaml",
        ]
        for fname in expected_files:
            fpath = os.path.join(self.manifest_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Missing Phase 2 manifest file: {fname}")

    def test_oidc_auth_configmap(self):
        """Verify Phase 2 OIDC ConfigMap configures Keycloak realm and client."""
        config_file = os.path.join(self.manifest_dir, "oidc-auth-configmap.yaml")
        with open(config_file, "r") as f:
            content = f.read()

        self.assertIn('AUTH_MODE: "oidc"', content)
        self.assertIn('OIDC_AUTHORITY: "https://keycloak.gdc.local/realms/gdc-dev-realm"', content)
        self.assertIn('OIDC_CLIENT_ID: "gdc-dev-client"', content)

    def test_values_override_phase2(self):
        """Verify Phase 2 Helm values enable Keycloak OIDC authentication."""
        values_file = os.path.join(self.manifest_dir, "values-gdc-phase2.yaml")
        with open(values_file, "r") as f:
            content = f.read()

        self.assertIn('type: "oidc"', content)
        self.assertIn("enabled: true", content) # Keycloak integration enabled
        self.assertIn('realm: "gdc-dev-realm"', content)
        self.assertIn('clientId: "gdc-dev-client"', content)


class TestGdcDevPhase2OIDCApplicationFlow(unittest.TestCase):
    """Phase 2 Keycloak OIDC Application Flow Unit Tests."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.landing_app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        self.operator_app_path = os.path.join(self.base_dir, "example-app", "operator", "app.py")

    def test_unauthenticated_oidc_renders_login_portal(self):
        """Verify unauthenticated user in OIDC mode receives Keycloak login prompt/page."""
        for subapp, fpath in [("landing-page", self.landing_app_path), ("operator", self.operator_app_path)]:
            spec = importlib.util.spec_from_file_location(f"{subapp}_oidc_app", fpath)
            mod = importlib.util.module_from_spec(spec)
            
            # Temporarily set AUTH_MODE=oidc
            old_auth = os.environ.get("AUTH_MODE")
            os.environ["AUTH_MODE"] = "oidc"
            try:
                spec.loader.exec_module(mod)
                # When user_id is "anonymous" or empty in OIDC mode
                html = mod.render_workspace_ui("test-session", "anonymous")
                self.assertIn("Sign in with Keycloak OIDC", html, f"{subapp} did not prompt for Keycloak login when anonymous under OIDC mode")
                self.assertIn("gdc-dev-realm", html)
            finally:
                if old_auth is not None:
                    os.environ["AUTH_MODE"] = old_auth
                else:
                    os.environ.pop("AUTH_MODE", None)

    def test_authenticated_oidc_renders_workspace(self):
        """Verify authenticated OIDC user receives active workspace IDE dashboard."""
        for subapp, fpath in [("landing-page", self.landing_app_path), ("operator", self.operator_app_path)]:
            spec = importlib.util.spec_from_file_location(f"{subapp}_oidc_app_auth", fpath)
            mod = importlib.util.module_from_spec(spec)
            
            old_auth = os.environ.get("AUTH_MODE")
            os.environ["AUTH_MODE"] = "oidc"
            try:
                spec.loader.exec_module(mod)
                html = mod.render_workspace_ui("test-session", "oidc-developer@gdc.local")
                self.assertIn("oidc-developer@gdc.local", html)
                self.assertIn("Mode: <strong>oidc</strong>", html)
                self.assertNotIn("Sign in with Keycloak OIDC", html)
            finally:
                if old_auth is not None:
                    os.environ["AUTH_MODE"] = old_auth
                else:
                    os.environ.pop("AUTH_MODE", None)


if __name__ == "__main__":
    unittest.main()
