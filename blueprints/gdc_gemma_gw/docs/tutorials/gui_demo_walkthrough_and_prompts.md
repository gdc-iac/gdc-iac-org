Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GUI Functional Walkthrough & Live Demo Playbook (Ports `8080`–`8084` & GDC-ag FQDNs)

> **Document ID:** `PLAYBOOK-GUI-DEMO-AND-WALKTHROUGH`  
> **Companion Guides:**  
> - [Zero-Tweak E2E Validation Runbook & Upgrade Suite](./e2e_zero_tweak_validation_runbook.md)  
> - [AI-Enabled Blueprint E2E Test Guide (GCP Staging & Development)](./ai_enabled_e2e_gcp_staging_guide.md)  
> - [AI-Enabled Blueprint E2E Deployment & Verification Guide (GDC-ag Production IaC)](./ai_enabled_e2e_gdc_production_iac_guide.md)

---

## 1. Demo & Test Overview: The 5-Endpoint Architecture

This playbook serves both as a **step-by-step manual QA checklist** for validating every GUI control across the AI-enabled blueprint stack and as a **scripted 15–20 minute live customer/executive demonstration**.

### 1.1. Quick-Reference Endpoint & Persona Matrix

| Workstation Port | GDC-ag Production FQDN | Interface Name | Login Persona & Credentials | Key Capabilities Demonstrated |
| :--- | :--- | :--- | :--- | :--- |
| **Port `8080`** | `https://ai-gateway.gdc.local` | **🧠 Gemma 4 Gateway Control Plane** | **Admin:** `charlie` / `password` | Keycloak OIDC SSO, live GPU/VRAM telemetry gauges, parameter override (`Temperature`, `Top-P`, model hot-swap), active session kill-switch, and real-time user blocklist. |
| **Port `8081`** | `https://intel.gdc.local` | **🛡️ Joint Intel Console + 💬 Gemma Client (via Gateway API)** | **Analyst:** `alice` / `password` | Exposed via **Kubernetes Gateway API (`HTTPRoute`)**. Hosts both the 4-tab **Joint Intelligence Console** (`Kafka`, `SITREP RAG`, `Agentic SQL`, `Tactical Chat`) and the **Standard Gemma Chat & GCS/S3 RAG Client**. |
| **Port `8082`** | `https://intel-ingress.gdc.local` | **🛡️ Joint Intel Console + 💬 Gemma Client (via Ingress)** | **Commander:** `charlie` / `password` | Exposed via **Kubernetes Ingress (`NGINX`)**. Identical application to Port `8081`, proving side-by-side Gateway API and Ingress parity and multi-user session tracking. |
| **Port `8083`** | `https://admin.dev.gdc.local` | **📊 `gdc-dev` Sovereign Admin & Telemetry Console** | **Platform Admin:** `cluster-admin@gdc.local` (1-click button) | Live PVC block storage consumption, real-time AI Swarm invocation telemetry (`3s` auto-refresh), session hibernate/terminate controls, and live **Cluster Broadcast Banner**. |
| **Port `8084`** | `https://dev.gdc.local` | **💻 `gdc-dev` Developer IDE & Multi-Agent Swarm** | **Developer:** `oidc-developer@gdc.local` (1-click button) | Browser-based Cloud IDE (`/instances/default-workspace`), **`▶ Run Code`** + **`Terminal - bash (project: default-workspace)`**, and **Multi-Agent AI Swarm** (`🐝 Swarm`, `📐 Architect`, `💻 Coder`, `🔍 Reviewer`) with **`💾 Save as File`**, **`📥 Insert into Editor`**, **`↩ Rollback Changes`**, and **`⚡ Fix with Gemma Agent`**. |

---

## 2. Pre-Demo Preparation: Generate a Sample Tactical Document for Upload (`10 Seconds`)

Before starting Scene 3 (the Document Upload & RAG demo on Port `8081`/`8082`), create a local text file named `Operation_Vanguard_Shield_Directive.txt` on your laptop (or download it from your workstation) containing specific facts that are **not** in the model's pre-training data:

