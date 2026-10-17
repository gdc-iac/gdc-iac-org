#!/usr/bin/env python3
"""
@file test_phase4_swarm.py
@brief Validation suite for Pattern 13: Phase 4 Multi-Agent Swarm Specialization on GDC Air-Gapped.

@details Validates:
1. gdc-dev-agent-config ConfigMap swarm configuration keys.
2. Helm values-gdc-phase3.yaml swarm specification.
3. SWARM_PERSONAS definitions (Architect, Coder, Reviewer, Swarm Coordinator).
4. Least-privilege tool access boundaries for each specialized agent.
5. handle_ai_chat persona selection and role response payload.
6. Workspace UI rendering of the Swarm Specialist selector.

@date 2026-09-03
"""

import os
import sys
import unittest
import json
import importlib.util

class TestGdcDevPhase4Swarm(unittest.TestCase):
    """Phase 4 Multi-Agent Swarm Specialization Tests."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.manifest_dir = os.path.join(self.base_dir, "manifests", "gdc")

    def test_swarm_configmap_declarations(self):
        """Verify gdc-dev-agent-config ConfigMap includes swarm configuration."""
        config_file = os.path.join(self.manifest_dir, "gdc-dev-agent-configmap.yaml")
        self.assertTrue(os.path.isfile(config_file), f"Missing manifest: {config_file}")
        with open(config_file, "r") as f:
            content = f.read()

        self.assertIn('AI_SWARM_ENABLED: "true"', content)
        self.assertIn('AI_SWARM_ROLES: "architect,coder,reviewer"', content)
        self.assertIn('AI_DEFAULT_ROLE: "swarm"', content)

    def test_swarm_helm_values_schema(self):
        """Verify values-gdc-phase3.yaml includes swarm roles configuration."""
        values_file = os.path.join(self.manifest_dir, "values-gdc-phase3.yaml")
        with open(values_file, "r") as f:
            content = f.read()

        self.assertIn("swarm:", content)
        self.assertIn("enabled: true", content)
        self.assertIn('defaultRole: "swarm"', content)
        self.assertIn("architect", content)
        self.assertIn("coder", content)
        self.assertIn("reviewer", content)

    def test_swarm_personas_structure(self):
        """Verify SWARM_PERSONAS has all required roles and attributes."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        personas = getattr(landing_app, "SWARM_PERSONAS", {})
        self.assertIn("architect", personas)
        self.assertIn("coder", personas)
        self.assertIn("reviewer", personas)
        self.assertIn("swarm", personas)

        for role, p in personas.items():
            self.assertIn("name", p)
            self.assertIn("system_prompt", p)
            self.assertIn("tools", p)
            self.assertIn("badge", p)

    def test_persona_tool_least_privilege(self):
        """Verify each agent role adheres to least-privilege tool isolation."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        personas = getattr(landing_app, "SWARM_PERSONAS", {})
        
        # Architect: Read-only planning & directory scaffolding
        arch_tools = personas["architect"]["tools"]
        self.assertIn("read_file", arch_tools)
        self.assertIn("list_directory", arch_tools)
        self.assertIn("create_directory", arch_tools)
        self.assertNotIn("apply_diff", arch_tools)
        self.assertNotIn("run_terminal_command", arch_tools)

        # Coder: Code mutation & patching
        coder_tools = personas["coder"]["tools"]
        self.assertIn("read_file", coder_tools)
        self.assertIn("write_file", coder_tools)
        self.assertIn("apply_diff", coder_tools)
        self.assertIn("create_directory", coder_tools)
        self.assertNotIn("run_terminal_command", coder_tools)

        # Reviewer: Terminal testing & verification
        rev_tools = personas["reviewer"]["tools"]
        self.assertIn("read_file", rev_tools)
        self.assertIn("run_terminal_command", rev_tools)
        self.assertNotIn("apply_diff", rev_tools)
        self.assertNotIn("write_file", rev_tools)
        self.assertNotIn("create_directory", rev_tools)

        # Swarm Coordinator: Full access
        swarm_tools = personas["swarm"]["tools"]
        self.assertEqual(len(swarm_tools), 6)
        self.assertIn("create_directory", swarm_tools)

    def test_handle_ai_chat_role_routing(self):
        """Verify handle_ai_chat returns appropriate role and agent_name."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        # Test role response metadata
        for role in ["architect", "coder", "reviewer", "swarm"]:
            req = {
                "prompt": "Create unit tests for primes.py",
                "role": role,
                "model": "gemma4:31b"
            }
            res = landing_app.handle_ai_chat(json.dumps(req), "test-user")
            self.assertEqual(res.get("role"), role)
            self.assertIn(role.capitalize() if role != "swarm" else "Swarm", res.get("agent_name"))

    def test_workspace_ui_renders_swarm_role_selector(self):
        """Verify render_workspace_ui renders the agent role dropdown and badges."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        os.environ["AI_ENABLED"] = "true"
        os.environ["AI_AGENT_MODE"] = "agentic"
        os.environ["AI_DEFAULT_ROLE"] = "swarm"
        
        html = landing_app.render_workspace_ui("test-session", "dev-user")
        self.assertIn('id="ai-agent-role"', html)
        self.assertIn('value="swarm"', html)
        self.assertIn('value="architect"', html)
        self.assertIn('value="coder"', html)
        self.assertIn('value="reviewer"', html)
        self.assertIn("ai-badge-swarm", html)

    def test_workspace_ui_renders_personas_and_models_by_default(self):
        """Verify render_workspace_ui renders persona selector and model selector by default even if AI_ENABLED is unset."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app_default", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        old_val = os.environ.pop("AI_ENABLED", None)
        try:
            html = landing_app.render_workspace_ui("test-session-default", "dev-user")
            self.assertIn('id="ai-agent-role"', html, "Persona selector must render by default")
            self.assertIn('id="ai-model-selector"', html, "Model selector must render by default")
            self.assertIn('value="swarm"', html)
            self.assertIn('value="architect"', html)
            self.assertIn('value="coder"', html)
            self.assertIn('value="reviewer"', html)
            self.assertIn('gemma4:31b', html)
            self.assertIn('gemma4:26b', html)
        finally:
            if old_val is not None:
                os.environ["AI_ENABLED"] = old_val

    def test_workspace_ui_terminal_and_ai_resizers(self):
        """Verify workspace UI renders dynamic resizers for terminal height and AI panel width."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        # 1. When AI is enabled: both terminal resizer and AI resizer must be present
        os.environ["AI_ENABLED"] = "true"
        html = landing_app.render_workspace_ui("test-session", "dev-user")
        self.assertIn('id="terminal-resizer"', html)
        self.assertIn('class="terminal-resizer"', html)
        self.assertIn('setTerminalHeight(', html)
        self.assertIn('toggleTerminalMaximize()', html)
        self.assertIn('id="btn-term-max"', html)
        self.assertIn('id="ai-resizer"', html)
        self.assertIn('class="ai-resizer"', html)
        self.assertIn('setAiWidth(', html)
        self.assertIn('toggleAiMaximize()', html)
        self.assertIn('id="btn-ai-max"', html)

        # 2. When AI is disabled: terminal resizer is present, but AI resizer is omitted
        os.environ["AI_ENABLED"] = "false"
        html_no_ai = landing_app.render_workspace_ui("test-session", "dev-user")
        self.assertIn('id="terminal-resizer"', html_no_ai)
        self.assertNotIn('id="ai-resizer"', html_no_ai)

    def test_workspace_file_management_and_templates(self):
        """Verify workspace disk persistence, file deletion, and project reset templates."""
        import tempfile
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        with tempfile.TemporaryDirectory() as tmp_ws:
            # 1. Test PROJECT_TEMPLATES existence
            templates = getattr(landing_app, "PROJECT_TEMPLATES", {})
            self.assertIn("telemetry", templates)
            self.assertIn("microservice", templates)
            self.assertIn("clean", templates)

            # 2. Test reset_project
            files = landing_app.reset_project("telemetry", workspace_dir=tmp_ws)
            self.assertIn("main.py", files)
            self.assertIn("telemetry.py", files)
            self.assertIn("test_telemetry.py", files)
            self.assertTrue(os.path.exists(os.path.join(tmp_ws, "telemetry.py")))

            # 3. Test load_workspace_files
            loaded = landing_app.load_workspace_files(workspace_dir=tmp_ws)
            self.assertIn("main.py", loaded)
            self.assertIn("telemetry.py", loaded)

            # 4. Test execute_tool write_file and read_file on disk
            test_files = {}
            success, write_msg = landing_app.execute_tool("write_file", {"path": "architecture.md", "content": "# Architecture Spec\n"}, test_files, workspace_dir=tmp_ws)
            self.assertTrue(success)
            self.assertIn("architecture.md", write_msg)
            self.assertTrue(os.path.exists(os.path.join(tmp_ws, "architecture.md")))

            read_success, read_res = landing_app.execute_tool("read_file", {"path": "architecture.md"}, test_files, workspace_dir=tmp_ws)
            self.assertTrue(read_success)
            self.assertIn("# Architecture Spec", read_res)

            # 5. Test UI elements
            html = landing_app.render_workspace_ui("test-session", "dev-user")
            self.assertIn("refreshFiles()", html)
            self.assertIn("showNewProjectModal()", html)
            self.assertIn("deleteFile(", html)
            self.assertIn("saveCode()", html)
            self.assertIn("new-project-modal", html)

    def test_multi_project_lifecycle_and_switching(self):
        """Verify multi-project directory isolation, listing, creation, switching, and deletion."""
        import tempfile
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        with tempfile.TemporaryDirectory() as tmp_root:
            orig_ws = landing_app.WORKSPACE_ROOT
            orig_projects = landing_app.PROJECTS_ROOT
            landing_app.WORKSPACE_ROOT = os.path.join(tmp_root, "workspace")
            landing_app.PROJECTS_ROOT = os.path.join(tmp_root, "dev-projects")
            try:
                # 1. Verify get_workspace_dir mapping
                def_dir = landing_app.get_workspace_dir("default-workspace")
                self.assertEqual(def_dir, landing_app.WORKSPACE_ROOT)

                custom_dir = landing_app.get_workspace_dir("telemetry-service")
                self.assertEqual(custom_dir, os.path.join(landing_app.PROJECTS_ROOT, "telemetry-service"))
                self.assertTrue(os.path.isdir(custom_dir))

                # 2. Populate default-workspace and custom project
                landing_app.reset_project("clean", workspace_dir=def_dir)
                landing_app.reset_project("telemetry", workspace_dir=custom_dir)

                # 3. Test list_projects
                projects = landing_app.list_projects()
                proj_names = [p["name"] for p in projects]
                self.assertIn("default-workspace", proj_names)
                self.assertIn("telemetry-service", proj_names)

                custom_p = next(p for p in projects if p["name"] == "telemetry-service")
                self.assertIn("telemetry.py", custom_p["files"])
                self.assertEqual(custom_p["file_count"], len(custom_p["files"]))

                # 4. Test delete_project for custom project
                del_ok, del_msg = landing_app.delete_project("telemetry-service")
                self.assertTrue(del_ok)
                self.assertFalse(os.path.exists(custom_dir))

                projects_after = landing_app.list_projects()
                proj_names_after = [p["name"] for p in projects_after]
                self.assertNotIn("telemetry-service", proj_names_after)

                # 5. Test UI elements for Project Switching
                html = landing_app.render_workspace_ui("telemetry-service", "dev-user")
                self.assertIn('id="header-project-select"', html)
                self.assertIn("switchProject(", html)
                self.assertIn("fetchProjects()", html)
                self.assertIn("createNewProject()", html)
                self.assertIn("deleteProject(", html)
                self.assertIn("tab-btn-switch", html)
                self.assertIn("tab-btn-create", html)
                self.assertIn("tab-btn-reset", html)
                self.assertIn("dev@gdc-session:~/telemetry-service$", html)
            finally:
                landing_app.WORKSPACE_ROOT = orig_ws
                landing_app.PROJECTS_ROOT = orig_projects

    def test_operator_multi_project_parity(self):
        """Verify operator app.py maintains feature parity for multi-project management."""
        app_path = os.path.join(self.base_dir, "example-app", "operator", "app.py")
        spec = importlib.util.spec_from_file_location("operator_app", app_path)
        operator_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(operator_app)

        self.assertTrue(hasattr(operator_app, "PROJECTS_ROOT"))
        self.assertTrue(hasattr(operator_app, "get_workspace_dir"))
        self.assertTrue(hasattr(operator_app, "list_projects"))
        self.assertTrue(hasattr(operator_app, "delete_project"))

        html = operator_app.render_workspace_ui("billing-service", "dev-user")
        self.assertIn('id="header-project-select"', html)
        self.assertIn("switchProject(", html)
        self.assertIn("dev@gdc-session:~/billing-service$", html)

    def test_save_as_file_and_full_output_actions(self):
        """Verify UI script renders Save as File and Copy All actions for full output preservation."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        os.environ["AI_ENABLED"] = "true"
        os.environ["AI_AGENT_MODE"] = "agentic"

        html = landing_app.render_workspace_ui("default-workspace", "dev-user")
        self.assertIn("saveResponseAsFile(", html)
        self.assertIn("💾 Save as File", html)
        self.assertIn("📋 Copy All", html)
        self.assertIn("architecture.md", html)


    def test_oidc_session_cookie_persistence(self):
        """Verify OIDC authentication state persists via cookies and across project URLs."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        html = landing_app.render_workspace_ui("default-workspace", "oidc-developer@gdc.local")
        self.assertIn("dev_auth_user", html)
        self.assertIn("oidc_login=success", html)
        self.assertIn("Exit Session", html)
        self.assertIn("/?logout=true", html)

    def test_dockerfile_tooling_declarations(self):
        """Verify Dockerfiles declare pre-baked tooling (git, kubectl, helm, docker-cli, gdcloud)."""
        landing_df = os.path.join(self.base_dir, "example-app", "landing-page", "Dockerfile")
        workspace_df = os.path.join(self.base_dir, "example-app", "workspace", "Dockerfile")

        self.assertTrue(os.path.isfile(landing_df), f"Missing Dockerfile: {landing_df}")
        self.assertTrue(os.path.isfile(workspace_df), f"Missing Dockerfile: {workspace_df}")

        with open(landing_df, "r") as f:
            landing_content = f.read()
        with open(workspace_df, "r") as f:
            workspace_content = f.read()

        # Both Dockerfiles must include core tools
        for content in (landing_content, workspace_content):
            self.assertIn("git", content)
            self.assertIn("kubectl", content)
            self.assertIn("helm", content)
            self.assertIn("docker", content)
            self.assertIn("gdcloud", content)
            self.assertIn("safe.directory", content)
            self.assertIn("HELM_CONFIG_HOME", content)
            self.assertIn("GDCLOUD_CONFIG_DIR", content)
            self.assertIn("USER 1000", content)

        # Workspace Dockerfile must include rootless Podman and Buildah, and exclude deprecated Kaniko
        self.assertIn("podman", workspace_content)
        self.assertIn("buildah", workspace_content)
        self.assertIn("fuse-overlayfs", workspace_content)
        self.assertNotIn("kaniko", workspace_content)

    def test_landing_page_service_account_binding(self):
        """Verify landing page deployment assigns serviceAccountName for in-cluster kubectl API access."""
        p3_deploy = os.path.join(self.manifest_dir, "gdc-dev-phase3-deployment.yaml")
        op_deploy = os.path.join(self.manifest_dir, "gdc-dev-operator.yaml")

        for f_path in (p3_deploy, op_deploy):
            with open(f_path, "r") as f:
                content = f.read()
            self.assertIn("serviceAccountName: gdc-dev-operator-sa", content)

    def test_architect_persona_read_only_confinement(self):
        """Verify Architect Agent strictly enforces read-only confinement and never returns waiting_for_approval."""
        from unittest.mock import patch, MagicMock

        for app_subdir, mod_name in [("landing-page", "landing_app_arch"), ("operator", "operator_app_arch")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            # Turn 1 tool call test: LLM attempts apply_diff
            mock_resp_t1 = MagicMock()
            mock_resp_t1.read.return_value = json.dumps({
                "choices": [{
                    "message": {
                        "content": "Designing caching architecture.",
                        "tool_calls": [{
                            "function": {
                                "name": "apply_diff",
                                "arguments": json.dumps({
                                    "path": "cache.py",
                                    "target_block": "",
                                    "replacement_block": "class RedisCache:\n    pass\n"
                                })
                            }
                        }]
                    }
                }]
            }).encode("utf-8")

            mock_opener_t1 = MagicMock()
            mock_opener_t1.open.return_value.__enter__.return_value = mock_resp_t1

            req_payload = {
                "prompt": "Design caching subsystem for Redis",
                "role": "architect",
                "files": {}
            }

            with patch.dict(os.environ, {"AI_AGENT_MODE": "agentic"}):
                with patch.object(app_mod, "AI_OPENER", mock_opener_t1):
                    res = app_mod.handle_ai_chat(json.dumps(req_payload), "test-user")
                    self.assertEqual(res.get("status"), "complete", f"{app_subdir} must return complete, not waiting_for_approval")
                    self.assertEqual(res.get("role"), "architect")
                    self.assertIn("Architectural Design Specification", res.get("reply", ""))
                    self.assertIn("RedisCache", res.get("reply", ""))
                    self.assertIn("Save as File", res.get("reply", ""))

            # Turn 2 tool call test: Turn 1 read_file -> Turn 2 attempts apply_diff
            mock_resp1 = MagicMock()
            mock_resp1.read.return_value = json.dumps({
                "choices": [{
                    "message": {
                        "content": "Inspecting context.",
                        "tool_calls": [{
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "main.py"})
                            }
                        }]
                    }
                }]
            }).encode("utf-8")

            mock_resp2 = MagicMock()
            mock_resp2.read.return_value = json.dumps({
                "choices": [{
                    "message": {
                        "content": "Synthesizing cache architecture.",
                        "tool_calls": [{
                            "function": {
                                "name": "apply_diff",
                                "arguments": json.dumps({
                                    "path": "cache.py",
                                    "target_block": "",
                                    "replacement_block": "class MemoryCache:\n    pass\n"
                                })
                            }
                        }]
                    }
                }]
            }).encode("utf-8")

            mock_opener_t2 = MagicMock()
            mock_opener_t2.open.return_value.__enter__.side_effect = [mock_resp1, mock_resp2]

            with patch.dict(os.environ, {"AI_AGENT_MODE": "agentic"}):
                with patch.object(app_mod, "AI_OPENER", mock_opener_t2):
                    res2 = app_mod.handle_ai_chat(json.dumps(req_payload), "test-user")
                    self.assertEqual(res2.get("status"), "complete", f"{app_subdir} ReAct Turn 2 must return complete")
                    self.assertEqual(res2.get("role"), "architect")
                    self.assertIn("MemoryCache", res2.get("reply", ""))
                    self.assertIn("Save as File", res2.get("reply", ""))

    def test_reviewer_persona_test_synthesis(self):
        """Verify Reviewer Agent intercepts main.py execution proposals during test synthesis and generates pytest suites."""
        from unittest.mock import patch, MagicMock

        for app_subdir, mod_name in [("landing-page", "landing_app_rev"), ("operator", "operator_app_rev")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            # Case 1: LLM proposes run_terminal_command: python3 main.py when asked to synthesize pytest suite
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "function": {
                                "name": "run_terminal_command",
                                "arguments": json.dumps({"command": "python3 main.py"})
                            }
                        }]
                    }
                }]
            }).encode("utf-8")

            mock_opener = MagicMock()
            mock_opener.open.return_value.__enter__.return_value = mock_resp

            req_payload = {
                "prompt": "Synthesize a pytest suite for get_ttl_seconds in test_main.py",
                "role": "reviewer",
                "filename": "main.py",
                "files": {}
            }

            with patch.dict(os.environ, {"AI_AGENT_MODE": "agentic"}):
                with patch.object(app_mod, "AI_OPENER", mock_opener):
                    res = app_mod.handle_ai_chat(json.dumps(req_payload), "test-user")
                    self.assertEqual(res.get("status"), "complete", f"{app_subdir} test synthesis must intercept main execution and return complete")
                    self.assertEqual(res.get("role"), "reviewer")
                    self.assertIn("pytest", res.get("reply", "").lower())
                    self.assertIn("@pytest.fixture", res.get("reply", ""))
                    self.assertIn("get_ttl_seconds", res.get("reply", ""))
                    self.assertIn("Save as File", res.get("reply", ""))

            # Case 2: LLM proposes run_terminal_command: pytest test_main.py when explicitly asked to run tests
            mock_resp_exec = MagicMock()
            mock_resp_exec.read.return_value = json.dumps({
                "choices": [{
                    "message": {
                        "content": "Running test suite.",
                        "tool_calls": [{
                            "function": {
                                "name": "run_terminal_command",
                                "arguments": json.dumps({"command": "pytest test_main.py"})
                            }
                        }]
                    }
                }]
            }).encode("utf-8")

            mock_opener_exec = MagicMock()
            mock_opener_exec.open.return_value.__enter__.return_value = mock_resp_exec

            req_payload_exec = {
                "prompt": "Run pytest test_main.py",
                "role": "reviewer",
                "filename": "test_main.py",
                "files": {}
            }

            with patch.dict(os.environ, {"AI_AGENT_MODE": "agentic"}):
                with patch.object(app_mod, "AI_OPENER", mock_opener_exec):
                    res_exec = app_mod.handle_ai_chat(json.dumps(req_payload_exec), "test-user")
                    self.assertEqual(res_exec.get("status"), "waiting_for_approval", f"{app_subdir} test execution must require approval")
                    self.assertEqual(res_exec.get("tool"), "run_terminal_command")
                    self.assertIn("pytest test_main.py", res_exec.get("diff_preview", ""))

            # Case 3: LLM proposes run_terminal_command: pytest test_main.py when asked to synthesize (must intercept)
            mock_resp_synth_pytest = MagicMock()
            mock_resp_synth_pytest.read.return_value = json.dumps({
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "function": {
                                "name": "run_terminal_command",
                                "arguments": json.dumps({"command": "pytest test_main.py"})
                            }
                        }]
                    }
                }]
            }).encode("utf-8")

            mock_opener_sp = MagicMock()
            mock_opener_sp.open.return_value.__enter__.return_value = mock_resp_synth_pytest

            with patch.dict(os.environ, {"AI_AGENT_MODE": "agentic"}):
                with patch.object(app_mod, "AI_OPENER", mock_opener_sp):
                    res_sp = app_mod.handle_ai_chat(json.dumps(req_payload), "test-user")
                    self.assertEqual(res_sp.get("status"), "complete", f"{app_subdir} test synthesis must intercept any terminal command")
                    self.assertEqual(res_sp.get("role"), "reviewer")
                    self.assertIn("pytest", res_sp.get("reply", "").lower())
                    self.assertIn("get_ttl_seconds", res_sp.get("reply", ""))

            # Case 4: Reviewer asked to synthesize test_cache.py
            req_payload_cache = {
                "prompt": "Synthesize a pytest suite for CacheService in test_cache.py",
                "role": "reviewer",
                "filename": "cache.py",
                "files": {}
            }
            with patch.dict(os.environ, {"AI_AGENT_MODE": "agentic"}):
                with patch.object(app_mod, "AI_OPENER", mock_opener_sp):
                    res_cache = app_mod.handle_ai_chat(json.dumps(req_payload_cache), "test-user")
                    self.assertEqual(res_cache.get("status"), "complete")
                    self.assertIn("CacheService", res_cache.get("reply", ""))
                    self.assertIn("test_cache.py", res_cache.get("reply", ""))

    def test_sanitize_python_code_self_attr_healing(self):
        """Verify sanitize_python_code automatically heals missing dot in self <attr> (e.g. self cache.set)."""
        for app_subdir, mod_name in [("landing-page", "landing_app_heal"), ("operator", "operator_app_heal")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            broken_code = "def test_foo(self):\n    self cache.set('k', 123)\n    self storage.get('k')\n    assert self is not None\n    return self if ok else None\n"
            healed = app_mod.sanitize_python_code(broken_code)
            self.assertIn("self.cache.set('k', 123)", healed)
            self.assertIn("self.storage.get('k')", healed)
            self.assertIn("assert self is not None", healed)
            self.assertIn("return self if ok else None", healed)


    def test_save_file_endpoint_resilience(self):
        """Verify POST /files/save and /instances/<sid>/files/save save files correctly, reject GET with 405, and handle edge cases."""
        import io
        for app_subdir, handler_name in [("landing-page", "LandingPageHandler"), ("operator", "SessionServiceHandler")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(f"{app_subdir}_test_save", app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            HandlerClass = getattr(app_mod, handler_name)

            class MockReq:
                def __init__(self, path, body=b"", headers=None):
                    self.path = path
                    self.rfile = io.BytesIO(body if isinstance(body, bytes) else body.encode("utf-8"))
                    self.wfile = io.BytesIO()
                    self.headers = headers or {"Content-Length": str(len(body)), "Content-Type": "application/json"}
                    self.response_code = None
                    self.response_headers = {}

                def send_response(self, code):
                    self.response_code = code

                def send_header(self, k, v):
                    self.response_headers[k] = v

                def end_headers(self):
                    pass

            # 1. Primary path POST /instances/default-workspace/files/save
            save_payload = json.dumps({"filename": "cache.py", "content": "class ModularCache:\n    pass\n"})
            req1 = MockReq("/instances/default-workspace/files/save", save_payload)
            HandlerClass.do_POST(req1)
            self.assertEqual(req1.response_code, 200, f"{app_subdir} primary save endpoint failed")
            self.assertEqual(req1.response_headers.get("Content-type"), "application/json")
            res1 = json.loads(req1.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res1.get("status"), "ok")
            self.assertEqual(res1.get("filename"), "cache.py")

            # 2. Fallback path POST /files/save
            req2 = MockReq("/files/save", save_payload)
            HandlerClass.do_POST(req2)
            self.assertEqual(req2.response_code, 200, f"{app_subdir} fallback save endpoint failed")
            self.assertEqual(req2.response_headers.get("Content-type"), "application/json")

            # 3. Double-slash resilience POST /instances//files/save
            req3 = MockReq("/instances//files/save", save_payload)
            HandlerClass.do_POST(req3)
            self.assertEqual(req3.response_code, 200, f"{app_subdir} double-slash save endpoint failed")

            # 4. Rejection of GET on mutation endpoints with HTTP 405 JSON
            req4 = MockReq("/instances/default-workspace/files/save")
            HandlerClass.do_GET(req4)
            self.assertEqual(req4.response_code, 405, f"{app_subdir} GET /files/save should return 405")
            self.assertEqual(req4.response_headers.get("Content-type"), "application/json")
            res4 = json.loads(req4.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res4.get("status"), 405)

            # 5. Missing filename -> HTTP 400 JSON
            bad_req = MockReq("/files/save", json.dumps({"content": "no filename"}))
            HandlerClass.do_POST(bad_req)
            self.assertEqual(bad_req.response_code, 400, f"{app_subdir} missing filename should return 400")
            self.assertEqual(bad_req.response_headers.get("Content-type"), "application/json")

            # 6. Path traversal -> HTTP 403 JSON
            trav_req = MockReq("/files/save", json.dumps({"filename": "../../etc/passwd", "content": "malicious"}))
            HandlerClass.do_POST(trav_req)
            self.assertEqual(trav_req.response_code, 403, f"{app_subdir} path traversal should return 403")
            self.assertEqual(trav_req.response_headers.get("Content-type"), "application/json")

    def test_apply_diff_resilience_and_quote_tolerance(self):
        """Verify apply_diff handles single vs double quote differences, blank lines, fuzzy matching, and safe fallbacks."""
        for app_subdir, mod_name in [("landing-page", "landing_app_diff"), ("operator", "operator_app_diff")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            # Scenario 1: Quote difference ('__main__' in diff vs "__main__" in file) and blank lines
            file_content = 'def main():\n    print("Hello GDC")\n\n\nif __name__ == "__main__":\n    main()\n'
            test_files = {"main.py": file_content}
            target_block = 'if __name__ == \'__main__\':\n    main()'
            replacement_block = 'def is_prime(n):\n    return n > 1\n\nif __name__ == "__main__":\n    print(is_prime(7))\n    main()'

            ok, msg = app_mod.execute_tool("apply_diff", {
                "path": "main.py",
                "target_block": target_block,
                "replacement_block": replacement_block
            }, test_files)
            self.assertTrue(ok, f"{app_subdir} failed quote-tolerant diff: {msg}")
            self.assertIn("def is_prime(n):", test_files["main.py"])
            self.assertIn("print(is_prime(7))", test_files["main.py"])

            # Scenario 2: Fuzzy matching when LLM introduces whitespace or slight comment variation
            file_content2 = 'def compute_metrics():\n    # calculate latency\n    lat = 100\n    return lat\n'
            test_files2 = {"metrics.py": file_content2}
            target_block2 = 'def compute_metrics():\n    lat = 100\n    return lat'
            replacement_block2 = 'def compute_metrics():\n    lat = 100\n    return lat * 2'
            ok2, msg2 = app_mod.execute_tool("apply_diff", {
                "path": "metrics.py",
                "target_block": target_block2,
                "replacement_block": replacement_block2
            }, test_files2)
            self.assertTrue(ok2, f"{app_subdir} failed fuzzy diff: {msg2}")
            self.assertIn("lat * 2", test_files2["metrics.py"])

            # Scenario 3: Fallback anchor when target_block is not found at all
            file_content3 = 'def helper():\n    pass\n\nif __name__ == "__main__":\n    helper()\n'
            test_files3 = {"main.py": file_content3}
            target_block3 = 'completely nonexistent nonmatching block of text'
            replacement_block3 = 'def new_feature():\n    return True\n'
            ok3, msg3 = app_mod.execute_tool("apply_diff", {
                "path": "main.py",
                "target_block": target_block3,
                "replacement_block": replacement_block3
            }, test_files3)
            self.assertTrue(ok3, f"{app_subdir} failed fallback anchor diff: {msg3}")
            self.assertIn("def new_feature():", test_files3["main.py"])
            idx_feat = test_files3["main.py"].find("def new_feature():")
            idx_main = test_files3["main.py"].find("if __name__ == \"__main__\":")
            self.assertLess(idx_feat, idx_main, "Fallback anchor should insert before main block")

    def test_ide_markdown_preview_and_architect_spec(self):
        """Verify Web IDE includes Markdown preview toggle and Architect outputs markdown specifications."""
        for app_subdir, mod_name in [("landing-page", "landing_app_md"), ("operator", "operator_app_md")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            # 1. UI rendering of Markdown preview components
            html = app_mod.render_workspace_ui("default-workspace", "dev-user")
            self.assertIn('id="btn-md-preview"', html)
            self.assertIn('class="btn-preview"', html)
            self.assertIn('id="markdown-preview"', html)
            self.assertIn('class="markdown-preview-pane"', html)
            self.assertIn("toggleMarkdownPreview()", html)
            self.assertIn("renderMarkdownToHtml(", html)
            self.assertIn("cache_architecture.md", html)

            # 2. Architect persona specification
            personas = getattr(app_mod, "SWARM_PERSONAS", {})
            arch_persona = personas.get("architect", {})
            self.assertIn("Markdown (.md", arch_persona.get("system_prompt", ""))
            self.assertIn("do NOT author implementation code", arch_persona.get("system_prompt", ""))

            # 3. Architect chat output format (Markdown specification, not Python code)
            arch_res = app_mod.handle_ai_chat(json.dumps({
                "prompt": "Design cache in cache_architecture.md",
                "role": "architect",
                "filename": "cache_architecture.md"
            }), "test-user")
            self.assertEqual(arch_res.get("role"), "architect")
            self.assertIn("cache_architecture.md", arch_res.get("reply", ""))
            self.assertIn("Architectural Design Specification", arch_res.get("reply", ""))
            self.assertNotIn("def solve():", arch_res.get("reply", ""))

    def test_sanitize_python_code_and_ligature_healing(self):
        """Verify sanitize_python_code heals ligature errors, missing defs, and bullet artifacts."""
        for app_subdir, mod_name in [("landing-page", "landing_app_san"), ("operator", "operator_app_san")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            sanitize_fn = getattr(app_mod, "sanitize_python_code", None)
            self.assertIsNotNone(sanitize_fn, f"{app_subdir} must export sanitize_python_code")

            # 1. Ligature / transcription error: 'le_exists' or 'ile_exists' -> 'file_exists'
            corrupted_code = (
                "class CacheService:\n"
                "    def __init__(self):\n"
                "        self.cache = {}\n\n"
                "    le_exists(self, key: str) -> bool:\n"
                "        return key in self.cache\n"
            )
            repaired = sanitize_fn(corrupted_code)
            self.assertIn("def file_exists(self, key: str) -> bool:", repaired)
            self.assertNotIn("    le_exists(", repaired)
            self.assertNotIn("    ile_exists(", repaired)
            
            # Verify AST parses cleanly
            import ast
            parsed = ast.parse(repaired)
            self.assertIsNotNone(parsed)

            # 2. Markdown bullets inside code
            bullet_code = (
                "class Worker:\n"
                "    - def process(self):\n"
                "        pass\n"
            )
            repaired_bullet = sanitize_fn(bullet_code)
            self.assertIn("    def process(self):", repaired_bullet)
            self.assertNotIn("- def", repaired_bullet)

            # 3. Missing def in standalone or member function
            missing_def = (
                "def helper():\n"
                "    pass\n\n"
                "compute_hash(data: str) -> str:\n"
                "    return data.strip()\n"
            )
            repaired_def = sanitize_fn(missing_def)
            self.assertIn("def compute_hash(data: str) -> str:", repaired_def)

    def test_apply_diff_class_method_indentation_preservation(self):
        """Verify apply_diff preserves method indentation inside classes and handles new file creation."""
        for app_subdir, mod_name in [("landing-page", "landing_app_indent"), ("operator", "operator_app_indent")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            # 1. Surgical replacement of a method inside a multi-method class
            original_class = (
                "class SovereignCache:\n"
                "    def __init__(self, max_size=100):\n"
                "        self.max_size = max_size\n"
                "        self.data = {}\n\n"
                "    def get(self, key: str):\n"
                "        return self.data.get(key)\n\n"
                "    def put(self, key: str, value):\n"
                "        self.data[key] = value\n"
            )
            test_files = {"cache.py": original_class}

            # Replace 'get' method with signature match
            replacement = (
                "    def get(self, key: str):\n"
                "        val = self.data.get(key)\n"
                "        return val"
            )
            ok, msg = app_mod.execute_tool("apply_diff", {
                "path": "cache.py",
                "target_block": "def get(self, key: str):",
                "replacement_block": replacement
            }, test_files)

            self.assertTrue(ok, f"Failed apply_diff in {app_subdir}: {msg}")
            result_code = test_files["cache.py"]
            self.assertIn("val = self.data.get(key)", result_code)
            # Crucial: subsequent method 'put' must remain intact with its 4-space indentation
            self.assertIn("    def put(self, key: str, value):", result_code)
            self.assertIn("        self.data[key] = value", result_code)

            import ast
            ast.parse(result_code)

            # 2. Auto-create new file when content is None and replacement is provided
            new_files = {}
            ok_new, msg_new = app_mod.execute_tool("apply_diff", {
                "path": "new_service.py",
                "target_block": "new file",
                "replacement_block": "def run():\n    return True\n"
            }, new_files)
            self.assertTrue(ok_new, f"Failed new file creation in {app_subdir}: {msg_new}")
            self.assertIn("new_service.py", new_files)
            self.assertIn("def run():", new_files["new_service.py"])

    def test_gateway_timeouts_and_client_resilience(self):
        """Verify 300s AI inference timeout declarations and client-side error handling for non-JSON responses."""
        repo_root = os.path.dirname(self.base_dir)
        candidate_dirs = [self.manifest_dir]
        prod_dir = os.path.join(repo_root, "deploy-to-production", "patterns", "p13-gdc-dev", "manifests", "gdc")
        if os.path.isdir(prod_dir):
            candidate_dirs.append(prod_dir)
        for path_prefix in candidate_dirs:
            agent_cfg = os.path.join(path_prefix, "gdc-dev-agent-configmap.yaml")
            self.assertTrue(os.path.isfile(agent_cfg), f"Missing {agent_cfg}")
            with open(agent_cfg, "r") as f:
                content = f.read()
            self.assertIn('AI_REQUEST_TIMEOUT: "300"', content)

            ai_cfg = os.path.join(path_prefix, "ai-gateway-configmap.yaml")
            self.assertTrue(os.path.isfile(ai_cfg), f"Missing {ai_cfg}")
            with open(ai_cfg, "r") as f:
                content_ai = f.read()
            self.assertIn('AI_REQUEST_TIMEOUT: "300"', content_ai)

        # Check client-side JS non-JSON error handling
        for app_subdir in ["landing-page", "operator"]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            with open(app_path, "r") as f:
                app_content = f.read()
            self.assertIn("application/json", app_content)
            self.assertIn("Gateway Timeout (HTTP 504)", app_content)
            self.assertIn("Bad Gateway (HTTP 502)", app_content)

    def test_swarm_3_stage_synthesis_and_live_telemetry_recording(self):
        """Verify Swarm mode produces a 3-stage response with runnable Python + unittest and records live telemetry on Port 8083."""
        import ast
        for app_subdir, mod_name in [("landing-page", "landing_app_swarm_tel"), ("operator", "operator_app_swarm_tel")]:
            app_path = os.path.join(self.base_dir, "example-app", app_subdir, "app.py")
            spec = importlib.util.spec_from_file_location(mod_name, app_path)
            app_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_mod)

            initial_total = app_mod.TELEMETRY.total_requests
            initial_swarm = app_mod.TELEMETRY.persona_counts.get("swarm", 0)

            res = app_mod.handle_ai_chat(json.dumps({
                "prompt": "Create a rate_limiter.py module with a token-bucket rate limiter class and unit tests",
                "role": "swarm",
                "model": "gemma4:26b",
                "filename": "main.py"
            }), "oidc-developer@gdc.local")

            self.assertEqual(res.get("status"), "complete")
            self.assertEqual(res.get("role"), "swarm")
            reply = res.get("reply", "")
            self.assertIn("[Architect Plan]", reply)
            self.assertIn("[Coder Implementation]", reply)
            self.assertIn("[Reviewer QA & Verification]", reply)
            self.assertIn("rate_limiter.py", reply)
            self.assertIn("calculate_tenant_budget", reply)
            self.assertNotIn("def solve():", reply)

            # Extract Python code block and verify AST syntax
            import re
            m_py = re.search(r"```python\s*([\s\S]*?)```", reply)
            self.assertIsNotNone(m_py, f"{app_subdir} Swarm reply must include a ```python block")
            ast.parse(m_py.group(1))

            # Verify structured 3-persona swarm_artifacts payload for per-persona Save As and Auto-Create All
            swarm_artifacts = res.get("swarm_artifacts")
            self.assertIsInstance(swarm_artifacts, list, f"{app_subdir} must return swarm_artifacts list")
            self.assertEqual(len(swarm_artifacts), 3)
            self.assertEqual([a.get("persona") for a in swarm_artifacts], ["architect", "coder", "reviewer"])
            self.assertEqual(
                [a.get("filename") for a in swarm_artifacts],
                ["rate_limiter_architecture.md", "rate_limiter.py", "test_rate_limiter.py"],
            )
            for item in swarm_artifacts:
                self.assertTrue(len(item.get("content", "")) > 40)
                if item["filename"].endswith(".py"):
                    ast.parse(item["content"])

            ws_html = app_mod.render_workspace_ui("default-workspace", "oidc-developer@gdc.local")
            self.assertIn("autoCreateAllSwarmFiles", ws_html)
            self.assertIn("saveSwarmPersonaOutput", ws_html)
            self.assertIn("saveCodeBlockAsFile", ws_html)

            # Verify TELEMETRY incremented and recorded the swarm event at index 0
            self.assertEqual(app_mod.TELEMETRY.total_requests, initial_total + 1)
            self.assertEqual(app_mod.TELEMETRY.persona_counts.get("swarm", 0), initial_swarm + 1)
            latest_ev = app_mod.TELEMETRY.recent_events[0]
            self.assertEqual(latest_ev.get("persona"), "swarm")
            self.assertEqual(latest_ev.get("model"), "gemma4:26b")
            self.assertIn("Swarm Complete", latest_ev.get("status", ""))

            # Verify Admin Telemetry UI pollTelemetry updates table and bars dynamically
            admin_html = app_mod.render_admin_telemetry_ui("admin@gdc.local")
            self.assertIn("id=\"cnt-swarm\"", admin_html)
            self.assertIn("id=\"cnt-coder\"", admin_html)
            self.assertIn("evBody.innerHTML = data.recent_events.slice(0, 20)", admin_html)

if __name__ == "__main__":
    unittest.main()
