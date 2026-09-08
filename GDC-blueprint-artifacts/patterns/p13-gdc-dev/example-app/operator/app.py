#!/usr/bin/env python3
"""
@file app.py
@brief GDC Developer Environment Operator Service (Phase 1, Phase 2, & Phase 3 Agentic Platform).

@details Serves the IDE landing page and session service, validating identity headers according to the
configured AUTH_MODE (Phase 1 mock header vs Phase 2 Keycloak OIDC). When under OIDC mode
and unauthenticated ("anonymous"), renders an enterprise Keycloak OIDC login portal.
Supports optional GDC Dev AI Coder Dock (Phase 2) and full In-Pod Agentic AI ReAct engine (Phase 3)
with tool calling (read_file, apply_diff, write_file, run_terminal_command, list_directory),
selective auto-approval, visual diff preview, terminal auto-repair hook, and model tiering.

@date 2026-09-01
"""

import os
import time
import socket
import json
import subprocess
import urllib.request
import urllib.error
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

HEADER_USER_KEY = os.environ.get("HEADER_USER_KEY", "X-User-ID")
MOCK_USER_ID = os.environ.get("MOCK_USER_ID", "dev-user-1")

# Module-level connection opener avoiding handler reconstruction per request
AI_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

WORKSPACE_ROOT = os.environ.get("DEV_WORKSPACE_ROOT", os.environ.get("THEIA_WORKSPACE_ROOT", "/tmp/workspace"))

def ensure_workspace_dir(workspace_dir=None, session_id="default-workspace", user_id="oidc-developer@gdc.local"):
    """Ensures workspace directory exists and has base entrypoint files on disk."""
    if workspace_dir is None:
        workspace_dir = WORKSPACE_ROOT
    os.makedirs(workspace_dir, exist_ok=True)
    main_py = os.path.join(workspace_dir, "main.py")
    if not os.path.exists(main_py):
        init_content = (
            "import os\nimport sys\n\n"
            "# Welcome to your resilient air-gapped GDC Developer Environment!\n"
            "def main():\n"
            f"    print(\"Workspace ID : {session_id}\")\n"
            f"    print(\"Active User  : {user_id}\")\n"
            "    print(\"Ready for high-security cloud development.\")\n\n"
            "if __name__ == \"__main__\":\n"
            "    main()\n"
        )
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(init_content)
    readme_md = os.path.join(workspace_dir, "README.md")
    if not os.path.exists(readme_md):
        with open(readme_md, "w", encoding="utf-8") as f:
            f.write(f"# Workspace: {session_id}\n\nResilient GDC Developer Environment (gdc-dev) on Google Distributed Cloud (Air-Gapped).\n")

def load_workspace_files(workspace_dir=None):
    """Recursively loads all text files from the workspace directory."""
    if workspace_dir is None:
        workspace_dir = WORKSPACE_ROOT
    if not os.path.exists(workspace_dir):
        return {}
    loaded = {}
    for root, dirs, files in os.walk(workspace_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in files:
            if f.startswith(".") or f.endswith(".pyc"):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, workspace_dir)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                    loaded[rel_path] = fh.read()
            except Exception:
                pass
    return loaded

def save_workspace_files(files_dict, workspace_dir=None):
    """Writes a dictionary of relative paths and content to workspace disk."""
    if workspace_dir is None:
        workspace_dir = WORKSPACE_ROOT
    os.makedirs(workspace_dir, exist_ok=True)
    for rel_path, content in files_dict.items():
        full_path = os.path.join(workspace_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)

PROJECT_TEMPLATES = {
    "telemetry": {
        "name": "📐 GDC Air-Gapped Telemetry Service",
        "description": "Modular telemetry collector with CPU, memory, and disk health probes + pytest suites.",
        "files": {
            "main.py": (
                "import os\nimport sys\nfrom telemetry import collect_metrics\n\n"
                "def main():\n"
                "    print('=== GDC Sovereign Telemetry Service ===')\n"
                "    metrics = collect_metrics()\n"
                "    for k, v in metrics.items():\n"
                "        print(f'  {k}: {v}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "telemetry.py": (
                "import os\nimport platform\n\n"
                "def collect_metrics():\n"
                "    return {\n"
                "        'service': 'gdc-telemetry',\n"
                "        'status': 'HEALTHY',\n"
                "        'cpu_load': '0.12',\n"
                "        'memory_util': '38%',\n"
                "        'disk_status': 'OK',\n"
                "        'air_gapped': True\n"
                "    }\n"
            ),
            "test_telemetry.py": (
                "import unittest\nfrom telemetry import collect_metrics\n\n"
                "class TestTelemetry(unittest.TestCase):\n"
                "    def test_metrics(self):\n"
                "        m = collect_metrics()\n"
                "        self.assertEqual(m['status'], 'HEALTHY')\n"
                "        self.assertTrue(m['air_gapped'])\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
            "README.md": (
                "# GDC Telemetry Service\n\n"
                "Modular telemetry and liveness probe service for sovereign GDC clusters.\n"
            )
        }
    },
    "microservice": {
        "name": "🚀 Python Sovereign Microservice",
        "description": "Standard air-gapped Python service with health checks and unit tests.",
        "files": {
            "main.py": (
                "import os\nimport sys\n\n"
                "def get_health():\n"
                "    return {'status': 'healthy', 'cloud': 'GDC-AirGapped'}\n\n"
                "def main():\n"
                "    print(f'Starting Microservice... Health: {get_health()}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "test_main.py": (
                "import unittest\nfrom main import get_health\n\n"
                "class TestMicroservice(unittest.TestCase):\n"
                "    def test_health(self):\n"
                "        h = get_health()\n"
                "        self.assertEqual(h['status'], 'healthy')\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
            "requirements.txt": "pytest>=7.0.0\n",
            "README.md": (
                "# Sovereign Microservice\n\n"
                "Modular Python microservice designed for sovereign GDC air-gapped deployment.\n"
            )
        }
    },
    "clean": {
        "name": "🧹 Clean Starting Workspace",
        "description": "Remove all existing files and start with a minimal main.py and README.md.",
        "files": {
            "main.py": (
                "import os\nimport sys\n\n"
                "def main():\n"
                "    print('Clean workspace initialized.')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "README.md": (
                "# Clean Workspace\n\n"
                "Ready for new application development.\n"
            )
        }
    }
}

def reset_project(template_name, session_id="default-workspace", user_id="oidc-developer@gdc.local", workspace_dir=None):
    """Cleans all workspace files and initializes chosen project template."""
    if workspace_dir is None:
        workspace_dir = WORKSPACE_ROOT
    os.makedirs(workspace_dir, exist_ok=True)
    for root, dirs, files in os.walk(workspace_dir, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except Exception:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except Exception:
                pass
    
    template = PROJECT_TEMPLATES.get(template_name, PROJECT_TEMPLATES["clean"])
    files_to_create = template["files"]
    save_workspace_files(files_to_create, workspace_dir)
    return files_to_create

PROJECTS_ROOT = os.environ.get("DEV_PROJECTS_ROOT", os.environ.get("THEIA_PROJECTS_ROOT", "/tmp/dev-projects"))

def get_workspace_dir(session_id="default-workspace"):
    """Returns the workspace directory for a specific project/session."""
    clean_id = "".join(c for c in str(session_id) if c.isalnum() or c in ("-", "_")).strip()
    if not clean_id or clean_id == "default-workspace":
        return WORKSPACE_ROOT
    proj_dir = os.path.join(PROJECTS_ROOT, clean_id)
    os.makedirs(proj_dir, exist_ok=True)
    return proj_dir

def list_projects():
    """Lists all available projects and their file counts."""
    projects = []
    # 1. default-workspace
    ensure_workspace_dir(workspace_dir=WORKSPACE_ROOT, session_id="default-workspace")
    def_files = load_workspace_files(workspace_dir=WORKSPACE_ROOT)
    projects.append({
        "name": "default-workspace",
        "path": WORKSPACE_ROOT,
        "file_count": len(def_files),
        "files": sorted(list(def_files.keys()))
    })
    # 2. Named projects under PROJECTS_ROOT
    if os.path.exists(PROJECTS_ROOT):
        for item in sorted(os.listdir(PROJECTS_ROOT)):
            full_item = os.path.join(PROJECTS_ROOT, item)
            if os.path.isdir(full_item) and item != "default-workspace":
                p_files = load_workspace_files(workspace_dir=full_item)
                projects.append({
                    "name": item,
                    "path": full_item,
                    "file_count": len(p_files),
                    "files": sorted(list(p_files.keys()))
                })
    return projects

def delete_project(project_name):
    """Deletes a project directory and all its files from disk."""
    clean_name = "".join(c for c in str(project_name) if c.isalnum() or c in ("-", "_")).strip()
    if not clean_name:
        return False, "Invalid project name"
    if clean_name == "default-workspace":
        reset_project("clean", workspace_dir=WORKSPACE_ROOT, session_id="default-workspace")
        return True, "Reset default-workspace to clean state"
    
    target_dir = os.path.join(PROJECTS_ROOT, clean_name)
    if os.path.exists(target_dir):
        import shutil
        shutil.rmtree(target_dir, ignore_errors=True)
        return True, f"Project '{clean_name}' and all its files deleted"
    return False, f"Project '{clean_name}' not found"

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path in workspace"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path in workspace"},
                    "content": {"type": "string", "description": "New content for the file"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_diff",
            "description": "Apply a surgical diff patch to replace a target block of code in an existing file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path"},
                    "target_block": {"type": "string", "description": "Existing block of code to match and replace"},
                    "replacement_block": {"type": "string", "description": "New replacement block of code"}
                },
                "required": ["path", "target_block", "replacement_block"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Safely execute a shell command in the workspace terminal sandbox (read-only verification/tests).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run (e.g. pytest, python3 main.py, ls -la)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default '.')"}
                },
                "required": []
            }
        }
    }
]

def classify_tool_permission(tool_name):
    """Classifies tool permission levels under the Selective Auto-Approval policy."""
    if tool_name in ("read_file", "list_directory"):
        return "AUTO_APPROVED"
    elif tool_name in ("apply_diff", "write_file"):
        return "REQUIRES_DIFF_APPROVAL"
    elif tool_name == "run_terminal_command":
        return "REQUIRES_COMMAND_APPROVAL"
    return "REQUIRES_EXPLICIT_APPROVAL"