```bash
cat << 'EOF' > ~/Operation_Vanguard_Shield_Directive.txt
CLASSIFICATION: UNCLASSIFIED // EXERCISE VANGUARD SHIELD
DOCUMENT ID: DIR-2026-SEC9-042
DATE: 15 OCTOBER 2026
SUBJECT: Sector 9 Autonomous Resupply & Communications Protocol

1. AUTHORIZATION CODEWORD:
   All autonomous logistics convoys transiting Route Alpha must authenticate
   at Checkpoint Sierra using codeword: VANGUARD-OMEGA-749.

2. BACKUP COMMUNICATIONS FREQUENCY:
   If primary satellite uplink (SATCOM-16) experiences atmospheric or EW
   interference, units must switch immediately to tactical UHF frequency
   314.85 MHz (Channel 19-Bravo).

3. FUEL RESERVE THRESHOLD:
   Forward Operating Base (FOB) Echo must maintain a minimum JP-8 fuel reserve
   of 42,500 gallons (7 days of supply) before authorizing heavy armor dispatch.
EOF
```

---

## 3. Scene 1: Port `8080` (`https://ai-gateway.gdc.local`) — `🧠 Gemma 4 Gateway Control Plane`

### Step 1.1: Verify Zero-Trust OIDC Login on the Gateway Control Plane
1. Open **Port `8080`** (`https://ai-gateway.gdc.local`).
2. **What to Observe Before Login:**
   - Top authentication banner displays **`🔒 Unauthenticated (Read-Only Telemetry)`**.
   - If you try to click **`Save Gateway Configuration`** or **`Block User`** while unauthenticated, the Gateway rejects the action (`401 Unauthorized`).
3. **Action:** Click **`🛡️ One-Click Admin (charlie)`** (or click **`🔑 Keycloak SSO Login (/auth)`** and sign in with username `charlie` and password `password`).
4. **Expected Result:**
   - The top bar updates to **`🟢 Authenticated via Keycloak OIDC: charlie (Role: ADMIN)`** with a **`Logout`** button.

### Step 1.2: Inspect Card 1 — `⚡ Live System Performance & Telemetry`
- **What to Observe:**
  - **Active Framework Badge:** Shows **`OLLAMA`** (or **`VLLM`** after the Step 6 engine flip) and **`Status: ONLINE`**.
  - **Live Gauges:** `CPU Load (%)`, `GPU Core Load (%)`, `Tokens Out/Sec`, `Active DB Pools`, and the **`VRAM Consumption`** progress bar updating every 2 seconds directly from the live inference pods.

### Step 1.3: Test Card 2 — `🎛️ Gateway Parameters Override` (True Gateway-Enforced Overrides)
1. **How It Works:** Any parameter saved in Card 2 (`Sampling Temperature`, `Top-P`, `Max Vision Tokens`, and `Model Variant Hot-Swap`) is persisted to `/tmp/gemma_gateway_state.json` across all Gateway workers and **unconditionally overrides** downstream client parameters on `/v1/chat/completions` (echoing the enforced values in `X-Gemma-Temperature`, `X-Gemma-Top-P`, and `X-Gemma-Vision-Budget` response headers).
2. **Action:**
   - Change **`Sampling Temperature`** from `0.7` to `0.2` and switch **`Model Variant Hot-Swap`** to **`Gemma 4 31B (Dense) — Deep Reasoning Tier 2`**, then click **`Save Gateway Configuration`**.
   - Open **Port `8081` (`Tactical Chat`)** with the model dropdown set to **`Gemma 4 Gateway (Auto)`** and send a simple conversational query: `Hello, confirm system status.`
3. **Expected Result:**
   - On Port `8080`, a green confirmation toast appears (`Gateway configuration updated successfully`).
   - On Port `8081`, even though the prompt is simple conversational text, the navbar routing badge displays **`→ gemma4:31b`** and generation uses `temperature=0.2`.
   - Return to **Port `8080`** and click **`↺ Reset to Auto`** to restore **`Gemma 4 Gateway (Auto: 26B MoE → 31B Dense)`**, **`Sampling Temperature`** `0.7`, **`Top-P`** `0.9`, and **`Max Vision Tokens`** `280`.

