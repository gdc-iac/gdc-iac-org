#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0.
"""
@file test_phase5_antigravity_notebooks.py
@brief Validation suite for Pattern 14 (`p14-antigravity-dev`): Antigravity SDK
Local Models & Integrated JupyterLab 4 Notebooks on GDC Air-Gapped (`v1.3`).

Validates:
1. Antigravity SDK Tri-Backend Configuration (`LocalOpenAIAgentConfig.lightweight()`,
   `LiteRTAgentConfig` with 16,384 GPU compaction cap, `LocalAgentConfig` GDC Gemini Chat Completions).
2. Typed `BlueprintAdaptationPlan` structured output generation.
3. Principle of Least Privilege (PoLP) tool policies (`policy.workspace_only`,
   `policy.ask_user`, `policy.deny`) and `is_safe_verify_cmd` predicate guard.
4. Scrubbed `SAFE_ENV` subprocess and Jupyter cell execution environment (`REQ-SEC-010`).
5. Structured `.ipynb` v4 cell tools (`notebook_list_cells`, `notebook_get_cell_outputs`,
   `notebook_edit_cell`, `notebook_run_cell`, `notebook_rollback_cell`) and `.ipynb.bak` rollback.
6. IPython Notebook Magics (`%%agy_architect`, `%%agy_builder`, `%%agy_verify`, `%agy_fix`).
7. Modular GDC Skills (`gdc-blueprint-adaptation`, `gdc-e2e-iac-knitting`,
   `gdc-notebook-mlops`, `gdc-security-opa`) discovery.
8. Outer Retry & Backend Failover Supervisor (`run_with_failover_supervisor`).
9. Unified Port 8080 `/ide/` + `/lab/` surface switcher and `/notebooks` REST API.
10. Pattern 14 ConfigMap & Helm chart `computeProfile` (`cpu-gateway` vs `gpu-litert-notebook`).
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest


class TestP14AntigravityAndNotebooks(unittest.TestCase):
    """Pattern 14 Antigravity SDK & Integrated JupyterLab 4 Test Suite."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.orch_dir = os.path.join(self.base_dir, "example-app", "orchestrator")
        if self.orch_dir not in sys.path:
            sys.path.insert(0, self.orch_dir)
        import gdc_agy_orchestrator as agy
        import gdc_antigravity_magic as agy_magic
        self.agy = agy
        self.agy_magic = agy_magic

    def test_tri_backend_agent_configs_and_lightweight_compaction(self):
        """Verify LocalOpenAIAgentConfig.lightweight(), LiteRTAgentConfig (16k GPU cap), and LocalAgentConfig."""
        # 1. Shared In-Cluster Gemma 4 Gateway (`LocalOpenAIAgentConfig.lightweight()`)
        gw_cfg = self.agy.build_agent_config_for_role(
            role="builder", backend_mode="gdc_gemma_gw"
        )
        self.assertIsInstance(gw_cfg, self.agy.LocalOpenAIAgentConfig)
        self.assertEqual(gw_cfg.behavior, self.agy.AgentBehavior.MINIMAL)
        self.assertFalse(gw_cfg.enable_subagents)
        self.assertEqual(gw_cfg.compaction.token_threshold, 40960)
        self.assertIsNone(gw_cfg.api_key)
        self.assertIn("gemma-gateway.gemma-inference.svc.cluster.local", gw_cfg.base_url)

        # 2. On-Device LiteRT-LM (`LiteRTAgentConfig` on GPU profile -> 16,384 token cap)
        old_prof = os.environ.get("COMPUTE_PROFILE")
        try:
            os.environ["COMPUTE_PROFILE"] = "gpu-litert-notebook"
            litert_cfg = self.agy.build_agent_config_for_role(
                role="builder", backend_mode="litert_on_device"
            )
            self.assertIsInstance(litert_cfg, self.agy.LiteRTAgentConfig)
            self.assertEqual(litert_cfg.backend, self.agy.LiteRTBackend.GPU)
            self.assertFalse(litert_cfg.download_if_missing)
            self.assertTrue(litert_cfg.enable_speculative_decoding)
            self.assertEqual(litert_cfg.compaction.token_threshold, 16384)
        finally:
            if old_prof is None:
                os.environ.pop("COMPUTE_PROFILE", None)
            else:
                os.environ["COMPUTE_PROFILE"] = old_prof

        # 3. Sovereign Gemini on GDC Air-Gapped Chat Completions API (`LocalAgentConfig`, `gemini-3.5-flash`)
        gemini_cfg = self.agy.build_agent_config_for_role(
            role="architect", backend_mode="gdc_gemini"
        )
        self.assertIsInstance(gemini_cfg, self.agy.LocalAgentConfig)
        self.assertEqual(gemini_cfg.model, "gemini-3.5-flash")
        self.assertIn("/v1/projects/", gemini_cfg.endpoint)
        self.assertTrue(gemini_cfg.endpoint.endswith("/chat/completions"))
        self.assertEqual(gemini_cfg.backend_kind, "gdc_gemini")

    def test_polp_policies_and_verifier_predicate_guard(self):
        """Verify PoLP role policies and is_safe_verify_cmd predicate guard."""
        with tempfile.TemporaryDirectory() as tmp_ws:
            arch_cfg = self.agy.build_agent_config_for_role("architect", workspace_dir=tmp_ws)
            builder_cfg = self.agy.build_agent_config_for_role("builder", workspace_dir=tmp_ws)
            verifier_cfg = self.agy.build_agent_config_for_role("verifier", workspace_dir=tmp_ws)

            # Architect allows read_file & notebook_list_cells, denies notebook_edit_cell & run_command
            dec, _ = self.agy.evaluate_tool_policy(
                arch_cfg.policies, "notebook_list_cells", {"notebook_path": "nb.ipynb"}, tmp_ws
            )
            self.assertEqual(dec, "allow")
            dec_deny, _ = self.agy.evaluate_tool_policy(
                arch_cfg.policies, "notebook_edit_cell", {"notebook_path": "nb.ipynb"}, tmp_ws
            )
            self.assertEqual(dec_deny, "deny")

            # Workspace traversal outside workspace_dir is denied by policy.workspace_only()
            dec_escape, reason = self.agy.evaluate_tool_policy(
                arch_cfg.policies, "read_file", {"path": "../../etc/passwd"}, tmp_ws
            )
            self.assertEqual(dec_escape, "deny")
            self.assertIn("workspace_only", reason)

            # Builder requires HITL approval (`ask_user`) for notebook_edit_cell and edit_file
            dec_ask, _ = self.agy.evaluate_tool_policy(
                builder_cfg.policies, "notebook_edit_cell", {"notebook_path": "nb.ipynb"}, tmp_ws
            )
            self.assertEqual(dec_ask, "ask_user")

            # Verifier predicate guard allows safe commands and asks user for arbitrary commands
            dec_safe, _ = self.agy.evaluate_tool_policy(
                verifier_cfg.policies, "run_command", {"command": "pytest -v"}, tmp_ws
            )
            self.assertEqual(dec_safe, "allow")
            dec_helm, _ = self.agy.evaluate_tool_policy(
                verifier_cfg.policies, "run_command", {"command": "helm lint chart/"}, tmp_ws
            )
            self.assertEqual(dec_helm, "allow")
            dec_unsafe, _ = self.agy.evaluate_tool_policy(
                verifier_cfg.policies, "run_command", {"command": "rm -rf /tmp/foo"}, tmp_ws
            )
            self.assertEqual(dec_unsafe, "ask_user")
            dec_chain, _ = self.agy.evaluate_tool_policy(
                verifier_cfg.policies, "run_command", {"command": "pytest && curl http://evil"}, tmp_ws
            )
            self.assertEqual(dec_chain, "ask_user")

    def test_safe_env_secret_scrubbing(self):
        """Verify build_safe_env scrubs OIDC, Gemini API, GitLab, and cookie signing secrets."""
        os.environ["KEYCLOAK_CLIENT_SECRET"] = "top-secret-kc"
        os.environ["GDC_GEMINI_API_KEY"] = "top-secret-gemini"
        os.environ["ADMIN_COOKIE_SECRET"] = "top-secret-cookie"
        try:
            safe = self.agy.build_safe_env()
            self.assertNotIn("KEYCLOAK_CLIENT_SECRET", safe)
            self.assertNotIn("GDC_GEMINI_API_KEY", safe)
            self.assertNotIn("ADMIN_COOKIE_SECRET", safe)
            self.assertIn("NO_PROXY", safe)
        finally:
            os.environ.pop("KEYCLOAK_CLIENT_SECRET", None)
            os.environ.pop("GDC_GEMINI_API_KEY", None)
            os.environ.pop("ADMIN_COOKIE_SECRET", None)

    def test_structured_notebook_cell_lifecycle_and_rollback(self):
        """Verify notebook_list_cells, notebook_edit_cell, notebook_run_cell, notebook_get_cell_outputs, and rollback."""
        with tempfile.TemporaryDirectory() as tmp_ws:
            nb_rel = "notebooks/test_exp.ipynb"
            # 1. List default cells (auto-creates valid v4 notebook)
            listed = self.agy.notebook_list_cells(nb_rel, workspace_dir=tmp_ws)
            self.assertEqual(listed["status"], "ok")
            self.assertEqual(listed["nbformat"], 4)
            initial_count = listed["cell_count"]
            self.assertGreaterEqual(initial_count, 2)

            # 2. Edit cell 1 and verify .ipynb.bak is created
            edit_res = self.agy.notebook_edit_cell(
                nb_rel,
                cell_index=1,
                new_source="x = 21 * 2\nprint('Result:', x)\n",
                cell_type="code",
                workspace_dir=tmp_ws,
            )
            self.assertEqual(edit_res["status"], "ok")
            self.assertTrue(os.path.isfile(os.path.join(tmp_ws, nb_rel + ".bak")))

            # 3. Run cell 1 and verify structured output capture
            run_res = self.agy.notebook_run_cell(nb_rel, cell_index=1, workspace_dir=tmp_ws)
            self.assertEqual(run_res["status"], "ok")
            self.assertIn("Result: 42", run_res["stdout"])

            out_res = self.agy.notebook_get_cell_outputs(nb_rel, cell_index=1, workspace_dir=tmp_ws)
            self.assertEqual(out_res["status"], "ok")
            self.assertIn("Result: 42", out_res["stdout"])

            # 4. Rollback cell to pre-mutation .ipynb.bak snapshot
            rb_res = self.agy.notebook_rollback_cell(nb_rel, workspace_dir=tmp_ws)
            self.assertEqual(rb_res["status"], "ok")
            after_rb = self.agy.notebook_get_cell_outputs(nb_rel, cell_index=1, workspace_dir=tmp_ws)
            self.assertNotIn("Result: 42", after_rb["source"])

            # 5. Add a new code cell (ClickOps / API add_cell) and verify cell_count increments
            add_res = self.agy.notebook_add_cell(
                nb_rel,
                cell_type="code",
                source="print('Added ClickOps Cell')\n",
                position=-1,
                workspace_dir=tmp_ws,
            )
            self.assertEqual(add_res["status"], "ok")
            self.assertEqual(add_res["cell_count"], initial_count + 1)
            new_idx = add_res["added_cell_index"]
            self.assertEqual(new_idx, initial_count)

            # 6. Delete the newly added cell (ClickOps / API delete_cell) and verify cell_count restores
            del_res = self.agy.notebook_delete_cell(
                nb_rel,
                cell_index=new_idx,
                workspace_dir=tmp_ws,
            )
            self.assertEqual(del_res["status"], "ok")
            self.assertEqual(del_res["cell_count"], initial_count)

    def test_ipython_notebook_magics_and_cell_error_autofix(self):
        """Verify %%agy_architect, %%agy_builder, %%agy_verify, and %agy_fix magics."""
        with tempfile.TemporaryDirectory() as tmp_ws:
            # 1. %%agy_architect
            arch_res = self.agy_magic.execute_notebook_magic(
                "agy_architect",
                cell="Adapt p02-genai-rag helm chart and add evaluation notebook",
                workspace_dir=tmp_ws,
            )
            self.assertEqual(arch_res["status"], "ok")
            self.assertEqual(arch_res["plan"]["target_blueprint"], "p02-genai-rag")
            self.assertTrue(arch_res["plan"]["helm_chart_sync_required"])
            self.assertIn("input_tokens", arch_res["total_usage"])

            # 2. %%agy_builder (selective HITL approval vs autonomous)
            b_ask = self.agy_magic.execute_notebook_magic(
                "agy_builder",
                line="notebooks/exp.ipynb",
                cell="Add latency benchmark cell",
                workspace_dir=tmp_ws,
                approval_policy="selective",
            )
            self.assertEqual(b_ask["status"], "waiting_for_approval")
            self.assertEqual(b_ask["tool"], "notebook_edit_cell")

            b_auto = self.agy_magic.execute_notebook_magic(
                "agy_builder",
                line="notebooks/exp.ipynb",
                cell="Add latency benchmark cell",
                workspace_dir=tmp_ws,
                approval_policy="autonomous",
            )
            self.assertEqual(b_auto["status"], "ok")

            # 3. %agy_fix (Notebook Cell Error Auto-Repair)
            fix_res = self.agy_magic.execute_notebook_magic(
                "agy_fix",
                line="1 / 0",
                workspace_dir=tmp_ws,
            )
            self.assertIn("Auto-Repaired", fix_res["proposed_cell_source"])

    def test_modular_gdc_skills_and_failover_supervisor(self):
        """Verify all 4 modular GDC SKILL.md bundles, ClickOps skill creation/deletion, and outer failover supervisor."""
        skills = self.agy.get_installed_skills()
        skill_names = [s["name"] for s in skills]
        for expected in (
            "gdc-blueprint-adaptation",
            "gdc-e2e-iac-knitting",
            "gdc-notebook-mlops",
            "gdc-security-opa",
        ):
            self.assertIn(expected, skill_names)

        # Verify workspace skills mirroring and ClickOps create/delete lifecycle
        with tempfile.TemporaryDirectory() as tmp_ws:
            copied_skills = self.agy.ensure_workspace_skills(tmp_ws)
            self.assertGreaterEqual(len(copied_skills), 4)
            self.assertTrue(os.path.isfile(os.path.join(tmp_ws, "skills", "gdc-security-opa", "SKILL.md")))

            created = self.agy.create_or_update_skill(
                skill_name="gdc-gpu-cost-governance",
                description="Enforces NVIDIA L4 GPU time-slicing quotas and 16k LiteRT token thresholds.",
                instructions="# GDC GPU Cost Governance\n\n1. Require `computeProfile: \"cpu-gateway\"` for standard pods.\n2. Cap GPU pods at 16,384 tokens.",
                workspace_dir=tmp_ws,
            )
            self.assertEqual(created["status"], "ok")
            self.assertEqual(created["skill"]["name"], "gdc-gpu-cost-governance")
            self.assertEqual(created["workspace_path"], "skills/gdc-gpu-cost-governance/SKILL.md")

            resolved = self.agy.resolve_skill_for_prompt(
                prompt="Audit GPU quota rules",
                selected_skill="gdc-gpu-cost-governance",
                workspace_dir=tmp_ws,
            )
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["name"], "gdc-gpu-cost-governance")

            deleted = self.agy.delete_skill("gdc-gpu-cost-governance", workspace_dir=tmp_ws)
            self.assertEqual(deleted["status"], "ok")

        # Test failover supervisor recovery after transient failure
        state = {"calls": 0}
        def flaky_call():
            state["calls"] += 1
            if state["calls"] < 2:
                raise RuntimeError("Gateway timeout")
            return {"status": "ok", "reply": "Recovered"}

        res, meta = self.agy.run_with_failover_supervisor(flaky_call, base_delay=0.01)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(meta["attempts"], 2)

    def test_landing_page_integrated_ide_and_jupyterlab_surface(self):
        """Verify landing-page app.py renders /ide/ + /lab/ switcher and returns agy_sdk_config & total_usage."""
        app_path = os.path.join(self.base_dir, "example-app", "landing-page", "app.py")
        spec = importlib.util.spec_from_file_location("p14_landing_app", app_path)
        landing_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(landing_app)

        html = landing_app.render_workspace_ui("test-session", "oidc-developer@gdc.local", view_mode="lab")
        self.assertIn("p14-antigravity-surface-bar", html)
        self.assertIn("Integrated JupyterLab 4 (/lab/)", html)
        self.assertIn("%%agy_architect", html)
        self.assertIn("fixNotebookCellWithAntigravity", html)
        self.assertIn("toggleCompleteNotebookView", html)
        self.assertIn("runAllNotebookCells", html)
        self.assertIn("openNotebookInCodeEditor", html)
        self.assertIn("downloadNotebookFile", html)
        self.assertIn("toggleP14SkillsDrawer", html)
        self.assertIn("openClickOpsNewSkillForm", html)
        self.assertIn("createOrUpdateClickOpsSkill", html)
        self.assertIn("useSkillInCodeIde", html)
        self.assertIn("mountIdeSkillSelectorBar", html)
        # Ensure no unescaped single quote breaks JS string literal in addBelowBtn
        self.assertNotIn("onclick=\"addNotebookCell('code', ' +", html)
        self.assertIn("onclick=\"addNotebookCell(&quot;code&quot;, ' +", html)

        chat_res = landing_app.handle_ai_chat(
            json.dumps({"prompt": "Adapt p03-db helm chart", "role": "architect", "selected_skill": "gdc-blueprint-adaptation"}),
            "oidc-developer@gdc.local",
        )
        self.assertIn("agy_sdk_config", chat_res)
        self.assertIn("blueprint_plan", chat_res)
        self.assertIn("total_usage", chat_res)
        self.assertEqual(chat_res["blueprint_plan"]["target_blueprint"], "p03-db")
        self.assertIsNotNone(chat_res["applied_skill"])
        self.assertEqual(chat_res["applied_skill"]["name"], "gdc-blueprint-adaptation")
        self.assertIn("Antigravity Skill Active", chat_res["reply"])

        # Verify ClickOps /instances/<session>/skills API (list_skills, create_skill, delete_skill)
        with tempfile.TemporaryDirectory() as tmp_skills_ws:
            sk_list = landing_app.handle_skills_api_request({"action": "list_skills"}, workspace_dir=tmp_skills_ws)
            self.assertEqual(sk_list["status"], "ok")
            self.assertGreaterEqual(sk_list["skill_count"], 4)

            sk_create = landing_app.handle_skills_api_request(
                {
                    "action": "create_skill",
                    "skill_name": "gdc-gpu-cost-governance",
                    "description": "Enforces NVIDIA L4 GPU time-slicing quotas and 16k LiteRT token thresholds.",
                    "body_markdown": "# GDC GPU Cost Governance\n\n1. Require `computeProfile: \"cpu-gateway\"` for standard workspaces.\n2. Cap GPU pods at 16,384 tokens.",
                },
                workspace_dir=tmp_skills_ws,
            )
            self.assertEqual(sk_create["status"], "ok")
            self.assertEqual(sk_create["skill"]["name"], "gdc-gpu-cost-governance")
            self.assertEqual(sk_create["workspace_path"], "skills/gdc-gpu-cost-governance/SKILL.md")

            sk_del = landing_app.handle_skills_api_request(
                {"action": "delete_skill", "skill_name": "gdc-gpu-cost-governance"},
                workspace_dir=tmp_skills_ws,
            )
            self.assertEqual(sk_del["status"], "ok")

        # Verify handle_notebook_api_request for list_cells, edit_cell, run_cell, rollback_cell, and magic
        with tempfile.TemporaryDirectory() as tmp_ws:
            nb_list = landing_app.handle_notebook_api_request(
                {"action": "list_cells", "notebook_path": "notebooks/demo.ipynb"},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_list["status"], "ok")
            self.assertGreaterEqual(nb_list["cell_count"], 2)

            nb_magic = landing_app.handle_notebook_api_request(
                {"action": "magic", "magic": "agy_architect", "cell": "Knitting p02-genai-rag with p12-keycloak", "apply_to_notebook": True},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_magic["status"], "ok")
            self.assertEqual(nb_magic["plan"]["target_blueprint"], "p02-genai-rag")
            self.assertEqual(nb_magic["updated_cell_index"], 0)
            self.assertGreaterEqual(len(nb_magic["cells"]), 3)

            nb_builder = landing_app.handle_notebook_api_request(
                {"action": "magic", "magic": "agy_builder", "cell": "Benchmark Gemma 4 latency", "apply_to_notebook": True},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_builder["status"], "ok")
            self.assertEqual(nb_builder["updated_cell_index"], 1)
            self.assertIn("Benchmark latency (ms):", nb_builder["cells"][1]["stdout"])

            # Verify ClickOps add_cell, per-cell Antigravity magic on Cell [3], %agy_fix on Cell [3], and delete_cell
            nb_add = landing_app.handle_notebook_api_request(
                {"action": "add_cell", "notebook_path": "notebooks/demo.ipynb", "cell_type": "code", "position": -1},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_add["status"], "ok")
            self.assertEqual(nb_add["cell_count"], 4)
            self.assertEqual(nb_add["added_cell_index"], 3)
            self.assertIn("%%agy_builder", nb_add["new_source"])

            # Running Cell [3] directly expands its inline %%agy_builder magic and runs the GPU/VRAM audit
            nb_run_c3 = landing_app.handle_notebook_api_request(
                {"action": "run_cell", "notebook_path": "notebooks/demo.ipynb", "cell_index": 3},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_run_c3["status"], "ok")
            self.assertEqual(nb_run_c3["updated_cell_index"], 3)
            self.assertIn("[GDC-ag Audit]", nb_run_c3["cells"][3]["stdout"])

            # Introduce a ZeroDivisionError in Cell [3] and repair Cell [3] via target_cell_index=3
            landing_app.handle_notebook_api_request(
                {
                    "action": "edit_cell",
                    "notebook_path": "notebooks/demo.ipynb",
                    "cell_index": 3,
                    "new_source": "gpu_qps = 250 / 0\nprint('GPU QPS:', gpu_qps)\n",
                },
                workspace_dir=tmp_ws,
            )
            nb_fix_c3 = landing_app.handle_notebook_api_request(
                {
                    "action": "magic",
                    "magic": "agy_fix",
                    "notebook_path": "notebooks/demo.ipynb",
                    "target_cell_index": 3,
                    "apply_to_notebook": True,
                },
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_fix_c3["status"], "ok")
            self.assertEqual(nb_fix_c3["updated_cell_index"], 3)
            self.assertIn("GPU QPS: 250.0", nb_fix_c3["cells"][3]["stdout"])

            nb_del = landing_app.handle_notebook_api_request(
                {"action": "delete_cell", "notebook_path": "notebooks/demo.ipynb", "cell_index": 3},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_del["status"], "ok")
            self.assertEqual(nb_del["cell_count"], 3)

            nb_fix = landing_app.handle_notebook_api_request(
                {
                    "action": "magic",
                    "magic": "agy_fix",
                    "notebook_path": "notebooks/demo.ipynb",
                    "line": "throughput_qps = 120 / 0",
                    "apply_to_notebook": True,
                },
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_fix["status"], "ok")
            self.assertEqual(nb_fix["updated_cell_index"], 2)
            self.assertIn("Throughput QPS: 120.0", nb_fix["cells"][2]["stdout"])
            self.assertFalse(nb_fix["cells"][2]["has_error"])
            self.assertIn("notebook_json", nb_fix)
            self.assertEqual(json.loads(nb_fix["notebook_json"])["nbformat"], 4)

            nb_run_all = landing_app.handle_notebook_api_request(
                {"action": "run_all_cells", "notebook_path": "notebooks/demo.ipynb"},
                workspace_dir=tmp_ws,
            )
            self.assertEqual(nb_run_all["status"], "ok")
            self.assertGreaterEqual(nb_run_all["executed_count"], 2)
            self.assertEqual(nb_run_all["error_count"], 0)

    def test_p14_manifests_and_helm_chart_profiles(self):
        """Verify Pattern 14 manifests and Helm chart declare cpu-gateway, gpu-litert-notebook, and Native GDC Notebook CRD."""
        cm_path = os.path.join(self.base_dir, "manifests", "gdc", "gdc-antigravity-notebook-configmap.yaml")
        self.assertTrue(os.path.isfile(cm_path))
        with open(cm_path, "r", encoding="utf-8") as f:
            cm_text = f.read()
        self.assertIn('AGY_SDK_ENABLED: "true"', cm_text)
        self.assertIn('JUPYTERLAB_ENABLED: "true"', cm_text)
        self.assertIn('LITERT_GPU_TOKEN_THRESHOLD: "16384"', cm_text)
        self.assertIn('AGY_LIGHTWEIGHT_TOKEN_THRESHOLD: "40960"', cm_text)

        chart_yaml_path = os.path.join(self.base_dir, "chart", "Chart.yaml")
        with open(chart_yaml_path, "r", encoding="utf-8") as f:
            chart_text = f.read()
        self.assertIn("name: p14-antigravity-dev", chart_text)

        values_yaml_path = os.path.join(self.base_dir, "chart", "values.yaml")
        with open(values_yaml_path, "r", encoding="utf-8") as f:
            values_text = f.read()
        self.assertIn('computeProfile: "cpu-gateway"', values_text)
        self.assertIn("gatewayTokenThreshold: 40960", values_text)
        self.assertIn("litertGpuTokenThreshold: 16384", values_text)
        self.assertIn('allowSimulatedOidc: "false"', values_text)

        gdc_res_path = os.path.join(self.base_dir, "chart", "templates", "gdc", "resources.yaml")
        with open(gdc_res_path, "r", encoding="utf-8") as f:
            gdc_res_text = f.read()
        self.assertIn("apiVersion: aiplatform.gdc.goog/v1", gdc_res_text)
        self.assertIn("kind: Notebook", gdc_res_text)

    def test_container_build_context_self_contained(self):
        """Verify landing-page and operator Docker build contexts contain orchestrator modules and skills."""
        for sub in ("landing-page", "operator"):
            sub_dir = os.path.join(self.base_dir, "example-app", sub)
            self.assertTrue(os.path.isfile(os.path.join(sub_dir, "gdc_agy_orchestrator.py")))
            self.assertTrue(os.path.isfile(os.path.join(sub_dir, "gdc_antigravity_magic.py")))
            self.assertTrue(os.path.isdir(os.path.join(sub_dir, "skills")))
            with open(os.path.join(sub_dir, "Dockerfile"), "r", encoding="utf-8") as f:
                df_text = f.read()
            self.assertIn("gdc_agy_orchestrator.py", df_text)
            self.assertIn("gdc_antigravity_magic.py", df_text)
            self.assertIn("COPY skills/ /opt/p14-antigravity/skills/", df_text)

    def test_operator_app_entrypoint_and_handlers(self):
        """Verify operator/app.py defines run(), run_health_server(), run_session_server(), and control_loop()."""
        operator_app_path = os.path.join(self.base_dir, "example-app", "operator", "app.py")
        spec = importlib.util.spec_from_file_location("p14_operator_app", operator_app_path)
        operator_app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(operator_app)
        for fn_name in (
            "run",
            "run_health_server",
            "run_session_server",
            "control_loop",
            "handle_notebook_api_request",
            "handle_skills_api_request",
        ):
            self.assertTrue(hasattr(operator_app, fn_name), f"Missing {fn_name} in operator/app.py")
            self.assertTrue(callable(getattr(operator_app, fn_name)), f"{fn_name} is not callable in operator/app.py")


if __name__ == "__main__":
    unittest.main()
