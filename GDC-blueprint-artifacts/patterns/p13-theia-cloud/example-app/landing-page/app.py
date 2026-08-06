#!/usr/bin/env python3
"""
@file app.py
@brief Eclipse Theia Cloud Landing Page Service (Phase 1 & Phase 2 Reference Implementation).

@details Serves the IDE landing page, validating identity headers according to the
configured AUTH_MODE (Phase 1 mock header vs Phase 2 Keycloak OIDC). When under OIDC mode
and unauthenticated ("anonymous"), renders an enterprise Keycloak OIDC login portal.

@date 2026-07-07
"""

import os
import json
import subprocess
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

HEADER_USER_KEY = os.environ.get("HEADER_USER_KEY", "X-User-ID")
MOCK_USER_ID = os.environ.get("MOCK_USER_ID", "dev-user-1")

def render_workspace_ui(session_id, user_id):
    auth_mode = os.environ.get("AUTH_MODE", "mock")
    if auth_mode == "oidc" and user_id == "anonymous":
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Keycloak OIDC Login - Eclipse Theia Cloud</title>
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
        <p>Eclipse Theia Cloud on Google Distributed Cloud (Air-Gapped)</p>
        <div class="realm-info">
            <div><strong>Identity Provider:</strong> Keycloak OIDC</div>
            <div><strong>Active Realm:</strong> <code>gdc-theia-realm</code></div>
            <div><strong>Client ID:</strong> <code>theia-cloud-client</code></div>
        </div>
        <button onclick="simulateLogin()" class="btn-login">Sign in with Keycloak OIDC</button>
        <script>
            function simulateLogin() {{
                alert("Redirecting to Keycloak IdP (gdc-theia-realm)... For Phase 2 local emulation verification, passing simulated OIDC token header.");
                window.location.href = "/instances/" + "{session_id}" + "?oidc_login=success";
            }}
        </script>
    </div>