---

## 4. Scene 2: Ports `8081` & `8082` — Mode 1: `🛡️ Joint Intelligence & Readiness Console`

### Step 2.1: Dual-Ingress OIDC Login (`Gateway API` on `8081` vs. `NGINX Ingress` on `8082`)
1. Open **Port `8081`** (`https://intel.gdc.local` — routed via **Kubernetes Gateway API `HTTPRoute`**).
   - Click **`Sign In with Keycloak SSO`** and log in as **`alice` / `password`** (Analyst role).
2. Open **Port `8082`** (`https://intel-ingress.gdc.local` — routed via **NGINX Ingress**) in a second tab or incognito window.
   - Click **`Sign In with Keycloak SSO`** and log in as **`charlie` / `password`** (Commander/Admin role).
3. **Expected Result:**
   - Both interfaces load the **Joint Intelligence & Readiness Console** (`🛡️ Intel Console` button highlighted in the top navigation bar).
   - Top navigation bar shows the **`Gemma 4 Gateway (Auto)`** model selector dropdown and the **`🧠 CoT`** (Chain-of-Thought) checkbox.

---

### Step 2.2: Tab 1 — `Tactical Feeds (Kafka)` (`Live Stream`)
1. Click **Tab 1: `Tactical Feeds (Kafka)`**.
2. **Action:**
   - Click through the domain filter pills (`ALL`, `LAND`, `AIR`, `SEA`, `SPACE`, `CYBER`) to filter live sensor telemetry.
   - Click **`⚡ Ingest Sensor Pings`** in the top-right corner of the feed panel.
3. **Expected Result:**
   - 5 new multi-domain sensor frames (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) appear at the top of the stream with timestamps, coordinates, sensor IDs (e.g., `AIR-SNS-402`, `CYBER-SNS-819`), and threat badges.

---

### Step 2.3: Tab 2 — `All-Source Intel (RAG)` (`SITREPs`)
1. Click **Tab 2: `All-Source Intel (RAG)`**.
2. **Action:** Click one of the **`Suggested Inquiries`** pills or copy-paste any of the following demo prompts and click **`Synthesize`**:

| Demo Prompt (Copy-Paste) | What to Expect in the UI |
| :--- | :--- |
| **`Summarize the primary threats to Convoy Route Alpha in Sector 9 and recommend immediate mitigation actions.`** | • **Tactical Intelligence Synthesis** panel streams a structured briefing citing **`[SITREP-2026-08-SEC9-CONVOY]`** and **`[HUMINT-2026-08-SEC9-BRIDGE]`** inline.<br>• **Retrieved Intelligence Sources** column on the right displays the matching classified cable cards with agency badges.<br>• Model badge displays **`Model: gemma4:26b`**. |
| **`Correlate recent cyber SCADA alerts with fuel stock status at FOB Alpha.`** | • Synthesizes findings across **`[CYBER-2026-08-SEC9-SCADA]`** and logistics reports, highlighting the Modbus probe at FOB Alpha's fuel depot and recommended isolation steps. |
| **`What electronic warfare or GPS jamming activity has been reported near Sector 9 air corridors?`** | • Cites **`[SIGINT-2026-08-SEC9-EW]`**, detailing UHF/GPS interference bearings and recommending backup inertial/UHF comms. |

---

### Step 2.4: Tab 3 — `Operational Readiness (SQL)` (`Agentic Text-to-SQL + Security Gate`)
1. Click **Tab 3: `Operational Readiness (SQL)`**.
2. **Part A — Valid Commander Readiness Audits:** Copy-paste these natural-language questions and click **`Audit`**:

