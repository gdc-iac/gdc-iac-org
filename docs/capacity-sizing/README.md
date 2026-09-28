# GDC Air-Gapped (`GDC-ag`) Workload Sizing & IO Procurement Toolkit

This directory contains a self-contained, zero-dependency toolkit for conducting **GDC Air-Gapped (`GDC-ag`) Customer Discovery Interviews**, collating `[F-01]`–`[F-28]` sizing inputs, and calculating **Day 0 (`T0`) Physical Rack Allocations** and **9–18 Month Hardware Procurement Orders (`T+12m` / `T+24m`)** for Infrastructure Operations (IO).

---

## 1. File Guide — Which File Should You Use?

| File | Purpose & When to Use |
| :--- | :--- |
| **[`gdc_ag_interview_form.html`](./gdc_ag_interview_form.html)** | **Step 1A (Electronic Interview & JSON Collator):** Open in any browser when a laptop/tablet is permitted in the discovery session (or when transcribing paper notes outside a SCIF). Guides you through Domains 0–5 (`[F-01]`–`[F-28]`), validates inputs, and exports `<project>_intake.json` or passes data directly into the Web Calculator in 1 click. |
| **[`gdc_ag_offline_interview_questionnaire.md`](./gdc_ag_offline_interview_questionnaire.md)** | **Step 1B (Printable Paper Guide for Strict SCIFs):** Print to paper/PDF when electronic devices are prohibited inside the room. Includes spoken plain-English prompts, silent `[F-01]`–`[F-28]` translation rules, and a **Blank Printable Tear-Off Worksheet (Section 6A)** to carry out of the SCIF. |
| **[`gdc_ag_sizing_calculator.html`](./gdc_ag_sizing_calculator.html)**<br>*(mirrored at [`index.html`](./index.html))* | **Step 2A (Interactive Web Sizing Calculator):** Consumes the collated intake data (via 1-click handoff from `gdc_ag_interview_form.html`, **`📂 Load Intake JSON`**, or interactive sliders) and calculates `T0`, `T+6m`, `T+12m`, and `T+24m` physical cores, 3x Ceph storage, GPU card layouts (**NVIDIA B300 `288GB` Exclusive for Gemini** vs **A100/H100 `80GB` MIG for Gemma**), and Kubernetes `NodePool` YAML. |
| **[`gdc_ag_sizing_cli.py`](./gdc_ag_sizing_cli.py)** | **Step 2B (Headless Offline Python CLI):** Zero-dependency Python 3 CLI that takes `--input <project>_intake.json` and outputs the full JSON/table report and Kubernetes YAML manifests (`--yaml-out`). |
| **[`customer_intake_example.json`](./customer_intake_example.json)** | **Pre-Populated Reference Input (`tactical-c2-prod`):** Sample JSON intake file matching the `J3 Operations Directorate` worked example in Section 7 of the questionnaire. |
| **[`MAINTENANCE.md`](./MAINTENANCE.md)** | **Zero-Rewrite Maintainer's Guide:** Copy-paste recipes for adding new workload blueprints (`P14+`), GPU SKUs, or platform service taxes via the single `SIZING_CONFIG` dictionary (`0` HTML or formula rewrites). |
| **[`presentation.html`](./presentation.html)** | **Executive Slide Deck:** Interactive HTML slide deck with the end-to-end GDC-ag sizing flowchart and architectural guardrails. |

---

## 2. How to Run the HTML Files (`gdc_ag_interview_form.html` & `gdc_ag_sizing_calculator.html`)

Both HTML files are **100% portable** (no backend database, npm build, or server install required). Choose the instructions below matching your device:

### Option A: Files Copied Locally to a Mac (`macOS`)
* **Method 1 — Direct Double-Click in Finder (No Terminal Needed):**
  1. Copy the `docs/capacity-sizing/` folder to your Mac (e.g., `~/Downloads/capacity-sizing/`).
  2. In **Finder**, double-click **`gdc_ag_interview_form.html`** (or right-click $\rightarrow$ *Open With* $\rightarrow$ *Google Chrome* / *Safari*).
  3. Complete the interview fields and click **`🚀 Pass to Web Calculator`** (which passes the collated data directly to `gdc_ag_sizing_calculator.html` via URL hash `#intake=...` even on `file://`), or click **`💾 Download Intake JSON`**.
* **Method 2 — Local Web Server via Mac `Terminal.app`:**
  ```bash
  cd ~/Downloads/capacity-sizing
  python3 -m http.server 8765
  ```
  Then open **`http://localhost:8765/gdc_ag_interview_form.html`** or **`http://localhost:8765/gdc_ag_sizing_calculator.html`**.

---

### Option B: Files Copied Locally to a Chromebook (`ChromeOS`)
* **Method 1 — Direct Open from ChromeOS `Files` App (No Linux Needed):**
  1. Save the `docs/capacity-sizing/` folder into **My Files** or **Downloads** in the ChromeOS **Files** app.
  2. Double-click **`gdc_ag_interview_form.html`** or **`gdc_ag_sizing_calculator.html`** (or right-click $\rightarrow$ *Open with View*).
  3. Use **`🚀 Pass to Web Calculator`** or **`💾 Download Intake JSON`** + **`📂 Load Intake JSON`** to move data between the interview form and the calculator.
* **Method 2 — Chromebook Linux Terminal (`Crostini`):**
  If your git repository is cloned inside the Chromebook Linux container:
  ```bash
  cd ~/GitHub/GDC-blueprints/docs/capacity-sizing
  python3 -m http.server 8765
  ```
  Then open **`http://localhost:8765/gdc_ag_interview_form.html`** in Chrome.

---

### Option C: Google Cloud Workstation (`~/GitHub/GDC-blueprints`)
1. Open your **Cloud Workstation terminal** and start the lightweight Python HTTP server:
   ```bash
   cd ~/GitHub/GDC-blueprints/docs/capacity-sizing
   git pull origin main
   python3 -m http.server 8765 --bind 0.0.0.0
   ```
2. **Open in Your Browser:**
   * **Using Cloud Workstation Web Preview:** Click the **Web Preview / Port Forward** button in the Cloud Workstation top bar, select port **`8765`**, and navigate to `/gdc_ag_interview_form.html` or `/gdc_ag_sizing_calculator.html`.
   * **Using SSH Port Forwarding from Your Local Laptop:**
     ```bash
     ssh -L 8765:localhost:8765 <your-user>@<your-workstation-or-cloudtop-host>
     ```
     Then open **`http://localhost:8765/gdc_ag_interview_form.html`** on your local browser.

---

## 3. Unambiguous End-to-End Workflow Summary

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: CAPTURE CUSTOMER INPUTS ([F-01] to [F-28])                                     │
│                                                                                        │
│  • Path A (Laptop Allowed): Open `gdc_ag_interview_form.html` in browser.              │
│  • Path B (Paper SCIF Only): Print `gdc_ag_offline_interview_questionnaire.md`,        │
│    fill in the BLANK Section 6A Tear-Off Sheet, then enter codes outside the SCIF.     │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: GENERATE / PASS THE COLLATED INTAKE PAYLOAD (`<project>_intake.json`)          │
│                                                                                        │
│  • Click `🚀 Pass to Web Calculator` in `gdc_ag_interview_form.html` (Instant Load)    │
│  • OR Click `💾 Download Intake JSON` to save `<project>_intake.json`                  │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: GENERATE DAY 0 RACK ALLOCATION & T+12M HARDWARE PURCHASE ORDER                 │
│                                                                                        │
│  • Web UI: `gdc_ag_sizing_calculator.html` (Visual Rack Bars, B300/MIG Slots, YAML)    │
│  • CLI:    `python3 gdc_ag_sizing_cli.py --input <project>_intake.json`                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```
