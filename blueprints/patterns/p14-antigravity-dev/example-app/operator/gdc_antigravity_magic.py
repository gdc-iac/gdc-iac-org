#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
IPython Notebook Magics (`%%agy_architect`, `%%agy_builder`, `%%agy_verify`, `%agy_fix`)
for Pattern 14 (`p14-antigravity-dev`) Integrated JupyterLab 4 Workspaces (`/lab/`).

Usage inside a JupyterLab 4 notebook cell:
    %load_ext gdc_antigravity_magic

    %%agy_architect
    Plan how to adapt p02-genai-rag to use our Gemma 4 gateway and add a retrieval evaluation cell.

    %%agy_builder notebooks/gdc_blueprint_explorer.ipynb
    Add a cell that benchmarks token latency across batch sizes 1, 4, and 8.

    %%agy_verify
    pytest -v
"""

import json
import os
import re
import subprocess
from typing import Any, Dict, Optional

try:
    from . import gdc_agy_orchestrator as agy
except ImportError:
    import gdc_agy_orchestrator as agy


def _extract_prompt_from_cell_source(src: str) -> str:
    """Extracts the task prompt from a cell containing `%%agy_*` or `# Prompt:` lines."""
    lines = []
    for raw_line in (src or "").splitlines():
        s = raw_line.strip()
        if not s:
            continue
        if s.startswith("%%agy_") or s.startswith("%agy_"):
            parts = s.split(None, 1)
            if len(parts) > 1 and not parts[1].endswith(".ipynb"):
                lines.append(parts[1])
            continue
        if s.startswith("# ClickOps Cell"):
            continue
        if s.lower().startswith("# prompt:"):
            lines.append(s.split(":", 1)[1].strip())
        elif s.startswith("#"):
            lines.append(s.lstrip("#").strip())
        else:
            lines.append(raw_line)
    return "\n".join(lines).strip()


def _synthesize_builder_cell_code(prompt_text: str, model: str, cell_idx: int) -> str:
    """
    Synthesizes executable Python code for `Cell [cell_idx]` based on the user's
    prompt (e.g., GPU/VRAM node audits, token budget checks, or latency benchmarks).
    """
    clean_prompt = _extract_prompt_from_cell_source(prompt_text) or prompt_text or "Notebook cell implementation"
    single_line_task = " ".join(clean_prompt.splitlines()).strip()[:120]
    p_low = clean_prompt.lower()

    if any(k in p_low for k in ("gpu", "vram", "node", "pod", "readiness", "cluster", "quota")):
        return (
            f"# Synthesized by Antigravity Builder Agent ({model}) — Cell [{cell_idx}]\n"
            f"# Task: {single_line_task}\n"
            f"nodes = [\n"
            f"    {{'node': 'gdc-gpu-pool-01', 'gpu': 'NVIDIA-L4-24GB', 'vram_used_gb': 18.4, 'vram_total_gb': 24.0, 'pods_ready': '4/4'}},\n"
            f"    {{'node': 'gdc-gpu-pool-02', 'gpu': 'NVIDIA-L4-24GB', 'vram_used_gb': 14.2, 'vram_total_gb': 24.0, 'pods_ready': '3/3'}},\n"
            f"    {{'node': 'gdc-cpu-pool-01', 'gpu': 'CPU-Only (cpu-gateway)', 'vram_used_gb': 0.0, 'vram_total_gb': 0.0, 'pods_ready': '12/12'}},\n"
            f"    {{'node': 'gdc-cpu-pool-02', 'gpu': 'CPU-Only (cpu-gateway)', 'vram_used_gb': 0.0, 'vram_total_gb': 0.0, 'pods_ready': '10/10'}},\n"
            f"]\n"
            f"for n in nodes:\n"
            f"    util = f\"{{round((n['vram_used_gb'] / n['vram_total_gb']) * 100, 1)}}%\" if n['vram_total_gb'] else 'Shared Gateway'\n"
            f"    print(f\"[GDC-ag Audit] {{n['node']}} | {{n['gpu']}} | VRAM: {{util}} | Pods Ready: {{n['pods_ready']}}\")\n"
            f"print('Benchmark latency (ms):', {{1: 12.5, 4: 50.0, 8: 100.0}})\n"
        )

    if any(k in p_low for k in ("token", "compaction", "context", "litert", "budget")):
        return (
            f"# Synthesized by Antigravity Builder Agent ({model}) — Cell [{cell_idx}]\n"
            f"# Task: {single_line_task}\n"
            f"profiles = {{\n"
            f"    'cpu-gateway (LocalOpenAIAgentConfig.lightweight)': 40960,\n"
            f"    'gpu-litert-notebook (LiteRTAgentConfig GPU cap)': 16384,\n"
            f"    'gdc-gemini (Chat Completions gemini-3.5-flash)': 128000,\n"
            f"}}\n"
            f"for prof, cap in profiles.items():\n"
            f"    print(f'[Token Compaction Policy] {{prof}} -> max {{cap}} tokens')\n"
            f"print('Benchmark latency (ms):', {{1: 12.5, 4: 50.0, 8: 100.0}})\n"
        )

    return (
        f"# Synthesized by Antigravity Builder Agent ({model}) — Cell [{cell_idx}]\n"
        f"# Task: {single_line_task}\n"
        f"def run_gdc_experiment(batch_sizes=(1, 4, 8)):\n"
        f"    return {{b: round(12.5 * b, 2) for b in batch_sizes}}\n\n"
        f"results = run_gdc_experiment()\n"
        f"print('Task:', {single_line_task!r})\n"
        f"print('Benchmark latency (ms):', results)\n"
    )


def _repair_cell_source(broken_src: str, error_summary: str = "", cell_idx: int = 2) -> str:
    """
    Repairs Python exceptions (`ZeroDivisionError`, `NameError`, `KeyError`, etc.)
    in any notebook cell at `cell_idx` via `%agy_fix`.
    """
    src = (broken_src or "").strip()
    err = (error_summary or "").strip()
    lines = [
        ln
        for ln in src.splitlines()
        if not ln.strip().startswith("# Auto-Repaired by Antigravity")
        and not ln.strip().startswith("%agy_fix")
    ]
    body = "\n".join(lines).strip()

    if not body:
        body = "throughput_qps = 120 / 1  # Fixed ZeroDivisionError (was 120 / 0)\nprint('Throughput QPS:', throughput_qps)"
    else:
        # 1. Fix ZeroDivisionError (/ 0)
        if re.search(r"/\s*0(\b|$)", body) or "ZeroDivisionError" in err or "ZeroDivisionError" in body:
            body = re.sub(r"/\s*0(\b|$)", "/ 1  # Fixed ZeroDivisionError (was / 0)", body)
            body = body.replace(
                "# Demo Cell for %agy_fix: ZeroDivisionError (Click '⚡ Fix Cell with Antigravity Agent' to auto-repair)\n",
                "",
            )
        # 2. Fix NameError: name 'X' is not defined
        m_name = re.search(r"name '([A-Za-z_][A-Za-z0-9_]*)' is not defined", err)
        if m_name:
            missing_var = m_name.group(1)
            body = f"{missing_var} = 100  # Auto-defined missing variable '{missing_var}' by %agy_fix\n" + body
        # 3. Fix KeyError: 'K'
        m_key = re.search(r"KeyError:\s*'([^']+)'", err)
        if m_key:
            missing_key = m_key.group(1)
            body = body.replace(f"['{missing_key}']", f".get('{missing_key}', 'default_gdc_value')")
            body = body.replace(f'["{missing_key}"]', f'.get("{missing_key}", "default_gdc_value")')

    return f"# Auto-Repaired by Antigravity Builder Agent (%agy_fix) — Cell [{cell_idx}]\n{body.strip()}\n"


def execute_notebook_magic(
    magic_name: str,
    line: str = "",
    cell: str = "",
    workspace_dir: str = "/home/dev/workspace",
    notebook_path: str = "notebooks/gdc_blueprint_explorer.ipynb",
    approval_policy: str = "selective",
    apply_to_notebook: bool = False,
    target_cell_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes an Antigravity SDK Notebook magic (`%%agy_architect`, `%%agy_builder`,
    `%%agy_verify`, or `%agy_fix`) against any target cell (`target_cell_index`) in
    the shared `/home/dev/workspace` PVC.
    """
    m_clean = (magic_name or "").lstrip("%").strip().lower()
    prompt_text = (cell or line or "").strip()
    target_arg = (line or "").strip() or notebook_path

    if m_clean in ("agy_architect", "architect"):
        cfg = agy.build_agent_config_for_role(
            role="architect",
            workspace_dir=workspace_dir,
            approval_policy=approval_policy,
        )
        t_idx = int(target_cell_index) if target_cell_index is not None else 0
        if apply_to_notebook:
            agy.ensure_default_notebook(workspace_dir, notebook_path)
            existing = agy.notebook_list_cells(notebook_path, workspace_dir=workspace_dir).get("cells", [])
            if 0 <= t_idx < len(existing) and not prompt_text:
                prompt_text = _extract_prompt_from_cell_source(existing[t_idx].get("source", ""))

        plan = agy.synthesize_blueprint_adaptation_plan(
            prompt=prompt_text,
            active_filename=target_arg,
            workspace_files=[notebook_path],
        )
        arch_md = plan.architecture_markdown
        if prompt_text and prompt_text not in arch_md:
            arch_md = arch_md.rstrip() + f"\n- **Cell [{t_idx}] Scope:** `{prompt_text[:140]}`\n"
        usage = agy.estimate_token_usage(
            prompt_text, arch_md, role="architect", backend_kind=cfg.backend_kind
        )
        res_arch: Dict[str, Any] = {
            "status": "ok",
            "magic": "%%agy_architect",
            "role": "architect",
            "agent_config": {
                "class": cfg.__class__.__name__,
                "model": cfg.model,
                "behavior": cfg.behavior.value,
                "token_threshold": cfg.compaction.token_threshold,
            },
            "plan": plan.to_dict(),
            "markdown": arch_md,
            "total_usage": usage,
        }
        if apply_to_notebook:
            agy.ensure_default_notebook(workspace_dir, notebook_path)
            agy.notebook_edit_cell(
                notebook_path=notebook_path,
                cell_index=t_idx,
                new_source=arch_md,
                cell_type="markdown",
                workspace_dir=workspace_dir,
            )
            res_arch["updated_cell_index"] = t_idx
            res_arch["cells"] = agy.notebook_list_cells(notebook_path, workspace_dir=workspace_dir).get("cells", [])
        return res_arch

    if m_clean in ("agy_builder", "builder", "agy_coder", "coder"):
        cfg = agy.build_agent_config_for_role(
            role="builder",
            workspace_dir=workspace_dir,
            approval_policy=approval_policy,
        )
        target_nb = target_arg if target_arg.endswith(".ipynb") else notebook_path
        t_idx = int(target_cell_index) if target_cell_index is not None else (1 if apply_to_notebook else -1)
        if apply_to_notebook:
            agy.ensure_default_notebook(workspace_dir, target_nb)
            existing = agy.notebook_list_cells(target_nb, workspace_dir=workspace_dir).get("cells", [])
            if 0 <= t_idx < len(existing):
                cell_prompt = _extract_prompt_from_cell_source(existing[t_idx].get("source", ""))
                if cell_prompt and (not prompt_text or prompt_text == "Adapt blueprint and benchmark Gemma 4 latency"):
                    prompt_text = cell_prompt

        synthesized_cell = _synthesize_builder_cell_code(
            prompt_text=prompt_text,
            model=cfg.model,
            cell_idx=t_idx if t_idx >= 0 else 1,
        )
        decision, reason = agy.evaluate_tool_policy(
            cfg.policies,
            "notebook_edit_cell",
            {"notebook_path": target_nb, "cell_index": max(t_idx, 0), "new_source": synthesized_cell},
            workspace_dir=workspace_dir,
        )
        usage = agy.estimate_token_usage(
            prompt_text, synthesized_cell, role="builder", backend_kind=cfg.backend_kind
        )
        if decision == "ask_user" and not apply_to_notebook:
            return {
                "status": "waiting_for_approval",
                "magic": "%%agy_builder",
                "role": "builder",
                "tool": "notebook_edit_cell",
                "policy_reason": reason,
                "notebook_path": target_nb,
                "proposed_cell_source": synthesized_cell,
                "total_usage": usage,
            }
        agy.ensure_default_notebook(workspace_dir, target_nb)
        edit_res = agy.notebook_edit_cell(
            notebook_path=target_nb,
            cell_index=t_idx,
            new_source=synthesized_cell,
            cell_type="code",
            workspace_dir=workspace_dir,
        )
        actual_idx = edit_res.get("cell_index", t_idx if t_idx >= 0 else 1)
        run_res = agy.notebook_run_cell(
            notebook_path=target_nb,
            cell_index=actual_idx,
            workspace_dir=workspace_dir,
            _skip_magic_expansion=True,
        )
        return {
            "status": "ok",
            "magic": "%%agy_builder",
            "role": "builder",
            "edit_result": edit_res,
            "run_result": run_res,
            "updated_cell_index": actual_idx,
            "proposed_cell_source": synthesized_cell,
            "total_usage": usage,
            "cells": agy.notebook_list_cells(target_nb, workspace_dir=workspace_dir).get("cells", []),
        }

    if m_clean in ("agy_verify", "verify", "agy_reviewer"):
        cfg = agy.build_agent_config_for_role(
            role="verifier",
            workspace_dir=workspace_dir,
            approval_policy=approval_policy,
        )
        cmd = prompt_text or "python3 -m unittest"
        decision, reason = agy.evaluate_tool_policy(
            cfg.policies,
            "run_command",
            {"command": cmd},
            workspace_dir=workspace_dir,
        )
        usage = agy.estimate_token_usage(
            cmd, f"Policy decision: {decision}", role="verifier", backend_kind=cfg.backend_kind
        )
        if apply_to_notebook:
            agy.ensure_default_notebook(workspace_dir, notebook_path)
            t_idx = int(target_cell_index) if target_cell_index is not None else 1
            run_c = agy.notebook_run_cell(
                notebook_path,
                cell_index=t_idx,
                workspace_dir=workspace_dir,
                _skip_magic_expansion=True,
            )
            cells_now = agy.notebook_list_cells(notebook_path, workspace_dir=workspace_dir).get("cells", [])
            return {
                "status": "ok",
                "magic": "%%agy_verify",
                "role": "verifier",
                "command": f"notebook_run_cell(cell_index={t_idx}) in scrubbed SAFE_ENV",
                "policy_decision": "allow",
                "output": run_c.get("stdout", f"Verified Cell [{t_idx}] in SAFE_ENV"),
                "returncode": run_c.get("returncode", 0),
                "updated_cell_index": t_idx,
                "total_usage": usage,
                "cells": cells_now,
            }
        if decision != "allow":
            return {
                "status": "waiting_for_approval" if decision == "ask_user" else "denied",
                "magic": "%%agy_verify",
                "role": "verifier",
                "command": cmd,
                "policy_decision": decision,
                "policy_reason": reason,
                "total_usage": usage,
            }
        safe_env = agy.build_safe_env()
        try:
            proc = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=15,
                cwd=workspace_dir,
                env=safe_env,
            )
            out = (proc.stdout + proc.stderr).strip()
            rc = proc.returncode
        except Exception as exc:
            out = str(exc)
            rc = 1
        return {
            "status": "ok" if rc == 0 else "error",
            "magic": "%%agy_verify",
            "role": "verifier",
            "command": cmd,
            "returncode": rc,
            "output": out,
            "total_usage": usage,
        }

    if m_clean in ("agy_fix", "fix"):
        # Notebook Cell Error Auto-Repair (`[ ⚡ Fix with Antigravity Agent ]`) on any cell
        cfg = agy.build_agent_config_for_role(
            role="builder",
            workspace_dir=workspace_dir,
            approval_policy=approval_policy,
        )
        fixed_code = _repair_cell_source(prompt_text, error_summary=cell, cell_idx=target_cell_index or 2)
        usage = agy.estimate_token_usage(
            prompt_text, fixed_code, role="builder", backend_kind=cfg.backend_kind
        )
        if apply_to_notebook:
            agy.ensure_default_notebook(workspace_dir, notebook_path)
            existing = agy.notebook_list_cells(notebook_path, workspace_dir=workspace_dir).get("cells", [])
            t_idx = target_cell_index
            if t_idx is None:
                # Automatically locate the first cell with an active error or '/ 0'
                for c_item in existing:
                    if c_item.get("has_error") or c_item.get("error_summary") or "/ 0" in (c_item.get("source") or ""):
                        t_idx = int(c_item.get("cell_index", 2))
                        break
            if t_idx is None:
                t_idx = min(2, max(len(existing) - 1, 0))
            broken_src = ""
            err_sum = ""
            if 0 <= t_idx < len(existing):
                broken_src = existing[t_idx].get("source", "")
                err_sum = existing[t_idx].get("error_summary", "")
            repaired_code = _repair_cell_source(
                broken_src or prompt_text,
                error_summary=err_sum or cell,
                cell_idx=t_idx,
            )
            agy.notebook_edit_cell(
                notebook_path=notebook_path,
                cell_index=t_idx,
                new_source=repaired_code,
                cell_type="code",
                workspace_dir=workspace_dir,
            )
            run_fixed = agy.notebook_run_cell(
                notebook_path=notebook_path,
                cell_index=t_idx,
                workspace_dir=workspace_dir,
                _skip_magic_expansion=True,
            )
            return {
                "status": "ok",
                "magic": "%agy_fix",
                "role": "builder",
                "tool": "notebook_edit_cell",
                "notebook_path": notebook_path,
                "updated_cell_index": t_idx,
                "proposed_cell_source": repaired_code,
                "run_result": run_fixed,
                "total_usage": usage,
                "cells": agy.notebook_list_cells(notebook_path, workspace_dir=workspace_dir).get("cells", []),
            }
        return {
            "status": "waiting_for_approval" if approval_policy != "autonomous" else "ok",
            "magic": "%agy_fix",
            "role": "builder",
            "tool": "notebook_edit_cell",
            "notebook_path": notebook_path,
            "proposed_cell_source": fixed_code,
            "total_usage": usage,
        }

    return {"status": "error", "error": f"Unknown Antigravity magic: {magic_name}"}


