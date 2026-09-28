# GDC-ag Sizing Calculator & CLI — Maintainer's Guide (`Zero-Rewrite Architecture`)

> **Design Philosophy: Deliberate Simplicity & Portability**
> Because Google Distributed Cloud Air-Gapped (`GDC-ag`) sizing tools must operate inside disconnected SCIFs, tactical command posts, and standalone laptops without internet access, Node.js, npm build pipelines, or external database dependencies, the entire toolchain consists of two self-contained files:
> 1. **Web Calculator & Visualizer:** [`gdc_ag_sizing_calculator.html`](./gdc_ag_sizing_calculator.html) (mirrored to [`index.html`](./index.html)) — Vanilla HTML + JavaScript in a single file.
> 2. **Headless CLI Calculator:** [`gdc_ag_sizing_cli.py`](./gdc_ag_sizing_cli.py) — Standard-library Python 3 (`0` pip dependencies).

To ensure **ongoing maintenance never requires HTML edits or calculation rewrites** when new services, blueprints, platform operators, or GPU hardware SKUs (such as **NVIDIA B300 for Gemini**) are introduced to GDC-ag, both tools use a **Single Declarative Catalog (`SIZING_CONFIG`)** at the top of the file.

---

## 1. Architecture: How the Zero-Rewrite Catalog Works

When [`gdc_ag_sizing_calculator.html`](./gdc_ag_sizing_calculator.html) loads in a browser, its initialization function (`initCatalogUI()`) reads the top-level `SIZING_CONFIG` JavaScript object and **automatically builds**:
1. **All Workload / Service Blueprint Checkboxes** (`Section 3B`) — including both Customer-Friendly plain-English descriptions (`friendlyDesc`) and Facilitator Coded labels (`codedDesc`).
2. **All GPU / Hardware Profile Dropdown Options** (`Section 2: [F-08]`) — including the target physical GPU SKU (e.g. `NVIDIA B300 (288GB HBM3e — Gemini Only)` vs. `NVIDIA A100/H100 (80GB MIG)` vs. `NVIDIA L4 (24GB)`), per-card VRAM, and MIG slot geometry.
3. **All Platform Service Isolation Taxes** (`Vault P11`, `Keycloak P12`, cluster quorum, or any future platform operator) based on the selected tenancy mode.
4. **Live Hardware Visualizer Cards & Guardrails** — automatically adapting the physical GPU card slot diagram, rack headroom progress bars, and hardware SKU warnings (`requiresB300`, `needsLargeModel`) to the selected entry in `SIZING_CONFIG`.

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                                SINGLE DECLARATIVE DATA BLOCK                               │
│                                    SIZING_CONFIG (Top of File)                             │
│  • blueprints:       { P1_DOCS_COLLAB, ..., P14_YOUR_NEW_SERVICE }                         │
│  • gpuProfiles:      { MIG_3G_40GB, NATIVE_GEMINI_ENDPOINT (B300 Only), ... }              │
│  • platformServices: { HARBOR_SCANNING, KEYCLOAK_VAULT, NEW_PLATFORM_OPERATOR, ... }       │
└──────────────────┬───────────────────────────────────┬─────────────────────────────────────┘
                   │                                   │
                   ▼                                   ▼                                     ▼