| Demo Prompt (Copy-Paste) | Expected Generated SQL & UI Output |
| :--- | :--- |
| **`Which military units in Sector 9 currently have a readiness rating below C1, and who are their commanders?`** | • **Generated SQL Box:** `SELECT unit_id, unit_name, branch, readiness_rating, commander, operational_status FROM military_units WHERE sector = 'Sector 9' AND readiness_rating != 'C1'...`<br>• **Data Table:** Displays matching units (`C2`, `C3`) with personnel counts and status.<br>• **Executive Summary:** 2–3 sentence commander briefing summarizing degraded units. |
| **`Show all equipment inventory items where operational readiness percentage is below 85%.`** | • **Generated SQL Box:** Queries `equipment_inventory` filtering on `readiness_percentage < 85`.<br>• **Data Table:** Lists specific vehicles/radar systems in repair.<br>• **Latency Badge:** Shows DB execution time in milliseconds (`~2–5 ms`). |
| **`List fuel and ammunition supply levels across all bases ordered by days of supply ascending.`** | • **Generated SQL Box:** Queries `fuel_and_supplies ORDER BY days_of_supply ASC`.<br>• **Executive Summary:** Identifies which Forward Operating Base requires priority JP-8 resupply. |

3. **Part B — Live Security Gate Demo (Destructive SQL Injection Rejection):**
   - Copy-paste either of these adversarial commands into the query box and click **`Audit`**:
     ```sql
     DROP TABLE military_units;
     ```
     or:
     ```sql
     DELETE FROM fuel_and_supplies WHERE sector = 'Sector 9';
     ```
   - **Expected Result:**
     - **Generated SQL Box:** Displays **`-- Rejected by Security Gate`**.
     - **Executive Summary Banner:** Displays **`Security Alert: Destructive DDL/DML command rejected by read-only Security Gate.`**
     - **Zero database rows are modified or deleted** (`0 rows returned`, `0.0 ms`).

---

### Step 2.5: Tab 4 — `Tactical Chat` (`Gemma 4`) — Complexity Auto-Routing (`26B` vs. `31B`) & `🧠 CoT`
1. Click **Tab 4: `Tactical Chat`**.
2. Ensure the top navigation bar dropdown is set to **`Gemma 4 Gateway (Auto)`**.
3. **Test 1 — Fast Tier 1 (`26B MoE`) Routing:**
   - **Prompt:**
     ```text
     Give a concise 3-bullet operational overview of why air-gapped local LLM inference is critical for tactical edge command posts.
     ```
   - **Expected Result:**
     - If **`🧠 CoT`** is checked, a collapsible **`Thought Process`** accordion appears above the final answer.
     - Next to the **`Gemma 4 Gateway (Auto)`** dropdown in the top navbar, the green routing badge updates to **`→ gemma4:26b`** (confirming the Gateway classified the prompt as Tier 1 conversational).
4. **Test 2 — Complex Tier 2 (`31B Dense`) Routing:**
   - **Prompt:**
     ```text
     Write a complete Python script that models convoy fuel consumption across multiple waypoints with elevation gain and outputs a JSON resupply schedule.
     ```
   - **Expected Result:**
     - Because the prompt contains code-generation complexity markers (`python`, `script`), `gemma-gateway` automatically routes it to the **31B Dense** specialist pool.
     - Next to **`Gemma 4 Gateway (Auto)`** in the top navbar, the routing badge updates to **`→ gemma4:31b`**.
5. **Test 3 — Toggle `🧠 CoT` Off:**
   - Uncheck **`🧠 CoT`** in the top navbar and send:
     ```text
     In one sentence, define NATO Readiness Rating C1.
     ```
   - **Expected Result:** The response renders immediately **without** any `<thought>` reasoning block.

---

## 5. Scene 3: Ports `8081` & `8082` — Mode 2: `💬 Gemma Client` (Document Upload, Strict RAG & General Chat Toggle)

