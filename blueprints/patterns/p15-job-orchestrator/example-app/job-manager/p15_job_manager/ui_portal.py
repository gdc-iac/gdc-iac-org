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
"""100% Offline, Self-Contained, CDN-Free Web UI for `:8080` Portal & `:8081` PA Admin (`REQ-UX-001`–`002`)."""

from __future__ import annotations

import html


def _esc(val: str) -> str:
    return html.escape(str(val or ""), quote=True)


def render_portal_html(
    engine_mode: str,
    gitops_mode: str,
    namespace: str,
    default_registry: str = "harbor.gdc.local/blueprint-images/",
    allow_simulated_oidc: bool = False,
    default_worker_tag: str = "v1.0.0",
) -> str:
    """Render 100% offline, CDN-free `:8080` AO/PA Job Portal SPA (`textContent`-only DOM updates)."""
    eng = _esc(engine_mode)
    gops = _esc(gitops_mode)
    ns = _esc(namespace)
    reg_prefix = default_registry.rstrip("/") + "/"
    default_img = _esc(f"{reg_prefix}p15-reference-worker:{default_worker_tag}")
    sim_hitl_btn = (
        ' <button class="btn btn-secondary" id="btn-demo-finding">+ Simulate Sample HITL Finding (Stepping-Stone)</button>'
        if allow_simulated_oidc
        else ""
    )
    signed_out_msg = (
        "Sign in above (Keycloak OIDC or Stepping-Stone persona) to load schedules and runs."
        if allow_simulated_oidc
        else "Sign in above with Keycloak OIDC to load schedules and runs."
    )
    second_approver_hint = (
        "pa-approver@gdc.local" if allow_simulated_oidc else "pa-alice"
    )
    empty_findings_msg = (
        "No enforcement findings yet. Run an enforcement job in hitl-approval mode (or click Simulate Sample HITL Finding in Stepping-Stone mode)."
        if allow_simulated_oidc
        else "No enforcement findings yet. Run an enforcement job in hitl-approval mode to review proposed patches here."
    )
    sim_hitl_js = (
        """
      const demoFndBtn = document.getElementById("btn-demo-finding");
      if (demoFndBtn) {
        demoFndBtn.addEventListener("click", async () => {
          const fb = document.getElementById("approval-feedback");
          clearNode(fb);
          const suffix = Math.random().toString(16).slice(2, 7);
          const jobId = "hitl-policy-check-" + suffix;
          const fndId = "fnd-" + suffix;
          const ns = document.getElementById("portal-ns").dataset.ns;
          const img = document.getElementById("f-image").value.trim();
          const sR = await fetch("/api/v1/schedules", {
            method: "POST", headers: apiHeaders(),
            body: JSON.stringify({
              job_id: jobId, namespace: ns, persona: currentPersona || "AO",
              job_class: "enforce", worker_mode: "enforce-resource-policy",
              enforcement_mode: "hitl-approval", worker_image: img,
              schedule_cron: "0 * * * *", timezone: "UTC"
            })
          });
          const sD = await sR.json().catch(() => ({}));
          if (!sR.ok) {
            const b = document.createElement("div"); b.className = "err-banner";
            b.textContent = "Step 1 failed (HTTP " + sR.status + "): " + (sD.error || "Sign in with a non-viewer account first.");
            fb.appendChild(b); return;
          }
          const tR = await fetch("/api/v1/schedules/" + encodeURIComponent(jobId) + "/trigger", {
            method: "POST", headers: apiHeaders(), body: JSON.stringify({dispatch_to_cluster: false})
          });
          const tD = await tR.json().catch(() => ({}));
          if (!tR.ok) {
            const b = document.createElement("div"); b.className = "err-banner";
            b.textContent = "Trigger failed (HTTP " + tR.status + "): " + (tD.error || "Unknown error");
            fb.appendChild(b); return;
          }
          const runId = tD.run.run_id;
          const cR = await fetch("/api/v1/runs/" + encodeURIComponent(runId) + "/complete", {
            method: "POST", headers: apiHeaders(),
            body: JSON.stringify({
              exit_code: 0,
              violations: [{
                finding_id: fndId, target_kind: "Deployment", target_namespace: ns,
                target_name: "sample-app-" + suffix, target_resource_version: "1",
                rule_id: "P15-REQ-OWNER-LABEL", severity: "warning",
                planned_patch: {metadata: {labels: {owner: "platform-ops"}}}
              }]
            })
          });
          const b = document.createElement("div");
          b.className = cR.ok ? "ok-banner" : "err-banner";
          b.textContent = cR.ok
            ? "Created pending HITL finding '" + fndId + "' requested by " + currentUser + ". Try clicking Approve as yourself (expect HTTP 403 Four-Eyes block), then Sign Out -> Sign In as a second operator (e.g. pa-approver@gdc.local) and click Approve!"
            : "Finding submission failed (HTTP " + cR.status + ")";
          fb.appendChild(b);
          await refreshAll();
        });
      }"""
        if allow_simulated_oidc
        else ""
    )
    sim_portal_block = (
        f"""
        <div class="auth-subbox auth-sim">
          <div class="auth-subhdr">Stepping-Stone Emulation Persona Sign-In <span class="badge-amber">Disabled in GDC-ag Production</span></div>
          <div class="auth-row">
            <input id="sim-user" value="ao-operator@gdc.local" placeholder="Username or email">
            <select id="sim-role">
              <option value="ao-job-operator">ao-job-operator (AO Read/Write &mdash; {ns})</option>
              <option value="pa-job-admin">pa-job-admin (PA Admin &mdash; All Namespaces)</option>
              <option value="job-viewer">job-viewer (Read-Only &mdash; {ns})</option>
            </select>
            <button class="btn btn-green" id="btn-sim-login">Sign In</button>
          </div>
        </div>"""
        if allow_simulated_oidc
        else ""
    )
    sim_portal_js = (
        """
      const simBtn = document.getElementById("btn-sim-login");
      if (simBtn) {
        simBtn.addEventListener("click", async () => {
          const errEl = document.getElementById("auth-error");
          errEl.className = "hidden";
          const r = await fetch("/auth/simulated", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              username: document.getElementById("sim-user").value.trim() || "ao-operator@gdc.local",
              role: document.getElementById("sim-role").value,
              namespace: document.getElementById("portal-ns").dataset.ns
            })
          });
          const d = await r.json().catch(() => ({}));
          if (!r.ok) {
            errEl.className = "err-banner";
            errEl.textContent = "HTTP " + r.status + ": " + (d.error || "Sign-in failed");
            return;
          }
          if (d.csrf_token) { csrfToken = d.csrf_token; localStorage.setItem("p15_csrf", d.csrf_token); }
          await refreshAll();
        });
      }"""
        if allow_simulated_oidc
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GDC Job Orchestrator Portal (:8080)</title>
  <style>
    :root {{
      --bg: #f4f7fb; --surface: #ffffff; --border: #dadce0; --text: #202124;
      --muted: #5f6368; --primary: #1a73e8; --green: #188038; --amber: #c26401; --red: #d93025;
    }}
    * {{ box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    header {{
      background: var(--surface); border-bottom: 1px solid var(--border);
      padding: 14px 24px; display: flex; justify-content: space-between; align-items: center;
    }}
    .badge {{
      display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px;
      font-weight: 600; background: #e8f0fe; color: var(--primary); margin-left: 8px;
    }}
    .pill-ok {{ background: #e6f4ea; color: var(--green); padding: 3px 10px; border-radius: 12px; font-weight: 700; font-size: 12px; display: inline-block; }}
    .pill-warn {{ background: #fef7e0; color: var(--amber); padding: 3px 10px; border-radius: 12px; font-weight: 700; font-size: 12px; display: inline-block; }}
    .pill-run {{ background: #e8f0fe; color: var(--primary); padding: 3px 10px; border-radius: 12px; font-weight: 700; font-size: 12px; display: inline-block; animation: pulseBadge 1.2s ease-in-out infinite; }}
    .pill-err {{ background: #fce8e6; color: var(--red); padding: 3px 10px; border-radius: 12px; font-weight: 700; font-size: 12px; display: inline-block; }}
    @keyframes pulseBadge {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.55; }} }}
    .prog-track {{ width: 140px; height: 8px; background: #e8eaed; border-radius: 99px; overflow: hidden; margin-top: 5px; }}
    .prog-fill-run {{ height: 100%; width: 65%; background: linear-gradient(90deg, #1a73e8, #669df6, #1a73e8); background-size: 200% 100%; animation: slideBar 1.2s linear infinite; }}
    .prog-fill-ok {{ height: 100%; width: 100%; background: var(--green); }}
    .prog-fill-err {{ height: 100%; width: 100%; background: var(--red); }}
    @keyframes slideBar {{ 0% {{ background-position: 200% 0; }} 100% {{ background-position: 0 0; }} }}
    nav {{
      display: flex; gap: 8px; padding: 10px 24px; background: var(--surface);
      border-bottom: 1px solid var(--border); align-items: center; justify-content: space-between;
    }}
    .nav-group {{ display: flex; gap: 8px; }}
    nav button {{
      border: 1px solid var(--border); background: var(--bg); padding: 8px 14px;
      border-radius: 6px; cursor: pointer; font-weight: 600; color: var(--text);
    }}
    nav button.active {{ background: var(--primary); color: #fff; border-color: var(--primary); }}
    main {{ max-width: 1380px; margin: 18px auto; padding: 0 24px 90px 24px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 14px; margin-bottom: 16px; }}
    .kpi-card {{ background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--primary); border-radius: 10px; padding: 14px 16px; }}
    .kpi-card.kpi-run {{ border-left-color: #1a73e8; }}
    .kpi-card.kpi-ok {{ border-left-color: var(--green); }}
    .kpi-card.kpi-warn {{ border-left-color: var(--amber); }}
    .kpi-label {{ color: var(--muted); font-size: 12.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }}
    .kpi-val {{ font-size: 28px; font-weight: 700; margin-top: 6px; }}
    .split-grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; margin-top: 12px; }}
    .split-grid > * {{ min-width: 0; }}
    .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
    .card-hdr {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
    .card-hdr h3 {{ margin: 0; font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
    th {{ color: var(--muted); font-weight: 600; background: #f8fafd; }}
    .row-highlight {{ background: #e8f0fe; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 12px; margin-bottom: 14px; }}
    .field {{ display: flex; flex-direction: column; gap: 4px; }}
    .field.span-all {{ grid-column: 1 / -1; }}
    .field label {{ font-size: 12px; font-weight: 700; color: var(--muted); }}
    .info-strip {{
      background: #f1f6fe; border: 1px solid #c5dafc; border-left: 4px solid var(--primary);
      border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 13px; color: #174ea6;
    }}
    .binding-strip {{
      background: #eff6ff; border: 1px solid #93c5fd; border-radius: 6px; padding: 10px 12px;
      margin-top: 8px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12.5px; color: #1e3a8a; font-weight: 600;
    }}
    input, select {{ padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; width: 100%; font-size: 13.5px; }}
    .btn {{ padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; font-weight: 600; background: var(--primary); color: #fff; font-size: 13px; white-space: nowrap; }}
    .btn-green {{ background: var(--green); color: #fff; }}
    .btn-secondary {{ background: #e8eaed; color: var(--text); }}
    .btn-warn {{ background: var(--amber); color: #fff; }}
    .btn-danger {{ background: var(--red); color: #fff; }}
    .hidden {{ display: none; }}
    pre {{ background: #0f172a; color: #f8fafc; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 12.5px; max-height: 290px; margin: 8px 0 0 0; line-height: 1.45; }}
    .warn-banner {{ background: #fef7e0; border: 1px solid #fde293; padding: 10px 12px; border-radius: 6px; color: #7c4a00; margin-top: 8px; }}
    .ok-banner {{ background: #e6f4ea; border: 1px solid #81c995; padding: 10px 12px; border-radius: 6px; color: #137333; margin-top: 8px; font-weight: 600; }}
    .err-banner {{ background: #fce8e6; border: 1px solid #f6aea9; padding: 10px 12px; border-radius: 6px; color: #a50e0e; margin-top: 8px; font-weight: 600; }}
    .live-banner-run {{
      background: linear-gradient(90deg, #e8f0fe, #d2e3fc); border: 2px solid #1a73e8;
      border-radius: 10px; padding: 14px 18px; margin-bottom: 16px; color: #174ea6;
      font-weight: 700; font-size: 14.5px; box-shadow: 0 2px 10px rgba(26,115,232,0.14);
    }}
    .live-banner-ok {{
      background: linear-gradient(90deg, #e6f4ea, #ceead6); border: 2px solid #188038;
      border-radius: 10px; padding: 14px 18px; margin-bottom: 16px; color: #137333;
      font-weight: 700; font-size: 14.5px;
    }}
    .live-banner-bar {{ width: 100%; height: 8px; background: rgba(255,255,255,0.7); border-radius: 99px; overflow: hidden; margin-top: 8px; }}
    .auth-bar {{ display: flex; align-items: center; gap: 10px; font-size: 13.5px; }}
    .auth-subbox {{ background: #f8fafd; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-top: 10px; }}
    .auth-sim {{ background: #fef7e0; border-color: #fde293; }}
    .auth-subhdr {{ font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
    .auth-row {{ display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; align-items: center; }}
    .auth-row-jwt {{ display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center; }}
    .badge-amber {{ background: #fde293; color: #7c4a00; padding: 2px 8px; border-radius: 10px; font-size: 11.5px; font-weight: 700; }}
    .sub-txt {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
  </style>
</head>
<body>
  <header>
    <div>
      <strong>Pattern 15: GDC-ag Job Management Portal (:8080)</strong>
      <span class="badge">Engine: {eng}</span>
      <span class="badge">GitOps: {gops}</span>
      <span class="badge" id="portal-ns" data-ns="{ns}">Namespace: {ns}</span>
    </div>
    <div class="auth-bar">
      <span id="auth-status">Not signed in</span>
      <button class="btn btn-secondary" id="btn-toggle-auth">Sign In</button>
      <button class="btn btn-secondary hidden" id="btn-logout">Sign Out</button>
    </div>
  </header>
  <nav id="portal-tabs">
    <div class="nav-group">
      <button data-tab="tab-dashboard" class="active">Dashboard</button>
      <button data-tab="tab-schedules">Catalogue &amp; Schedules</button>
      <button data-tab="tab-runs">Run Explorer &amp; Logs</button>
      <button data-tab="tab-approvals">Enforcement &amp; HITL Queue</button>
      <button data-tab="tab-notifications">Notifications &amp; Outbox</button>
    </div>
    <button class="btn" id="btn-nav-add-job">+ Add New Job</button>
  </nav>
  <main>
    <div class="card" id="auth-panel">
      <div class="card-hdr">
        <h3>Sign In to Job Portal (:8080)</h3>
        <span class="sub-txt">Surface-isolated session cookie (<code>jobs_user_session</code>) + CSRF protection</span>
      </div>
      <div class="auth-subbox">
        <div class="auth-subhdr">Keycloak OIDC Sign-In (Production RS256 JWKS + PKCE S256)</div>
        <div class="auth-row-jwt">
          <input id="oidc-jwt-input" type="password" placeholder="Paste Keycloak RS256 Bearer JWT to exchange for a browser session cookie (POST /auth/oidc/session)">
          <button class="btn" id="btn-oidc-jwt-login">Sign In with Keycloak JWT</button>
          <button class="btn btn-secondary" id="btn-oidc-pkce">Keycloak PKCE Login URL</button>
        </div>
        <div id="oidc-pkce-out" class="sub-txt" style="margin-top:6px;"></div>
      </div>{sim_portal_block}
      <div id="auth-error" class="hidden"></div>
    </div>

    <section id="tab-dashboard">
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">Registered Schedules</div><div class="kpi-val" id="kpi-jobs">0</div></div>
        <div class="kpi-card kpi-run"><div class="kpi-label">Running Now</div><div class="kpi-val" id="kpi-running">0</div></div>
        <div class="kpi-card kpi-ok"><div class="kpi-label">Succeeded Runs</div><div class="kpi-val" id="kpi-succeeded">0</div></div>
        <div class="kpi-card kpi-warn"><div class="kpi-label">HITL / Outbox Delivered</div><div class="kpi-val"><span id="kpi-approvals">0</span> / <span id="kpi-outbox">0</span></div></div>
      </div>

      <div id="live-run-banner" class="hidden"></div>

      <div class="card" id="card-live-runs">
        <div class="card-hdr">
          <h3>Live Job Execution &amp; Recent Runs</h3>
          <span class="sub-txt" id="status-msg">Ready. Zero external CDN dependencies loaded.</span>
        </div>
        <table>
          <thead><tr><th>Job ID &amp; Mode</th><th>Run ID / Engine Ref</th><th>Live Status</th><th>Output Metrics &amp; Artifact</th><th>Action</th></tr></thead>
          <tbody id="tbl-dash-runs"></tbody>
        </table>
      </div>

      <div class="split-grid">
        <div class="card" id="card-dash-result">
          <div class="card-hdr"><h3>Latest Job Result (result.json)</h3></div>
          <pre id="dash-latest-result">Add a job and click Run Now to view live execution results and Object Storage artifacts here.</pre>
        </div>
        <div class="card" id="card-dash-schedules">
          <div class="card-hdr">
            <h3>Active Job Schedules</h3>
            <button class="btn btn-secondary" id="btn-dash-add-job">+ Register Job</button>
          </div>
          <div id="dash-schedule-feedback"></div>
          <table>
            <thead><tr><th>Job ID</th><th>Mode</th><th>State</th><th>Actions</th></tr></thead>
            <tbody id="tbl-dash-schedules"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-schedules" class="hidden">
      <div class="card" id="card-add-job-form">
        <div class="card-hdr"><h3>Add / Preview Job Schedule (UTC Internal Windows)</h3></div>
        <div class="info-strip" id="onboarding-flow-note">
          <strong>How custom scripts enter the Orchestrator:</strong>
          1) Package <code>p15_jobs/runner.py</code> in a non-root container &rarr;
          2) Push pinned tag to the allowlisted registry &rarr;
          3) Bind the <strong>Pinned Worker Image</strong> &amp; <strong>Worker Mode</strong> below (compiled into <code>gdc-standard-job-runner-v1</code> &mdash; zero raw script uploads or PodSpecs).
        </div>
        <div class="form-grid">
          <div class="field">
            <label for="f-job-id">Job ID (DNS-1123)</label>
            <input id="f-job-id" placeholder="e.g. ao-inventory-audit-15m">
          </div>
          <div class="field">
            <label for="f-persona">Persona</label>
            <select id="f-persona"><option value="AO">AO (Application Operator)</option><option value="PA">PA (Platform Admin)</option></select>
          </div>
          <div class="field">
            <label for="f-class">Job Class</label>
            <select id="f-class"><option value="batch">batch</option><option value="monitor">monitor</option><option value="enforce">enforce</option></select>
          </div>
          <div class="field">
            <label for="f-mode">Worker Mode (Passed as --mode)</label>
            <select id="f-mode">
              <option value="batch-watermarked-rollup">batch-watermarked-rollup (Built-in Reference Worker)</option>
              <option value="monitor-platform-hygiene">monitor-platform-hygiene (Built-in Reference Worker)</option>
              <option value="enforce-resource-policy">enforce-resource-policy (Built-in HITL/Enforcement Worker)</option>
              <option value="inventory-audit-report">inventory-audit-report (Custom Example Image)</option>
              <option value="__custom__">Custom worker mode...</option>
            </select>
            <input id="f-mode-custom" class="hidden" style="margin-top:6px;" placeholder="Enter custom --mode name (e.g. my-custom-job)">
          </div>
          <div class="field">
            <label for="f-cron">5-Field Cron Expression</label>
            <input id="f-cron" value="*/15 * * * *" placeholder="*/15 * * * *">
          </div>
          <div class="field">
            <label for="f-tz">IANA Timezone</label>
            <input id="f-tz" value="UTC" placeholder="UTC">
          </div>
          <div class="field">
            <label for="f-enf">Enforcement Ladder Mode</label>
            <select id="f-enf"><option value="audit">audit (default)</option><option value="hitl-approval">hitl-approval</option><option value="auto-remediate">auto-remediate</option></select>
          </div>
          <div class="field">
            <label>Approved Runner Template</label>
            <input value="gdc-standard-job-runner-v1" disabled>
          </div>
          <div class="field span-all" id="field-worker-image">
            <label for="f-image">Pinned Worker Image (Allowlisted Registry &mdash; Packages Your Job Script)</label>
            <input id="f-image" value="{default_img}" placeholder="registry/image:v1.0.0">
            <div class="sub-txt" id="mode-source-hint"></div>
          </div>
        </div>
        <button class="btn btn-secondary" id="btn-preview-cron">1. Preview Next 5 Runs</button>
        <button class="btn btn-green" id="btn-create-job">2. Save &amp; Register Job</button>
        <div id="schedule-action-feedback"></div>
        <div id="cron-preview-box"></div>
      </div>
      <div class="card">
        <div class="card-hdr"><h3>Registered Job Schedules</h3></div>
        <table>
          <thead><tr><th>Job ID</th><th>Persona</th><th>Class</th><th>Mode</th><th>Cron (TZ)</th><th>Enforcement</th><th>State</th><th>Actions</th></tr></thead>
          <tbody id="tbl-schedules"></tbody>
        </table>
      </div>
    </section>

    <section id="tab-runs" class="hidden">
      <div class="card">
        <div class="card-hdr"><h3>Run Explorer, Structured Job Results &amp; Redacted Object Storage Logs</h3></div>
        <table>
          <thead><tr><th>Run ID</th><th>Job ID</th><th>Trigger</th><th>UTC Window</th><th>Status</th><th>Result Summary</th><th>Action</th></tr></thead>
          <tbody id="tbl-runs"></tbody>
        </table>
        <div class="split-grid">
          <div>
            <strong>Job Output &amp; Metrics (result.json / summary_json)</strong>
            <pre id="run-result-viewer">Select a run and click "View Results &amp; Logs" to inspect structured job output, watermarks, and Object Storage URIs.</pre>
          </div>
          <div>
            <strong>Archived Redacted Execution Logs (Object Storage)</strong>
            <pre id="run-log-viewer">Select a run to inspect redacted Object Storage logs.</pre>
          </div>
        </div>
      </div>
    </section>

    <section id="tab-approvals" class="hidden">
      <div class="card">
        <div class="card-hdr">
          <h3>Enforcement Findings &amp; Four-Eyes HITL Approval Queue</h3>
          <div>{sim_hitl_btn}</div>
        </div>
        <div class="info-strip">
          <strong>What Four-Eyes HITL &amp; TOCTOU Mean:</strong>
          Enforcement jobs in <code>hitl-approval</code> mode never auto-mutate Kubernetes resources. Each policy finding is parked here with a cryptographic <code>SHA-256</code> digest of the planned patch + live <code>resourceVersion</code> (<strong>TOCTOU</strong> guard against stale overwrites). Under the <strong>Four-Eyes Rule</strong>, the requester is blocked (<code>HTTP 403</code>) from approving their own finding &mdash; click <strong>Sign Out</strong>, sign in as a second operator (e.g. <code>{second_approver_hint}</code>), and click <strong>Approve</strong> (or use <strong>1-Click Rollback</strong> after remediation).
        </div>
        <div id="approval-feedback"></div>
        <table>
          <thead><tr><th>Finding ID</th><th>Target</th><th>Rule</th><th>Patch SHA-256</th><th>Status</th><th>Requested By</th><th>Actions</th></tr></thead>
          <tbody id="tbl-findings"></tbody>
        </table>
      </div>
    </section>

    <section id="tab-notifications" class="hidden">
      <div class="card">
        <div class="card-hdr"><h3>Namespace Notification Sinks</h3></div>
        <div class="form-grid">
          <div class="field"><label for="s-name">Sink Name</label><input id="s-name" value="demo-webhook" placeholder="Sink Name"></div>
          <div class="field">
            <label for="s-type">Sink Type</label>
            <select id="s-type">
              <option value="generic-webhook">generic-webhook</option>
              <option value="smtp-relay">smtp-relay</option>
              <option value="chat-webhook">chat-webhook</option>
              <option value="itsm-webhook">itsm-webhook</option>
              <option value="portal-feed">portal-feed</option>
            </select>
          </div>
          <div class="field span-all"><label for="s-url">Target Internal URL (Must be in PA ALLOWED_NOTIFICATION_HOSTS)</label><input id="s-url" placeholder="https://webhooks.gdc.local/events"></div>
        </div>
        <button class="btn" id="btn-add-sink">1. Register Sink</button>
        <button class="btn btn-green" id="btn-test-sink">2. Send Test Notification</button>
        <div id="sink-feedback"></div>
      </div>
      <div class="card">
        <div class="card-hdr"><h3>Transactional Notification Outbox Ledger</h3></div>
        <table>
          <thead><tr><th>Outbox ID</th><th>Sink</th><th>Event</th><th>Severity</th><th>Status</th><th>Attempts</th></tr></thead>
          <tbody id="tbl-outbox"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    (function() {{
      "use strict";
      let csrfToken = localStorage.getItem("p15_csrf") || "";
      let jobsById = {{}};
      let currentUser = "";
      let currentPersona = "AO";
      let hasRunningJobs = false;
      function apiHeaders() {{
        const h = {{"Content-Type": "application/json"}};
        const latest = localStorage.getItem("p15_csrf") || csrfToken;
        if (latest) {{
          csrfToken = latest;
          h["X-CSRF-Token"] = latest;
        }}
        return h;
      }}
      function clearNode(el) {{ while (el.firstChild) el.removeChild(el.firstChild); }}
      function addCell(tr, text) {{
        const td = document.createElement("td");
        td.textContent = String(text == null ? "" : text);
        tr.appendChild(td);
        return td;
      }}
      function buildStatusCell(status) {{
        const td = document.createElement("td");
        const st = String(status || "");
        const span = document.createElement("span");
        span.className = st === "Succeeded" ? "pill-ok" : (st === "Running" || st === "Pending" ? "pill-run" : "pill-err");
        span.textContent = st === "Succeeded" ? "\u2713 Succeeded" : (st === "Running" ? "\u25cf Running" : st);
        td.appendChild(span);
        const track = document.createElement("div");
        track.className = "prog-track";
        const fill = document.createElement("div");
        fill.className = st === "Succeeded" ? "prog-fill-ok" : (st === "Running" || st === "Pending" ? "prog-fill-run" : "prog-fill-err");
        track.appendChild(fill);
        td.appendChild(track);
        return td;
      }}
      function summarizeRun(r) {{
        const s = r.summary_json || {{}};
        const m = s.metrics || s;
        const parts = [];
        if (m.inventory_items_audited != null) parts.push("Audited: " + m.inventory_items_audited);
        if (m.compliant_count != null) parts.push("Compliant: " + m.compliant_count);
        if (m.non_compliant_count != null) parts.push("Findings: " + m.non_compliant_count);
        if (m.compliance_pct != null) parts.push(m.compliance_pct + "%");
        if (m.records != null) parts.push("Records: " + m.records);
        if (s.items_processed != null && parts.length === 0) parts.push("Items: " + s.items_processed);
        if (r.exit_code != null) parts.push("exit=" + r.exit_code);
        if (parts.length === 0 && r.status === "Running") return "Executing container pod & writing WAL to Object Storage...";
        return parts.length ? parts.join(" \u2022 ") : (r.artifact_uri || "-");
      }}
      async function inspectRun(r) {{
        const resEl = document.getElementById("run-result-viewer");
        const logEl = document.getElementById("run-log-viewer");
        const doc = {{
          run_id: r.run_id,
          job_id: r.job_id,
          status: r.status,
          exit_code: r.exit_code,
          engine_mode: r.engine_mode,
          engine_ref: r.engine_ref,
          window_utc: r.window_start + " -> " + r.window_end,
          shard_key: r.shard_key,
          artifact_uri: r.artifact_uri || "-",
          summary: r.summary_json || {{}}
        }};
        resEl.textContent = JSON.stringify(doc, null, 2);
        logEl.textContent = "Fetching redacted Object Storage logs for " + r.run_id + "...";
        try {{
          const resp = await fetch("/api/v1/runs/" + encodeURIComponent(r.run_id) + "/logs");
          if (resp.ok) {{
            logEl.textContent = "=== Archived Redacted Log (" + r.run_id + ") ===\\n" + (await resp.text());
          }} else {{
            logEl.textContent = "No archived stdout.log uploaded yet (HTTP " + resp.status + ").";
          }}
        }} catch (err) {{
          logEl.textContent = "Unable to load archived logs: " + String(err);
        }}
      }}
      function activateTab(tabId) {{
        document.querySelectorAll("#portal-tabs button[data-tab]").forEach((b) => {{
          b.classList.toggle("active", b.dataset.tab === tabId);
        }});
        document.querySelectorAll("main > section").forEach((s) => {{
          s.classList.toggle("hidden", s.id !== tabId);
        }});
        window.scrollTo({{top: 0, behavior: "instant"}});
      }}
      document.querySelectorAll("#portal-tabs button[data-tab]").forEach((btn) => {{
        btn.addEventListener("click", () => activateTab(btn.dataset.tab));
      }});
      ["btn-nav-add-job", "btn-dash-add-job"].forEach((id) => {{
        const el = document.getElementById(id);
        if (el) el.addEventListener("click", () => activateTab("tab-schedules"));
      }});
      function buildScheduleStateCell(j) {{
        const td = document.createElement("td");
        const span = document.createElement("span");
        if (j.circuit_breaker_open) {{
          span.className = "pill-err";
          span.textContent = "Circuit-Open";
        }} else if (j.suspended) {{
          span.className = "pill-warn";
          span.textContent = "Paused";
        }} else {{
          span.className = "pill-ok";
          span.textContent = "Active";
        }}
        td.appendChild(span);
        return td;
      }}
      function showScheduleBanner(ok, msg) {{
        ["schedule-action-feedback", "dash-schedule-feedback"].forEach((id) => {{
          const fb = document.getElementById(id);
          if (!fb) return;
          clearNode(fb);
          const banner = document.createElement("div");
          banner.className = ok ? "ok-banner" : "err-banner";
          banner.textContent = msg;
          fb.appendChild(banner);
        }});
      }}
      async function toggleJobPause(jobId, pause) {{
        const action = pause ? "pause" : "resume";
        const resp = await fetch("/api/v1/schedules/" + encodeURIComponent(jobId) + "/" + action, {{
          method: "POST", headers: apiHeaders(), body: JSON.stringify({{}})
        }});
        const data = await resp.json().catch(() => ({{}}));
        if (!resp.ok) {{
          showScheduleBanner(false, "HTTP " + resp.status + ": " + (data.error || ("Unable to " + action + " job")));
        }} else if (data.reconcile && data.reconcile.gitops_protected) {{
          showScheduleBanner(false, "GitOps-protected schedule: export YAML MR to " + action + " '" + jobId + "'.");
        }} else if (data.reconcile && data.reconcile.cluster_error) {{
          showScheduleBanner(false, "Saved " + action + " in ledger, but Kubernetes update failed: " + data.reconcile.cluster_error);
        }} else {{
          showScheduleBanner(true, (pause ? "Paused" : "Resumed") + " schedule '" + jobId + "' (Kubernetes CronJob/CronWorkflow suspend=" + String(pause) + ").");
        }}
        await refreshAll();
      }}
      async function deleteJobFromUi(jobId) {{
        const resp = await fetch("/api/v1/schedules/" + encodeURIComponent(jobId), {{
          method: "DELETE", headers: apiHeaders()
        }});
        const data = await resp.json().catch(() => ({{}}));
        if (!resp.ok) {{
          showScheduleBanner(false, "HTTP " + resp.status + ": " + (data.error || "Unable to delete schedule"));
        }} else if (data.reconcile && data.reconcile.gitops_protected) {{
          showScheduleBanner(false, "GitOps-protected schedule: remove '" + jobId + "' via Git MR.");
        }} else if (data.cluster_error) {{
          showScheduleBanner(false, "Deleted '" + jobId + "' from Portal, but Kubernetes delete failed: " + data.cluster_error);
        }} else {{
          showScheduleBanner(true, "Deleted schedule '" + jobId + "' (removed from Portal & Kubernetes CronJob/CronWorkflow).");
        }}
        await refreshAll();
      }}
      async function triggerJobFromUi(jobId) {{
        const trResp = await fetch("/api/v1/schedules/" + encodeURIComponent(jobId) + "/trigger", {{
          method: "POST", headers: apiHeaders(), body: JSON.stringify({{shards: ["shard-00"]}})
        }});
        const trData = await trResp.json().catch(() => ({{}}));
        window.__p15LastTrigger = {{ok: trResp.ok, status: trResp.status, data: trData}};
        const clusterNote = trData.submitted_to_cluster
          ? " — Kubernetes job dispatched (auto-updating every 5s)."
          : " — queued on Dashboard.";
        showScheduleBanner(
          trResp.ok,
          trResp.ok
            ? "Triggered " + ((trData.run && trData.run.run_id) || jobId) + " (" + (trData.manifest_kind || "Run") + ")" + clusterNote
            : "Trigger failed (HTTP " + trResp.status + "): " + (trData.error || "Unknown error")
        );
        await refreshAll();
        if (trResp.ok) activateTab("tab-dashboard");
        return trData;
      }}
      async function refreshAll() {{
        try {{
          const meR = await fetch("/auth/me");
          const authPanel = document.getElementById("auth-panel");
          const toggleBtn = document.getElementById("btn-toggle-auth");
          const logoutBtn = document.getElementById("btn-logout");
          if (!meR.ok) {{
            currentUser = "";
            document.getElementById("auth-status").textContent = "Not signed in";
            authPanel.classList.remove("hidden");
            toggleBtn.classList.remove("hidden");
            logoutBtn.classList.add("hidden");
            document.getElementById("status-msg").textContent = "{signed_out_msg}";
            ["kpi-jobs", "kpi-running", "kpi-succeeded", "kpi-approvals", "kpi-outbox"].forEach((id) => {{
              document.getElementById(id).textContent = "0";
            }});
            document.getElementById("live-run-banner").className = "hidden";
            ["tbl-dash-runs", "tbl-dash-schedules", "tbl-schedules", "tbl-runs", "tbl-findings", "tbl-outbox"].forEach((id) => {{
              clearNode(document.getElementById(id));
            }});
            return;
          }}
          const me = await meR.json();
          currentUser = me.principal || "";
          currentPersona = me.persona || "AO";
          document.getElementById("auth-status").textContent =
            "Signed in: " + me.principal + " (" + me.persona + (me.can_mutate ? "" : " read-only") + ")";
          authPanel.classList.add("hidden");
          toggleBtn.classList.add("hidden");
          logoutBtn.classList.remove("hidden");

          const [jobsR, runsR, findR, obxR] = await Promise.all([
            fetch("/api/v1/schedules"), fetch("/api/v1/runs"),
            fetch("/api/v1/findings"), fetch("/api/v1/notifications/outbox")
          ]);
          if (!jobsR.ok) return;
          const jobs = (await jobsR.json()).items || [];
          const runs = (await runsR.json()).items || [];
          const findings = (await findR.json()).items || [];
          const outbox = (await obxR.json()).items || [];
          jobsById = {{}};
          jobs.forEach((j) => {{ jobsById[j.job_id] = j; }});

          const runningCount = runs.filter((r) => r.status === "Running" || r.status === "Pending").length;
          hasRunningJobs = runningCount > 0;
          const succeededCount = runs.filter((r) => r.status === "Succeeded").length;
          document.getElementById("kpi-jobs").textContent = String(jobs.length);
          document.getElementById("kpi-running").textContent = String(runningCount);
          document.getElementById("kpi-succeeded").textContent = String(succeededCount);
          document.getElementById("kpi-approvals").textContent = String(
            findings.filter((f) => f.status === "pending_approval").length
          );
          document.getElementById("kpi-outbox").textContent = String(
            outbox.filter((o) => o.status === "delivered").length
          );
          document.getElementById("status-msg").textContent =
            jobs.length + " schedules \u2022 " + runningCount + " running \u2022 " + succeededCount + " succeeded (100% offline UI)";

          // Dashboard: Live Execution Banner (unmistakable visual signal for Running -> Succeeded)
          const liveBanner = document.getElementById("live-run-banner");
          clearNode(liveBanner);
          const activeRun = runs.find((r) => r.status === "Running" || r.status === "Pending");
          const newestRun = runs[0];
          if (activeRun) {{
            const meta = jobsById[activeRun.job_id] || {{}};
            const imgShort = meta.worker_image ? String(meta.worker_image).split("/").pop() : "";
            liveBanner.className = "live-banner-run";
            const msg = document.createElement("div");
            msg.textContent = "\u25cf LIVE JOB RUNNING: " + activeRun.job_id +
              (meta.worker_mode ? " (" + meta.worker_mode + ")" : "") +
              (imgShort ? "  \u2022  Image: " + imgShort : "") +
              "  \u2022  Run: " + activeRun.run_id +
              "  \u2022  Engine: " + (activeRun.engine_ref || activeRun.engine_mode);
            liveBanner.appendChild(msg);
            const bar = document.createElement("div");
            bar.className = "live-banner-bar";
            const fill = document.createElement("div");
            fill.className = "prog-fill-run";
            bar.appendChild(fill);
            liveBanner.appendChild(bar);
          }} else if (newestRun && newestRun.status === "Succeeded") {{
            liveBanner.className = "live-banner-ok";
            const msg = document.createElement("div");
            msg.textContent = "\u2713 LATEST JOB SUCCEEDED: " + newestRun.job_id +
              " (" + newestRun.run_id + ")  \u2022  " + summarizeRun(newestRun);
            liveBanner.appendChild(msg);
          }} else {{
            liveBanner.className = "hidden";
          }}

          // Dashboard: Live Job Execution & Recent Runs (most recent 8 runs)
          const dRunBody = document.getElementById("tbl-dash-runs");
          clearNode(dRunBody);
          if (runs.length === 0) {{
            const emptyTr = document.createElement("tr");
            const emptyTd = addCell(emptyTr, "No runs recorded yet. Click '+ Add New Job' to create and run your first job.");
            emptyTd.colSpan = 5;
            dRunBody.appendChild(emptyTr);
          }} else {{
            runs.slice(0, 8).forEach((r, idx) => {{
              const tr = document.createElement("tr");
              if (idx === 0) tr.className = "row-highlight";
              const meta = jobsById[r.job_id] || {{}};
              const jobTd = document.createElement("td");
              const strong = document.createElement("strong");
              strong.textContent = r.job_id;
              jobTd.appendChild(strong);
              if (meta.worker_mode) {{
                const sub = document.createElement("div");
                sub.className = "sub-txt";
                sub.textContent = meta.worker_mode;
                jobTd.appendChild(sub);
              }}
              tr.appendChild(jobTd);
              const refTd = document.createElement("td");
              refTd.textContent = r.run_id;
              if (r.engine_ref && r.engine_ref !== r.run_id) {{
                const sub = document.createElement("div");
                sub.className = "sub-txt";
                sub.textContent = r.engine_ref;
                refTd.appendChild(sub);
              }}
              tr.appendChild(refTd);
              tr.appendChild(buildStatusCell(r.status));
              const outTd = document.createElement("td");
              outTd.textContent = summarizeRun(r);
              if (r.artifact_uri) {{
                const uriDiv = document.createElement("div");
                uriDiv.className = "sub-txt";
                uriDiv.textContent = r.artifact_uri;
                outTd.appendChild(uriDiv);
              }}
              tr.appendChild(outTd);
              const actTd = document.createElement("td");
              const btn = document.createElement("button");
              btn.className = "btn btn-secondary";
              btn.textContent = "Inspect Output";
              btn.onclick = async () => {{
                activateTab("tab-runs");
                await inspectRun(r);
              }};
              actTd.appendChild(btn);
              tr.appendChild(actTd);
              dRunBody.appendChild(tr);
            }});
          }}

          // Dashboard: Latest Completed Job Result preview
          const latestDone = runs.find((r) => r.status === "Succeeded") || runs[0];
          const dashRes = document.getElementById("dash-latest-result");
          if (latestDone) {{
            dashRes.textContent = JSON.stringify({{
              job_id: latestDone.job_id,
              run_id: latestDone.run_id,
              status: latestDone.status,
              engine_ref: latestDone.engine_ref,
              artifact_uri: latestDone.artifact_uri || "-",
              summary: latestDone.summary_json || {{}}
            }}, null, 2);
          }}

          // Dashboard: Active Schedules quick table (newest registered first!)
          const dSchedBody = document.getElementById("tbl-dash-schedules");
          clearNode(dSchedBody);
          const recentJobs = jobs.slice().sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
          recentJobs.slice(0, 6).forEach((j, idx) => {{
            const tr = document.createElement("tr");
            if (idx === 0) tr.className = "row-highlight";
            const idTd = document.createElement("td");
            const stg = document.createElement("strong");
            stg.textContent = j.job_id;
            idTd.appendChild(stg);
            const crSub = document.createElement("div");
            crSub.className = "sub-txt";
            crSub.textContent = j.schedule_cron + " (" + j.timezone + ")";
            idTd.appendChild(crSub);
            tr.appendChild(idTd);
            addCell(tr, j.worker_mode);
            tr.appendChild(buildScheduleStateCell(j));
            const actTd = document.createElement("td");
            const b = document.createElement("button");
            b.className = "btn";
            b.textContent = "\u25b6 Run Now";
            b.style.marginRight = "6px";
            b.onclick = () => triggerJobFromUi(j.job_id);
            actTd.appendChild(b);
            const pBtn = document.createElement("button");
            pBtn.className = j.suspended ? "btn btn-green" : "btn btn-warn";
            pBtn.textContent = j.suspended ? "Resume" : "Pause";
            pBtn.onclick = () => toggleJobPause(j.job_id, !j.suspended);
            actTd.appendChild(pBtn);
            tr.appendChild(actTd);
            dSchedBody.appendChild(tr);
          }});

          // Catalogue & Schedules full table
          const sBody = document.getElementById("tbl-schedules");
          clearNode(sBody);
          jobs.forEach((j) => {{
            const tr = document.createElement("tr");
            addCell(tr, j.job_id);
            addCell(tr, j.persona);
            addCell(tr, j.job_class);
            const modeTd = document.createElement("td");
            modeTd.textContent = j.worker_mode;
            if (j.worker_image) {{
              const imgSub = document.createElement("div");
              imgSub.className = "sub-txt";
              imgSub.textContent = String(j.worker_image).split("/").pop();
              modeTd.appendChild(imgSub);
            }}
            tr.appendChild(modeTd);
            addCell(tr, j.schedule_cron + " (" + j.timezone + ")");
            addCell(tr, j.enforcement_mode);
            tr.appendChild(buildScheduleStateCell(j));
            const actTd = document.createElement("td");
            const runBtn = document.createElement("button");
            runBtn.className = "btn";
            runBtn.textContent = "Run Now";
            runBtn.style.marginRight = "6px";
            runBtn.onclick = () => triggerJobFromUi(j.job_id);
            actTd.appendChild(runBtn);
            const pauseBtn = document.createElement("button");
            pauseBtn.className = j.suspended ? "btn btn-green" : "btn btn-warn";
            pauseBtn.textContent = j.suspended ? "Resume" : "Pause";
            pauseBtn.style.marginRight = "6px";
            pauseBtn.onclick = () => toggleJobPause(j.job_id, !j.suspended);
            actTd.appendChild(pauseBtn);
            const delBtn = document.createElement("button");
            delBtn.className = "btn btn-danger";
            delBtn.textContent = "Delete";
            delBtn.onclick = () => deleteJobFromUi(j.job_id);
            actTd.appendChild(delBtn);
            tr.appendChild(actTd);
            sBody.appendChild(tr);
          }});

          // Run Explorer full table
          const rBody = document.getElementById("tbl-runs");
          clearNode(rBody);
          runs.forEach((r) => {{
            const tr = document.createElement("tr");
            addCell(tr, r.run_id);
            addCell(tr, r.job_id);
            addCell(tr, r.trigger_type);
            addCell(tr, r.window_start + " -> " + r.window_end);
            tr.appendChild(buildStatusCell(r.status));
            addCell(tr, summarizeRun(r));
            const actTd = document.createElement("td");
            const viewBtn = document.createElement("button");
            viewBtn.className = "btn btn-secondary";
            viewBtn.textContent = "View Results & Logs";
            viewBtn.onclick = () => inspectRun(r);
            actTd.appendChild(viewBtn);
            tr.appendChild(actTd);
            rBody.appendChild(tr);
          }});

          async function decideFinding(f, decision) {{
            const fb = document.getElementById("approval-feedback");
            clearNode(fb);
            const resp = await fetch("/api/v1/approvals/" + encodeURIComponent(f.finding_id) + "/decide", {{
              method: "POST",
              headers: apiHeaders(),
              body: JSON.stringify({{
                decision: decision,
                reason: decision === "approved" ? "Peer-approved in Portal UI" : "Rejected in Portal UI",
                planned_patch_sha256: f.planned_patch_sha256
              }})
            }});
            const data = await resp.json().catch(() => ({{}}));
            const banner = document.createElement("div");
            banner.className = resp.ok ? "ok-banner" : "err-banner";
            banner.textContent = resp.ok
              ? "HTTP " + resp.status + " OK: Finding '" + f.finding_id + "' -> " + ((data.finding && data.finding.status) || decision) + (data.snapshot_uri ? " (pre-action snapshot archived: " + data.snapshot_uri + ")" : "")
              : "HTTP " + resp.status + ": " + (data.error || "Approval action rejected");
            fb.appendChild(banner);
            await refreshAll();
          }}
          async function rollbackFinding(f) {{
            const fb = document.getElementById("approval-feedback");
            clearNode(fb);
            const resp = await fetch("/api/v1/approvals/" + encodeURIComponent(f.finding_id) + "/rollback", {{
              method: "POST",
              headers: apiHeaders(),
              body: JSON.stringify({{reason: "1-Click snapshot rollback from Portal UI"}})
            }});
            const data = await resp.json().catch(() => ({{}}));
            const banner = document.createElement("div");
            banner.className = resp.ok ? "ok-banner" : "err-banner";
            banner.textContent = resp.ok
              ? "HTTP " + resp.status + " OK: Rolled back '" + f.finding_id + "' from pre-action snapshot."
              : "HTTP " + resp.status + ": " + (data.error || "Rollback failed");
            fb.appendChild(banner);
            await refreshAll();
          }}

          const fBody = document.getElementById("tbl-findings");
          clearNode(fBody);
          if (findings.length === 0) {{
            const emptyTr = document.createElement("tr");
            const emptyTd = addCell(emptyTr, "{empty_findings_msg}");
            emptyTd.colSpan = 7;
            fBody.appendChild(emptyTr);
          }} else {{
            findings.forEach((f) => {{
              const tr = document.createElement("tr");
              addCell(tr, f.finding_id);
              addCell(tr, f.target_kind + "/" + f.target_namespace + "/" + f.target_name);
              addCell(tr, f.rule_id);
              addCell(tr, String(f.planned_patch_sha256 || "").slice(0, 16) + "...");
              addCell(tr, f.status);
              addCell(tr, f.requested_by);
              const actTd = document.createElement("td");
              if (f.status === "pending_approval") {{
                const appBtn = document.createElement("button");
                appBtn.className = "btn btn-green";
                appBtn.textContent = "Approve";
                appBtn.style.marginRight = "6px";
                appBtn.onclick = () => decideFinding(f, "approved");
                actTd.appendChild(appBtn);
                const rejBtn = document.createElement("button");
                rejBtn.className = "btn btn-danger";
                rejBtn.textContent = "Reject";
                rejBtn.onclick = () => decideFinding(f, "rejected");
                actTd.appendChild(rejBtn);
              }} else if (f.status === "remediated") {{
                const rbBtn = document.createElement("button");
                rbBtn.className = "btn btn-warn";
                rbBtn.textContent = "1-Click Rollback";
                rbBtn.onclick = () => rollbackFinding(f);
                actTd.appendChild(rbBtn);
              }} else {{
                actTd.textContent = "-";
              }}
              tr.appendChild(actTd);
              fBody.appendChild(tr);
            }});
          }}

          const oBody = document.getElementById("tbl-outbox");
          clearNode(oBody);
          outbox.forEach((o) => {{
            const tr = document.createElement("tr");
            addCell(tr, o.outbox_id);
            addCell(tr, o.sink_name);
            addCell(tr, o.event_type);
            addCell(tr, o.severity);
            addCell(tr, o.status);
            addCell(tr, o.attempts);
            oBody.appendChild(tr);
          }});
        }} catch (err) {{
          document.getElementById("status-msg").textContent = "Awaiting authenticated OIDC session.";
        }}
      }}
      document.getElementById("btn-preview-cron").addEventListener("click", async () => {{
        const box = document.getElementById("cron-preview-box");
        clearNode(box);
        const resp = await fetch("/api/v1/schedules/preview", {{
          method: "POST",
          headers: apiHeaders(),
          body: JSON.stringify({{
            schedule_cron: document.getElementById("f-cron").value,
            timezone: document.getElementById("f-tz").value,
            persona: document.getElementById("f-persona").value
          }})
        }});
        const data = await resp.json();
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(data, null, 2);
        box.appendChild(pre);
        (data.dst_warnings || []).forEach((w) => {{
          const div = document.createElement("div");
          div.className = "warn-banner";
          div.textContent = w;
          box.appendChild(div);
        }});
      }});
      const MODE_SOURCE_HINTS = {{
        "batch-watermarked-rollup": "Job contents: example-app/jobs/p15_jobs/batch_rollup.py (baked into p15-reference-worker) — processes watermarked batch windows, writes WAL + result.json to Object Storage.",
        "monitor-platform-hygiene": "Job contents: example-app/jobs/p15_jobs/monitor_hygiene.py (baked into p15-reference-worker) — checks namespace hygiene and advances monotonic watermarks.",
        "enforce-resource-policy": "Job contents: example-app/jobs/p15_jobs/enforce_policy.py (baked into p15-reference-worker) — scans resources for missing labels and emits SHA-256 HITL/remediation patches.",
        "inventory-audit-report": "Job contents: examples/custom-job-inventory/p15_jobs/runner.py (custom image p15-example-inventory-job:v1.0.0) — queries live K8s Services via attached ServiceAccount.",
        "__custom__": "Custom container image implementing `python3 -m p15_jobs.runner --mode <your-mode>`."
      }};
      function getSelectedWorkerMode() {{
        const sel = document.getElementById("f-mode");
        if (sel.value === "__custom__") {{
          return document.getElementById("f-mode-custom").value.trim();
        }}
        return sel.value;
      }}
      function syncModeHint() {{
        const sel = document.getElementById("f-mode");
        const customEl = document.getElementById("f-mode-custom");
        customEl.classList.toggle("hidden", sel.value !== "__custom__");
        const hintEl = document.getElementById("mode-source-hint");
        if (hintEl) hintEl.textContent = MODE_SOURCE_HINTS[sel.value] || MODE_SOURCE_HINTS["__custom__"];
      }}
      document.getElementById("f-mode").addEventListener("change", syncModeHint);
      syncModeHint();
      document.getElementById("btn-create-job").addEventListener("click", async () => {{
        const fb = document.getElementById("schedule-action-feedback");
        clearNode(fb);
        const resp = await fetch("/api/v1/schedules", {{
          method: "POST",
          headers: apiHeaders(),
          body: JSON.stringify({{
            job_id: document.getElementById("f-job-id").value,
            persona: document.getElementById("f-persona").value,
            job_class: document.getElementById("f-class").value,
            worker_mode: getSelectedWorkerMode(),
            schedule_cron: document.getElementById("f-cron").value,
            timezone: document.getElementById("f-tz").value,
            worker_image: document.getElementById("f-image").value,
            enforcement_mode: document.getElementById("f-enf").value
          }})
        }});
        const data = await resp.json().catch(() => ({{}}));
        const banner = document.createElement("div");
        if (resp.ok) {{
          const clusterErr = data.reconcile && data.reconcile.cluster_error;
          banner.className = clusterErr ? "warn-banner" : "ok-banner";
          const kind = (data.reconcile && data.reconcile.manifest_kind) || "Schedule";
          const sched = data.schedule || {{}};
          banner.textContent = clusterErr
            ? "Saved " + (sched.job_id || "schedule") + " in ledger, but Kubernetes " + kind + " apply failed: " + clusterErr
            : "Registered " + (sched.job_id || "schedule") + " (HTTP " + resp.status + ", applied live Kubernetes " + kind + "). Click Run Now below to watch it execute on the Dashboard.";
          fb.appendChild(banner);
          const bind = document.createElement("div");
          bind.id = "compiled-runtime-binding";
          bind.className = "binding-strip";
          bind.textContent = "Compiled Runtime Binding:  Image [" + (sched.worker_image || "") + "]  \u2192  python3 -m p15_jobs.runner --mode=" + (sched.worker_mode || "") + "  \u2022  Template: " + (sched.template_name || "gdc-standard-job-runner-v1");
          fb.appendChild(bind);
          if (data.reconcile && data.reconcile.manifest_yaml) {{
            const pre = document.createElement("pre");
            pre.id = "compiled-manifest-preview";
            pre.textContent = data.reconcile.manifest_yaml;
            fb.appendChild(pre);
          }}
        }} else {{
          banner.className = "err-banner";
          banner.textContent = "Error HTTP " + resp.status + ": " + (data.error || "Unable to save schedule");
          fb.appendChild(banner);
        }}
        await refreshAll();
      }});
      document.getElementById("btn-add-sink").addEventListener("click", async () => {{
        const fb = document.getElementById("sink-feedback");
        clearNode(fb);
        const resp = await fetch("/api/v1/notifications/sinks", {{
          method: "POST",
          headers: apiHeaders(),
          body: JSON.stringify({{
            name: document.getElementById("s-name").value.trim(),
            type: document.getElementById("s-type").value,
            url: document.getElementById("s-url").value.trim()
          }})
        }});
        const data = await resp.json().catch(() => ({{}}));
        const b = document.createElement("div");
        b.className = resp.ok ? "ok-banner" : "err-banner";
        b.textContent = resp.ok
          ? "Registered sink '" + ((data.sink && data.sink.name) || document.getElementById("s-name").value) + "' (HTTP " + resp.status + "). Now click '2. Send Test Notification'."
          : "HTTP " + resp.status + ": " + (data.error || "Sink registration failed");
        fb.appendChild(b);
        await refreshAll();
      }});
      document.getElementById("btn-test-sink").addEventListener("click", async () => {{
        const fb = document.getElementById("sink-feedback");
        clearNode(fb);
        const name = document.getElementById("s-name").value.trim();
        const resp = await fetch("/api/v1/notifications/sinks/" + encodeURIComponent(name) + "/test", {{
          method: "POST",
          headers: apiHeaders(),
          body: JSON.stringify({{}})
        }});
        const data = await resp.json().catch(() => ({{}}));
        const b = document.createElement("div");
        b.className = resp.ok ? "ok-banner" : "err-banner";
        b.textContent = resp.ok
          ? "Delivered " + (data.hmac_signed ? "HMAC-SHA256 signed " : "") + "test notification to '" + name + "' (HTTP " + (data.status_code || resp.status) + ", " + (data.latency_ms != null ? data.latency_ms : 0) + "ms) — recorded as 'delivered' in outbox."
          : "HTTP " + resp.status + ": " + (data.error || "Test notification failed");
        fb.appendChild(b);
        await refreshAll();
      }});{sim_hitl_js}
      document.getElementById("btn-toggle-auth").addEventListener("click", () => {{
        document.getElementById("auth-panel").classList.toggle("hidden");
      }});
      function clearFeedbackBanners() {{
        ["approval-feedback", "schedule-action-feedback", "dash-schedule-feedback", "sink-feedback"].forEach((id) => {{
          const el = document.getElementById(id);
          if (el) clearNode(el);
        }});
      }}
      document.getElementById("btn-logout").addEventListener("click", async () => {{
        await fetch("/auth/logout", {{method: "POST"}});
        csrfToken = "";
        localStorage.removeItem("p15_csrf");
        clearFeedbackBanners();
        await refreshAll();
      }});
      document.getElementById("btn-oidc-pkce").addEventListener("click", async () => {{
        const r = await fetch("/auth/oidc/login");
        const d = await r.json().catch(() => ({{}}));
        document.getElementById("oidc-pkce-out").textContent = d.authorize_url
          ? "Keycloak PKCE (" + (d.pkce_method || "S256") + ") Authorize URL: " + d.authorize_url
          : "Unable to build OIDC login URL.";
      }});
      document.getElementById("btn-oidc-jwt-login").addEventListener("click", async () => {{
        const errEl = document.getElementById("auth-error");
        errEl.className = "hidden";
        const tok = document.getElementById("oidc-jwt-input").value.replace(/^Bearer\\s+/i, "").replace(/\\s+/g, "");
        if (!tok) {{
          errEl.className = "err-banner";
          errEl.textContent = "Paste a Keycloak RS256 JWT first (from Step 5.2 / 5.3 echo $AO_JWT or $PA_JWT).";
          return;
        }}
        try {{
          const r = await fetch("/auth/oidc/session", {{
            method: "POST",
            credentials: "same-origin",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{token: tok}})
          }});
          const d = await r.json().catch(() => ({{}}));
          if (!r.ok) {{
            errEl.className = "err-banner";
            errEl.textContent = "HTTP " + r.status + ": " + (d.error || "Keycloak JWT verification failed");
            return;
          }}
          if (d.csrf_token) {{ csrfToken = d.csrf_token; localStorage.setItem("p15_csrf", d.csrf_token); }}
          document.getElementById("oidc-jwt-input").value = "";
          clearFeedbackBanners();
          await refreshAll();
        }} catch (err) {{
          errEl.className = "err-banner";
          errEl.textContent = "Sign-in request failed: " + String(err);
        }}
      }});{sim_portal_js}
      window.__p15RefreshAll = refreshAll;
      window.__p15ActivateTab = activateTab;
      setInterval(() => {{
        if (currentUser && hasRunningJobs) refreshAll();
      }}, 5000);
      refreshAll();
    }})();
  </script>
</body>
</html>
"""


def render_admin_html(engine_mode: str, allow_simulated_oidc: bool = False) -> str:
    """Render 100% offline, CDN-free `:8081` PA Platform Admin Console."""
    eng = _esc(engine_mode)
    sim_admin_block = (
        """
      <div class="subbox simbox">
        <div class="subhdr">Stepping-Stone Persona Test <span class="amber-pill">Disabled in GDC-ag Production</span></div>
        <div class="row">
          <input id="admin-sim-user" value="ao-operator@gdc.local" placeholder="Username or email">
          <select id="admin-sim-role">
            <option value="ao-job-operator">ao-job-operator (Test 403 Rejection on :8081)</option>
            <option value="pa-job-admin">pa-job-admin (PA Platform Admin)</option>
          </select>
          <button class="btn-primary" id="btn-admin-sim-login">Sign In to :8081</button>
        </div>
      </div>"""
        if allow_simulated_oidc
        else ""
    )
    sim_admin_js = (
        """
      const simBtn = document.getElementById("btn-admin-sim-login");
      if (simBtn) {
        simBtn.addEventListener("click", async () => {
          const errEl = document.getElementById("admin-auth-error");
          errEl.className = "hidden";
          const r = await fetch("/auth/simulated", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              username: document.getElementById("admin-sim-user").value.trim() || "pa-admin@gdc.local",
              role: document.getElementById("admin-sim-role").value
            })
          });
          const d = await r.json().catch(() => ({}));
          if (!r.ok) {
            errEl.className = "errbox";
            errEl.textContent = "HTTP " + r.status + (r.status === 403 ? " Forbidden" : "") + ": " + (d.error || "PA role required on Port 8081");
            return;
          }
          if (d.csrf_token) localStorage.setItem("p15_admin_csrf", d.csrf_token);
          await loadAdmin();
        });
      }"""
        if allow_simulated_oidc
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GDC PA Job Platform Admin Console (:8081)</title>
  <style>
    * {{ box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }}
    body {{ margin: 0; background: #0f172a; color: #f8fafc; }}
    header {{ padding: 16px 24px; background: #1e293b; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }}
    .hdr-right {{ display: flex; align-items: center; gap: 10px; font-size: 13.5px; }}
    .pill {{ background: #dc2626; color: #fff; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; }}
    .amber-pill {{ background: #92400e; color: #fef3c7; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 700; }}
    main {{ max-width: 1180px; margin: 24px auto; padding: 0 24px; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px; margin-bottom: 16px; }}
    .subbox {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px 14px; margin-top: 10px; }}
    .simbox {{ border-color: #b45309; }}
    .subhdr {{ font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; align-items: center; }}
    .row-jwt {{ display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; }}
    input, select {{ padding: 8px 10px; border: 1px solid #475569; border-radius: 6px; background: #020617; color: #f8fafc; font-size: 13.5px; width: 100%; }}
    button {{ padding: 8px 14px; border-radius: 6px; border: none; font-weight: 700; cursor: pointer; background: #dc2626; color: #fff; white-space: nowrap; }}
    .btn-primary {{ background: #2563eb; color: #fff; }}
    .btn-sec {{ background: #334155; color: #f8fafc; }}
    .errbox {{ background: #450a0a; border: 1px solid #ef4444; color: #fecaca; border-radius: 6px; padding: 10px 12px; margin-top: 10px; font-weight: 700; }}
    .hidden {{ display: none; }}
    pre {{ background: #020617; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 12.5px; }}
  </style>
</head>
<body>
  <header>
    <div><strong>Pattern 15: PA Platform Admin Console (:8081)</strong> — Engine: {eng}</div>
    <div class="hdr-right">
      <span id="admin-auth-status">Not signed in</span>
      <button class="btn-sec hidden" id="btn-admin-logout">Sign Out</button>
      <span class="pill">PA-ONLY ISOLATED SURFACE</span>
    </div>
  </header>
  <main>
    <div class="card" id="admin-auth-panel">
      <h3>PA Admin Authentication (:8081 &mdash; Role <code>pa-job-admin</code> Required)</h3>
      <div class="subbox">
        <div class="subhdr">Keycloak OIDC Sign-In (Production RS256 JWKS &mdash; Client <code>p15-job-admin</code>)</div>
        <div class="row-jwt">
          <input id="admin-jwt-input" type="password" placeholder="Paste Keycloak RS256 Bearer JWT (AO tokens receive HTTP 403; pa-job-admin receives HTTP 200)">
          <button class="btn-primary" id="btn-admin-jwt-login">Sign In with Keycloak JWT</button>
        </div>
      </div>{sim_admin_block}
      <div id="admin-auth-error" class="hidden"></div>
    </div>

    <div class="card">
      <h3>Global Emergency Pause-All Kill-Switch &amp; SSRF Allowlist Governance</h3>
      <button id="btn-kill-switch">Toggle Emergency Pause-All</button>
      <pre id="admin-overview">Loading PA platform governance state...</pre>
    </div>
  </main>
  <script>
    (function() {{
      "use strict";
      let currentPaused = false;
      async function loadAdmin() {{
        const meR = await fetch("/auth/me");
        const panel = document.getElementById("admin-auth-panel");
        const logoutBtn = document.getElementById("btn-admin-logout");
        const statusEl = document.getElementById("admin-auth-status");
        const el = document.getElementById("admin-overview");
        if (!meR.ok) {{
          statusEl.textContent = "Not signed in";
          panel.classList.remove("hidden");
          logoutBtn.classList.add("hidden");
          el.textContent = "HTTP " + meR.status + ": PA role 'pa-job-admin' required on Port 8081. Sign in above.";
          return;
        }}
        const me = await meR.json();
        statusEl.textContent = "Signed in: " + me.principal + " (" + me.persona + ")";
        panel.classList.add("hidden");
        logoutBtn.classList.remove("hidden");
        const r = await fetch("/admin/v1/overview");
        if (!r.ok) {{
          el.textContent = "HTTP " + r.status + ": PA role 'pa-job-admin' required on Port 8081.";
          return;
        }}
        const ov = await r.json();
        currentPaused = Boolean(ov.emergency_pause_all);
        document.getElementById("btn-kill-switch").textContent = currentPaused
          ? "Resume All Jobs (Clear Kill-Switch)"
          : "Activate Emergency Pause-All";
        el.textContent = JSON.stringify(ov, null, 2);
      }}
      document.getElementById("btn-admin-logout").addEventListener("click", async () => {{
        await fetch("/auth/logout", {{method: "POST"}});
        localStorage.removeItem("p15_admin_csrf");
        localStorage.removeItem("p15_csrf");
        await loadAdmin();
      }});
      document.getElementById("btn-admin-jwt-login").addEventListener("click", async () => {{
        const errEl = document.getElementById("admin-auth-error");
        errEl.className = "hidden";
        const tok = document.getElementById("admin-jwt-input").value.replace(/^Bearer\\s+/i, "").replace(/\\s+/g, "");
        if (!tok) {{
          errEl.className = "errbox";
          errEl.textContent = "Paste a Keycloak RS256 JWT first (from Step 5.2 / 5.3 echo $AO_JWT or $PA_JWT).";
          return;
        }}
        try {{
          const r = await fetch("/auth/oidc/session", {{
            method: "POST",
            credentials: "same-origin",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{token: tok}})
          }});
          const d = await r.json().catch(() => ({{}}));
          if (!r.ok) {{
            errEl.className = "errbox";
            errEl.textContent = "HTTP " + r.status + (r.status === 403 ? " Forbidden" : "") + ": " + (d.error || "PA role required on Port 8081");
            return;
          }}
          if (d.csrf_token) localStorage.setItem("p15_admin_csrf", d.csrf_token);
          document.getElementById("admin-jwt-input").value = "";
          await loadAdmin();
        }} catch (err) {{
          errEl.className = "errbox";
          errEl.textContent = "Sign-in request failed: " + String(err);
        }}
      }});{sim_admin_js}
      document.getElementById("btn-kill-switch").addEventListener("click", async () => {{
        const csrf = localStorage.getItem("p15_admin_csrf") || localStorage.getItem("p15_csrf") || "";
        const hdrs = {{"Content-Type": "application/json"}};
        if (csrf) hdrs["X-CSRF-Token"] = csrf;
        await fetch("/admin/v1/kill-switch", {{
          method: "POST",
          headers: hdrs,
          body: JSON.stringify({{paused: !currentPaused}})
        }});
        loadAdmin();
      }});
      loadAdmin();
    }})();
  </script>
</body>
</html>
"""