def execute_tool(tool_name, args, files_dict, workspace_dir=None):
    """Safely executes an in-pod workspace tool against memory buffers and persistent files."""
    if workspace_dir is None:
        workspace_dir = WORKSPACE_ROOT
    os.makedirs(workspace_dir, exist_ok=True)

    if tool_name == "read_file":
        path = args.get("path", "")
        if path in files_dict:
            return True, files_dict[path]
        full_path = os.path.join(workspace_dir, path)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    files_dict[path] = content
                    return True, content
            except Exception as e:
                return False, f"Error reading {path}: {e}"
        return False, f"File '{path}' not found in workspace"

    elif tool_name == "apply_diff":
        path = args.get("path", "")
        target = args.get("target_block", "")
        replacement = args.get("replacement_block", "")
        
        content = files_dict.get(path)
        if content is None:
            full_path = os.path.join(workspace_dir, path)
            if os.path.isfile(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                return False, f"File '{path}' not found"

        if target not in content:
            target_norm = target.replace("\r\n", "\n")
            content_norm = content.replace("\r\n", "\n")
            if target_norm in content_norm:
                new_content = content_norm.replace(target_norm, replacement, 1)
            elif target.strip() in content:
                new_content = content.replace(target.strip(), replacement, 1)
            elif not target.strip():
                new_content = content + "\n" + replacement
            else:
                target_lines = [line.strip() for line in target.splitlines() if line.strip()]
                content_lines = content.splitlines()
                matched = False
                if target_lines:
                    for i in range(len(content_lines) - len(target_lines) + 1):
                        if all(content_lines[i + j].strip() == target_lines[j] for j in range(len(target_lines))):
                            before = "\n".join(content_lines[:i])
                            after = "\n".join(content_lines[i + len(target_lines):])
                            parts = [p for p in [before, replacement, after] if p]
                            new_content = "\n".join(parts)
                            matched = True
                            break
                if not matched:
                    return False, f"Target block not found in '{path}'"
        else:
            new_content = content.replace(target, replacement, 1)

        files_dict[path] = new_content
        full_path = os.path.join(workspace_dir, path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception:
            pass
        return True, f"Successfully applied surgical patch to '{path}'"

    elif tool_name == "write_file":
        path = args.get("path", "")
        content = args.get("content", "")
        files_dict[path] = content
        full_path = os.path.join(workspace_dir, path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass
        return True, f"Successfully created/updated '{path}'"

    elif tool_name == "list_directory":
        path = args.get("path", ".")
        target_dir = os.path.normpath(os.path.join(workspace_dir, path))
        disk_files = []
        if os.path.isdir(target_dir):
            for root, _, f_list in os.walk(target_dir):
                for f in f_list:
                    if not f.startswith("."):
                        disk_files.append(os.path.relpath(os.path.join(root, f), workspace_dir))
        all_files = sorted(list(set(list(files_dict.keys()) + disk_files)))
        return True, json.dumps({"files": all_files, "directory": path})

    elif tool_name == "run_terminal_command":
        cmd = args.get("command", "")
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15, cwd=workspace_dir)
            out = (res.stdout + res.stderr).strip()
            return True, out if out else f"Command completed with exit code {res.returncode}"
        except Exception as e:
            return False, f"Command execution failed: {e}"

    return False, f"Unknown tool: {tool_name}"

SWARM_PERSONAS = {
    "architect": {
        "name": "📐 Architect Agent",
        "role_title": "Architecture & Planning",
        "badge": "Architect",
        "system_prompt": (
            "You are the GDC Dev Architect Agent in Google Distributed Cloud (gdc-dev) Air-Gapped. "
            "Your responsibility is high-level architectural planning, system modularity, "
            "interface design, file scaffolding, and breaking complex engineering tasks into clear, actionable steps. "
            "When given a task, inspect workspace context, examine file trees, and formulate a structured, phased technical blueprint. "
            "Focus on clean architecture, component isolation, and air-gapped security boundaries."
        ),
        "tools": ["read_file", "list_directory"]
    },
    "coder": {
        "name": "💻 Coder Agent",
        "role_title": "Implementation & Diffs",
        "badge": "Coder",
        "system_prompt": (
            "You are the GDC Dev Coder Agent in Google Distributed Cloud (gdc-dev) Air-Gapped. "
            "Your responsibility is robust, surgical code implementation and refactoring. "
            "You write clean, production-ready code adhering to existing project style. "
            "The active file content is already provided in the prompt context, so do not call read_file unless you need other files. "
            "You author surgical unified diffs using `apply_diff` or create new files using `write_file`. "
            "Minimize code churn and adhere strictly to the architectural design."
        ),
        "tools": ["read_file", "write_file", "apply_diff"]
    },
    "reviewer": {
        "name": "🔍 Reviewer / QA Agent",
        "role_title": "QA & Security Audit",
        "badge": "Reviewer",
        "system_prompt": (
            "You are the GDC Dev Reviewer / QA Agent in Google Distributed Cloud (gdc-dev) Air-Gapped. "
            "Your responsibility is code verification, automated unit test synthesis (pytest/unittest), "
            "syntax and edge case analysis, security boundary checks, and regression verification. "
            "You test code using `run_terminal_command` and identify potential bugs, regressions, or vulnerabilities."
        ),
        "tools": ["read_file", "run_terminal_command"]
    },
    "swarm": {
        "name": "🐝 Multi-Agent Swarm",
        "role_title": "Collaborative Swarm",
        "badge": "Swarm",
        "system_prompt": (
            "You are the GDC Dev Multi-Agent Swarm Coordinator in Google Distributed Cloud (gdc-dev) Air-Gapped. "
            "You orchestrate a specialized 3-agent developer team (📐 Architect, 💻 Coder, 🔍 Reviewer). "
            "For complex engineering requests, coordinate all 3 perspectives in your response:\n"
            "1. [📐 Architect Plan]: Analyze existing code, directory structure, and state the technical strategy.\n"
            "2. [💻 Coder Implementation]: Provide the concrete implementation or call `apply_diff` / `write_file`.\n"
            "3. [🔍 Reviewer QA]: Provide unit test verification, edge case checklist, and command to run.\n"
            "Use tools (read_file, apply_diff, write_file, run_terminal_command, list_directory) as needed."
        ),
        "tools": ["read_file", "write_file", "apply_diff", "run_terminal_command", "list_directory"]
    }
}

AI_CSS = """
.ai-resizer { width: 6px; background: #252526; border-left: 1px solid #383838; border-right: 1px solid #1e1e1e; cursor: col-resize; transition: background 0.15s ease; user-select: none; display: flex; align-items: center; justify-content: center; flex-shrink: 0; z-index: 10; }
.ai-resizer:hover, .ai-resizer.resizing { background: #58a6ff; }
.ai-resizer::after { content: ''; width: 2px; height: 36px; background: #6e7681; border-radius: 1px; }
.ai-resizer:hover::after, .ai-resizer.resizing::after { background: #ffffff; }
.ai-sidebar { width: 380px; min-width: 260px; max-width: 85vw; background: #252526; border-left: none; display: flex; flex-direction: column; flex-shrink: 0; }
.ai-header { background: #2d2d2d; padding: 10px 12px; font-size: 12px; font-weight: bold; color: #58a6ff; border-bottom: 1px solid #383838; display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.btn-resizer-preset { background: #21262d; border: 1px solid #30363d; color: #8b949e; padding: 1px 5px; border-radius: 3px; font-size: 10px; cursor: pointer; line-height: 1.2; transition: all 0.15s ease; }
.btn-resizer-preset:hover { background: #30363d; color: #58a6ff; border-color: #58a6ff; }
.btn-resizer-preset.active { background: #1f3a5f; color: #58a6ff; border-color: #388bfd; }
.ai-badge { background: #1f6feb; color: #ffffff; font-size: 10px; padding: 2px 6px; border-radius: 8px; }
.ai-model-selector { background: #1f6feb; color: #ffffff; font-size: 11px; font-weight: 600; border: 1px solid #388bfd; border-radius: 6px; padding: 2px 6px; outline: none; cursor: pointer; }
.ai-model-selector option { background: #161b22; color: #c9d1d9; }
.ai-role-selector { background: #21262d; color: #d2a8ff; font-size: 11px; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; padding: 2px 6px; outline: none; cursor: pointer; }
.ai-role-selector option { background: #161b22; color: #c9d1d9; }
.ai-agent-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-bottom: 6px; }
.ai-badge-architect { background: #1f3a5f; color: #58a6ff; border: 1px solid #388bfd44; }
.ai-badge-coder { background: #1f4e30; color: #7ee787; border: 1px solid #2ea04344; }
.ai-badge-reviewer { background: #4c3216; color: #e3b341; border: 1px solid #bb800944; }
.ai-badge-swarm { background: #3d1f5f; color: #d2a8ff; border: 1px solid #a371f744; }
.ai-messages { flex: 1; overflow-y: auto; padding: 12px; font-size: 12px; display: flex; flex-direction: column; gap: 8px; }
.ai-msg { padding: 8px; border-radius: 6px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.4; }
.ai-msg-user { background: #373e47; color: #ffffff; align-self: flex-end; max-width: 90%; }
.ai-msg-bot { background: #1f242c; border: 1px solid #383838; color: #c9d1d9; align-self: flex-start; max-width: 95%; word-break: break-word; }
.ai-code-block { background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 8px 10px; font-family: 'Courier New', Courier, monospace; font-size: 11px; overflow-x: auto; margin: 6px 0; color: #7ee787; white-space: pre; }
.ai-code-container { margin: 8px 0; border: 1px solid #30363d; border-radius: 6px; overflow: hidden; background: #0d1117; }
.ai-code-header { background: #161b22; padding: 4px 8px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; font-size: 11px; }
.ai-code-lang { color: #8b949e; font-family: monospace; font-weight: bold; text-transform: uppercase; font-size: 10px; }
.ai-code-actions { display: flex; gap: 4px; }
.btn-code-action { background: #21262d; border: 1px solid #363b42; color: #c9d1d9; border-radius: 3px; padding: 2px 6px; font-size: 10px; cursor: pointer; display: inline-flex; align-items: center; gap: 3px; font-weight: 500; }
.btn-code-action:hover { background: #30363d; color: #58a6ff; border-color: #58a6ff; }
.ai-inline-code { background: #21262d; padding: 1px 4px; border-radius: 3px; font-family: monospace; font-size: 11px; color: #79c0ff; }
.ai-msg-actions { display: flex; gap: 6px; margin-top: 8px; border-top: 1px solid #30363d; padding-top: 6px; }
.btn-msg-action { background: #21262d; border: 1px solid #363b42; color: #c9d1d9; border-radius: 4px; padding: 3px 8px; font-size: 11px; cursor: pointer; display: flex; align-items: center; gap: 4px; font-weight: 500; }
.btn-msg-action:hover { background: #30363d; color: #58a6ff; border-color: #58a6ff; }
.ai-input-box { display: flex; padding: 8px; background: #1e1e1e; border-top: 1px solid #383838; gap: 6px; align-items: center; }
.ai-input { flex: 1; background: #2a2d2e; border: 1px solid #383838; color: #ffffff; padding: 6px 8px; border-radius: 4px; font-size: 12px; outline: none; }
.ai-input:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-ai-send { background: #238636; color: #ffffff; border: none; padding: 6px 14px; border-radius: 4px; font-size: 12px; cursor: pointer; font-weight: bold; }
.btn-ai-send:hover { background: #2ea043; }
.btn-ai-stop { background: #da3633; color: #ffffff; border: none; padding: 6px 14px; border-radius: 4px; font-size: 12px; cursor: pointer; font-weight: bold; }
.btn-ai-stop:hover { background: #b62324; }
.ai-approval-card { background: #161b22; border: 1px solid #d29922; border-radius: 6px; padding: 10px; margin-top: 8px; }
.ai-approval-title { color: #d29922; font-weight: bold; font-size: 11px; margin-bottom: 4px; display: flex; align-items: center; gap: 4px; }
.ai-approval-tool { font-size: 11px; color: #c9d1d9; margin-bottom: 6px; }
.ai-diff-preview { background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 6px; font-family: monospace; font-size: 11px; max-height: 120px; overflow-y: auto; color: #8b949e; white-space: pre-wrap; margin-bottom: 8px; }
.btn-approve { background: #238636; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; font-weight: bold; margin-right: 6px; }
.btn-approve:hover { background: #2ea043; }
.btn-reject { background: #373e47; color: #f85149; border: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; }
.btn-reject:hover { background: #444c56; }
.btn-term-repair { background: #388bfd26; color: #58a6ff; border: 1px solid #388bfd66; border-radius: 4px; padding: 2px 8px; font-size: 11px; cursor: pointer; margin-top: 4px; display: inline-flex; align-items: center; gap: 4px; font-weight: bold; }
.btn-term-repair:hover { background: #388bfd4d; color: #79c0ff; }
"""

AI_JS_TEMPLATE = """
let aiAbortController = null;
let isAiGenerating = false;
let pendingApprovalAction = null;
let currentAiModel = "__CODER_MODEL__";
let currentAiRole = "__DEFAULT_ROLE__";

function onRoleChange(val) {
    currentAiRole = val;
    const msgBox = document.getElementById("ai-messages");
    if (msgBox) {
        const notice = document.createElement("div");
        notice.style.fontSize = "11px";
        notice.style.margin = "4px 0";
        const roleLabels = {
            "swarm": "🐝 Multi-Agent Swarm (Autonomous Collaboration)",
            "architect": "📐 Architect Agent (Planning & Scaffolding)",
            "coder": "💻 Coder Agent (Implementation & Diffs)",
            "reviewer": "🔍 Reviewer / QA Agent (Tests & Security)"
        };
        notice.innerHTML = '<span class="ai-agent-badge ai-badge-' + val + '">' + (roleLabels[val] || val) + '</span>';
        msgBox.appendChild(notice);
        msgBox.scrollTop = msgBox.scrollHeight;
    }
}

function onModelChange(val) {
    currentAiModel = val;
    const msgBox = document.getElementById("ai-messages");
    if (msgBox) {
        const notice = document.createElement("div");
        notice.style.color = "#58a6ff";
        notice.style.fontSize = "11px";
        notice.style.margin = "4px 0";
        notice.innerHTML = "<em>🔄 Model switched to <strong>" + val + "</strong></em>";
        msgBox.appendChild(notice);
        msgBox.scrollTop = msgBox.scrollHeight;
    }
}

function toggleAiAction() {
    if (isAiGenerating) {
        stopAi();
    } else {
        const input = document.getElementById("ai-input");
        if (input) askAi(input.value);
    }
}

function stopAi() {
    if (aiAbortController) {
        aiAbortController.abort();
        aiAbortController = null;
    }
    isAiGenerating = false;
    pendingApprovalAction = null;
    const btn = document.getElementById("btn-ai-action");
    const input = document.getElementById("ai-input");
    if (btn) {
        btn.textContent = "Ask";
        btn.className = "btn-ai-send";
    }
    if (input) {
        input.disabled = false;
        input.placeholder = "Ask Gemma AI...";
        input.focus();
    }
    const msgBox = document.getElementById("ai-messages");
    if (msgBox) {
        const stopNotice = document.createElement("div");
        stopNotice.style.color = "#d29922";
        stopNotice.style.fontSize = "11px";
        stopNotice.style.margin = "4px 0";
        stopNotice.innerHTML = "<em>⏹ Prompt generation stopped by user.</em>";
        msgBox.appendChild(stopNotice);
        msgBox.scrollTop = msgBox.scrollHeight;
    }
}

function extractCodeSnippet(text) {
    const blocks = [];
    const regex = /```(\\w+)?\\s*([\\s\\S]*?)```/g;
    let m;
    while ((m = regex.exec(text)) !== null) {
        blocks.push({ lang: (m[1] || "").toLowerCase(), code: m[2].trim() });
    }
    if (blocks.length === 0) return text.trim();
    // Prioritize python or py code block over text/markdown/bash directory trees
    const pythonBlock = blocks.find(b => b.lang === "python" || b.lang === "py" || b.code.includes("def ") || b.code.includes("import "));
    if (pythonBlock) return pythonBlock.code;
    // Otherwise pick the largest code block
    const largestBlock = blocks.reduce((max, b) => b.code.length > max.code.length ? b : max, blocks[0]);
    return largestBlock.code;
}

function formatAiResponse(text) {
    const parts = text.split(/(```[\\s\\S]*?```)/g);
    return parts.map(part => {
        const m = part.match(/```(\\w+)?\\s*([\\s\\S]*?)```/);
        if (m) {
            const lang = (m[1] || "code").toLowerCase();
            const rawCode = m[2].trim();
            const escapedCode = rawCode.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const isCode = ["python", "py", "code", "json", "js", "sh", "bash"].includes(lang) || rawCode.includes("def ") || rawCode.includes("import ") || rawCode.includes("class ");
            const insertBtn = isCode ?
                '<button class="btn-code-action" onclick="insertCodeBlock(this)">📥 Insert into Editor</button>' : '';
            return '<div class="ai-code-container">' +
                   '  <div class="ai-code-header">' +
                   '    <span class="ai-code-lang">' + lang + '</span>' +
                   '    <div class="ai-code-actions">' +
                   '      <button class="btn-code-action" onclick="copyCodeBlock(this)">📋 Copy</button>' +
                   insertBtn +
                   '    </div>' +
                   '  </div>' +
                   '  <pre class="ai-code-block" style="margin:0; border:none; border-radius:0;"><code>' + escapedCode + '</code></pre>' +
                   '</div>';
        }
        return part.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                   .replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>')
                   .replace(/\\n/g, '<br>');
    }).join("");
}

function copyCodeBlock(btn) {
    const container = btn.closest(".ai-code-container");
    if (!container) return;
    const codeEl = container.querySelector("code");
    const code = codeEl ? codeEl.innerText : "";
    navigator.clipboard.writeText(code).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = "✓ Copied!";
        btn.style.color = "#3fb950";
        setTimeout(() => { btn.innerHTML = orig; btn.style.color = ""; }, 2000);
    });
}

function insertCodeBlock(btn) {
    const container = btn.closest(".ai-code-container");
    if (!container) return;
    const codeEl = container.querySelector("code");
    const code = codeEl ? codeEl.innerText : "";
    const editor = document.getElementById("code-editor");
    if (editor && code) {
        if (typeof files !== "undefined" && typeof currentFile !== "undefined" && files[currentFile]) {
            lastFileBackup = { path: currentFile, content: files[currentFile] };
        }
        editor.value = code;
        if (typeof files !== "undefined" && typeof currentFile !== "undefined") {
            files[currentFile] = code;
            fetch("/instances/" + sessionId + "/files/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename: currentFile, content: code })
            }).catch(e => console.error(e));
        }
        const orig = btn.innerHTML;
        btn.innerHTML = "✓ Inserted!";
        btn.style.color = "#3fb950";
        setTimeout(() => { btn.innerHTML = orig; btn.style.color = ""; }, 2000);
    }
}

function copyResponse(btn) {
    const parentMsg = btn.closest(".ai-msg-bot");
    if (!parentMsg) return;
    const rawText = parentMsg.getAttribute("data-raw") || parentMsg.innerText;
    navigator.clipboard.writeText(rawText).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = "✓ Copied All!";
        btn.style.color = "#3fb950";
        setTimeout(() => {
            btn.innerHTML = orig;
            btn.style.color = "";
        }, 2000);
    });
}

async function saveResponseAsFile(btn) {
    const parentMsg = btn.closest(".ai-msg-bot");
    if (!parentMsg) return;
    const rawText = parentMsg.getAttribute("data-raw") || parentMsg.innerText;
    const role = parentMsg.getAttribute("data-role") || currentAiRole || "";
    let defaultFilename = "architecture.md";
    if (role === "reviewer") defaultFilename = "test_review.md";
    else if (role === "coder") defaultFilename = "solution.py";
    else if (role === "architect") defaultFilename = "architecture.md";
    else defaultFilename = "notes.md";

    const filename = prompt("Enter filename to save full response to:", defaultFilename);
    if (!filename) return;
    const cleanFilename = filename.trim();
    if (!cleanFilename) return;

    try {
        const resp = await fetch("/instances/" + sessionId + "/files/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: cleanFilename, content: rawText })
        });
        const data = await resp.json();
        files[cleanFilename] = rawText;
        currentFile = cleanFilename;
        renderFileList();
        switchFile(cleanFilename);
        appendTerminal("save " + cleanFilename, "Saved full response to " + cleanFilename + " (" + (data.bytes || rawText.length) + " bytes).", "");
        const orig = btn.innerHTML;
        btn.innerHTML = "✓ Saved " + cleanFilename + "!";
        btn.style.color = "#3fb950";
        setTimeout(() => { btn.innerHTML = orig; btn.style.color = ""; }, 2500);
    } catch (err) {
        alert("Failed to save file: " + err.message);
    }
}

function insertIntoEditor(btn) {
    const parentMsg = btn.closest(".ai-msg-bot");
    if (!parentMsg) return;
    const rawText = parentMsg.getAttribute("data-raw") || parentMsg.innerText;
    const role = parentMsg.getAttribute("data-role") || currentAiRole || "";
    
    let contentToInsert = rawText;
    if (role === "coder" && currentFile && currentFile.endsWith(".py")) {
        const code = extractCodeSnippet(rawText);
        if (code && code !== rawText) {
            contentToInsert = code;
        }
    } else if (role === "architect") {
        contentToInsert = rawText;
    }

    const editor = document.getElementById("code-editor");
    if (editor) {
        if (typeof files !== "undefined" && typeof currentFile !== "undefined" && files[currentFile]) {
            lastFileBackup = { path: currentFile, content: files[currentFile] };
        }
        editor.value = contentToInsert;
        if (typeof files !== "undefined" && typeof currentFile !== "undefined") {
            files[currentFile] = contentToInsert;
            fetch("/instances/" + sessionId + "/files/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename: currentFile, content: contentToInsert })
            }).catch(e => console.error(e));
        }
        const orig = btn.innerHTML;
        btn.innerHTML = "✓ Inserted!";
        btn.style.color = "#3fb950";
        setTimeout(() => {
            btn.innerHTML = orig;
            btn.style.color = "";
        }, 2000);
        appendTerminal("insert " + currentFile, "Inserted AI response into " + currentFile + " (" + contentToInsert.length + " chars).", "");
    }
}

function triggerTerminalRepair(cmd, err) {
    const input = document.getElementById("ai-input");
    const promptText = "Fix the error in terminal when running `" + cmd + "`:\\n" + err;
    if (input) {
        input.value = promptText;
        askAi(promptText);
    }
}

let lastFileBackup = null;

function rollbackLastChange(btn) {
    if (!lastFileBackup || typeof files === "undefined") return;
    files[lastFileBackup.path] = lastFileBackup.content;
    const editor = document.getElementById("code-editor");
    if (editor && currentFile === lastFileBackup.path) {
        editor.value = lastFileBackup.content;
    }
    fetch("/instances/" + sessionId + "/files/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: lastFileBackup.path, content: lastFileBackup.content })
    }).catch(e => console.error(e));
    if (typeof renderFileList === "function") renderFileList();
    appendTerminal("git checkout " + lastFileBackup.path, "Reverted " + lastFileBackup.path + " to previous state before agent modification.", "");
    lastFileBackup = null;
    if (btn) {
        btn.innerHTML = "✓ Reverted";
        btn.disabled = true;
        btn.style.opacity = "0.6";
    }
}

async function submitApproval(approved) {
    if (!pendingApprovalAction) return;
    const action = pendingApprovalAction;
    pendingApprovalAction = null;

    const editor = document.getElementById("code-editor");
    if (editor && typeof files !== "undefined" && typeof currentFile !== "undefined") {
        files[currentFile] = editor.value;
    }

    if (approved && action.args && action.args.path && typeof files !== "undefined" && files[action.args.path]) {
        lastFileBackup = { path: action.args.path, content: files[action.args.path] };
    }

    const approvalCard = document.getElementById("ai-approval-card-active");
    if (approvalCard) {
        approvalCard.innerHTML = approved ? 
            "<span style='color: #3fb950;'>✓ Action Approved. Executing...</span>" : 
            "<span style='color: #f85149;'>✕ Action Rejected by User.</span>";
    }

    if (!approved) {
        isAiGenerating = false;
        const btn = document.getElementById("btn-ai-action");
        if (btn) { btn.textContent = "Ask"; btn.className = "btn-ai-send"; }
        return;
    }

    // Call backend with approved action
    await askAi(action.prompt, {
        approval: { approved: true, tool: action.tool, args: action.args, role: action.role }
    });
}

async function askAi(prompt, options = {}) {
    if (!prompt || !prompt.trim() || (isAiGenerating && !options.approval)) return;
    const input = document.getElementById("ai-input");
    if (input) {
        input.value = "";
        input.disabled = true;
        input.placeholder = "Gemma Agent is thinking...";
    }
    
    const msgBox = document.getElementById("ai-messages");
    if (!options.approval) {
        const userMsg = document.createElement("div");
        userMsg.className = "ai-msg ai-msg-user";
        userMsg.textContent = prompt;
        if (msgBox) msgBox.appendChild(userMsg);
    }
    
    const botMsg = document.createElement("div");
    botMsg.className = "ai-msg ai-msg-bot";
    botMsg.innerHTML = "<em>🤖 Gemma Agent is reasoning & selecting tools...</em>";
    if (msgBox) {
        msgBox.appendChild(botMsg);
        msgBox.scrollTop = msgBox.scrollHeight;
    }

    isAiGenerating = true;
    const btn = document.getElementById("btn-ai-action");
    if (btn) {
        btn.textContent = "⏹ Stop";
        btn.className = "btn-ai-stop";
    }

    aiAbortController = new AbortController();
    
    try {
        const editor = document.getElementById("code-editor");
        const activeContext = editor ? editor.value.slice(0, 4000) : "";
        const activeFilename = typeof currentFile !== "undefined" ? currentFile : "main.py";

        // Ensure in-memory files dictionary reflects the current live editor state
        if (editor && typeof files !== "undefined") {
            files[activeFilename] = editor.value;
        }

        const reqBody = {
            prompt: prompt,
            model: currentAiModel,
            role: currentAiRole,
            filename: activeFilename,
            context: activeContext,
            files: typeof files !== "undefined" ? files : {},
            approval: options.approval || null
        };

        const resp = await fetch("/instances/" + sessionId + "/ai-chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(reqBody),
            signal: aiAbortController.signal
        });
        const data = await resp.json();

        // Check if agent requires Selective Auto-Approval confirmation
        if (data.status === "waiting_for_approval") {
            pendingApprovalAction = { prompt: prompt, tool: data.tool, args: data.args, role: data.role || currentAiRole };
            let previewText = data.diff_preview || JSON.stringify(data.args, null, 2);
            const agentName = data.agent_name || "💻 Coder Agent";
            const role = data.role || currentAiRole;
            botMsg.innerHTML = '<span class="ai-agent-badge ai-badge-' + role + '">' + agentName + '</span><br>' + (data.reply || "Proposed workspace modification:") +
                '<div id="ai-approval-card-active" class="ai-approval-card">' +
                '  <div class="ai-approval-title">⚠️ Action Approval Required (' + data.tool + ')</div>' +
                '  <div class="ai-approval-tool">Target: <code>' + (data.args.path || data.args.command || "") + '</code></div>' +
                '  <pre class="ai-diff-preview">' + previewText.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") + '</pre>' +
                '  <div>' +
                '    <button onclick="submitApproval(true)" class="btn-approve">✓ Approve & Execute</button>' +
                '    <button onclick="submitApproval(false)" class="btn-reject">✕ Reject</button>' +
                '  </div>' +
                '</div>';
            return;
        }

        // If tool mutated files in-place, sync editor
        if (data.updated_files && typeof files !== "undefined") {
            for (const [k, v] of Object.entries(data.updated_files)) {
                files[k] = v;
                fetch("/instances/" + sessionId + "/files/save", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ filename: k, content: v })
                }).catch(e => console.error(e));
                if (k === currentFile && editor) editor.value = v;
            }
            if (typeof renderFileList === "function") renderFileList();
        }

        const replyText = data.reply || data.content || "Task completed successfully.";
        let rollbackBtnHtml = "";
        if (lastFileBackup) {
            rollbackBtnHtml = '<button onclick="rollbackLastChange(this)" class="btn-msg-action" style="color: #f85149; border-color: #f8514966;">↩ Rollback Changes</button>';
        }
        const agentName = data.agent_name || "Gemma Agent";
        const role = data.role || currentAiRole;
        const headerBadge = '<span class="ai-agent-badge ai-badge-' + role + '">' + agentName + '</span><br>';
        botMsg.setAttribute("data-raw", replyText);
        botMsg.setAttribute("data-role", role);
        botMsg.innerHTML = headerBadge + formatAiResponse(replyText) + 
            '<div class="ai-msg-actions">' +
            '    <button onclick="copyResponse(this)" class="btn-msg-action" title="Copy entire response text">📋 Copy All</button>' +
            '    <button onclick="saveResponseAsFile(this)" class="btn-msg-action" title="Save entire output to a file (e.g. architecture.md)">💾 Save as File</button>' +
            '    <button onclick="insertIntoEditor(this)" class="btn-msg-action" title="Insert output into editor">📥 Insert into Editor</button>' +
            rollbackBtnHtml +
            '</div>';

    } catch (err) {
        if (err.name === "AbortError") {
            botMsg.innerHTML = "<em>[Prompt generation cancelled]</em>";
        } else {
            botMsg.innerHTML = '<span style="color: #f85149;">Inference Error: ' + err.message + '</span>';
        }
    } finally {
        if (!pendingApprovalAction) {
            isAiGenerating = false;
            if (btn) {
                btn.textContent = "Ask";
                btn.className = "btn-ai-send";
            }
            if (input) {
                input.disabled = false;
                input.placeholder = "Ask Gemma AI...";
                input.focus();
            }
            aiAbortController = null;
        }
        if (msgBox) msgBox.scrollTop = msgBox.scrollHeight;
    }
}

// AI Output Width Resizing & LocalStorage Persistence
function initAiResizer() {
    const resizer = document.getElementById("ai-resizer");
    const aiSidebar = document.querySelector(".ai-sidebar");
    const mainContainer = document.querySelector(".main");
    if (!resizer || !aiSidebar || !mainContainer) return;

    let isDragging = false;
    let startX = 0;
    let startWidth = 0;

    const savedWidth = localStorage.getItem("gdc_dev_ai_width");
    if (savedWidth) {
        const parsed = parseInt(savedWidth, 10);
        if (!isNaN(parsed) && parsed >= 260) {
            aiSidebar.style.width = parsed + "px";
            updateAiWidthButtons(parsed);
        }
    }

    resizer.addEventListener("mousedown", function(e) {
        isDragging = true;
        startX = e.clientX;
        startWidth = aiSidebar.getBoundingClientRect().width;
        resizer.classList.add("resizing");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        e.preventDefault();
    });

    window.addEventListener("mousemove", function(e) {
        if (!isDragging) return;
        const deltaX = startX - e.clientX;
        const mainWidth = mainContainer.getBoundingClientRect().width;
        const maxWidth = Math.max(280, mainWidth - 320);
        let newWidth = startWidth + deltaX;
        if (newWidth < 260) newWidth = 260;
        if (newWidth > maxWidth) newWidth = maxWidth;
        aiSidebar.style.width = newWidth + "px";
        updateAiWidthButtons(newWidth);
    });

    window.addEventListener("mouseup", function() {
        if (isDragging) {
            isDragging = false;
            resizer.classList.remove("resizing");
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
            const finalWidth = Math.round(aiSidebar.getBoundingClientRect().width);
            localStorage.setItem("gdc_dev_ai_width", finalWidth);
        }
    });

    resizer.addEventListener("dblclick", function() {
        const currentWidth = Math.round(aiSidebar.getBoundingClientRect().width);
        const targetWidth = (currentWidth > 450) ? 380 : 560;
        setAiWidth(targetWidth);
    });
}

function setAiWidth(w) {
    const aiSidebar = document.querySelector(".ai-sidebar");
    const mainContainer = document.querySelector(".main");
    if (!aiSidebar) return;
    let target = w;
    if (mainContainer) {
        const maxWidth = Math.max(280, mainContainer.getBoundingClientRect().width - 320);
        if (target > maxWidth) target = maxWidth;
    }
    aiSidebar.style.width = target + "px";
    localStorage.setItem("gdc_dev_ai_width", target);
    updateAiWidthButtons(target);
}

function updateAiWidthButtons(currentWidth) {
    const buttons = document.querySelectorAll(".btn-resizer-preset");
    buttons.forEach(btn => {
        const val = parseInt(btn.textContent.trim(), 10);
        if (!isNaN(val)) {
            if (Math.abs(val - currentWidth) < 25) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        }
    });
}

function toggleAiMaximize() {
    const aiSidebar = document.querySelector(".ai-sidebar");
    const mainContainer = document.querySelector(".main");
    const btn = document.getElementById("btn-ai-max");
    if (!aiSidebar || !mainContainer) return;
    const currentWidth = Math.round(aiSidebar.getBoundingClientRect().width);
    const mainWidth = mainContainer.getBoundingClientRect().width;
    const maxWidth = Math.max(340, mainWidth - 320);
    if (currentWidth >= maxWidth - 30) {
        setAiWidth(380);
        if (btn) { btn.innerHTML = "⤢"; btn.title = "Maximize AI Panel"; }
    } else {
        setAiWidth(maxWidth);
        if (btn) { btn.innerHTML = "🗗"; btn.title = "Restore AI Panel Width"; }
    }
}

initAiResizer();
"""

def handle_ai_chat(post_data, user_id, workspace_dir=None):
    """Processes AI chat and Phase 3 Agentic ReAct tool execution requests."""
    if workspace_dir is None:
        workspace_dir = WORKSPACE_ROOT
    os.makedirs(workspace_dir, exist_ok=True)
    try:
        data = json.loads(post_data) if isinstance(post_data, str) else post_data
    except Exception:
        data = {}
        
    prompt = data.get("prompt", "")
    filename = data.get("filename", "main.py")
    context = data.get("context", "")
    client_files = data.get("files", {})
    approval = data.get("approval", None)
    
    req_model = data.get("model", os.environ.get("AI_CODER_MODEL", "gemma4:31b"))
    coder_model = os.environ.get("AI_CODER_MODEL", "gemma4:31b")
    tier1_model = os.environ.get("AI_TIER1_MODEL", "gemma4:26b")
    
    # Model Tiering Dynamic Routing Logic
    if req_model == "auto":
        reasoning_triggers = ("fix", "error", "traceback", "repair", "diff", "patch", "test", "assert", "fail", "create", "refactor")
        if any(w in prompt.lower() for w in reasoning_triggers) or (context and len(context) > 500):
            model = coder_model
            print(f"[MODEL-TIERING] Escalated to Tier 2 reasoning model: {model}", flush=True)
        else:
            model = tier1_model
            print(f"[MODEL-TIERING] Routed to Tier 1 fast model: {model}", flush=True)
    else:
        model = req_model

    req_role = data.get("role", os.environ.get("AI_DEFAULT_ROLE", "swarm")).lower()
    persona = SWARM_PERSONAS.get(req_role, SWARM_PERSONAS["swarm"])
    agent_name = persona["name"]

    openai_url = os.environ.get("OPENAI_API_BASE_URL", "http://gemma-gateway.gemma-inference.svc.cluster.local/v1")
    request_timeout = float(os.environ.get("AI_REQUEST_TIMEOUT", "300"))
    agent_mode = os.environ.get("AI_AGENT_MODE", "passive").lower()
    approval_policy = os.environ.get("AI_APPROVAL_POLICY", "selective").lower()
    
    # 1. Handle Pending Approved Action Execution (Phase 3)
    if approval and approval.get("approved"):
        tool_name = approval.get("tool")
        tool_args = approval.get("args", {})
        ok, obs = execute_tool(tool_name, tool_args, client_files, workspace_dir)
        target_path = tool_args.get("path", filename)
        if ok:
            updated_code = client_files.get(target_path, "")
            reply_text = (
                f"✅ **Action Approved & Applied**\n\n"
                f"Successfully executed `{tool_name}` on `{target_path}`.\n\n"
                f"```python\n# {target_path} (updated by {agent_name})\n{updated_code}\n```\n\n"
                f"The active editor has been updated with the verified implementation. Click `▶ Run Code` to verify execution."
            )
        else:
            reply_text = f"❌ **Action Execution Error**\n\nFailed to apply `{tool_name}` to `{target_path}`: {obs}\n\nPlease check the target file content and retry."
        return {"status": "complete", "reply": reply_text, "updated_files": client_files, "role": req_role, "agent_name": agent_name}

    # Construct context-aware prompt if editor code is provided
    if context and context.strip():
        user_content = f"Active file: `{filename}`\n```\n{context.strip()}\n```\n\nTask: {prompt}"
    else:
        user_content = prompt
        
    payload_dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": persona["system_prompt"]},
            {"role": "user", "content": user_content}
        ]
    }

    # Enable OpenAI-compatible Function Calling tools if Agentic Mode is active
    if agent_mode == "agentic":
        allowed_tools = persona.get("tools", [])
        filtered_tools = [t for t in AGENT_TOOLS if t["function"]["name"] in allowed_tools]
        if filtered_tools:
            payload_dict["tools"] = filtered_tools
            payload_dict["tool_choice"] = "auto"

    gw_req_payload = json.dumps(payload_dict).encode('utf-8')
    
    reply_text = ""
    try:
        req = urllib.request.Request(
            f"{openai_url}/chat/completions",
            data=gw_req_payload,
            headers={"Content-Type": "application/json", HEADER_USER_KEY: user_id}
        )
        print(f"[AI-CHAT] Sending request to Gemma Gateway ({model}, {agent_name}): {openai_url}/chat/completions", flush=True)
        with AI_OPENER.open(req, timeout=request_timeout) as resp:
            gw_resp = json.loads(resp.read().decode('utf-8'))
            choices = gw_resp.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                reply_text = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls", [])

                # Phase 3: Evaluate Tool Calls
                if tool_calls and agent_mode == "agentic":
                    first_call = tool_calls[0]
                    t_name = first_call.get("function", {}).get("name", "")
                    try:
                        t_args = json.loads(first_call.get("function", {}).get("arguments", "{}"))
                    except Exception:
                        t_args = {}

                    perm = classify_tool_permission(t_name)

                    # Selective Auto-Approval: Read tools run immediately; Mutations require user approval
                    if perm == "AUTO_APPROVED" or approval_policy == "full_auto":
                        ok, obs = execute_tool(t_name, t_args, client_files, workspace_dir)
                        # Multi-turn ReAct: feed tool observation back to Gemma so it can synthesize the diff/code
                        try:
                            turn2_payload = dict(payload_dict)
                            turn2_payload["messages"] = list(payload_dict["messages"])
                            turn2_payload["messages"].append({
                                "role": "assistant",
                                "content": f"I am reading `{t_args.get('path', '')}` to inspect context."
                            })
                            turn2_payload["messages"].append({
                                "role": "user",
                                "content": f"[Observation from tool `{t_name}` on `{t_args.get('path', '')}`]:\n```\n{obs}\n```\nNow generate the surgical diff using `apply_diff` to complete the task: {prompt}"
                            })
                            req2 = urllib.request.Request(
                                f"{openai_url}/chat/completions",
                                data=json.dumps(turn2_payload).encode('utf-8'),
                                headers={"Content-Type": "application/json", HEADER_USER_KEY: user_id}
                            )
                            with AI_OPENER.open(req2, timeout=request_timeout) as resp2:
                                gw_resp2 = json.loads(resp2.read().decode('utf-8'))
                                choices2 = gw_resp2.get("choices", [])
                                if choices2:
                                    msg2 = choices2[0].get("message", {})
                                    reply2 = msg2.get("content", "") or ""
                                    tool_calls2 = msg2.get("tool_calls", [])
                                    if tool_calls2:
                                        call2 = tool_calls2[0]
                                        t2_name = call2.get("function", {}).get("name", "")
                                        try:
                                            t2_args = json.loads(call2.get("function", {}).get("arguments", "{}"))
                                        except Exception:
                                            t2_args = {}
                                        if t2_name == "apply_diff":
                                            tgt2 = t2_args.get("target_block", "")
                                            rep2 = t2_args.get("replacement_block", "")
                                            diff_prev2 = f"--- a/{t2_args.get('path', 'file')}\n+++ b/{t2_args.get('path', 'file')}\n" + \
                                                         "".join(f"- {l}\n" for l in tgt2.splitlines()) + \
                                                         "".join(f"+ {l}\n" for l in rep2.splitlines())
                                        else:
                                            diff_prev2 = t2_args.get("replacement_block", json.dumps(t2_args, indent=2))
                                        return {
                                            "status": "waiting_for_approval",
                                            "tool": t2_name,
                                            "args": t2_args,
                                            "diff_preview": diff_prev2,
                                            "reply": reply2 or f"I propose executing `{t2_name}` to update your code.",
                                            "role": req_role,
                                            "agent_name": agent_name
                                        }
                                    elif reply2:
                                        return {
                                            "status": "complete",
                                            "reply": reply2,
                                            "updated_files": client_files,
                                            "role": req_role,
                                            "agent_name": agent_name
                                        }
                        except Exception as e2:
                            print(f"[AI-CHAT] ReAct second turn skipped: {e2}", flush=True)

                        reply_text = f"⚙️ Tool executed: `{t_name}`.\nObservation: {obs}\n\n" + (reply_text or "Ready for next step.")
                        return {"status": "complete", "reply": reply_text, "updated_files": client_files, "role": req_role, "agent_name": agent_name}
                    else:
                        # Request user approval via Interactive Card
                        if t_name == "apply_diff":
                            tgt = t_args.get("target_block", "")
                            rep = t_args.get("replacement_block", "")
                            diff_preview = f"--- a/{t_args.get('path', 'file')}\n+++ b/{t_args.get('path', 'file')}\n" + \
                                           "".join(f"- {l}\n" for l in tgt.splitlines()) + \
                                           "".join(f"+ {l}\n" for l in rep.splitlines())
                        else:
                            diff_preview = t_args.get("replacement_block", json.dumps(t_args, indent=2))
                        return {
                            "status": "waiting_for_approval",
                            "tool": t_name,
                            "args": t_args,
                            "diff_preview": diff_preview,
                            "reply": reply_text or f"I propose executing `{t_name}` to resolve your task.",
                            "role": req_role,
                            "agent_name": agent_name
                        }

                print("[AI-CHAT] Received completion from Gemma Gateway successfully!", flush=True)
    except urllib.error.HTTPError as e:
        err_detail = ""
        try:
            err_detail = e.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        err_msg = f"HTTP {e.code}: {err_detail or e.reason}"
        print(f"[AI-CHAT ERROR] Gateway HTTP error: {err_msg}", flush=True)
        reply_text = f"*(Gemma Gateway HTTP error: {err_msg})*\n\n```python\n# Fallback response for: {prompt}\ndef solve():\n    return 'Verified with Gemma 4 on GDC'\n```"
    except Exception as e:
        print(f"[AI-CHAT ERROR] Gateway communication error: {e}", flush=True)
        reply_text = f"*(Gemma Gateway communication error: {e})*\n\n```python\n# Fallback response for: {prompt}\ndef solve():\n    return 'Verified with Gemma 4 on GDC'\n```"

    return {"status": "complete", "reply": reply_text, "updated_files": client_files, "role": req_role, "agent_name": agent_name}