┌────────────────────────────────────┐  ┌────────────────────────────────────┐  ┌────────────────────────────────────┐
│ HTML Interview Form                │  │ Web Sizing Calculator              │  │ Offline Python CLI                 │
│ (`gdc_ag_interview_form.html`)     │  │ (`gdc_ag_sizing_calculator.html`)  │  │ (`gdc_ag_sizing_cli.py`)           │
│ • Auto-renders interview domains   │  │ • Auto-renders checkboxes & GPUs   │  │ • Consumes `<project>_intake.json` │
│ • Collates [F-01]–[F-28] answers   │  │ • Loads `<project>_intake.json`    │  │ • Supports external catalog via:   │
│ • Exports `<project>_intake.json`  │  │ • Or 1-click `?autoload=intake`    │  │   `--catalog custom_catalog.json`  │
└────────────────────────────────────┘  └────────────────────────────────────┘  └────────────────────────────────────┘
```

---

## 2. Recipe A: Adding a New Workload Blueprint or Service (`0` HTML/Formula Edits)

To add a new application pattern or GDC service (for example, **`P14_SPEECH_ASR`: Sovereign Audio Transcription & Translation Service**):

### Step 1: Add 1 Object Entry to `SIZING_CONFIG.blueprints`
Open [`gdc_ag_sizing_calculator.html`](./gdc_ag_sizing_calculator.html), locate `const SIZING_CONFIG = { blueprints: { ... } }` near the top of the `<script>` block, and add your service entry:

```javascript
      P14_SPEECH_ASR: {
        name: "P14: Speech & Audio ASR",
        friendlyDesc: "<b>Voice & Audio Transcription:</b> Real-time radio/audio transcription & translation (P14 ASR)",
        codedDesc: "<b>[P14_SPEECH_ASR]:</b> Whisper/Chirp Streaming ASR + Translation Worker Pool",
        defaultChecked: false,
        minNodes: 2,
        needsLargeModel: false,      // Set true if workload requires >= 40GB VRAM (Gemma 26B/31B)
        requiresGeminiB300: false,   // Set true if workload requires Native Gemini on NVIDIA B300
        tiers: {
          TIER_S: { podCpu: 4.0,  podRam: 16, dbCpu: 2, dbRam: 8,  blockGib: 100, objGib: 250,  migSlices: 1 },
          TIER_M: { podCpu: 8.0,  podRam: 32, dbCpu: 4, dbRam: 16, blockGib: 250, objGib: 1000, migSlices: 2 },
          TIER_L: { podCpu: 16.0, podRam: 64, dbCpu: 8, dbRam: 32, blockGib: 500, objGib: 4096, migSlices: 4 }
        }
      },
```

### What Happens Automatically:
* A new checkbox automatically appears in **Section 3B** of the Web Calculator.
* Clicking **🔄 Switch to Coded Mode (`[F-01]`–`[F-28]`)** automatically toggles the checkbox text between `friendlyDesc` and `codedDesc`.
* Selecting `P14_SPEECH_ASR` automatically adds its `podCpu`, `podRam`, `dbCpu` (respecting the Consolidated vs. Siloed DB policy), `blockGib + objGib` storage (multiplied through the 3x Ceph and backup waterfall), and `migSlices` across all 4 time horizons (`T0`, `T+6m`, `T+12m`, `T+24m`).
* Exporting or importing Section 6 transcription blocks (`F18B_BLUEPRINT_PATTERNS`) automatically includes `P14_SPEECH_ASR`.

---

## 3. Recipe B: Adding or Updating a GPU Hardware SKU (e.g., `NVIDIA B300` for Gemini)

Currently on GDC-ag:
* **Native GDC Gemini (`NATIVE_GEMINI_ENDPOINT`)** is supported **exclusively via NVIDIA B300 (`288GB HBM3e`)** hardware and cannot be scheduled onto A100, H100, or L4 GPUs.
* **Self-Hosted Open-Weights (`Gemma 4 26B/31B` via `vLLM`)** run on **NVIDIA A100/H100 (`80GB HBM`)** using hardware-isolated MIG slices (`1g.10gb`, `2g.20gb`, `3g.40gb`, `7g.80gb`).
* **Single-Tenant PoC Workloads (`Ollama`)** can run on **NVIDIA L4 (`24GB GDDR6`, whole-card, no MIG)**.

If GDC introduces a new GPU SKU (or if Gemini support expands to a new accelerator SKU in a future release), edit `SIZING_CONFIG.gpuProfiles` in [`gdc_ag_sizing_calculator.html`](./gdc_ag_sizing_calculator.html):

```javascript
      NATIVE_GEMINI_ENDPOINT: {
        label: "GDC Gemini API (B300 Only)",
        gpuSku: "NVIDIA B300 (288GB HBM3e — Gemini Exclusive)",
        cardVramGb: 288,
        slicesPerPhysicalCard: 2,
        vramGb: 144,
        isolationLabel: "Dedicated B300 Gemini Appliance Pool",
        requiresB300: true,
        defaultSelected: false,
        friendlyOption: "Massive 500-Page Reports / 1M Token Context (-> GDC Native Gemini on NVIDIA B300 288GB Only)",
        codedOption: "[NATIVE_GEMINI_ENDPOINT] GDC Vertex Gemini API (Requires NVIDIA B300 288GB Hardware)"
      },