1. In the top navigation bar on **Port `8081`** (or `8082`), click **`💬 Gemma Client`** (next to `🛡️ Intel Console`).
2. **What to Observe:** The UI switches immediately to the **Standard Gemma Workspace Client** (left sidebar with **Conversations** and **Uploaded Files**, main multi-turn chat canvas, and the **`Use provided sources`** checkbox in the bottom input bar).

### Step 3.1: Upload a Document to Cloud / Object Storage (`gs://gemma-client-files-${PROJECT_ID}` or `s3://gemma-rag-bucket`)
1. In the left sidebar under **Files**, click **`Upload File`** and select `~/Operation_Vanguard_Shield_Directive.txt` (created in Section 2 above).
2. **Expected Result:**
   - The upload completes (`HTTP 200`) and `Operation_Vanguard_Shield_Directive.txt` appears in the **Files** list in the left sidebar.
   - Make sure the checkbox next to `Operation_Vanguard_Shield_Directive.txt` is **checked**, and the **`Use provided sources`** checkbox at the bottom of the chat input bar is **checked**.

### Step 3.2: Test Strict Document-Grounded RAG (`Use provided sources` = CHECKED)
1. **Prompt 1 (In-Document Fact Extraction):**
   ```text
   According to the uploaded directive, what is the exact authorization codeword required at Checkpoint Sierra, what is the backup UHF frequency, and what is the minimum JP-8 fuel reserve at FOB Echo?
   ```
   - **Expected Result:**
     - The assistant extracts the exact values from the uploaded file:
       - Codeword: **`VANGUARD-OMEGA-749`**
       - Backup Frequency: **`314.85 MHz`** (`Channel 19-Bravo`)
       - Minimum Fuel Reserve: **`42,500 gallons`** (`7 days of supply`)
     - The routing badge next to `Gemma 4 Gateway (Auto)` shows **`→ gemma4:26b`**.

2. **Prompt 2 (Out-of-Document Guardrail Verification while `Use provided sources` is still CHECKED):**
   ```text
   What is the capital of Japan and what is its population?
   ```
   - **Expected Result:**
     - Because **`Use provided sources`** is checked and Japan is not mentioned in `Operation_Vanguard_Shield_Directive.txt`, the model strictly obeys source grounding and replies:
       > `"I cannot answer this based on the provided sources."`

### Step 3.3: Uncheck `Use provided sources` and Verify Seamless Return to General Chat
1. **Action:** In the **exact same chat conversation**, **uncheck** the **`Use provided sources`** checkbox at the bottom of the chat input bar.
2. **Prompt 3 (General Knowledge Question after Unchecking `Use provided sources`):**
   ```text
   What is the capital of Japan and what is it famous for?
   ```
   - **Expected Result:**
     - The backend strips the prior refusal from the conversation context and switches to general assistant mode.
     - The model answers normally about **Tokyo** without refusing!
3. **Prompt 4 (Document Reference + General Knowledge Hybrid):**
   ```text
   Write a Python function that validates whether a given codeword matches 'VANGUARD-OMEGA-749' and whether a fuel reading is above 42500 gallons.
   ```
   - **Expected Result:**
     - Generates the Python validation function and updates the routing badge to **`→ gemma4:31b`**.

---

## 6. Scene 4: Cross-Console Zero-Trust Governance (`Ports 8081/8082` $\rightarrow$ `Port 8080`)

1. Switch back to your **Port `8080`** tab (`🧠 Gemma 4 Gateway Control Plane`).
2. **Inspect Card 3 (`🕵️ Active User Session Oversight & Kill-Switch`):**
   - **Expected Result:** Both **`alice`** (from Port `8081`) and **`charlie`** (from Port `8082`) now appear as active sessions with their client IP, request count, and a red **`Kill Session`** button.
3. **Inspect Card 4 (`👥 User Access Blocklist Management`):**
   - **Action:** Type `alice` into the **`Block User ID`** input box and click **`Block User`**.
   - **Expected Result:** `alice` appears in the active blocklist on Port `8080`.
4. **Verify Instant Revocation on Port `8081`:**
   - Switch to **Port `8081`** (logged in as `alice`) and send a chat message.
   - **Expected Result:** The Gateway immediately rejects `alice`'s request (`403 Forbidden: User 'alice' is blocked by administrator policy`).