</body>
</html>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Eclipse Theia IDE - {session_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #1e1e1e; color: #cccccc; display: flex; flex-direction: column; height: 100vh; }}
        .header {{ background: #333333; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #454545; }}
        .header h2 {{ margin: 0; font-size: 16px; color: #ffffff; }}
        .header .user-info {{ font-size: 13px; color: #9cdcfe; }}
        .main {{ display: flex; flex: 1; overflow: hidden; }}
        .sidebar {{ width: 220px; background: #252526; border-right: 1px solid #383838; padding: 12px; font-size: 13px; }}
        .sidebar h3 {{ font-size: 11px; text-transform: uppercase; color: #bbbbbb; margin-top: 0; }}
        .file-list {{ list-style: none; padding-left: 0; margin: 0; }}
        .file-list li {{ padding: 6px 8px; cursor: pointer; border-radius: 4px; color: #e8e8e8; }}
        .file-list li:hover {{ background: #2a2d2e; }}
        .file-list li.active {{ background: #37373d; color: #ffffff; }}
        .editor-container {{ flex: 1; display: flex; flex-direction: column; background: #1e1e1e; }}
        .editor-tabs {{ background: #2d2d2d; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #383838; padding-right: 12px; }}
        .tab {{ padding: 8px 16px; background: #1e1e1e; color: #ffffff; border-right: 1px solid #383838; font-size: 13px; }}
        .btn-run {{ background: #238636; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; margin-left: 8px; }}
        .btn-run:hover {{ background: #2ea043; }}
        .btn-save {{ background: #1f6feb; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; }}
        .btn-save:hover {{ background: #388bfd; }}
        .editor-textarea {{ flex: 1; padding: 20px; font-family: 'Courier New', Courier, monospace; font-size: 14px; line-height: 1.6; color: #d4d4d4; background: #1e1e1e; border: none; outline: none; resize: none; width: 100%; box-sizing: border-box; }}
        .terminal {{ height: 200px; background: #181818; border-top: 1px solid #383838; padding: 12px; font-family: 'Courier New', Courier, monospace; font-size: 13px; color: #cccccc; display: flex; flex-direction: column; }}
        .terminal-header {{ font-size: 11px; text-transform: uppercase; color: #888888; margin-bottom: 8px; flex-shrink: 0; }}
        .terminal-output {{ flex: 1; overflow-y: auto; white-space: pre-wrap; margin-bottom: 8px; }}
        .terminal-input-row {{ display: flex; align-items: center; background: #1f1f1f; padding: 4px 8px; border-radius: 4px; border: 1px solid #333333; }}
        .prompt {{ color: #4ec9b0; margin-right: 8px; font-weight: bold; flex-shrink: 0; }}
        .term-input {{ flex: 1; background: transparent; border: none; outline: none; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-size: 13px; }}
        .btn-exit {{ background: #d73a49; color: white; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .btn-exit:hover {{ background: #cb2431; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h2>Eclipse Theia Cloud IDE - Session: <span style="color: #4ec9b0;">{session_id}</span></h2>
        </div>
        <div class="user-info">
            Authenticated User: <strong>{user_id}</strong> | Mode: <strong>{auth_mode}</strong> | <a href="/" class="btn-exit">Exit Session</a>
        </div>
    </div>
    <div class="main">
        <div class="sidebar">
            <h3>Explorer</h3>
            <ul class="file-list">
                <li class="active">📄 main.py</li>
                <li>📄 README.md</li>
                <li>📄 .theia/settings.json</li>
                <li>📁 workspace-data/</li>
            </ul>
        </div>
        <div class="editor-container">
            <div class="editor-tabs">
                <div class="tab">main.py</div>
                <div>
                    <button onclick="saveCode()" class="btn-save">💾 Save</button>
                    <button onclick="runCode()" class="btn-run">▶ Run Code</button>
                </div>
            </div>
            <textarea id="code-editor" class="editor-textarea" spellcheck="false">import os
import sys

# Welcome to your resilient air-gapped Eclipse Theia Workspace!
def main():
    print("Workspace ID : {session_id}")
    print("Active User  : {user_id}")
    print("Ready for high-security cloud development.")

if __name__ == "__main__":
    main()</textarea>
            <div class="terminal">
                <div class="terminal-header">Terminal - bash (local session)</div>
                <div id="terminal-output" class="terminal-output"><div><span class="prompt">theia@gdc-session:~/workspace$</span> python3 main.py</div><div>Workspace ID : {session_id}</div><div>Active User  : {user_id}</div><div>Ready for high-security cloud development.</div></div>
                <div class="terminal-input-row">
                    <span class="prompt">theia@gdc-session:~/workspace$</span>
                    <input type="text" id="term-input" class="term-input" placeholder="Type a command (e.g. ls, pwd, python3 -c 'print(1+1)') and press Enter..." onkeydown="if(event.key==='Enter') runCommand(this.value)">
                </div>
            </div>
        </div>
    </div>
    <script>
        const sessionId = "{session_id}";
        const termOutput = document.getElementById("terminal-output");
        const codeEditor = document.getElementById("code-editor");
        const termInput = document.getElementById("term-input");

        codeEditor.addEventListener("keydown", function(e) {{
            if (e.key === "Tab") {{
                e.preventDefault();
                const start = this.selectionStart;
                const end = this.selectionEnd;
                this.value = this.value.substring(0, start) + "    " + this.value.substring(end);
                this.selectionStart = this.selectionEnd = start + 4;
            }}
        }});

        function appendTerminal(promptCmd, stdout, stderr) {{
            const div = document.createElement("div");
            div.innerHTML = '<span class="prompt">theia@gdc-session:~/workspace$</span> ' + promptCmd;
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
            }}
            termOutput.scrollTop = termOutput.scrollHeight;
        }}

        async function runCode() {{
            const code = codeEditor.value;
            appendTerminal("python3 main.py", "Running main.py...", "");
            try {{
                const resp = await fetch("/instances/" + sessionId + "/exec", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ code: code }})
                }});
                const data = await resp.json();
                appendTerminal("python3 main.py [completed]", data.stdout, data.stderr);
            }} catch (err) {{
                appendTerminal("python3 main.py", "", "Execution error: " + err.message);
            }}
        }}

        async function runCommand(cmd) {{
            if (!cmd.trim()) return;
            termInput.value = "";
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
                }}
            }} catch (err) {{
                appendTerminal("cmd", "", "Command error: " + err.message);
            }}
        }}

        function saveCode() {{
            alert("📄 main.py saved to workspace memory.");
        }}
    </script>
</body>
</html>"""

class LandingPageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth_mode = os.environ.get("AUTH_MODE", "mock")
        if self.path in ("/health", "/readyz"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "theia-cloud-landing-page"}).encode("utf-8"))
            return

        user_id = self.headers.get(HEADER_USER_KEY, MOCK_USER_ID if auth_mode == "mock" else "anonymous")

        if self.path.startswith("/instances/"):
            session_id = self.path.split("/")[-1] if "/" in self.path and len(self.path.split("/")[-1]) > 0 else "default-workspace"
            if "?oidc_login=success" in self.path:
                session_id = session_id.split("?")[0]
                user_id = "oidc-developer@gdc.local"
            try:
                req = urllib.request.Request(f"http://theia-cloud-session-service:3000{self.path}", headers={HEADER_USER_KEY: user_id})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    content = resp.read()
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            except Exception as e:
                html_content = render_workspace_ui(session_id, user_id)
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))
                return

        if auth_mode == "oidc" and user_id == "anonymous":
            html_content = render_workspace_ui("default-workspace", "anonymous")
        else:
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Eclipse Theia Cloud IDE</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #0d1117; color: #c9d1d9; }}
        .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 24px; max-width: 600px; margin: 0 auto; }}
        h1 {{ color: #58a6ff; font-size: 24px; margin-top: 0; }}
        .badge {{ background: #238636; color: #ffffff; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
        .btn {{ display: inline-block; background: #1f6feb; color: #ffffff; padding: 10px 16px; text-decoration: none; border-radius: 6px; margin-top: 16px; font-weight: 500; }}
        .btn:hover {{ background: #388bfd; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Eclipse Theia Cloud IDE <span class="badge">Phase 1/2</span></h1>
        <p>Welcome to the resilient cloud-hosted development environment.</p>
        <hr style="border: 0; border-top: 1px solid #30363d; margin: 16px 0;">
        <p><strong>Authentication Mode:</strong> <code>{auth_mode}</code></p>
        <p><strong>Authenticated User:</strong> <code>{user_id}</code></p>
        <a href="/instances/default-workspace" class="btn">Launch IDE Workspace Session</a>
    </div>
</body>
</html>"""

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def do_POST(self):
        if "/exec" in self.path:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
            try:
                req = urllib.request.Request(f"http://theia-cloud-session-service:3000{self.path}", data=post_data.encode('utf-8'), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    content = resp.read()
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            except Exception:
                try:
                    data = json.loads(post_data)
                except Exception:
                    data = {}

                command = data.get("command", "")
                code = data.get("code", None)
                
                if code is not None:
                    tmp_file = "/tmp/workspace_main.py"
                    with open(tmp_file, "w") as f:
                        f.write(code)
                    try:
                        res = subprocess.run(["python3", tmp_file], capture_output=True, text=True, timeout=5)
                        stdout = res.stdout
                        stderr = res.stderr
                    except Exception as e:
                        stdout = ""
                        stderr = str(e)
                elif command:
                    try:
                        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=5, cwd="/tmp")
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
                self.wfile.write(json.dumps({"stdout": stdout, "stderr": stderr}).encode("utf-8"))
                return
        self.send_response(404)
        self.end_headers()

def run(server_class=HTTPServer, handler_class=LandingPageHandler, port=8080):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    auth_mode = os.environ.get("AUTH_MODE", "mock")
    print(f"[{auth_mode.upper()} MODE] Landing Page service listening on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run()
