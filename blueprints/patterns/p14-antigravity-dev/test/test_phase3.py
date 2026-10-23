#!/usr/bin/env python3
"""
@file test_phase3.py
@brief Validation suite for Pattern 13: GDC Developer Environment (gdc-dev) (Phase 3 Enterprise PKI & Hardening).

@details Executes structural manifest checks for GDC Platform PKI cert-manager integration
(disabling self-signed CA), persistent PVC storage configuration, and multi-tenant
NetworkPolicy boundaries on Google Distributed Cloud (GDC) Air-Gapped using standard
string/regex validation.

@date 2026-07-07
"""

import os
import unittest

class TestGdcDevPhase3PKIAndHardening(unittest.TestCase):
    """Phase 3 GDC Platform PKI cert-manager and Cluster Hardening Tests."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifest_dir = os.path.join(self.base_dir, "manifests", "gdc")

    def test_phase3_manifest_files_exist(self):
        """Verify required Phase 3 PKI, PVC, and NetworkPolicy manifest files exist."""
        expected_files = [
            "values-gdc-phase3.yaml",
            "certificate.yaml",
            "network-policy.yaml",
        ]
        for fname in expected_files:
            fpath = os.path.join(self.manifest_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Missing Phase 3 manifest file: {fname}")

    def test_values_override_phase3_pki_and_pvc(self):
        """Verify Phase 3 Helm values disable self-signed CA and enable GDC cert-manager + PVC."""
        values_file = os.path.join(self.manifest_dir, "values-gdc-phase3.yaml")
        with open(values_file, "r") as f:
            content = f.read()

        # Check self-signed CA disabled in favor of platform PKI
        self.assertIn("create: false", content, "values-gdc-phase3.yaml must set tls.issuerCa.create=false")
        self.assertIn('clusterIssuer: "gdc-ca-issuer"', content, "values-gdc-phase3.yaml must specify gdc-ca-issuer")
        
        # Check persistent storage (PVC) enabled for workspace sessions
        self.assertIn("storage:", content, "values-gdc-phase3.yaml must define workspace storage settings")
        self.assertIn("enabled: true", content)
        self.assertIn("storageClassName:", content)

    def test_cert_manager_certificate_manifest(self):
        """Verify cert-manager Certificate manifest targets gdc-ca-issuer and dev.gdc.local."""
        cert_file = os.path.join(self.manifest_dir, "certificate.yaml")
        with open(cert_file, "r") as f:
            content = f.read()

        self.assertIn("apiVersion: cert-manager.io/v1", content)
        self.assertIn("kind: Certificate", content)
        self.assertIn("name: gdc-dev-tls-cert", content)
        self.assertIn("namespace: gdc-dev", content)
        self.assertIn("secretName: gdc-dev-tls-secret", content)
        self.assertIn("dev.gdc.local", content)
        self.assertIn("name: gdc-ca-issuer", content)
        self.assertIn("kind: ClusterIssuer", content)

    def test_network_policy_manifest(self):
        """Verify NetworkPolicy enforces tenant boundary around operator and workspace pods."""
        netpol_file = os.path.join(self.manifest_dir, "network-policy.yaml")
        with open(netpol_file, "r") as f:
            content = f.read()

        self.assertIn("apiVersion: networking.k8s.io/v1", content)
        self.assertIn("kind: NetworkPolicy", content)
        self.assertIn("name: gdc-dev-netpol", content)
        self.assertIn("namespace: gdc-dev", content)
        self.assertIn("policyTypes:", content)
        self.assertIn("- Ingress", content)
        self.assertIn("- Egress", content)


if __name__ == "__main__":
    unittest.main()