5. **Restore Access on Port `8080`:**
   - Return to **Port `8080`**, click **`Unblock`** next to `alice` in Card 4, and verify `alice` can chat again on Port `8081`.

---

## 7. Scene 5: Ports `8083` & `8084` — `gdc-dev` Sovereign Cloud IDE & Multi-Agent Swarm

### Step 5.1: Port `8083` (`https://admin.dev.gdc.local`) — Sovereign Admin & Telemetry Console
1. Open **Port `8083`** (`https://admin.dev.gdc.local`).
2. Click **`Sign in with Keycloak OIDC (Admin Account)`** (`cluster-admin@gdc.local`).
3. **What to Observe:**
   - **Hybrid Telemetry Dashboard:** Displays the 5 seeded baseline telemetry events, live workspace PVC storage usage, active developer workspaces, and agent latency histograms.
4. **Publish a Live Cluster Broadcast Banner:**
   - In the **`📢 Cluster-Wide Broadcast Banner`** card, enter:
     ```text
     ⚡ Sovereign AI Notice: Gemma 4 26B MoE + 31B Dense Gateway Online in Zone 1
     ```
   - Click **`Publish Broadcast`**.

### Step 5.2: Port `8084` (`https://dev.gdc.local`) — Developer IDE & Multi-Agent Swarm
1. Open **Port `8084`** (`https://dev.gdc.local`).
2. Click **`Sign in with Keycloak OIDC`** (`oidc-developer@gdc.local`) and click **`Launch IDE`** (or navigate to `/instances/default-workspace`).
3. **Verify Broadcast Banner Propagation:**
   - At the very top of the Developer IDE, confirm that the banner **`⚡ Sovereign AI Notice: Gemma 4 26B MoE + 31B Dense Gateway Online in Zone 1`** is displayed in real time.
4. **Test the `🤖 GDC Dev AI Swarm` Panel (Right Dock):**
   - Select personas from the `#ai-agent-role` dropdown (`🐝 Swarm`, `📐 Architect`, `💻 Coder`, `🔍 Reviewer`) or use the quick-action chips (`🧪 Gen Tests`, `🔍 Audit`, `⚡ Refactor`, `📐 Plan`):

