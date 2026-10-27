#!/usr/bin/env python3
"""
@file test_telemetry.py
@brief Validation suite for Pattern 13: GDC Sovereign Admin & Telemetry Console.

@details Validates:
1. Thread-safe TelemetryCollector lifecycle, baseline metrics, live request recording, and summary aggregation.
2. Server-side rendered dark-mode Admin Telemetry UI (KPIs, distribution charts, workspaces, inference feed).
3. OpenMetrics / Prometheus metrics exposition format (/metrics).
4. Operator and Landing Page service telemetry route integration (/admin, /metrics, /admin/telemetry/json).

@date 2026-09-08
"""

import os
import sys
import unittest
import json
import importlib.util

class TestGdcDevTelemetry(unittest.TestCase):
    """Admin Telemetry and Prometheus Exposition Validation Tests."""

    @classmethod
    def setUpClass(cls):
        os.environ["UNIT_TEST"] = "true"
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lp_path = os.path.join(cls.base_dir, "example-app", "landing-page", "app.py")
        op_path = os.path.join(cls.base_dir, "example-app", "operator", "app.py")

        spec_lp = importlib.util.spec_from_file_location("landing_app", lp_path)
        cls.landing_app = importlib.util.module_from_spec(spec_lp)
        sys.modules["landing_app"] = cls.landing_app
        spec_lp.loader.exec_module(cls.landing_app)

        spec_op = importlib.util.spec_from_file_location("operator_app", op_path)
        cls.operator_app = importlib.util.module_from_spec(spec_op)
        sys.modules["operator_app"] = cls.operator_app
        spec_op.loader.exec_module(cls.operator_app)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("UNIT_TEST", None)
        if hasattr(cls, "landing_app") and hasattr(cls.landing_app, "TELEMETRY"):
            cls.landing_app.TELEMETRY.set_broadcast("", sync_peers=False)
        if hasattr(cls, "operator_app") and hasattr(cls.operator_app, "TELEMETRY"):
            cls.operator_app.TELEMETRY.set_broadcast("", sync_peers=False)

    def test_telemetry_collector_lifecycle(self):
        """Verify TelemetryCollector initialization, recording, and summary aggregation."""
        collector = self.landing_app.TelemetryCollector()
        self.assertGreaterEqual(collector.total_requests, 5)
        self.assertGreater(collector.successful_requests, 0)
        self.assertIn("gemma4:26b", collector.model_counts)
        self.assertIn("coder", collector.persona_counts)

        # Record a new simulated AI request
        collector.record_ai_request(
            session_id="test-session",
            user_id="test-engineer@gdc.local",
            persona="architect",
            model="gemma4:31b",
            latency_ms=750.5,
            success=True,
            status="200 OK (Verified)"
        )

        summary = collector.get_summary()
        self.assertGreaterEqual(summary["total_requests"], 6)
        self.assertGreaterEqual(summary["model_counts"]["gemma4:31b"], 1)
        self.assertGreaterEqual(summary["persona_counts"]["architect"], 1)
        self.assertEqual(summary["recent_events"][0]["session_id"], "test-session")
        self.assertEqual(summary["recent_events"][0]["model"], "gemma4:31b")
        self.assertTrue(summary["success_rate_pct"] > 0)
        self.assertIn("uptime_formatted", summary)
        self.assertIn("total_storage_mb", summary)

    def test_admin_telemetry_html_rendering(self):
        """Verify server-side rendered Admin Telemetry Web UI components and branding."""
        html = self.landing_app.render_admin_telemetry_ui(user_id="admin-secops@gdc.local")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("GDC Developer Platform — Sovereign Admin & Telemetry", html)
        self.assertIn("admin-secops@gdc.local", html)

        # Verify 4-Up KPI stat cards
        self.assertIn("Active Workspaces", html)
        self.assertIn("AI Swarm Invocations", html)
        self.assertIn("Avg Inference Latency", html)
        self.assertIn("PVC Workspace Storage", html)

        # Verify Distribution charts
        self.assertIn("Sovereign AI Model Routing Distribution", html)
        self.assertIn("gemma4:26b", html)
        self.assertIn("gemma4:31b", html)
        self.assertIn("Specialist Agent Persona Utilization", html)
        self.assertIn("Multi-Agent Swarm", html)

        # Verify Tables and Client-side poll script
        self.assertIn("Active Developer Workspaces & Tenancy Allocation", html)
        self.assertIn("Live In-Pod Agentic Inference & Query Feed", html)
        self.assertIn("/admin/telemetry/json", html)
        self.assertIn("/metrics", html)

    def test_prometheus_metrics_format(self):
        """Verify OpenMetrics/Prometheus exposition endpoint text format."""
        prom_text = self.landing_app.generate_prometheus_metrics()
        self.assertIn("# HELP gdc_dev_uptime_seconds", prom_text)
        self.assertIn("# TYPE gdc_dev_uptime_seconds gauge", prom_text)
        self.assertIn("gdc_dev_uptime_seconds", prom_text)

        self.assertIn("# HELP gdc_dev_workspaces_active", prom_text)
        self.assertIn("# TYPE gdc_dev_workspaces_active gauge", prom_text)

        self.assertIn("# HELP gdc_dev_projects_total", prom_text)
        self.assertIn("# TYPE gdc_dev_projects_total gauge", prom_text)

        self.assertIn("# HELP gdc_dev_storage_bytes", prom_text)
        self.assertIn("# TYPE gdc_dev_storage_bytes gauge", prom_text)

        self.assertIn("# HELP gdc_dev_ai_requests_total", prom_text)
        self.assertIn("# TYPE gdc_dev_ai_requests_total counter", prom_text)
        self.assertIn('gdc_dev_ai_requests_total{model="gemma4:26b"}', prom_text)

        self.assertIn("# HELP gdc_dev_ai_persona_requests_total", prom_text)
        self.assertIn('gdc_dev_ai_persona_requests_total{persona="coder"}', prom_text)

        self.assertIn("# HELP gdc_dev_ai_latency_seconds_sum", prom_text)
        self.assertIn("# HELP gdc_dev_ai_latency_seconds_count", prom_text)

    def test_landing_page_and_operator_telemetry_integration(self):
        """Verify both Landing Page and Operator services provide telemetry engines and links."""
        self.assertTrue(hasattr(self.landing_app, "TelemetryCollector"))
        self.assertTrue(hasattr(self.landing_app, "TELEMETRY"))
        self.assertTrue(hasattr(self.landing_app, "generate_prometheus_metrics"))
        self.assertTrue(hasattr(self.landing_app, "render_admin_telemetry_ui"))

        self.assertTrue(hasattr(self.operator_app, "TelemetryCollector"))
        self.assertTrue(hasattr(self.operator_app, "TELEMETRY"))
        self.assertTrue(hasattr(self.operator_app, "generate_prometheus_metrics"))
        self.assertTrue(hasattr(self.operator_app, "render_admin_telemetry_ui"))

        # Verify admin telemetry UI renders Prometheus and export links
        admin_lp_html = self.landing_app.render_admin_telemetry_ui("admin-secops@gdc.local")
        self.assertIn("/metrics", admin_lp_html)
        self.assertIn("Prometheus", admin_lp_html)

        admin_op_html = self.operator_app.render_admin_telemetry_ui("admin-secops@gdc.local")
        self.assertIn("/metrics", admin_op_html)
        self.assertIn("Prometheus", admin_op_html)

    def test_session_termination_and_eviction(self):
        """Verify active session termination, 403 eviction page, and audit logging."""
        collector = self.landing_app.TelemetryCollector()
        collector.register_or_update_session("session-alpha", "dev-alice@gdc.local")
        self.assertFalse(collector.is_session_terminated("session-alpha"))

        # Evict session
        success = collector.terminate_session("session-alpha", reason="Security compliance revocation", admin_user="admin-secops")
        self.assertTrue(success)
        self.assertTrue(collector.is_session_terminated("session-alpha"))
        self.assertEqual(collector.sessions["session-alpha"]["status"], "terminated")
        self.assertEqual(collector.sessions["session-alpha"]["termination_reason"], "Security compliance revocation")
        self.assertEqual(collector.sessions["session-alpha"]["terminated_by"], "admin-secops")

        # Verify audit log recorded eviction
        events = collector.recent_events
        self.assertTrue(any("Session Terminated" in ev.get("status", "") for ev in events))

        # Verify summary stats
        summary = collector.get_summary()
        self.assertGreaterEqual(summary["session_stats"]["terminated"], 1)

        # Verify 403 Forbidden termination eviction page HTML
        html_403 = self.landing_app.render_terminated_session_page(
            "session-alpha",
            reason="Security compliance revocation",
            admin_user="admin-secops"
        )
        self.assertIn("Workspace Session Terminated", html_403)
        self.assertIn("session-alpha", html_403)
        self.assertIn("Security compliance revocation", html_403)
        self.assertIn("admin-secops", html_403)
        self.assertIn("Return to Portal", html_403)

    def test_session_hibernation_and_resumption(self):
        """Verify session hibernation to pause compute and subsequent resumption."""
        collector = self.landing_app.TelemetryCollector()
        collector.register_or_update_session("session-beta", "dev-bob@gdc.local")
        self.assertFalse(collector.is_session_hibernated("session-beta"))

        # Hibernate session
        collector.hibernate_session("session-beta", admin_user="admin-ops")
        self.assertTrue(collector.is_session_hibernated("session-beta"))
        self.assertEqual(collector.sessions["session-beta"]["status"], "hibernated")

        summary_hib = collector.get_summary()
        self.assertGreaterEqual(summary_hib["session_stats"]["hibernated"], 1)

        # Resume session
        resumed = collector.resume_session("session-beta", admin_user="admin-ops")
        self.assertTrue(resumed)
        self.assertFalse(collector.is_session_hibernated("session-beta"))
        self.assertEqual(collector.sessions["session-beta"]["status"], "active")

    def test_cluster_broadcast_announcements(self):
        """Verify cluster-wide announcement banner publishing, getter, and workspace real-time injection."""
        collector = self.landing_app.TelemetryCollector()
        self.assertIsNone(collector.broadcast_banner)
        self.assertIsNone(collector.get_broadcast())

        # Publish broadcast announcement
        banner = collector.set_broadcast("Cluster scheduled upgrade at 23:00 UTC. Save work.", severity="warning", admin_user="admin-cluster")
        self.assertIsNotNone(collector.broadcast_banner)
        self.assertEqual(collector.get_broadcast(), banner)
        self.assertEqual(banner["severity"], "warning")
        self.assertEqual(banner["message"], "Cluster scheduled upgrade at 23:00 UTC. Save work.")

        # Test workspace UI banner injection and real-time polling script
        self.landing_app.TELEMETRY.set_broadcast("Urgent maintenance notice", severity="critical")
        ws_html = self.landing_app.render_workspace_ui("default-workspace", "test-user")
        self.assertIn("cluster-broadcast-container", ws_html)
        self.assertIn("cluster-broadcast-banner", ws_html)
        self.assertIn("data-key=", ws_html)
        self.assertIn("CRITICAL BROADCAST", ws_html)
        self.assertIn("Urgent maintenance notice", ws_html)
        self.assertIn("pollBroadcastAnnouncement", ws_html)
        self.assertIn("/api/broadcast", ws_html)

        # Clear broadcast and verify container remains for live updates while banner is removed
        self.landing_app.TELEMETRY.set_broadcast("")
        self.assertIsNone(self.landing_app.TELEMETRY.broadcast_banner)
        self.assertIsNone(self.landing_app.TELEMETRY.get_broadcast())
        ws_html_cleared = self.landing_app.render_workspace_ui("default-workspace", "test-user")
        self.assertIn('<div id="cluster-broadcast-container"></div>', ws_html_cleared)
        self.assertNotIn('<div id="cluster-broadcast-container"><div id="cluster-broadcast-banner"', ws_html_cleared)
        self.assertIn("pollBroadcastAnnouncement", ws_html_cleared)

        # Verify operator service parity
        op_collector = self.operator_app.TelemetryCollector()
        self.assertIsNone(op_collector.get_broadcast())
        op_banner = op_collector.set_broadcast("Operator notice", severity="info")
        self.assertEqual(op_collector.get_broadcast()["message"], "Operator notice")
        ws_op_html = self.operator_app.render_workspace_ui("default-workspace", "test-user")
        self.assertIn("cluster-broadcast-container", ws_op_html)
        self.assertIn("pollBroadcastAnnouncement", ws_op_html)

    def test_workspace_ui_js_syntax_integrity(self):
        """Verify that render_workspace_ui generates syntactically valid JS without unbalanced braces."""
        import re
        for app in (self.landing_app, self.operator_app):
            html = app.render_workspace_ui("default-workspace", "test-user")
            script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
            self.assertIsNotNone(script_match, "Inline script tag must exist in workspace UI")
            script = script_match.group(1)
            # Ensure try-catch in pollBroadcastAnnouncement is properly formed
            self.assertIn("pollBroadcastAnnouncement", script)
            # Validate brace balance (curly braces must perfectly match and never go negative)
            s_clean = re.sub(r'//.*', '', script)
            s_clean = re.sub(r'/\*.*?\*/', '', s_clean, flags=re.DOTALL)
            curly = 0
            for line in s_clean.splitlines():
                for c in line:
                    if c == '{': curly += 1
                    elif c == '}': curly -= 1
                    self.assertGreaterEqual(curly, 0, f"Unmatched closing brace found in script for {app.__file__}")
            self.assertEqual(curly, 0, f"Unbalanced braces in script for {app.__file__}")

    def test_dynamic_governance_policy_overrides(self):
        """Verify live runtime AI agent reasoning and model tiering governance overrides."""
        collector = self.landing_app.TelemetryCollector()
        pol = collector.set_policy(agent_mode="agentic", default_model="gemma4:31b", approval_policy="strict", admin_user="admin-gov")
        self.assertEqual(pol["agent_mode"], "agentic")
        self.assertEqual(pol["default_model"], "gemma4:31b")
        self.assertEqual(pol["approval_policy"], "strict")

        summary = collector.get_summary()
        self.assertEqual(summary["policy_overrides"]["agent_mode"], "agentic")
        self.assertEqual(summary["policy_overrides"]["default_model"], "gemma4:31b")

    def test_audit_trail_export_and_clearing(self):
        """Verify audit trail JSON summary payload and administrator clearing."""
        collector = self.landing_app.TelemetryCollector()
        summary = collector.get_summary()
        self.assertIn("recent_events", summary)
        self.assertGreater(len(summary["recent_events"]), 0)

        # Verify JSON serializability for export
        json_export = json.dumps(summary)
        self.assertIn("recent_events", json_export)

        # Clear audit events
        collector.clear_events(admin_user="admin-auditor")
        self.assertEqual(len(collector.recent_events), 1)
        self.assertIn("Audit logs cleared", collector.recent_events[0]["status"])

    def test_prometheus_session_gauges(self):
        """Verify OpenMetrics exposition includes active, hibernated, and terminated gauges."""
        prom_text = self.landing_app.generate_prometheus_metrics()
        self.assertIn("# HELP gdc_dev_sessions_active", prom_text)
        self.assertIn("# TYPE gdc_dev_sessions_active gauge", prom_text)
        self.assertIn("gdc_dev_sessions_active", prom_text)

        self.assertIn("# HELP gdc_dev_sessions_hibernated", prom_text)
        self.assertIn("# TYPE gdc_dev_sessions_hibernated gauge", prom_text)
        self.assertIn("gdc_dev_sessions_hibernated", prom_text)

        self.assertIn("# HELP gdc_dev_sessions_terminated", prom_text)
        self.assertIn("# TYPE gdc_dev_sessions_terminated gauge", prom_text)
        self.assertIn("gdc_dev_sessions_terminated", prom_text)

    def test_admin_rbac_context_resolution(self):
        """Verify get_auth_context correctly parses headers, cookies, and roles."""
        # Standard non-admin user via mock headers
        ctx = self.landing_app.get_auth_context({"X-User-ID": "dev-user-1", "X-User-Roles": "dev-user"})
        self.assertFalse(ctx["is_admin"])
        self.assertEqual(ctx["user_id"], "dev-user-1")
        self.assertEqual(ctx["role"], "developer")

        # Admin via X-User-Roles
        ctx_admin = self.landing_app.get_auth_context({"X-User-ID": "admin@gdc.local", "X-User-Roles": "admin,dev-admin"})
        self.assertTrue(ctx_admin["is_admin"])
        self.assertEqual(ctx_admin["user_id"], "admin@gdc.local")
        self.assertEqual(ctx_admin["role"], "admin")

        # Admin via Keycloak X-Forwarded-Groups / Roles
        ctx_oidc = self.landing_app.get_auth_context({"X-Forwarded-User": "cluster-admin@corp.internal", "X-Forwarded-Groups": "gdc-admin,staff"})
        self.assertTrue(ctx_oidc["is_admin"])
        self.assertEqual(ctx_oidc["role"], "admin")

        # Admin via dev_auth_role cookie
        ctx_cookie = self.landing_app.get_auth_context({"Cookie": "dev_auth_user=admin@gdc.local; dev_auth_role=admin"})
        self.assertTrue(ctx_cookie["is_admin"])
        self.assertEqual(ctx_cookie["role"], "admin")

    def test_admin_forbidden_page_rendering(self):
        """Verify render_admin_forbidden_page produces a 403 screen with explanation and login link."""
        html = self.landing_app.render_admin_forbidden_page(user_id="dev-user-1", current_role="dev-user", auth_mode="mock")
        self.assertIn("403 Forbidden: Administrator Role Required", html)
        self.assertIn("dev-user-1", html)
        self.assertIn("/?login=admin", html)
        self.assertIn("DEV-USER", html)

    def test_dual_port_admin_auth_isolation(self):
        """Verify Port 8081 get_admin_auth_context isolates admin sessions from dev cookies."""
        self.assertTrue(hasattr(self.landing_app, "AdminConsoleHandler"))
        self.assertTrue(hasattr(self.landing_app, "get_admin_auth_context"))

        # Unauthenticated visitor on port 8081 defaults strictly to anonymous (no auto-login)
        ctx_default = self.landing_app.get_admin_auth_context({})
        self.assertFalse(ctx_default["is_admin"])
        self.assertEqual(ctx_default["user_id"], "anonymous")
        self.assertEqual(ctx_default["role"], "anonymous")

        # Developer cookie from port 8080 does NOT grant admin access on port 8081
        ctx_with_dev_cookie = self.landing_app.get_admin_auth_context({"Cookie": "dev_auth_user=dev-user-1; dev_auth_role=developer"})
        self.assertFalse(ctx_with_dev_cookie["is_admin"])
        self.assertEqual(ctx_with_dev_cookie["user_id"], "anonymous")

        # Dedicated admin cookie authenticates admin session on port 8081
        ctx_custom_admin = self.landing_app.get_admin_auth_context({"Cookie": "admin_auth_user=secops-lead@gdc.local; admin_auth_role=admin"})
        self.assertTrue(ctx_custom_admin["is_admin"])
        self.assertEqual(ctx_custom_admin["user_id"], "secops-lead@gdc.local")

    def test_realtime_broadcast_http_endpoints(self):
        """Verify unauthenticated GET /api/broadcast and /system/broadcast routes with no-cache headers."""
        import io

        class DummyHandler:
            def __init__(self, path):
                self.path = path
                self.headers = {}
                self.wfile = io.BytesIO()
                self.responses = []
                self.header_dict = {}
            def send_response(self, code):
                self.responses.append(code)
            def send_header(self, k, v):
                self.header_dict[k] = v
            def end_headers(self):
                pass

        # 1. Landing Page Handler (/api/broadcast)
        self.landing_app.TELEMETRY.set_broadcast("Urgent system patching at 02:00", severity="critical", admin_user="secops")
        dummy_lp = DummyHandler("/api/broadcast")
        self.landing_app.LandingPageHandler.do_GET(dummy_lp)
        self.assertEqual(dummy_lp.responses, [200])
        self.assertEqual(dummy_lp.header_dict.get("Content-type"), "application/json")
        self.assertEqual(dummy_lp.header_dict.get("Cache-Control"), "no-cache, no-store, must-revalidate")
        body_lp = json.loads(dummy_lp.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_lp["status"], "ok")
        self.assertEqual(body_lp["broadcast"]["message"], "Urgent system patching at 02:00")
        self.assertEqual(body_lp["broadcast"]["severity"], "critical")

        # 2. Operator Service Handler (/system/broadcast)
        self.operator_app.TELEMETRY.set_broadcast("Session server reload scheduled", severity="warning", admin_user="operator")
        dummy_op = DummyHandler("/system/broadcast")
        self.operator_app.SessionServiceHandler.do_GET(dummy_op)
        self.assertEqual(dummy_op.responses, [200])
        body_op = json.loads(dummy_op.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_op["status"], "ok")
        self.assertEqual(body_op["broadcast"]["message"], "Session server reload scheduled")

        # 3. Dedicated Admin Console Handler (/api/broadcast)
        dummy_admin = DummyHandler("/api/broadcast")
        self.landing_app.AdminConsoleHandler.do_GET(dummy_admin)
        self.assertEqual(dummy_admin.responses, [200])
        body_admin = json.loads(dummy_admin.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_admin["status"], "ok")
        self.assertEqual(body_admin["broadcast"]["message"], "Urgent system patching at 02:00")

        # Clean up
        self.landing_app.TELEMETRY.set_broadcast("")
        self.operator_app.TELEMETRY.set_broadcast("")

    def test_broadcast_post_publication_and_json_error_handling(self):
        """Verify all broadcast POST endpoints return valid JSON and error handlers never return HTML."""
        import io

        class DummyPostHandler:
            def __init__(self, path, body_dict=None, headers=None):
                self.path = path
                self.headers = headers or {}
                raw_body = json.dumps(body_dict if body_dict is not None else {}).encode("utf-8")
                self.rfile = io.BytesIO(raw_body)
                self.wfile = io.BytesIO()
                self.headers["Content-Length"] = str(len(raw_body))
                self.responses = []
                self.header_dict = {}

            def send_response(self, code):
                self.responses.append(code)

            def send_header(self, k, v):
                self.header_dict[k] = v

            def end_headers(self):
                pass

        admin_headers = {
            "Cookie": "admin_auth_user=admin@gdc.local; admin_auth_role=admin; dev_auth_user=admin@gdc.local; dev_auth_role=admin"
        }

        # 1. OperatorHealthHandler (Port 8080) POST handling
        op_h_post = DummyPostHandler(
            "/admin/system/broadcast?v=test",
            {"message": "Cluster-wide upgrade scheduled", "severity": "warning", "sync_peers": False}
        )
        self.operator_app.OperatorHealthHandler.do_POST(op_h_post)
        self.assertEqual(op_h_post.responses, [200])
        self.assertEqual(op_h_post.header_dict.get("Content-type"), "application/json")
        body_op_post = json.loads(op_h_post.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_op_post["status"], "broadcast_updated")
        self.assertEqual(body_op_post["banner"]["message"], "Cluster-wide upgrade scheduled")
        self.assertNotIn("<html", op_h_post.wfile.getvalue().decode("utf-8").lower())

        # 1b. OperatorHealthHandler send_error guarantees JSON (never Python's default HTML)
        dummy_err = DummyPostHandler("/error")
        self.operator_app.OperatorHealthHandler.send_error(dummy_err, 501, "Unsupported method ('POST')")
        self.assertEqual(dummy_err.responses, [501])
        self.assertEqual(dummy_err.header_dict.get("Content-type"), "application/json")
        err_json = json.loads(dummy_err.wfile.getvalue().decode("utf-8"))
        self.assertEqual(err_json["status"], 501)
        self.assertIn("Unsupported", err_json["error"])
        self.assertNotIn("<html", dummy_err.wfile.getvalue().decode("utf-8").lower())

        # 1c. OperatorHealthHandler 404 fallback returns JSON
        dummy_404 = DummyPostHandler("/non-existent-route")
        self.operator_app.OperatorHealthHandler.do_POST(dummy_404)
        self.assertEqual(dummy_404.responses, [404])
        self.assertEqual(dummy_404.header_dict.get("Content-type"), "application/json")
        res_404 = json.loads(dummy_404.wfile.getvalue().decode("utf-8"))
        self.assertEqual(res_404["status"], 404)
        self.assertNotIn("<html", dummy_404.wfile.getvalue().decode("utf-8").lower())

        # 2. AdminConsoleHandler (Port 8081) POST handling with query string
        admin_post = DummyPostHandler(
            "/admin/system/broadcast?nocache=123",
            {"message": "Maintenance window active", "severity": "critical", "sync_peers": False},
            headers=admin_headers
        )
        self.landing_app.AdminConsoleHandler.do_POST(admin_post)
        self.assertEqual(admin_post.responses, [200])
        self.assertEqual(admin_post.header_dict.get("Content-type"), "application/json")
        body_admin_post = json.loads(admin_post.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_admin_post["status"], "broadcast_updated")
        self.assertEqual(body_admin_post["banner"]["message"], "Maintenance window active")
        self.assertEqual(body_admin_post["banner"]["severity"], "critical")
        self.assertNotIn("<html", admin_post.wfile.getvalue().decode("utf-8").lower())

        # 2b. AdminConsoleHandler 404 and send_error JSON validation
        admin_404 = DummyPostHandler("/invalid/route", headers=admin_headers)
        self.landing_app.AdminConsoleHandler.do_POST(admin_404)
        self.assertEqual(admin_404.responses, [404])
        self.assertEqual(admin_404.header_dict.get("Content-type"), "application/json")
        self.assertNotIn("<html", admin_404.wfile.getvalue().decode("utf-8").lower())

        admin_err = DummyPostHandler("/admin/error")
        self.landing_app.AdminConsoleHandler.send_error(admin_err, 500, "Database unreachable")
        self.assertEqual(admin_err.responses, [500])
        self.assertEqual(admin_err.header_dict.get("Content-type"), "application/json")
        err_admin_json = json.loads(admin_err.wfile.getvalue().decode("utf-8"))
        self.assertEqual(err_admin_json["status"], 500)
        self.assertEqual(err_admin_json["error"], "Database unreachable")
        self.assertNotIn("<html", admin_err.wfile.getvalue().decode("utf-8").lower())

        # 3. LandingPageHandler POST broadcast and fallback JSON 404
        lp_post = DummyPostHandler(
            "/system/broadcast",
            {"message": "Landing page notification", "severity": "info", "sync_peers": False},
            headers=admin_headers
        )
        self.landing_app.LandingPageHandler.do_POST(lp_post)
        self.assertEqual(lp_post.responses, [200])
        body_lp_post = json.loads(lp_post.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_lp_post["status"], "ok")
        self.assertNotIn("<html", lp_post.wfile.getvalue().decode("utf-8").lower())

        lp_404 = DummyPostHandler("/non-existent-action", headers=admin_headers)
        self.landing_app.LandingPageHandler.do_POST(lp_404)
        self.assertEqual(lp_404.responses, [404])
        self.assertEqual(lp_404.header_dict.get("Content-type"), "application/json")
        self.assertNotIn("<html", lp_404.wfile.getvalue().decode("utf-8").lower())

        # 4. SessionServiceHandler (Port 3000) POST broadcast and fallback JSON 404
        sess_post = DummyPostHandler(
            "/api/broadcast",
            {"message": "Session service notification", "severity": "info", "sync_peers": False},
            headers=admin_headers
        )
        self.operator_app.SessionServiceHandler.do_POST(sess_post)
        self.assertEqual(sess_post.responses, [200])
        body_sess_post = json.loads(sess_post.wfile.getvalue().decode("utf-8"))
        self.assertEqual(body_sess_post["status"], "ok")
        self.assertNotIn("<html", sess_post.wfile.getvalue().decode("utf-8").lower())

        sess_404 = DummyPostHandler("/non-existent-action", headers=admin_headers)
        self.operator_app.SessionServiceHandler.do_POST(sess_404)
        self.assertEqual(sess_404.responses, [404])
        self.assertEqual(sess_404.header_dict.get("Content-type"), "application/json")
        self.assertNotIn("<html", sess_404.wfile.getvalue().decode("utf-8").lower())

        # Clean up
        self.landing_app.TELEMETRY.set_broadcast("", sync_peers=False)
        self.operator_app.TELEMETRY.set_broadcast("", sync_peers=False)

    def test_strict_port_separation_and_admin_redirection(self):
        """Verify Port 8080/3000 strictly redirect /admin and ?login=admin to Port 8081."""
        import io

        class DummyGetHandler:
            def __init__(self, path, headers=None):
                self.path = path
                self.headers = headers or {}
                self.wfile = io.BytesIO()
                self.responses = []
                self.header_dict = {}
                self.headers_sent = []
            def send_response(self, code):
                self.responses.append(code)
            def send_header(self, k, v):
                self.header_dict[k] = v
                self.headers_sent.append((k, v))
            def end_headers(self):
                pass

        # 1. LandingPageHandler (Port 8080) GET /admin -> 302 redirect to Port 8081
        lp_admin = DummyGetHandler("/admin")
        self.landing_app.LandingPageHandler.do_GET(lp_admin)
        self.assertEqual(lp_admin.responses, [302])
        self.assertIn(":8081/", lp_admin.header_dict.get("Location", ""))

        # 2. LandingPageHandler (Port 8080) GET /admin/telemetry -> 302 redirect to Port 8081
        lp_telem = DummyGetHandler("/admin/telemetry")
        self.landing_app.LandingPageHandler.do_GET(lp_telem)
        self.assertEqual(lp_telem.responses, [302])
        self.assertIn(":8081/", lp_telem.header_dict.get("Location", ""))

        # 3. SessionServiceHandler (Port 3000) GET /admin -> 302 redirect to Port 8081
        sess_admin = DummyGetHandler("/admin")
        self.operator_app.SessionServiceHandler.do_GET(sess_admin)
        self.assertEqual(sess_admin.responses, [302])
        self.assertIn(":8081/", sess_admin.header_dict.get("Location", ""))

        # 4. Port 8080 ?login=admin in mock mode redirects to Port 8081 without granting admin on 8080
        lp_login = DummyGetHandler("/?login=admin")
        self.landing_app.LandingPageHandler.do_GET(lp_login)
        self.assertEqual(lp_login.responses, [302])
        self.assertIn(":8081/?login=admin", lp_login.header_dict.get("Location", ""))
        self.assertFalse(any("dev_auth_role=admin" in v for k, v in lp_login.headers_sent))

        # 5. Port 3000 ?login=admin in mock mode redirects to Port 8081
        sess_login = DummyGetHandler("/?login=admin")
        self.operator_app.SessionServiceHandler.do_GET(sess_login)
        self.assertEqual(sess_login.responses, [302])
        self.assertIn(":8081/?login=admin", sess_login.header_dict.get("Location", ""))

        # 6. Central Portal (/) on Port 8080 links to Port 8081 and has no in-place admin escalation
        lp_root = DummyGetHandler("/")
        self.landing_app.LandingPageHandler.do_GET(lp_root)
        self.assertEqual(lp_root.responses, [200])
        html = lp_root.wfile.getvalue().decode("utf-8")
        self.assertIn("8081", html)
        self.assertNotIn("🔑 Admin Login", html)

    def test_admin_console_logout_and_oidc_relogin(self):
        """Verify Port 8081 /logout sets admin_logged_out cookie, redirects to /login, and supports OIDC re-auth."""
        import io

        class DummyGetHandler:
            def __init__(self, path, headers=None):
                self.path = path
                self.headers = headers or {}
                self.wfile = io.BytesIO()
                self.responses = []
                self.header_dict = {}
                self.headers_sent = []
            def send_response(self, code):
                self.responses.append(code)
            def send_header(self, k, v):
                self.header_dict[k] = v
                self.headers_sent.append((k, v))
            def end_headers(self):
                pass

        # 1. GET /logout on Port 8081 clears admin session, sets admin_logged_out=true, redirects to /login
        d_logout = DummyGetHandler("/logout")
        self.landing_app.AdminConsoleHandler.do_GET(d_logout)
        self.assertEqual(d_logout.responses, [302])
        self.assertEqual(d_logout.header_dict.get("Location"), "/login")
        self.assertTrue(any("admin_logged_out=true" in v for k, v in d_logout.headers_sent))

        # 2. Subsequent GET / with admin_logged_out=true redirects to /login (no infinite loop)
        d_after = DummyGetHandler("/", headers={"Cookie": "admin_logged_out=true"})
        self.landing_app.AdminConsoleHandler.do_GET(d_after)
        self.assertEqual(d_after.responses, [302])
        self.assertEqual(d_after.header_dict.get("Location"), "/login")

        # 3. GET /login renders dedicated Sovereign Admin Sign-In page
        d_login = DummyGetHandler("/login")
        self.landing_app.AdminConsoleHandler.do_GET(d_login)
        self.assertEqual(d_login.responses, [200])
        html_login = d_login.wfile.getvalue().decode("utf-8")
        self.assertIn("Sovereign Admin Sign-In", html_login)
        self.assertIn("/login/oidc", html_login)
        self.assertIn("Sign in as Mock Admin", html_login)

        # 4. GET /login/oidc without headers renders Sovereign Admin OIDC portal
        d_portal = DummyGetHandler("/login/oidc")
        self.landing_app.AdminConsoleHandler.do_GET(d_portal)
        self.assertEqual(d_portal.responses, [200])
        html_portal = d_portal.wfile.getvalue().decode("utf-8")
        self.assertIn("Keycloak OIDC Admin Authentication", html_portal)

        # 5. GET /login/oidc with Admin OIDC identity sets admin cookies and redirects to /
        d_admin_oidc = DummyGetHandler("/login/oidc", headers={
            "X-Forwarded-User": "admin-lead@gdc.local",
            "X-Forwarded-Groups": "sovereign-admin,admin"
        })
        self.landing_app.AdminConsoleHandler.do_GET(d_admin_oidc)
        self.assertEqual(d_admin_oidc.responses, [302])
        self.assertEqual(d_admin_oidc.header_dict.get("Location"), "/")
        self.assertTrue(any("admin_auth_role=admin" in v for k, v in d_admin_oidc.headers_sent))
        self.assertTrue(any("admin_auth_user=admin-lead@gdc.local" in v for k, v in d_admin_oidc.headers_sent))

        # 6. GET /login/oidc with Developer (Non-Admin) OIDC identity returns 403 Forbidden
        d_dev_oidc = DummyGetHandler("/login/oidc", headers={
            "X-Forwarded-User": "dev-user@gdc.local",
            "X-Forwarded-Groups": "developer"
        })
        self.landing_app.AdminConsoleHandler.do_GET(d_dev_oidc)
        self.assertEqual(d_dev_oidc.responses, [403])
        html_403 = d_dev_oidc.wfile.getvalue().decode("utf-8")
        self.assertIn("403 Forbidden: Administrator Role Required", html_403)

    def test_production_oidc_mode_enforcement(self):
        """Verify that under AUTH_MODE=oidc, all mock backdoors and mock buttons are strictly disabled."""
        import io

        class DummyGetHandler:
            def __init__(self, path, headers=None):
                self.path = path
                self.headers = headers or {}
                self.wfile = io.BytesIO()
                self.responses = []
                self.header_dict = {}
                self.headers_sent = []
            def send_response(self, code):
                self.responses.append(code)
            def send_header(self, k, v):
                self.header_dict[k] = v
                self.headers_sent.append((k, v))
            def end_headers(self):
                pass

        old_auth_mode = os.environ.get("AUTH_MODE")
        os.environ["AUTH_MODE"] = "oidc"
        try:
            # 1. Port 8080 ?login=admin in OIDC mode redirects to /login/oidc (mock backdoor blocked)
            d_lp_mock = DummyGetHandler("/?login=admin")
            self.landing_app.LandingPageHandler.do_GET(d_lp_mock)
            self.assertEqual(d_lp_mock.responses, [302])
            self.assertEqual(d_lp_mock.header_dict.get("Location"), "/login/oidc")

            # 2. Port 8080 ?login=dev in OIDC mode redirects to /login/oidc
            d_lp_dev = DummyGetHandler("/?login=dev")
            self.landing_app.LandingPageHandler.do_GET(d_lp_dev)
            self.assertEqual(d_lp_dev.responses, [302])
            self.assertEqual(d_lp_dev.header_dict.get("Location"), "/login/oidc")

            # 3. Port 8081 ?login=admin in OIDC mode redirects to /login/oidc
            d_admin_mock = DummyGetHandler("/?login=admin")
            self.landing_app.AdminConsoleHandler.do_GET(d_admin_mock)
            self.assertEqual(d_admin_mock.responses, [302])
            self.assertEqual(d_admin_mock.header_dict.get("Location"), "/login/oidc")

            # 4. Port 8081 /login in OIDC mode does NOT contain mock login options
            d_login_oidc = DummyGetHandler("/login")
            self.landing_app.AdminConsoleHandler.do_GET(d_login_oidc)
            self.assertEqual(d_login_oidc.responses, [200])
            html_login = d_login_oidc.wfile.getvalue().decode("utf-8")
            self.assertNotIn("Sign in as Mock Admin", html_login)
            self.assertIn("Keycloak OIDC", html_login)

            # 5. Port 8081 unauthenticated visitor redirects to /login
            d_root = DummyGetHandler("/")
            self.landing_app.AdminConsoleHandler.do_GET(d_root)
            self.assertEqual(d_root.responses, [302])
            self.assertEqual(d_root.header_dict.get("Location"), "/login")

            # 6. Port 8081 forged cookies without OIDC headers are ignored and treated as unauthenticated
            d_forged = DummyGetHandler("/", headers={"Cookie": "admin_auth_user=admin@gdc.local; admin_auth_role=admin"})
            self.landing_app.AdminConsoleHandler.do_GET(d_forged)
            self.assertEqual(d_forged.responses, [302])
            self.assertEqual(d_forged.header_dict.get("Location"), "/login")
        finally:
            if old_auth_mode is not None:
                os.environ["AUTH_MODE"] = old_auth_mode
            else:
                os.environ.pop("AUTH_MODE", None)

    def test_oidc_end_to_end_login_and_workspace_redirection(self):
        """Verify Sovereign Admin OIDC login, Developer Console OIDC login, and direct workspace redirection."""
        import io

        class DummyGetHandler:
            def __init__(self, path, headers=None):
                self.path = path
                self.headers = headers or {}
                self.wfile = io.BytesIO()
                self.responses = []
                self.header_dict = {}
                self.headers_sent = []
            def send_response(self, code):
                self.responses.append(code)
            def send_header(self, k, v):
                self.header_dict[k] = v
                self.headers_sent.append((k, v))
            def end_headers(self):
                pass

        old_auth_mode = os.environ.get("AUTH_MODE")
        os.environ["AUTH_MODE"] = "oidc"
        try:
            # 1. Sovereign Admin Console (Port 8081): /login links directly to /login/oidc?simulated=admin
            d_login = DummyGetHandler("/login")
            self.landing_app.AdminConsoleHandler.do_GET(d_login)
            self.assertEqual(d_login.responses, [200])
            html_admin_login = d_login.wfile.getvalue().decode("utf-8")
            self.assertIn('/login/oidc?simulated=admin', html_admin_login)

            # 2. Sovereign Admin Console: clicking OIDC button authenticates as cluster-admin and redirects to /
            d_admin_btn = DummyGetHandler("/login/oidc?simulated=admin")
            self.landing_app.AdminConsoleHandler.do_GET(d_admin_btn)
            self.assertEqual(d_admin_btn.responses, [302])
            self.assertEqual(d_admin_btn.header_dict.get("Location"), "/")
            admin_cookies = "; ".join(v.split(";")[0] for k, v in d_admin_btn.headers_sent if k == "Set-Cookie")
            self.assertIn("admin_auth_user=cluster-admin@gdc.local", admin_cookies)

            # 3. Sovereign Admin Console: GET / with cluster-admin cookie grants full admin access (no 302 loop)
            d_admin_root = DummyGetHandler("/", headers={"Cookie": admin_cookies})
            self.landing_app.AdminConsoleHandler.do_GET(d_admin_root)
            self.assertEqual(d_admin_root.responses, [200])
            html_admin_root = d_admin_root.wfile.getvalue().decode("utf-8")
            self.assertIn("Sovereign Admin & Telemetry", html_admin_root)
            self.assertIn("cluster-admin@gdc.local", html_admin_root)

            # 4. Developer Console (Port 8080): unauthenticated GET / renders Keycloak SSO portal (no mock card)
            d_dev_anon = DummyGetHandler("/")
            self.landing_app.LandingPageHandler.do_GET(d_dev_anon)
            self.assertEqual(d_dev_anon.responses, [200])
            html_dev_anon = d_dev_anon.wfile.getvalue().decode("utf-8")
            self.assertIn("Sign in with Keycloak OIDC", html_dev_anon)
            self.assertIn("gdc-dev-realm", html_dev_anon)
            self.assertNotIn("Launch Developer Workspace", html_dev_anon)

            # 5. Developer Console: /login/oidc sets oidc-developer cookies and redirects to workspace
            d_dev_login = DummyGetHandler("/login/oidc")
            self.landing_app.LandingPageHandler.do_GET(d_dev_login)
            self.assertEqual(d_dev_login.responses, [302])
            self.assertEqual(d_dev_login.header_dict.get("Location"), "/instances/default-workspace?oidc_login=success")
            dev_cookies = "; ".join(v.split(";")[0] for k, v in d_dev_login.headers_sent if k == "Set-Cookie")
            self.assertIn("dev_auth_user=oidc-developer@gdc.local", dev_cookies)

            # 6. Developer Console: GET / when authenticated redirects directly to /instances/default-workspace
            d_dev_auth = DummyGetHandler("/", headers={"Cookie": dev_cookies})
            self.landing_app.LandingPageHandler.do_GET(d_dev_auth)
            self.assertEqual(d_dev_auth.responses, [302])
            self.assertEqual(d_dev_auth.header_dict.get("Location"), "/instances/default-workspace")

            # 7. Developer Console: GET /?logout=true sets dev_logged_out=true
            d_dev_logout = DummyGetHandler("/?logout=true", headers={"Cookie": dev_cookies})
            self.landing_app.LandingPageHandler.do_GET(d_dev_logout)
            self.assertEqual(d_dev_logout.responses, [302])
            dev_logout_cookies = "; ".join(v.split(";")[0] for k, v in d_dev_logout.headers_sent if k == "Set-Cookie")
            self.assertIn("dev_logged_out=true", dev_logout_cookies)

            # 8. Developer Console: GET / after logout renders login portal without auto-logging in
            d_dev_logged_out = DummyGetHandler("/", headers={"Cookie": dev_logout_cookies})
            self.landing_app.LandingPageHandler.do_GET(d_dev_logged_out)
            self.assertEqual(d_dev_logged_out.responses, [200])
            html_dev_logged_out = d_dev_logged_out.wfile.getvalue().decode("utf-8")
            self.assertIn("Sign in with Keycloak OIDC", html_dev_logged_out)
        finally:
            if old_auth_mode is not None:
                os.environ["AUTH_MODE"] = old_auth_mode
            else:
                os.environ.pop("AUTH_MODE", None)


if __name__ == "__main__":
    unittest.main()