def render_workspace_ui(session_id, user_id):
    auth_mode = os.environ.get("AUTH_MODE", "mock")
    ai_enabled = os.environ.get("AI_ENABLED", "false").lower() == "true"
    ai_default_model = os.environ.get("AI_DEFAULT_MODEL", "gemma4:31b")
    ai_coder_model = os.environ.get("AI_CODER_MODEL", "gemma4:31b")
    gemini_tier1 = os.environ.get("AI_GEMINI_TIER1_MODEL", "gemini-2.0-flash")
    gemini_tier2 = os.environ.get("AI_GEMINI_TIER2_MODEL", "gemini-2.0-pro")
    agent_mode = os.environ.get("AI_AGENT_MODE", "passive").lower()
    ai_default_role = os.environ.get("AI_DEFAULT_ROLE", "swarm").lower()

    ws_dir = get_workspace_dir(session_id)
    ensure_workspace_dir(session_id=session_id, user_id=user_id, workspace_dir=ws_dir)
    disk_files = load_workspace_files(workspace_dir=ws_dir)
    
    initial_files = {
        "main.py": f"import os\nimport sys\n\n# Welcome to your resilient air-gapped GDC Developer Environment!\ndef main():\n    print(\"Workspace ID : {session_id}\")\n    print(\"Active User  : {user_id}\")\n    print(\"Ready for high-security cloud development.\")\n\nif __name__ == \"__main__\":\n    main()",
        "README.md": f"# Workspace: {session_id}\n\nResilient GDC Developer Environment (gdc-dev) on Google Distributed Cloud (Air-Gapped).\nConnected to Keycloak OIDC SSO and Gemma 4 AI Gateway.",
        ".dev/settings.json": json.dumps({"editor.fontSize": 14, "editor.tabSize": 4, "files.autoSave": "afterDelay"}, indent=2)
    }
    workspace_files = disk_files if disk_files else initial_files
    if not disk_files:
        save_workspace_files(initial_files, workspace_dir=ws_dir)
    files_json = json.dumps(workspace_files)

    if auth_mode == "oidc" and user_id == "anonymous":
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Keycloak OIDC Login - GDC Developer Environment</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #0d1117; color: #c9d1d9; display: flex; align-items: center; justify-content: center; height: 100vh; }}
        .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 32px; max-width: 440px; width: 100%; text-align: center; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }}
        h1 {{ color: #58a6ff; font-size: 22px; margin-bottom: 8px; }}
        p {{ color: #8b949e; font-size: 14px; margin-bottom: 24px; }}
        .realm-info {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; font-size: 13px; color: #c9d1d9; margin-bottom: 24px; text-align: left; }}
        .btn-login {{ display: block; width: 100%; background: #238636; color: #ffffff; padding: 12px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 15px; border: none; cursor: pointer; box-sizing: border-box; }}
        .btn-login:hover {{ background: #2ea043; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🔐 Enterprise SSO Authentication</h1>
        <p>GDC Developer Environment on Google Distributed Cloud (Air-Gapped)</p>
        <div class="realm-info">
            <div><strong>Identity Provider:</strong> Keycloak OIDC</div>
            <div><strong>Active Realm:</strong> <code>gdc-dev-realm</code></div>
            <div><strong>Client ID:</strong> <code>gdc-dev-client</code></div>
        </div>
        <button onclick="simulateLogin()" class="btn-login">Sign in with Keycloak OIDC</button>
        <script>
            function simulateLogin() {{
                alert("Redirecting to Keycloak IdP (gdc-dev-realm)... For Phase 2 local emulation verification, passing simulated OIDC token header.");
                document.cookie = "dev_auth_user=oidc-developer@gdc.local; Path=/; SameSite=Lax";
                window.location.href = "/instances/" + "{session_id}" + "?oidc_login=success";
            }}
        </script>
    </div>
</body>
</html>"""

    ai_dock_html = ""
    ai_css_block = ""
    ai_js_block = ""
    if ai_enabled:
        ai_css_block = AI_CSS
        dock_title = "🤖 GDC Dev AI Swarm" if agent_mode == "agentic" else "🤖 GDC Dev AI Assistant (Gemma 4)"
        ai_dock_html = f"""
        <div id="ai-resizer" class="ai-resizer" title="Drag to adjust AI panel width (Double-click to toggle)"></div>
        <div class="ai-sidebar">
            <div class="ai-header">
                <div style="display: flex; align-items: center; gap: 6px; overflow: hidden;">
                    <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{dock_title}</span>
                    <div class="ai-width-controls" style="display: flex; gap: 2px; align-items: center; flex-shrink: 0;">
                        <button onclick="setAiWidth(320)" class="btn-resizer-preset" title="Compact width (320px)">320</button>
                        <button onclick="setAiWidth(420)" class="btn-resizer-preset" title="Medium width (420px)">420</button>
                        <button onclick="setAiWidth(560)" class="btn-resizer-preset" title="Wide width (560px)">560</button>
                        <button onclick="toggleAiMaximize()" id="btn-ai-max" class="btn-resizer-preset" title="Maximize / Restore AI panel">⤢</button>
                    </div>
                </div>
                <div style="display: flex; gap: 4px; align-items: center; flex-shrink: 0;">
                    <select id="ai-agent-role" class="ai-role-selector" onchange="onRoleChange(this.value)" title="Active Swarm Specialist Persona">
                        <option value="swarm" {"selected" if ai_default_role == "swarm" else ""}>🐝 Swarm</option>
                        <option value="architect" {"selected" if ai_default_role == "architect" else ""}>📐 Architect</option>
                        <option value="coder" {"selected" if ai_default_role == "coder" else ""}>💻 Coder</option>
                        <option value="reviewer" {"selected" if ai_default_role == "reviewer" else ""}>🔍 Reviewer</option>
                    </select>
                    <select id="ai-model-selector" class="ai-model-selector" onchange="onModelChange(this.value)" title="Active Gemma / Gemini Model">
                        <option value="gemma4:31b" {"selected" if "31b" in ai_default_model else ""}>⚡ 31b</option>
                        <option value="gemma4:26b" {"selected" if "26b" in ai_default_model else ""}>🚀 26b</option>
                        <option value="auto">🔄 Auto</option>
                        <option value="{gemini_tier2}">🌐 {gemini_tier2}</option>
                        <option value="{gemini_tier1}">⚡ {gemini_tier1}</option>
                    </select>
                </div>
            </div>
            <div id="ai-messages" class="ai-messages">
                <div class="ai-msg ai-msg-bot" data-raw="Hello! We are your sovereign developer swarm connected to gdc_gemma_gw.">
                    <span class="ai-agent-badge ai-badge-swarm">🐝 Multi-Agent Swarm</span><br>
                    Hello <code>{user_id}</code>! We are your sovereign developer swarm connected to <code>gdc_gemma_gw</code>.<br>
                    • <strong>📐 Architect:</strong> Project structure & modular planning.<br>
                    • <strong>💻 Coder:</strong> Surgical diff authoring & implementation.<br>
                    • <strong>🔍 Reviewer:</strong> Unit test synthesis & security audits.<br>
                    Select an individual specialist above or use <strong>🐝 Swarm</strong> for collaborative execution!
                    <div class="ai-msg-actions">
                        <button onclick="copyResponse(this)" class="btn-msg-action">📋 Copy All</button>
                    </div>
                </div>
            </div>
            <div class="ai-input-box">
                <input type="text" id="ai-input" class="ai-input" placeholder="Ask Gemma AI Swarm..." onkeydown="if(event.key==='Enter' && !isAiGenerating) askAi(this.value)">
                <button id="btn-ai-action" onclick="toggleAiAction()" class="btn-ai-send">Ask</button>
            </div>
        </div>
        """
        ai_js_block = AI_JS_TEMPLATE.replace("__CODER_MODEL__", ai_coder_model).replace("__DEFAULT_ROLE__", ai_default_role)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>GDC Developer Environment - {session_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #1e1e1e; color: #cccccc; display: flex; flex-direction: column; height: 100vh; }}
        .header {{ background: #333333; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #454545; }}
        .header h2 {{ margin: 0; font-size: 16px; color: #ffffff; }}
        .header .user-info {{ font-size: 13px; color: #9cdcfe; }}
        .main {{ display: flex; flex: 1; overflow: hidden; }}
        .sidebar {{ width: 250px; background: #252526; border-right: 1px solid #383838; padding: 12px; font-size: 13px; display: flex; flex-direction: column; }}
        .sidebar-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .sidebar-header h3 {{ font-size: 11px; text-transform: uppercase; color: #bbbbbb; margin: 0; }}
        .btn-sidebar-icon {{ background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 4px; padding: 2px 7px; font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
        .btn-sidebar-icon:hover {{ background: #30363d; color: #58a6ff; border-color: #58a6ff; }}
        .btn-new-file {{ background: #238636; color: #ffffff; border: none; border-radius: 4px; padding: 3px 8px; font-size: 11px; cursor: pointer; font-weight: bold; display: flex; align-items: center; gap: 4px; }}
        .btn-new-file:hover {{ background: #2ea043; }}
        .new-file-box {{ background: #1f242c; border: 1px solid #58a6ff; border-radius: 4px; padding: 6px; margin-bottom: 8px; display: none; }}
        .new-file-box input {{ width: 100%; background: #0d1117; border: 1px solid #30363d; color: #ffffff; padding: 4px 6px; font-size: 12px; border-radius: 4px; outline: none; box-sizing: border-box; margin-bottom: 6px; }}
        .new-file-actions {{ display: flex; justify-content: flex-end; gap: 4px; }}
        .btn-create-confirm {{ background: #238636; color: white; border: none; padding: 2px 8px; border-radius: 3px; font-size: 11px; cursor: pointer; font-weight: bold; }}
        .btn-create-cancel {{ background: #373e47; color: white; border: none; padding: 2px 8px; border-radius: 3px; font-size: 11px; cursor: pointer; }}
        .file-list {{ list-style: none; padding-left: 0; margin: 0; flex: 1; overflow-y: auto; }}
        .file-list li {{ padding: 6px 8px; cursor: pointer; border-radius: 4px; color: #e8e8e8; display: flex; justify-content: space-between; align-items: center; }}
        .file-list li:hover {{ background: #2a2d2e; }}
        .file-list li.active {{ background: #37373d; color: #ffffff; }}
        .file-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .btn-file-delete {{ background: transparent; border: none; color: #8b949e; cursor: pointer; padding: 2px 4px; border-radius: 3px; font-size: 11px; opacity: 0.35; transition: opacity 0.15s; }}
        .file-list li:hover .btn-file-delete {{ opacity: 1; color: #f85149; }}
        .editor-container {{ flex: 1; display: flex; flex-direction: column; background: #1e1e1e; min-width: 260px; overflow: hidden; }}
        .editor-tabs {{ background: #2d2d2d; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #383838; padding-right: 12px; }}
        .tabs-list {{ display: flex; align-items: center; overflow-x: auto; }}
        .tab {{ padding: 8px 12px; background: #252526; color: #888888; border-right: 1px solid #383838; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; }}
        .tab.active {{ background: #1e1e1e; color: #ffffff; }}
        .tab-close {{ color: #888888; font-size: 11px; margin-left: 4px; border-radius: 3px; padding: 0 3px; cursor: pointer; }}
        .tab-close:hover {{ color: #ffffff; background: #3c3c3c; }}
        .tab-add {{ padding: 6px 12px; background: transparent; color: #888888; border: none; font-size: 16px; cursor: pointer; font-weight: bold; }}
        .tab-add:hover {{ color: #ffffff; }}
        .btn-run {{ background: #238636; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; margin-left: 8px; }}
        .btn-run:hover {{ background: #2ea043; }}
        .btn-save {{ background: #1f6feb; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; }}
        .btn-save:hover {{ background: #388bfd; }}
        .editor-textarea {{ flex: 1; min-height: 80px; padding: 20px; font-family: 'Courier New', Courier, monospace; font-size: 14px; line-height: 1.6; color: #d4d4d4; background: #1e1e1e; border: none; outline: none; resize: none; width: 100%; box-sizing: border-box; }}
        .terminal-resizer {{ height: 6px; background: #252526; border-top: 1px solid #383838; border-bottom: 1px solid #181818; cursor: row-resize; transition: background 0.15s ease; user-select: none; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
        .terminal-resizer:hover, .terminal-resizer.resizing {{ background: #58a6ff; }}
        .terminal-resizer::after {{ content: ''; width: 36px; height: 2px; background: #6e7681; border-radius: 1px; }}
        .terminal-resizer:hover::after, .terminal-resizer.resizing::after {{ background: #ffffff; }}
        .terminal {{ height: 220px; min-height: 80px; max-height: calc(100vh - 120px); background: #181818; border-top: none; padding: 12px; font-family: 'Courier New', Courier, monospace; font-size: 13px; color: #cccccc; display: flex; flex-direction: column; flex-shrink: 0; }}
        .terminal-header {{ font-size: 11px; text-transform: uppercase; color: #888888; margin-bottom: 8px; flex-shrink: 0; display: flex; justify-content: space-between; align-items: center; }}
        .btn-term-size {{ background: #21262d; border: 1px solid #30363d; color: #8b949e; padding: 1px 6px; border-radius: 3px; font-size: 10px; cursor: pointer; line-height: 1.3; transition: all 0.15s ease; }}
        .btn-term-size:hover {{ background: #30363d; color: #58a6ff; border-color: #58a6ff; }}
        .btn-term-size.active {{ background: #1f3a5f; color: #58a6ff; border-color: #388bfd; }}
        .terminal-output {{ flex: 1; overflow-y: auto; white-space: pre-wrap; margin-bottom: 8px; }}
        .terminal-input-row {{ display: flex; align-items: center; background: #1f1f1f; padding: 4px 8px; border-radius: 4px; border: 1px solid #333333; }}
        .prompt {{ color: #4ec9b0; margin-right: 8px; font-weight: bold; flex-shrink: 0; }}
        .term-input {{ flex: 1; background: transparent; border: none; outline: none; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-size: 13px; }}
        .btn-exit {{ background: #d73a49; color: white; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .btn-exit:hover {{ background: #cb2431; }}
        .modal-overlay {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; z-index: 1000; }}
        .modal-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; width: 480px; max-width: 90vw; padding: 18px; box-shadow: 0 12px 32px rgba(0,0,0,0.6); display: flex; flex-direction: column; gap: 10px; }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
        .modal-header h3 {{ margin: 0; font-size: 14px; color: #58a6ff; }}
        .btn-modal-close {{ background: transparent; border: none; color: #8b949e; font-size: 14px; cursor: pointer; }}
        .btn-modal-close:hover {{ color: #ffffff; }}
        .project-template-option {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 10px; margin-bottom: 8px; cursor: pointer; transition: all 0.15s ease; }}
        .project-template-option:hover {{ border-color: #58a6ff; background: #1c2128; }}
        .project-template-option.active {{ border-color: #238636; background: #122319; }}
        .template-title {{ font-size: 12px; font-weight: bold; color: #c9d1d9; margin-bottom: 4px; }}
        .template-desc {{ font-size: 11px; color: #8b949e; line-height: 1.3; }}
        .modal-footer {{ display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid #30363d; padding-top: 10px; }}
        .btn-modal-cancel {{ background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; }}
        .btn-modal-cancel:hover {{ background: #30363d; }}
        .btn-modal-confirm {{ background: #238636; border: none; color: white; padding: 6px 14px; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer; }}
        .btn-modal-confirm:hover {{ background: #2ea043; }}
        {ai_css_block}
    </style>
</head>
<body>
    <div class="header">
        <div style="display: flex; align-items: center; gap: 14px;">
            <h2>GDC Developer Environment (gdc-dev)</h2>
            <div style="display: flex; align-items: center; gap: 6px; background: #252526; border: 1px solid #383838; padding: 3px 8px; border-radius: 6px;">
                <span style="font-size: 11px; color: #8b949e; font-weight: bold;">📁 Project:</span>
                <select id="header-project-select" onchange="switchProject(this.value)" style="background: #1e1e1e; color: #4ec9b0; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; font-size: 12px; font-weight: bold; outline: none; cursor: pointer;">
                    <option value="{session_id}" selected>📁 {session_id}</option>
                </select>
                <button onclick="showNewProjectModal()" style="background: #238636; color: white; border: none; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold; cursor: pointer;" title="Manage / Create / Switch Projects">⚙️ Projects</button>
            </div>
        </div>
        <div class="user-info">
            Authenticated User: <strong>{user_id}</strong> | Mode: <strong>{auth_mode}</strong> | <a href="/?logout=true" class="btn-exit" onclick="document.cookie='dev_auth_user=; Path=/; Max-Age=0; SameSite=Lax'; document.cookie='theia_auth_user=; Path=/; Max-Age=0; SameSite=Lax';">Exit Session</a>
        </div>
    </div>
    <div class="main">
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>Explorer</h3>
                <div style="display: flex; gap: 4px;">
                    <button onclick="refreshFiles()" class="btn-sidebar-icon" title="Refresh files from disk">🔄</button>
                    <button onclick="showNewProjectModal()" class="btn-sidebar-icon" title="Start New Project / Switch Workspace">📁</button>
                    <button onclick="showNewFileDialog()" class="btn-new-file" title="Create a new file">+ File</button>
                </div>
            </div>
            <div id="new-file-box" class="new-file-box">
                <input type="text" id="new-filename-input" placeholder="e.g. prime_checker.py" onkeydown="if(event.key==='Enter') confirmNewFile(); if(event.key==='Escape') hideNewFileDialog();">
                <div class="new-file-actions">
                    <button onclick="hideNewFileDialog()" class="btn-create-cancel">Cancel</button>
                    <button onclick="confirmNewFile()" class="btn-create-confirm">Create</button>
                </div>
            </div>
            <ul id="file-list" class="file-list"></ul>
        </div>
        <div class="editor-container">
            <div class="editor-tabs">
                <div id="tabs-list" class="tabs-list">
                    <button onclick="showNewFileDialog()" class="tab-add" title="New File">+</button>
                </div>
                <div>
                    <button onclick="saveCode()" class="btn-save">💾 Save</button>
                    <button onclick="runCode()" class="btn-run">▶ Run Code</button>
                </div>
            </div>
            <textarea id="code-editor" class="editor-textarea" spellcheck="false">{workspace_files.get("main.py", "")}</textarea>
            <div id="terminal-resizer" class="terminal-resizer" title="Drag to adjust terminal height (Double-click to toggle)"></div>
            <div class="terminal">
                <div class="terminal-header">
                    <span>Terminal - bash (project: {session_id})</span>
                    <div class="terminal-size-controls" style="display: flex; gap: 4px; align-items: center;">
                        <span style="font-size: 10px; color: #888888;">Height:</span>
                        <button onclick="setTerminalHeight(140)" class="btn-term-size" title="Compact height (140px)">140px</button>
                        <button onclick="setTerminalHeight(220)" class="btn-term-size" title="Default height (220px)">220px</button>
                        <button onclick="setTerminalHeight(360)" class="btn-term-size" title="Medium height (360px)">360px</button>
                        <button onclick="setTerminalHeight(500)" class="btn-term-size" title="Expanded height (500px)">500px</button>
                        <button onclick="toggleTerminalMaximize()" id="btn-term-max" class="btn-term-size" title="Maximize / Restore Terminal">⤢</button>
                    </div>
                </div>
                <div id="terminal-output" class="terminal-output"><div><span class="prompt">dev@gdc-session:~/{session_id}$</span> python3 main.py</div><div>Workspace ID : {session_id}</div><div>Active User  : {user_id}</div><div>Ready for high-security cloud development.</div></div>
                <div class="terminal-input-row">
                    <span class="prompt">dev@gdc-session:~/{session_id}$</span>
                    <input type="text" id="term-input" class="term-input" placeholder="Type a command (e.g. ls, pwd, touch helper.py, python3 main.py) and press Enter..." onkeydown="if(event.key==='Enter') runCommand(this.value)">
                </div>
            </div>
        </div>
        {ai_dock_html}
    </div>

    <!-- Project Switcher & Workspace Management Modal -->
    <div id="new-project-modal" class="modal-overlay" style="display: none;">
        <div class="modal-card" style="width: 520px;">
            <div class="modal-header">
                <h3>📁 Project Management & Workspace Switcher</h3>
                <button onclick="closeNewProjectModal()" class="btn-modal-close">✕</button>
            </div>
            <div style="display: flex; gap: 8px; border-bottom: 1px solid #30363d; padding-bottom: 8px; margin-bottom: 8px;">
                <button id="tab-btn-switch" onclick="switchModalTab('switch')" style="background: #21262d; border: 1px solid #30363d; color: #58a6ff; padding: 5px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer;">🔄 Switch Project</button>
                <button id="tab-btn-create" onclick="switchModalTab('create')" style="background: transparent; border: 1px solid transparent; color: #8b949e; padding: 5px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer;">➕ New Project</button>
                <button id="tab-btn-reset" onclick="switchModalTab('reset')" style="background: transparent; border: 1px solid transparent; color: #8b949e; padding: 5px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer;">🧹 Reset Current</button>
            </div>

            <!-- Tab 1: Switch Project -->
            <div id="modal-view-switch">
                <p style="color: #8b949e; font-size: 12px; margin-bottom: 10px; line-height: 1.4;">
                    Switch between sovereign development projects. Each project maintains its own isolated disk files, editor tabs, and terminal environment.
                </p>
                <div id="project-list-container" style="max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;">
                    <div style="color: #8b949e; font-size: 12px; padding: 12px; text-align: center;">Loading projects...</div>
                </div>
            </div>

            <!-- Tab 2: Create New Project -->
            <div id="modal-view-create" style="display: none;">
                <p style="color: #8b949e; font-size: 12px; margin-bottom: 10px; line-height: 1.4;">
                    Create a new sovereign project on dedicated disk storage. Choose an initial scaffolding template.
                </p>
                <div style="margin-bottom: 12px;">
                    <label style="display: block; font-size: 11px; font-weight: bold; color: #c9d1d9; margin-bottom: 4px;">Project Name:</label>
                    <input type="text" id="new-project-name" placeholder="e.g. telemetry-service, billing-api, sovereign-model" style="width: 100%; background: #0d1117; border: 1px solid #30363d; color: #ffffff; padding: 6px 10px; font-size: 13px; border-radius: 4px; outline: none; box-sizing: border-box;" onkeydown="if(event.key==='Enter') createNewProject();">
                </div>
                <div style="font-size: 11px; font-weight: bold; color: #c9d1d9; margin-bottom: 6px;">Select Initial Template:</div>
                <div class="project-template-option active" onclick="selectTemplate('telemetry', this)">
                    <div class="template-title">📐 GDC Air-Gapped Telemetry Service</div>
                    <div class="template-desc">Modular telemetry collector with CPU, memory, and disk health probes + pytest suites.</div>
                </div>
                <div class="project-template-option" onclick="selectTemplate('microservice', this)">
                    <div class="template-title">🚀 Python Sovereign Microservice</div>
                    <div class="template-desc">Standard air-gapped Python service with health checks and unit tests.</div>
                </div>
                <div class="project-template-option" onclick="selectTemplate('clean', this)">
                    <div class="template-title">🧹 Clean / Empty Starting Project</div>
                    <div class="template-desc">Minimal starting workspace with entrypoint main.py and README.md.</div>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px;">
                    <button onclick="createNewProject()" class="btn-modal-confirm">🚀 Create & Open Project</button>
                </div>
            </div>

            <!-- Tab 3: Reset Workspace -->
            <div id="modal-view-reset" style="display: none;">
                <p style="color: #f85149; font-size: 12px; margin-bottom: 10px; line-height: 1.4;">
                    <strong>Warning:</strong> Resetting will wipe all files in the current active project (<code>{session_id}</code>) and re-initialize it with the chosen template.
                </p>
                <div class="project-template-option active" onclick="selectTemplate('telemetry', this)">
                    <div class="template-title">📐 GDC Air-Gapped Telemetry Service</div>
                    <div class="template-desc">Re-initialize current project as Telemetry Service.</div>
                </div>
                <div class="project-template-option" onclick="selectTemplate('microservice', this)">
                    <div class="template-title">🚀 Python Sovereign Microservice</div>
                    <div class="template-desc">Re-initialize current project as Python Sovereign Microservice.</div>
                </div>
                <div class="project-template-option" onclick="selectTemplate('clean', this)">
                    <div class="template-title">🧹 Clean Starting Workspace</div>
                    <div class="template-desc">Remove all files in current project and reset to empty main.py.</div>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px;">
                    <button onclick="confirmResetCurrentProject()" class="btn-modal-confirm" style="background: #da3633;">⚠️ Reset Active Project</button>
                </div>
            </div>

            <div class="modal-footer">
                <button onclick="closeNewProjectModal()" class="btn-modal-cancel">Close</button>
            </div>
        </div>
    </div>

    <script>
        const sessionId = "{session_id}";
        const termOutput = document.getElementById("terminal-output");
        const codeEditor = document.getElementById("code-editor");
        const termInput = document.getElementById("term-input");

        const files = {files_json};
        let currentFile = "main.py";
        let selectedProjectTemplate = "telemetry";

        function switchProject(projectName) {{
            if (!projectName || projectName === sessionId) return;
            appendTerminal("switch-project " + projectName, "Switching to project: " + projectName + "...", "");
            const authQuery = window.location.search.includes("oidc_login=success") ? "?oidc_login=success" : "";
            window.location.href = "/instances/" + projectName + authQuery;
        }}

        function switchModalTab(tabName) {{
            ["switch", "create", "reset"].forEach(t => {{
                const view = document.getElementById("modal-view-" + t);
                const btn = document.getElementById("tab-btn-" + t);
                if (view) view.style.display = (t === tabName) ? "block" : "none";
                if (btn) {{
                    if (t === tabName) {{
                        btn.style.background = "#21262d";
                        btn.style.borderColor = "#30363d";
                        btn.style.color = "#58a6ff";
                    }} else {{
                        btn.style.background = "transparent";
                        btn.style.borderColor = "transparent";
                        btn.style.color = "#8b949e";
                    }}
                }}
            }});
            if (tabName === "switch") {{
                fetchProjects();
            }}
        }}

        async function fetchProjects() {{
            try {{
                const resp = await fetch("/instances/" + sessionId + "/projects");
                const data = await resp.json();
                const headerSelect = document.getElementById("header-project-select");
                const listContainer = document.getElementById("project-list-container");
                if (data.projects) {{
                    if (headerSelect) {{
                        headerSelect.innerHTML = "";
                        data.projects.forEach(p => {{
                            const opt = document.createElement("option");
                            opt.value = p.name;
                            opt.textContent = "📁 " + p.name + " (" + p.file_count + " files)";
                            if (p.name === sessionId) opt.selected = true;
                            headerSelect.appendChild(opt);
                        }});
                    }}
                    if (listContainer) {{
                        listContainer.innerHTML = "";
                        data.projects.forEach(p => {{
                            const isCurrent = p.name === sessionId;
                            const card = document.createElement("div");
                            card.style.cssText = "background: #0d1117; border: 1px solid " + (isCurrent ? "#238636" : "#30363d") + "; border-radius: 6px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center;";
                            
                            const left = document.createElement("div");
                            left.innerHTML = '<div style="font-weight: bold; color: ' + (isCurrent ? "#58a6ff" : "#ffffff") + '; font-size: 13px;">📁 ' + p.name + 
                                (isCurrent ? ' <span style="background: #238636; color: white; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px;">Active</span>' : '') + 
                                '</div><div style="font-size: 11px; color: #8b949e; margin-top: 3px;">' + p.file_count + ' files: ' + (p.files.slice(0, 3).join(", ") + (p.files.length > 3 ? "..." : "")) + '</div>';
                            
                            const right = document.createElement("div");
                            right.style.cssText = "display: flex; gap: 6px; align-items: center;";

                            if (!isCurrent) {{
                                const switchBtn = document.createElement("button");
                                switchBtn.textContent = "🚀 Switch";
                                switchBtn.style.cssText = "background: #1f6feb; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer;";
                                switchBtn.onclick = () => switchProject(p.name);
                                right.appendChild(switchBtn);
                            }}

                            if (p.name !== "default-workspace") {{
                                const delBtn = document.createElement("button");
                                delBtn.innerHTML = "🗑️";
                                delBtn.title = "Delete project " + p.name;
                                delBtn.style.cssText = "background: #21262d; border: 1px solid #30363d; color: #f85149; padding: 4px 8px; border-radius: 4px; font-size: 11px; cursor: pointer;";
                                delBtn.onclick = () => deleteProject(p.name);
                                right.appendChild(delBtn);
                            }}

                            card.appendChild(left);
                            card.appendChild(right);
                            listContainer.appendChild(card);
                        }});
                    }}
                }}
            }} catch (err) {{
                console.error("Error fetching projects:", err);
            }}
        }}

        async function createNewProject() {{
            const input = document.getElementById("new-project-name");
            const name = input ? input.value.trim() : "";
            if (!name) {{
                alert("Please enter a project name.");
                if (input) input.focus();
                return;
            }}
            const cleanName = name.replace(/[^a-zA-Z0-9_-]/g, "");
            if (!cleanName) {{
                alert("Project name must contain alphanumeric characters, hyphens, or underscores.");
                return;
            }}
            closeNewProjectModal();
            appendTerminal("create-project " + cleanName, "Creating project '" + cleanName + "' with template '" + selectedProjectTemplate + "'...", "");
            try {{
                const resp = await fetch("/instances/" + sessionId + "/projects/create", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ name: cleanName, template: selectedProjectTemplate }})
                }});
                const data = await resp.json();
                if (data.redirect_url) {{
                    const authQuery = window.location.search.includes("oidc_login=success") ? "?oidc_login=success" : "";
                    window.location.href = data.redirect_url + authQuery;
                }} else {{
                    fetchProjects();
                }}
            }} catch (err) {{
                appendTerminal("create-project", "", "Failed to create project: " + err.message);
            }}
        }}

        async function deleteProject(projectName) {{
            if (!confirm("Are you sure you want to permanently delete project '" + projectName + "' and all its files from disk?")) return;
            try {{
                const resp = await fetch("/instances/" + sessionId + "/projects/delete", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ name: projectName }})
                }});
                const data = await resp.json();
                if (data.status === "ok") {{
                    appendTerminal("delete-project " + projectName, "Deleted project '" + projectName + "'.", "");
                    if (projectName === sessionId && data.redirect_url) {{
                        const authQuery = window.location.search.includes("oidc_login=success") ? "?oidc_login=success" : "";
                        window.location.href = data.redirect_url + authQuery;
                    }} else {{
                        fetchProjects();
                    }}
                }} else {{
                    alert("Error deleting project: " + (data.message || "Unknown error"));
                }}
            }} catch (err) {{
                alert("Failed to delete project: " + err.message);
            }}
        }}

        function confirmResetCurrentProject() {{
            if (!confirm("Reset all files in active project '" + sessionId + "' to '" + selectedProjectTemplate + "' template?")) return;
            confirmNewProject();
        }}

        function showNewProjectModal() {{
            const modal = document.getElementById("new-project-modal");
            if (modal) {{
                modal.style.display = "flex";
                switchModalTab("switch");
                fetchProjects();
            }}
        }}

        function closeNewProjectModal() {{
            const modal = document.getElementById("new-project-modal");
            if (modal) modal.style.display = "none";
        }}

        function selectTemplate(tmpl, el) {{
            selectedProjectTemplate = tmpl;
            document.querySelectorAll(".project-template-option").forEach(opt => opt.classList.remove("active"));
            if (el) el.classList.add("active");
        }}

        async function confirmNewProject() {{
            closeNewProjectModal();
            appendTerminal("init-project " + selectedProjectTemplate, "Resetting workspace and initializing " + selectedProjectTemplate + "...", "");
            try {{
                const resp = await fetch("/instances/" + sessionId + "/project/reset", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ template: selectedProjectTemplate, clean_all: true }})
                }});
                const data = await resp.json();
                if (data.files) {{
                    for (const k in files) delete files[k];
                    for (const [k, v] of Object.entries(data.files)) {{
                        files[k] = v;
                    }}
                    currentFile = files.hasOwnProperty("telemetry.py") ? "telemetry.py" : (files.hasOwnProperty("main.py") ? "main.py" : Object.keys(files)[0]);
                    renderFileList();
                    switchFile(currentFile);
                    appendTerminal("init-project [completed]", "Project initialized successfully with files:\\n" + Object.keys(files).map(f => "  - " + f).join("\\n"), "");
                    fetchProjects();
                }} else if (data.error) {{
                    appendTerminal("init-project [error]", "", data.error);
                }}
            }} catch (err) {{
                appendTerminal("init-project", "", "Failed to initialize project: " + err.message);
            }}
        }}

        function renderFileList() {{
            const ul = document.getElementById("file-list");
            const tabsList = document.getElementById("tabs-list");
            if (!ul) return;
            ul.innerHTML = "";

            if (tabsList) {{
                const addBtn = tabsList.querySelector(".tab-add");
                tabsList.innerHTML = "";
                if (addBtn) tabsList.appendChild(addBtn);
            }}

            const filenames = Object.keys(files);
            if (!filenames.includes(currentFile) && filenames.length > 0) {{
                currentFile = filenames[0];
            }}

            filenames.forEach(name => {{
                // Explorer Item
                const li = document.createElement("li");
                li.id = "file-" + name;
                if (name === currentFile) li.className = "active";
                li.onclick = () => switchFile(name);

                const span = document.createElement("span");
                span.className = "file-name";
                span.textContent = "📄 " + name;
                li.appendChild(span);

                const delBtn = document.createElement("button");
                delBtn.className = "btn-file-delete";
                delBtn.title = "Delete " + name;
                delBtn.innerHTML = "🗑️";
                delBtn.onclick = (e) => {{
                    e.stopPropagation();
                    deleteFile(name);
                }};
                li.appendChild(delBtn);
                ul.appendChild(li);

                // Tab Item
                if (tabsList) {{
                    const addBtn = tabsList.querySelector(".tab-add");
                    const tab = document.createElement("div");
                    tab.id = "tab-" + name;
                    tab.className = "tab" + (name === currentFile ? " active" : "");
                    tab.onclick = () => switchFile(name);

                    const titleSpan = document.createElement("span");
                    titleSpan.textContent = name;
                    tab.appendChild(titleSpan);

                    const closeSpan = document.createElement("span");
                    closeSpan.className = "tab-close";
                    closeSpan.textContent = "✕";
                    closeSpan.title = "Close tab";
                    closeSpan.onclick = (e) => {{
                        e.stopPropagation();
                        closeTab(name);
                    }};
                    tab.appendChild(closeSpan);

                    if (addBtn) tabsList.insertBefore(tab, addBtn);
                    else tabsList.appendChild(tab);
                }}
            }});

            if (codeEditor && files[currentFile] !== undefined) {{
                codeEditor.value = files[currentFile];
            }}
        }}

        function closeTab(filename) {{
            const tab = document.getElementById("tab-" + filename);
            if (tab) tab.remove();
            if (currentFile === filename) {{
                const remaining = Object.keys(files).filter(f => f !== filename);
                if (remaining.length > 0) switchFile(remaining[0]);
            }}
        }}

        function showNewFileDialog() {{
            const box = document.getElementById("new-file-box");
            if (!box) return;
            box.style.display = "block";
            const input = document.getElementById("new-filename-input");
            if (input) {{
                input.value = "";
                input.focus();
            }}
        }}

        function hideNewFileDialog() {{
            const box = document.getElementById("new-file-box");
            if (box) box.style.display = "none";
        }}

        async function confirmNewFile() {{
            const input = document.getElementById("new-filename-input");
            if (!input) return;
            const name = input.value.trim();
            if (!name) return;

            // Check if file already exists on disk
            try {{
                const resp = await fetch("/instances/" + sessionId + "/files");
                const data = await resp.json();
                if (data.files && data.files[name] !== undefined) {{
                    files[name] = data.files[name];
                    appendTerminal("open " + name, "Opened existing workspace file: " + name, "");
                    hideNewFileDialog();
                    renderFileList();
                    switchFile(name);
                    return;
                }}
            }} catch (e) {{}}

            if (!files.hasOwnProperty(name)) {{
                const ext = name.split('.').pop().toLowerCase();
                let defaultContent = "# " + name + "\\n\\n";
                if (ext === "md") defaultContent = "# " + name + "\\n\\n";
                else if (ext === "json") defaultContent = "{{\\n  \\n}}\\n";
                files[name] = defaultContent;

                try {{
                    await fetch("/instances/" + sessionId + "/files/save", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ filename: name, content: defaultContent }})
                    }});
                }} catch (e) {{}}
                appendTerminal("touch " + name, "Created " + name + " in workspace.", "");
            }}

            hideNewFileDialog();
            renderFileList();
            switchFile(name);
        }}

        async function deleteFile(filename) {{
            if (filename === "main.py") {{
                if (!confirm("Are you sure you want to delete main.py? This is the primary application entrypoint.")) return;
            }} else {{
                if (!confirm("Delete '" + filename + "' from workspace?")) return;
            }}
            try {{
                const resp = await fetch("/instances/" + sessionId + "/files/delete", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ filename: filename }})
                }});
                delete files[filename];
                appendTerminal("rm " + filename, "Deleted " + filename + " from workspace.", "");
                const remaining = Object.keys(files);
                if (currentFile === filename) {{
                    currentFile = remaining.length > 0 ? remaining[0] : "main.py";
                }}
                renderFileList();
                if (remaining.length > 0) {{
                    switchFile(currentFile);
                }} else if (codeEditor) {{
                    codeEditor.value = "";
                }}
            }} catch (err) {{
                alert("Failed to delete " + filename + ": " + err.message);
            }}
        }}

        async function refreshFiles() {{
            try {{
                const resp = await fetch("/instances/" + sessionId + "/files");
                const data = await resp.json();
                if (data.files) {{
                    for (const k in files) {{
                        if (!data.files.hasOwnProperty(k)) {{
                            delete files[k];
                        }}
                    }}
                    for (const [k, v] of Object.entries(data.files)) {{
                        files[k] = v;
                    }}
                    const fileKeys = Object.keys(files);
                    if (!files.hasOwnProperty(currentFile) && fileKeys.length > 0) {{
                        currentFile = fileKeys[0];
                    }}
                    renderFileList();
                    if (files.hasOwnProperty(currentFile)) {{
                        switchFile(currentFile);
                    }}
                    appendTerminal("refresh", "Synced files with workspace disk (" + fileKeys.length + " files).", "");
                }}
            }} catch (err) {{
                appendTerminal("refresh", "", "Error refreshing files: " + err.message);
            }}
        }}

        function switchFile(filename) {{
            if (!files.hasOwnProperty(filename)) return;
            if (codeEditor) {{
                files[currentFile] = codeEditor.value;
                currentFile = filename;
                codeEditor.value = files[filename];
            }}

            document.querySelectorAll("#file-list li").forEach(li => li.classList.remove("active"));
            const activeLi = document.getElementById("file-" + filename);
            if (activeLi) activeLi.classList.add("active");

            document.querySelectorAll(".tabs-list .tab").forEach(tab => tab.classList.remove("active"));
            const activeTab = document.getElementById("tab-" + filename);
            if (activeTab) activeTab.classList.add("active");

            if (codeEditor) codeEditor.focus();
        }}

        if (codeEditor) {{
            codeEditor.addEventListener("input", function() {{
                if (typeof files !== "undefined" && typeof currentFile !== "undefined") {{
                    files[currentFile] = codeEditor.value;
                }}
            }});
            codeEditor.addEventListener("keydown", function(e) {{
                if ((e.ctrlKey || e.metaKey) && e.key === "s") {{
                    e.preventDefault();
                    saveCode();
                }}
                if (e.key === "Tab") {{
                    e.preventDefault();
                    const start = this.selectionStart;
                    const end = this.selectionEnd;
                    this.value = this.value.substring(0, start) + "    " + this.value.substring(end);
                    this.selectionStart = this.selectionEnd = start + 4;
                }}
            }});
        }}

        function appendTerminal(promptCmd, stdout, stderr) {{
            if (!termOutput) return;
            const div = document.createElement("div");
            div.innerHTML = '<span class="prompt">dev@gdc-session:~/{session_id}$</span> ' + promptCmd;
            termOutput.appendChild(div);
            if (stdout) {{
                const out = document.createElement("div");
                out.textContent = stdout;
                termOutput.appendChild(out);
            }}
            if (stderr) {{
                const err = document.createElement("div");
                err.style.color = "#f85149";
                err.textContent = stderr;
                termOutput.appendChild(err);

                // Phase 3 Terminal Hook: Auto-Repair Action
                const fixBtn = document.createElement("button");
                fixBtn.className = "btn-term-repair";
                fixBtn.innerHTML = "⚡ Fix with Gemma Agent";
                fixBtn.onclick = () => triggerTerminalRepair(promptCmd, stderr);
                termOutput.appendChild(fixBtn);
            }}
            termOutput.scrollTop = termOutput.scrollHeight;
        }}

        async function runCode() {{
            if (!codeEditor) return;
            files[currentFile] = codeEditor.value;
            const code = codeEditor.value;
            appendTerminal("python3 " + currentFile, "Running " + currentFile + "...", "");
            try {{
                const resp = await fetch("/instances/" + sessionId + "/exec", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ code: code, filename: currentFile }})
                }});
                const data = await resp.json();
                appendTerminal("python3 " + currentFile + " [completed]", data.stdout, data.stderr);
            }} catch (err) {{
                appendTerminal("python3 " + currentFile, "", "Execution error: " + err.message);
            }}
        }}

        async function runCommand(cmd) {{
            if (!cmd || !cmd.trim()) return;
            if (termInput) termInput.value = "";
            appendTerminal(cmd, "", "");
            try {{
                const resp = await fetch("/instances/" + sessionId + "/exec", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ command: cmd }})
                }});
                const data = await resp.json();
                if (data.stdout || data.stderr) {{
                    appendTerminal(cmd + " [output]", data.stdout, data.stderr);
                }} else if (cmd.trim().startsWith("ls")) {{
                    appendTerminal(cmd + " [output]", "(empty directory)", "");
                }} else {{
                    appendTerminal(cmd + " [output]", "(command completed with no output)", "");
                }}
                if (cmd.startsWith("touch ") || cmd.startsWith("rm ") || cmd.includes(">") || cmd.startsWith("cat ") || cmd.startsWith("ls")) {{
                    refreshFiles();
                }}
            }} catch (err) {{
                appendTerminal("cmd", "", "Command error: " + err.message);
            }}
        }}

        async function saveCode() {{
            if (!codeEditor) return;
            files[currentFile] = codeEditor.value;
            const saveBtn = document.querySelector(".btn-save");
            const origText = saveBtn ? saveBtn.textContent : "💾 Save";
            if (saveBtn) saveBtn.textContent = "⏳ Saving...";
            try {{
                const resp = await fetch("/instances/" + sessionId + "/files/save", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ filename: currentFile, content: codeEditor.value }})
                }});
                const data = await resp.json();
                if (saveBtn) {{
                    saveBtn.textContent = "✓ Saved";
                    setTimeout(() => {{ if (saveBtn) saveBtn.textContent = origText; }}, 1500);
                }}
                appendTerminal("save " + currentFile, "📄 Saved " + currentFile + " (" + (data.bytes || codeEditor.value.length) + " bytes) to disk.", "");
            }} catch (err) {{
                if (saveBtn) saveBtn.textContent = origText;
                appendTerminal("save " + currentFile, "", "Error saving file: " + err.message);
            }}
        }}

        // Terminal Height Resizing & LocalStorage Persistence
        function initTerminalResizer() {{
            const resizer = document.getElementById("terminal-resizer");
            const terminal = document.querySelector(".terminal");
            const container = document.querySelector(".editor-container");
            if (!resizer || !terminal || !container) return;

            let isDragging = false;
            let startY = 0;
            let startHeight = 0;

            const savedHeight = localStorage.getItem("gdc_dev_terminal_height");
            if (savedHeight) {{
                const parsed = parseInt(savedHeight, 10);
                if (!isNaN(parsed) && parsed >= 80) {{
                    terminal.style.height = parsed + "px";
                    updateTermSizeButtons(parsed);
                }}
            }}

            resizer.addEventListener("mousedown", function(e) {{
                isDragging = true;
                startY = e.clientY;
                startHeight = terminal.getBoundingClientRect().height;
                resizer.classList.add("resizing");
                document.body.style.cursor = "row-resize";
                document.body.style.userSelect = "none";
                e.preventDefault();
            }});

            window.addEventListener("mousemove", function(e) {{
                if (!isDragging) return;
                const deltaY = startY - e.clientY;
                const containerRect = container.getBoundingClientRect();
                const maxHeight = Math.max(80, containerRect.height - 100);
                let newHeight = startHeight + deltaY;
                if (newHeight < 80) newHeight = 80;
                if (newHeight > maxHeight) newHeight = maxHeight;
                terminal.style.height = newHeight + "px";
                updateTermSizeButtons(newHeight);
            }});

            window.addEventListener("mouseup", function() {{
                if (isDragging) {{
                    isDragging = false;
                    resizer.classList.remove("resizing");
                    document.body.style.cursor = "";
                    document.body.style.userSelect = "";
                    const finalHeight = Math.round(terminal.getBoundingClientRect().height);
                    localStorage.setItem("gdc_dev_terminal_height", finalHeight);
                }}
            }});

            resizer.addEventListener("dblclick", function() {{
                const currentHeight = Math.round(terminal.getBoundingClientRect().height);
                const targetHeight = (currentHeight > 260) ? 220 : 380;
                setTerminalHeight(targetHeight);
            }});
        }}

        function setTerminalHeight(h) {{
            const terminal = document.querySelector(".terminal");
            const container = document.querySelector(".editor-container");
            if (!terminal) return;
            let target = h;
            if (container) {{
                const maxHeight = Math.max(80, container.getBoundingClientRect().height - 100);
                if (target > maxHeight) target = maxHeight;
            }}
            terminal.style.height = target + "px";
            localStorage.setItem("gdc_dev_terminal_height", target);
            updateTermSizeButtons(target);
        }}

        function updateTermSizeButtons(currentHeight) {{
            const buttons = document.querySelectorAll(".btn-term-size");
            buttons.forEach(btn => {{
                const val = parseInt(btn.textContent.trim(), 10);
                if (!isNaN(val)) {{
                    if (Math.abs(val - currentHeight) < 25) {{
                        btn.classList.add("active");
                    }} else {{
                        btn.classList.remove("active");
                    }}
                }}
            }});
        }}

        function toggleTerminalMaximize() {{
            const terminal = document.querySelector(".terminal");
            const container = document.querySelector(".editor-container");
            const btn = document.getElementById("btn-term-max");
            if (!terminal || !container) return;
            const currentHeight = Math.round(terminal.getBoundingClientRect().height);
            const maxHeight = Math.max(140, container.getBoundingClientRect().height - 100);
            if (currentHeight >= maxHeight - 25) {{
                setTerminalHeight(220);
                if (btn) {{ btn.innerHTML = "⤢"; btn.title = "Maximize Terminal"; }}
            }} else {{
                setTerminalHeight(maxHeight);
                if (btn) {{ btn.innerHTML = "🗗"; btn.title = "Restore Terminal Height"; }}
            }}
        }}

        renderFileList();
        switchFile(currentFile);
        fetchProjects();
        initTerminalResizer();

        {ai_js_block}
    </script>
</body>
</html>"""

class OperatorHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/readyz"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "gdc-dev-operator"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

class SessionServiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth_mode = os.environ.get("AUTH_MODE", "mock")
        if self.path in ("/health", "/readyz"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "gdc-dev-operator"}).encode("utf-8"))
            return

        cookie_header = self.headers.get("Cookie", "")
        auth_cookie = None
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("dev_auth_user="):
                auth_cookie = part.split("=", 1)[1]
                break
            elif part.startswith("theia_auth_user=") and not auth_cookie:
                auth_cookie = part.split("=", 1)[1]

        header_user = self.headers.get(HEADER_USER_KEY)
        if header_user:
            user_id = header_user
        elif auth_cookie and auth_mode == "oidc":
            user_id = auth_cookie
        elif auth_mode == "mock":
            user_id = MOCK_USER_ID
        else:
            user_id = "anonymous"

        if "?logout=true" in self.path or self.path == "/logout":
            self.send_response(302)
            self.send_header("Set-Cookie", "dev_auth_user=; Path=/; Max-Age=0; SameSite=Lax")
            self.send_header("Set-Cookie", "theia_auth_user=; Path=/; Max-Age=0; SameSite=Lax")
            self.send_header("Location", "/")
            self.end_headers()
            return

        parts = [p for p in self.path.split("/") if p]
        session_id = parts[1] if len(parts) > 1 and parts[0] == "instances" else "default-workspace"
        
        if "?oidc_login=success" in self.path:
            session_id = session_id.split("?")[0]
            user_id = "oidc-developer@gdc.local"

        session_id = session_id.split("?")[0]
        ws_dir = get_workspace_dir(session_id)

        if self.path.endswith("/projects"):
            proj_list = list_projects()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"current_project": session_id, "projects": proj_list}).encode("utf-8"))
            return

        if self.path.endswith("/files"):
            ensure_workspace_dir(session_id=session_id, user_id=user_id, workspace_dir=ws_dir)
            files_map = load_workspace_files(workspace_dir=ws_dir)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"files": files_map, "project": session_id}).encode("utf-8"))
            return
            
        html_content = render_workspace_ui(session_id, user_id)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        if user_id != "anonymous" and auth_mode == "oidc":
            self.send_header("Set-Cookie", f"dev_auth_user={user_id}; Path=/; SameSite=Lax")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def do_POST(self):
        auth_mode = os.environ.get("AUTH_MODE", "mock")
        cookie_header = self.headers.get("Cookie", "")
        auth_cookie = None
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("dev_auth_user="):
                auth_cookie = part.split("=", 1)[1]
                break
            elif part.startswith("theia_auth_user=") and not auth_cookie:
                auth_cookie = part.split("=", 1)[1]

        header_user = self.headers.get(HEADER_USER_KEY)
        if header_user:
            user_id = header_user
        elif auth_cookie and auth_mode == "oidc":
            user_id = auth_cookie
        elif auth_mode == "mock":
            user_id = MOCK_USER_ID
        else:
            user_id = "oidc-developer@gdc.local"

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        session_id = "default-workspace"
        if self.path.startswith("/instances/"):
            parts = [p for p in self.path.split("/") if p]
            if len(parts) > 1 and parts[0] == "instances":
                session_id = parts[1].split("?")[0]
        ws_dir = get_workspace_dir(session_id)

        # Multi-Project lifecycle endpoints
        if "/projects/create" in self.path:
            try:
                data = json.loads(post_data)
            except Exception:
                data = {}
            p_name = data.get("name", "").strip()
            p_tmpl = data.get("template", "telemetry")
            if not p_name:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Project name is required"}).encode("utf-8"))
                return
            p_clean = "".join(c for c in p_name if c.isalnum() or c in ("-", "_")).strip()
            if not p_clean:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid project name"}).encode("utf-8"))
                return
            p_dir = get_workspace_dir(p_clean)
            os.makedirs(p_dir, exist_ok=True)
            created_files = reset_project(p_tmpl, session_id=p_clean, user_id=user_id, workspace_dir=p_dir)
            redirect_url = f"/instances/{p_clean}"
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "name": p_clean,
                "template": p_tmpl,
                "files": created_files,
                "redirect_url": redirect_url
            }).encode("utf-8"))
            return

        if "/projects/delete" in self.path:
            try:
                data = json.loads(post_data)
            except Exception:
                data = {}
            p_name = data.get("name", "").strip()
            p_clean = "".join(c for c in p_name if c.isalnum() or c in ("-", "_")).strip()
            if not p_clean:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Project name is required"}).encode("utf-8"))
                return
            success, msg = delete_project(p_clean)
            redirect_url = "/instances/default-workspace" if p_clean == session_id else None
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok" if success else "error",
                "name": p_clean,
                "message": msg,
                "redirect_url": redirect_url
            }).encode("utf-8"))
            return

        # Local handlers
        if "/ai-chat" in self.path:
            resp_data = handle_ai_chat(post_data, user_id, workspace_dir=ws_dir)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        if "/files/save" in self.path:
            try:
                data = json.loads(post_data)
            except Exception:
                data = {}
            filename = data.get("filename", "")
            content = data.get("content", "")
            if filename:
                full_path = os.path.join(ws_dir, filename)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "filename": filename, "bytes": len(content), "project": session_id}).encode("utf-8"))
                return

        if "/files/delete" in self.path:
            try:
                data = json.loads(post_data)
            except Exception:
                data = {}
            filename = data.get("filename", "")
            if filename:
                full_path = os.path.join(ws_dir, filename)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "deleted": filename, "project": session_id}).encode("utf-8"))
                return

        if "/project/reset" in self.path:
            try:
                data = json.loads(post_data)
            except Exception:
                data = {}
            tmpl = data.get("template", "telemetry")
            new_files = reset_project(tmpl, session_id=session_id, user_id=user_id, workspace_dir=ws_dir)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "template": tmpl, "files": new_files, "project": session_id}).encode("utf-8"))
            return

        if "/exec" in self.path:
            try:
                data = json.loads(post_data)
            except Exception:
                data = {}

            command = data.get("command", "")
            code = data.get("code", None)
            filename = data.get("filename", "main.py")
            ensure_workspace_dir(session_id=session_id, user_id=user_id, workspace_dir=ws_dir)

            if code is not None:
                full_path = os.path.join(ws_dir, filename)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(code)
                try:
                    res = subprocess.run(["python3", filename], capture_output=True, text=True, timeout=10, cwd=ws_dir)
                    stdout = res.stdout
                    stderr = res.stderr
                except Exception as e:
                    stdout = ""
                    stderr = str(e)
            elif command:
                try:
                    res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15, cwd=ws_dir)
                    stdout = res.stdout
                    stderr = res.stderr
                except Exception as e:
                    stdout = ""
                    stderr = str(e)
            else:
                stdout = "No command or code provided.\n"
                stderr = ""

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"stdout": stdout, "stderr": stderr, "project": session_id}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def run_health_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, OperatorHealthHandler)
    print(f"[OPERATOR] Healthcheck server running on port {port}...")
    httpd.serve_forever()