| Dropdown Persona (`#ai-agent-role`) | Demo Prompt (Copy-Paste) | Exact Live UI Buttons & Verification Steps |
| :--- | :--- | :--- |
| **`💻 Coder`**<br>*(New File Synthesis & Execution)* | **`Write a Python script named health_check.py using only the standard library (urllib.request and json, not requests) that queries http://gemma-gateway.gemma-inference.svc.cluster.local/v1/models and prints the HTTP status code and active model IDs.`** | 1. Displays **`💻 Coder Agent`** badge in green and renders a `PYTHON` code block with header buttons (**`📋 Copy`**, **`📥 Insert into Editor`**) and footer buttons (**`📋 Copy All`**, **`💾 Save as File`**, **`📥 Insert into Editor`**).<br>2. Click **`💾 Save as File`** at the bottom of the response card, confirm **`health_check.py`** in the browser dialog (`Enter filename to save full response to:`), and click **OK**.<br>3. Confirm **`🐍 health_check.py`** appears in the left **Explorer** tree and opens as the active tab in the center editor.<br>4. Click the green **`▶ Run Code`** button in the top-right editor bar (or type `python3 health_check.py` into the bottom **`Terminal - bash (project: default-workspace)`** prompt next to `dev@gdc-session:~/default-workspace$` and press `Enter`) to verify live cross-namespace connectivity to `gemma-gateway`. |
| **`💻 Coder`**<br>*(In-Place Editor Insert & 1-Click Rollback)* | *(Click `🐍 main.py` in the left Explorer first)*<br>**`Add a helper function is_prime(n) to main.py and call it in main() to print all prime numbers up to 20.`** | 1. If the model returns a `PYTHON` code block, click **`📥 Insert into Editor`** to update `main.py` in-place (or if the model emits an `apply_diff` tool call, click **`✓ Approve & Execute`** on the `⚠️ Action Approval Required` card).<br>2. Click **`▶ Run Code`** in the top-right editor bar to run `main.py`.<br>3. Click **`↩ Rollback Changes`** (at the bottom of the message after inserting/applying) to restore `main.py` to its previous state. |
| **`📐 Architect`** | **`Design a zero-trust retry and circuit-breaker specification in architecture.md for calling an air-gapped vLLM InferencePool from a Python microservice.`** | 1. Displays **`📐 Architect Agent`** badge in blue (read-only tool isolation).<br>2. Click **`💾 Save as File`** $\rightarrow$ confirm `architecture.md` $\rightarrow$ click the **`👁️ Preview`** button in the top-right editor bar to render the formatted Markdown specification. |
| **`🔍 Reviewer`** | **`Synthesize a comprehensive pytest unit test suite in test_main.py for is_prime(n) covering 0, 1, negative numbers, primes (2, 3, 19), and non-primes (4, 9, 15).`** | 1. Displays **`🔍 Reviewer / QA Agent`** badge in gold and synthesizes `test_main.py`.<br>2. Click **`💾 Save as File`** $\rightarrow$ confirm `test_main.py` $\rightarrow$ run `pytest test_main.py` in the bottom **`Terminal - bash (project: default-workspace)`** input bar. |
| **`🐝 Swarm`** | **`Build a complete CLI utility in rate_limiter.py with argument parsing and unit tests that calculates token rate-limit budgets per tenant.`** | 1. Displays **`🐝 Multi-Agent Swarm`** badge in purple and renders a structured 3-stage response (`### 📐 1. [Architect Plan]`, `### 💻 2. [Coder Implementation]`, `### 🔍 3. [Reviewer QA & Verification]`) with per-stage **`💾 Save as...`** buttons on each persona header, **`💾 Save As...`** buttons on every code block, and a **`🐝 Swarm Persona Deliverables (3 Agents)`** action bar at the bottom.<br>2. Click **`⚡ Auto-Create All Swarm Files (3)`** in the Swarm Deliverables bar to automatically create and save all 3 agent deliverables to the workspace in one click (`rate_limiter_architecture.md`, `rate_limiter.py`, and `test_rate_limiter.py`), or click the individual persona buttons (**`📐 Save Architect`**, **`💻 Save Coder`**, **`🔍 Save Reviewer`**) to save any single stage with a custom filename.<br>3. Click the green **`▶ Run Code`** button in the top-right editor bar (or run `python3 rate_limiter.py` and `python3 -m unittest test_rate_limiter.py -v` in the bottom **`Terminal - bash (project: default-workspace)`** input bar) to verify both the implementation module and the standalone Reviewer test suite. |

   - **Bonus — Terminal Auto-Repair (`⚡ Fix with Gemma Agent`):**
     - In the bottom **`Terminal - bash (project: default-workspace)`** input row (`dev@gdc-session:~/default-workspace$`), run:
       ```bash
       python3 -c "assert False, 'Enclave checksum verification failed'"
       ```
     - Click the **`⚡ Fix with Gemma Agent`** button that appears directly beneath the red traceback in the terminal output to automatically send the command and stack trace to the AI Swarm for diagnosis.

5. **Verify Real-Time Cross-Console Telemetry (`8084` $\rightarrow$ `8083` & `8080`):**
   - Look back at **Port `8083`** (`gdc-dev` Admin Console): Confirm the **Total AI Invocations** counter incremented and the new `coder` / `swarm` event appears at the top of the **Live Invocation Audit Log** with latency and token counts.
   - Look back at **Port `8080`** (`Gemma 4 Gateway Control Plane`): Confirm **`oidc-developer@gdc.local`** now appears in the **`🕵️ Active User Session Oversight & Kill-Switch`** table alongside `alice` and `charlie`.