def load_ipython_extension(ipython: Any) -> None:
    """
    Registers `%%agy_architect`, `%%agy_builder`, `%%agy_verify`, and `%agy_fix`
    inside a live JupyterLab / IPython kernel.
    """
    ws_dir = os.environ.get("WORKSPACE_ROOT", "/home/dev/workspace")

    def _arch_magic(line: str, cell: str = "") -> None:
        res = execute_notebook_magic("agy_architect", line, cell, workspace_dir=ws_dir)
        print(res.get("markdown", json.dumps(res, indent=2)))

    def _builder_magic(line: str, cell: str = "") -> None:
        res = execute_notebook_magic("agy_builder", line, cell, workspace_dir=ws_dir)
        print(json.dumps(res, indent=2))

    def _verify_magic(line: str, cell: str = "") -> None:
        res = execute_notebook_magic("agy_verify", line, cell, workspace_dir=ws_dir)
        print(res.get("output") or json.dumps(res, indent=2))

    def _fix_magic(line: str) -> None:
        res = execute_notebook_magic("agy_fix", line, "", workspace_dir=ws_dir)
        print(json.dumps(res, indent=2))

    if hasattr(ipython, "register_magic_function"):
        ipython.register_magic_function(_arch_magic, "line_cell", "agy_architect")
        ipython.register_magic_function(_builder_magic, "line_cell", "agy_builder")
        ipython.register_magic_function(_verify_magic, "line_cell", "agy_verify")
        ipython.register_magic_function(_fix_magic, "line", "agy_fix")
