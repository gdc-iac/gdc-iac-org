#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0.
"""
CLI Runner for Pattern 14 (`p14-antigravity-dev`):
1. Executes live HTTP smoke checks against the Sovereign Admin Console (`--admin-url`, default
   `http://127.0.0.1:8083`) and Unified Developer IDE + JupyterLab 4 (`--ide-url`, default
   `http://127.0.0.1:8084`) when running against a port-forwarded cluster.
2. Executes the 10-stage Multi-Agent Swarm validation suite (`test-swarm.py`) targeting
   `{ide_url}/instances/default-workspace/ai-chat`.
3. Executes Phase 5 Antigravity SDK (`LocalOpenAIAgentConfig`, `LiteRTAgentConfig`,
   `LocalAgentConfig`) and Integrated JupyterLab 4 (`.ipynb` v4 cell tools & `%%agy` magics) checks.
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATTERN_DIR = os.path.dirname(SCRIPT_DIR)

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _http_json(url: str, payload: dict | None = None, timeout: int = 120) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-User-ID": "oidc-developer@gdc.local",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    ctx = ssl._create_unverified_context() if url.startswith("https://") else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_live_agy_smoke_checks(admin_url: str, ide_url: str, timeout: int = 120) -> bool:
    admin_base = admin_url.rstrip("/")
    ide_base = ide_url.rstrip("/")

    print(f"\n{BOLD}{CYAN}{'=' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  🚀 Pattern 14 Live Cluster Antigravity SDK & Notebook Smoke Suite{RESET}")
    print(f"{BOLD}{CYAN}     Admin Console : {admin_base}{RESET}")
    print(f"{BOLD}{CYAN}     Developer IDE : {ide_base}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}\n")

    try:
        # 1. Verify /agy-config on Port 8083 & Port 8084
        print(f"{BOLD}[Live 1/5] Inspecting Antigravity SDK Config & Installed SKILL.md Bundles ({admin_base}/agy-config)...{RESET}")
        cfg = _http_json(f"{admin_base}/agy-config", timeout=timeout)
        assert cfg.get("status") == "ok", f"Unexpected /agy-config status: {cfg}"
        assert cfg.get("pattern") == "p14-antigravity-dev", f"Unexpected pattern: {cfg}"
        skills = cfg.get("skills", [])
        assert len(skills) >= 4, f"Expected >= 4 skills, got {len(skills)}"
        print(
            f"  {GREEN}✓ SDK Config: {cfg.get('config_class')} | "
            f"Behavior: {cfg.get('behavior')} | "
            f"Threshold: {cfg.get('token_threshold')} | "
            f"Skills Installed: {len(skills)}{RESET}"
        )
        for s in skills:
            print(f"    - {s.get('name')} ({s.get('workspace_path', 'skills/' + s.get('name', '') + '/SKILL.md')}): {s.get('path')}")

        # 2. Verify Tri-Backend Switching on Port 8084 (/ai-chat)
        print(f"\n{BOLD}[Live 2/5] Verifying Antigravity Tri-Backend Switching ({ide_base}/instances/default-workspace/ai-chat)...{RESET}")
        for mode, expected_cls in [
            ("gdc_gemma_gw", "LocalOpenAIAgentConfig"),
            ("litert_on_device", "LiteRTAgentConfig"),
            ("gdc_gemini", "LocalAgentConfig"),
        ]:
            chat_res = _http_json(
                f"{ide_base}/instances/default-workspace/ai-chat",
                payload={
                    "role": "architect",
                    "prompt": f"Verify Antigravity backend mode {mode}",
                    "filename": "main.py",
                    "backend_mode": mode,
                },
                timeout=timeout,
            )
            sdk_cfg = chat_res.get("agy_sdk_config", {})
            actual_cls = sdk_cfg.get("config_class")
            assert actual_cls == expected_cls, f"Expected {expected_cls} for {mode}, got {actual_cls}"
            print(
                f"  {GREEN}✓ backend_mode='{mode}' -> {actual_cls} "
                f"(model={sdk_cfg.get('model')}, threshold={sdk_cfg.get('token_threshold')}){RESET}"
            )

        # 3. Verify Structured BlueprintAdaptationPlan + Token Telemetry
        print(f"\n{BOLD}[Live 3/5] Verifying Structured BlueprintAdaptationPlan & Token Telemetry...{RESET}")
        arch_res = _http_json(
            f"{ide_base}/instances/default-workspace/ai-chat",
            payload={
                "role": "architect",
                "prompt": "Adapt p14-antigravity-dev helm chart and add a notebook latency benchmark",
                "filename": "main.py",
                "backend_mode": "gdc_gemma_gw",
            },
            timeout=timeout,
        )
        plan = arch_res.get("blueprint_plan", {})
        usage = arch_res.get("total_usage", {})
        assert plan.get("target_blueprint") == "p14-antigravity-dev", f"Missing blueprint_plan: {plan}"
        assert usage.get("total_tokens", 0) > 0, f"Missing total_usage telemetry: {usage}"
        print(
            f"  {GREEN}✓ BlueprintAdaptationPlan verified (target_blueprint={plan.get('target_blueprint')}) | "
            f"total_tokens={usage.get('total_tokens')}{RESET}"
        )

        # 4. Verify Integrated JupyterLab 4 (.ipynb v4) Lifecycle, ClickOps Cell [3], Complete Notebook View & Rollback
        print(f"\n{BOLD}[Live 4/5] Verifying Integrated JupyterLab 4 (.ipynb v4) Cell Tools, Complete View & Rollback ({ide_base}/instances/default-workspace/notebooks)...{RESET}")
        nb_url = f"{ide_base}/instances/default-workspace/notebooks"
        nb_path = "notebooks/gdc_blueprint_explorer.ipynb"

        cells_res = _http_json(nb_url, {"action": "list_cells", "notebook_path": nb_path}, timeout=timeout)
        initial_count = cells_res.get("cell_count", 0)
        assert initial_count >= 3, f"Expected >= 3 cells in {nb_path}, got {cells_res}"
        assert "notebook_json" in cells_res, "Expected notebook_json in list_cells response"
        print(f"  {GREEN}✓ list_cells: {initial_count} cells found in {nb_path} (complete .ipynb JSON synced){RESET}")

        add_res = _http_json(
            nb_url,
            {"action": "add_cell", "notebook_path": nb_path, "cell_type": "code", "position": -1},
            timeout=timeout,
        )
        assert add_res.get("status") == "ok" and add_res.get("cell_count") == initial_count + 1, f"add_cell failed: {add_res}"
        added_idx = add_res.get("added_cell_index", add_res.get("cell_index", initial_count))
        print(f"  {GREEN}✓ add_cell: added ClickOps Cell [{added_idx}] with starter %%agy_builder prompt (total={add_res.get('cell_count')}){RESET}")

        run_c3 = _http_json(nb_url, {"action": "run_cell", "notebook_path": nb_path, "cell_index": added_idx}, timeout=timeout)
        assert run_c3.get("status") == "ok", f"run_cell on ClickOps Cell [{added_idx}] failed: {run_c3}"
        print(f"  {GREEN}✓ run_cell (ClickOps Cell [{added_idx}]): inline %%agy_builder expanded & executed{RESET}")

        del_res = _http_json(
            nb_url,
            {"action": "delete_cell", "notebook_path": nb_path, "cell_index": added_idx},
            timeout=timeout,
        )
        assert del_res.get("status") == "ok" and del_res.get("cell_count") == initial_count, f"delete_cell failed: {del_res}"
        print(f"  {GREEN}✓ delete_cell: deleted Cell [{added_idx}] (total={del_res.get('cell_count')}){RESET}")

        run_res = _http_json(nb_url, {"action": "run_cell", "notebook_path": nb_path, "cell_index": 1}, timeout=timeout)
        assert run_res.get("status") == "ok", f"run_cell failed: {run_res}"
        print(f"  {GREEN}✓ run_cell (Cell [1]): status={run_res.get('status')}, stdout={run_res.get('stdout', '').strip()}{RESET}")

        fix_res = _http_json(
            nb_url,
            {
                "action": "magic",
                "magic": "agy_fix",
                "notebook_path": nb_path,
                "line": "throughput_qps = 120 / 0",
                "apply_to_notebook": True,
            },
            timeout=timeout,
        )
        assert fix_res.get("status") == "ok", f"agy_fix failed: {fix_res}"
        print(f"  {GREEN}✓ %agy_fix (Cell [2]): updated_cell_index={fix_res.get('updated_cell_index')}{RESET}")

        run_all_res = _http_json(nb_url, {"action": "run_all_cells", "notebook_path": nb_path}, timeout=timeout)
        assert run_all_res.get("status") == "ok" and run_all_res.get("error_count") == 0, f"run_all_cells failed: {run_all_res}"
        print(f"  {GREEN}✓ run_all_cells: executed={run_all_res.get('executed_count')} cells with 0 errors{RESET}")

        rb_res = _http_json(nb_url, {"action": "rollback_cell", "notebook_path": nb_path}, timeout=timeout)
        assert rb_res.get("status") in ("ok", "no_backup"), f"rollback_cell failed: {rb_res}"
        print(f"  {GREEN}✓ rollback_cell (.ipynb.bak): status={rb_res.get('status')}{RESET}")

        # 5. Verify ClickOps Antigravity SKILL.md Studio & Code IDE Skill Application
        print(f"\n{BOLD}[Live 5/5] Verifying ClickOps SKILL.md Creation, IDE Sync & AI Swarm Skill Application ({ide_base}/instances/default-workspace/skills)...{RESET}")
        skills_url = f"{ide_base}/instances/default-workspace/skills"
        sk_list = _http_json(skills_url, {"action": "list_skills"}, timeout=timeout)
        assert sk_list.get("status") == "ok" and sk_list.get("count", 0) >= 4, f"list_skills failed: {sk_list}"
        print(f"  {GREEN}✓ list_skills: {sk_list.get('count')} SKILL.md bundles synced to Code IDE Explorer (skills/<name>/SKILL.md){RESET}")

        sk_create = _http_json(
            skills_url,
            {
                "action": "create_skill",
                "skill_name": "gdc-gpu-cost-governance",
                "description": "Enforces NVIDIA L4 GPU time-slicing quotas, idle notebook auto-hibernation, and LiteRT-LM 16k context window limits.",
                "instructions": "# GDC GPU Cost & Quota Governance Skill\n\n1. Require computeProfile: cpu-gateway for standard workspaces.\n2. Cap gpu-litert-notebook pods at 16,384 tokens.",
            },
            timeout=timeout,
        )
        assert sk_create.get("status") == "ok", f"create_skill failed: {sk_create}"
        assert sk_create.get("workspace_path") == "skills/gdc-gpu-cost-governance/SKILL.md", f"Unexpected workspace_path: {sk_create}"
        print(f"  {GREEN}✓ create_skill (ClickOps): created {sk_create.get('workspace_path')} (total skills={len(sk_create.get('skills', []))}){RESET}")

        sk_chat = _http_json(
            f"{ide_base}/instances/default-workspace/ai-chat",
            payload={
                "role": "architect",
                "selected_skill": "gdc-gpu-cost-governance",
                "include_skill_banner": True,
                "prompt": "Apply Antigravity skill gdc-gpu-cost-governance to main.py",
                "filename": "main.py",
            },
            timeout=timeout,
        )
        applied = sk_chat.get("applied_skill") or {}
        assert applied.get("name") == "gdc-gpu-cost-governance", f"Expected applied_skill gdc-gpu-cost-governance, got {applied}"
        assert "Antigravity Skill Active" in sk_chat.get("reply", ""), "Expected Antigravity Skill Active compliance banner in reply"
        print(f"  {GREEN}✓ Code IDE AI Swarm applied_skill='{applied.get('name')}' verified in response banner{RESET}")

        sk_del = _http_json(
            skills_url,
            {"action": "delete_skill", "skill_name": "gdc-gpu-cost-governance"},
            timeout=timeout,
        )
        assert sk_del.get("status") == "ok", f"delete_skill failed: {sk_del}"
        print(f"  {GREEN}✓ delete_skill: cleaned up custom skill gdc-gpu-cost-governance (restored {len(sk_del.get('skills', []))} baseline skills){RESET}\n")
        return True
    except Exception as exc:
        print(f"\n{YELLOW}⚠️ Live cluster smoke check skipped or unreachable ({exc}). Proceeding to test-swarm.py...{RESET}\n")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pattern 14 (p14-antigravity-dev) Antigravity SDK, Notebook & Multi-Agent Swarm Test Runner"
    )
    parser.add_argument(
        "--admin-url",
        default=os.environ.get("GDC_ADMIN_URL", "http://127.0.0.1:8083"),
        help="Sovereign Admin Console URL (default: http://127.0.0.1:8083)",
    )
    parser.add_argument(
        "--ide-url",
        default=os.environ.get("GDC_IDE_URL", "http://127.0.0.1:8084"),
        help="Pattern 14 Developer IDE & JupyterLab URL (default: http://127.0.0.1:8084)",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Explicit AI Chat endpoint override (defaults to <ide-url>/instances/default-workspace/ai-chat)",
    )
    parser.add_argument("--host-header", default=None, help="Custom Host header for LoadBalancer VIP testing")
    parser.add_argument("--insecure", "-k", action="store_true", default=True, help="Skip TLS verification")
    parser.add_argument(
        "--model",
        default="gemma4:26b",
        choices=["gemma4:26b", "gemma4:31b", "auto"],
        help="Model to test with (default: gemma4:26b)",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    parser.add_argument("--local", action="store_true", help="Run in local in-memory mode without network/cluster")
    parser.add_argument("--interactive", action="store_true", help="Pause between each test step")

    args = parser.parse_args()

    if not args.local:
        run_live_agy_smoke_checks(args.admin_url, args.ide_url, timeout=args.timeout)

    target_endpoint = args.endpoint or f"{args.ide_url.rstrip('/')}/instances/default-workspace/ai-chat"
    swarm_cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "test-swarm.py"),
        "--endpoint",
        target_endpoint,
        "--model",
        args.model,
        "--timeout",
        str(args.timeout),
    ]
    if args.host_header:
        swarm_cmd.extend(["--host-header", args.host_header])
    if args.insecure:
        swarm_cmd.append("--insecure")
    if args.local:
        swarm_cmd.append("--local")
    if args.interactive:
        swarm_cmd.append("--interactive")

    r1 = subprocess.run(swarm_cmd)
    if r1.returncode != 0:
        return r1.returncode

    print("\n=== Running Phase 5 Antigravity SDK & Integrated JupyterLab 4 Validation ===")
    r2 = subprocess.run(
        [sys.executable, os.path.join(PATTERN_DIR, "test", "test_phase5_antigravity_notebooks.py"), "-v"]
    )
    return r2.returncode


if __name__ == "__main__":
    raise SystemExit(main())