def run_session_server(port=3000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, SessionServiceHandler)
    print(f"[OPERATOR] Session service running on port {port}...")
    httpd.serve_forever()

def control_loop():
    auth_mode = os.environ.get("AUTH_MODE", "mock")
    ai_enabled = os.environ.get("AI_ENABLED", "false")
    agent_mode = os.environ.get("AI_AGENT_MODE", "passive")
    print(f"============================================================")
    print(f" GDC Developer Environment Operator (v1.3.0) - Phase 1, 2 & 3 ")
    print(f" Authentication Mode : {auth_mode}")
    print(f" Mock User Identity  : {MOCK_USER_ID}")
    print(f" AI Integration Mode : {ai_enabled} (Agent: {agent_mode})")
    print(f"============================================================")
    print(f"[INFO] Watching Gateway API HTTPRoutes in namespace 'gdc-dev'...")
    
    counter = 0
    while True:
        time.sleep(15)
        counter += 1
        print(f"[HEARTBEAT {counter}] Operator control loop active. Reconciling workspace sessions...")

if __name__ == "__main__":
    health_thread = Thread(target=run_health_server, args=(8080,), daemon=True)
    health_thread.start()
    session_thread = Thread(target=run_session_server, args=(3000,), daemon=True)
    session_thread.start()
    control_loop()