```

### What Happens Automatically:
* The **Section 2 (`[F-08]`) dropdown** automatically displays the updated `friendlyOption` / `codedOption`.
* The **Live Hardware Visualizer (`Visual Card 1B`)** automatically switches its card header and progress bars from `NVIDIA A100/H100 (80GB)` to `NVIDIA B300 (288GB HBM3e — Gemini Exclusive)` with `144GB` / `288GB` slots.
* When `requiresB300: true` is active, an automatic **Hardware Procurement Guardrail** warns the Infrastructure Operator (IO) that unallocated rack GPUs must be physical **NVIDIA B300** units (not A100/H100/L4).

---

## 4. Recipe C: Adding a New Platform-Managed Service Isolation Tax

When a customer requests `DEDICATED_SINGLE_TENANT` or `HYBRID_DEDICATED_SVC` isolation (`[F-05]`), the calculator adds the control-plane overhead of dedicated platform services (`Vault P11`, `Keycloak P12`, cluster quorum).

To add a new platform-level service (for example, a dedicated **`SIEM_OTEL_COLLECTOR`** or **`ALLOYDB_OMNI_OPERATOR`**), add an entry to `SIZING_CONFIG.platformServices`:

```javascript
      SIEM_OTEL_COLLECTOR: {
        name: "Dedicated Security Log / SIEM Forwarder",
        vcpu: 4,
        ramGib: 16,
        usableGib: 100,
        minNodes: 2,
        applyInModes: ["DEDICATED_SINGLE_TENANT", "HYBRID_DEDICATED_SVC"]
      }
```

The calculator automatically sums `vcpu`, `ramGib`, and `usableGib` across all entries in `SIZING_CONFIG.platformServices` whose `applyInModes` array matches the selected `[F-05]` tenancy policy.

---

## 5. Recipe D: Adding Services to the Python CLI Without Editing Code (`--catalog`)

The Python CLI ([`gdc_ag_sizing_cli.py`](./gdc_ag_sizing_cli.py)) contains the exact same `SIZING_CONFIG` dictionary so it works as a single standalone file. However, you can also export, customize, and pass a JSON catalog file at runtime without editing `gdc_ag_sizing_cli.py`:

```bash
# 1. Export the current built-in service & hardware catalog to a JSON file:
python3 ./docs/capacity-sizing/gdc_ag_sizing_cli.py --dump-catalog ./my_custom_catalog.json

# 2. Edit ./my_custom_catalog.json (add new blueprints, GPU SKUs, or platform services)

# 3. Run the sizing calculator using your custom catalog + customer intake JSON:
python3 ./docs/capacity-sizing/gdc_ag_sizing_cli.py \
  --catalog ./my_custom_catalog.json \
  --input ./docs/capacity-sizing/customer_intake_example.json
```

---

## 6. Two-Step Maintenance Checklist Before Committing

Whenever you update [`gdc_ag_sizing_calculator.html`](./gdc_ag_sizing_calculator.html):

1. **Sync `index.html` with `gdc_ag_sizing_calculator.html`** (so `python3 -m http.server 8080` serves the updated calculator at the root `/` path):
   ```bash
   cp ./docs/capacity-sizing/gdc_ag_sizing_calculator.html ./docs/capacity-sizing/index.html
   ```
2. **Verify the CLI Calculator executes cleanly:**
   ```bash
   python3 ./docs/capacity-sizing/gdc_ag_sizing_cli.py --demo
   ```
