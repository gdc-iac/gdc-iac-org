# GDC Air-Gapped (GDC-ag) Workload Sizing & IO Procurement Framework
## Executive & Technical Presentation Deck

````carousel
# Slide 1: Executive Summary — The Air-Gapped Sizing Paradox
### Why Traditional Cloud Sizing Fails in Disconnected SCIF Enclaves

* **The Cloud Illusion vs. Air-Gapped Reality:**
  * In public cloud, capacity is elastic and procurement takes seconds via API.
  * In **Google Distributed Cloud Air-Gapped (GDC-ag)**, hardware is physically fixed inside accredited SCIF racks, and adding compute, storage, or GPUs requires **9 to 18 months** for supply-chain delivery, TEMPEST/SCIF security accreditation, and physical racking.
* **Three Critical Operational Failure Modes This Framework Solves:**
  1. **Customer Intimidation & "Guesswork BOMs":** Mission owners know their operational problem (Track B) but freeze when asked for Kubernetes `vCPU`, `pgvector` RAM, or `VRAM` KV-cache specs—leading to wildly inaccurate hardware orders.
  2. **The Hidden 22.2x Storage & Platform Overhead Trap:** Naive sizing ignores Kubernetes system reservations (`22%`), Ceph `3x` physical replication, 14-day local snapshots (`2.7x`), and active DR mirroring (`2x`), causing Day 0 storage exhaustion at Month 4.
  3. **The 9–18 Month Procurement Blind Spot:** Infrastructure Operators (IOs) allocate Day 0 (`T0`) racks without visibility into `T+12m` workload ramps—discovering too late that they needed to issue a Purchase Order **on Day 0** to survive Year 1.

<!-- slide -->

# Slide 2: End-to-End Process Flowchart (SCIF Intake to IO Execution)
### How Operational Needs Transform into Physical Rack Allocations & PO Gates

```mermaid
flowchart TD
    subgraph S1["Stage 1: Offline SCIF Customer Intake (No Laptops Allowed)"]
        C_START["Customer Enters Intake Interview"] --> C_TYPE{"Customer Persona?"}
        C_TYPE -->|"Track A: Technical IT Team"| T_A["Provides Exact VM / Pod / DB BOM"]
        C_TYPE -->|"Track B: Mission Owner"| T_B["Describes Mission Workflow in Plain English"]
        T_B --> TWO_LAYER["Facilitator Uses Two-Layer Conversational Guide"]
    end

    subgraph S2["Stage 2: Silent Facilitator Translation (Outside SCIF)"]
        T_A --> LEDGER["Section 6 Tear-Off Transcription Ledger"]
        TWO_LAYER --> LEDGER
        LEDGER --> CODES["Maps Answers to Deterministic Codes [F-01] to [F-28]"]
        CODES --> MODS["Applies Modifiers: Confidence Buffer [F-04B] + Lifespan [F-20C] + Tenancy Tax [F-05]"]
    end

    subgraph S3["Stage 3: Deterministic Calculation & Hardware Bin-Packing Engine"]
        MODS --> ENGINE["CLI (gdc_ag_sizing_cli.py) or Web Visualizer (index.html)"]
        ENGINE --> KUBE_MATH["Compute Engine: Applies 22% Kube System Reserve + N+1 HA Nodes"]
        ENGINE --> CEPH_MATH["Storage Engine: Applies 3x Ceph + 14d Snapshots + 2x Active DR (22.2x Multiplier)"]
        ENGINE --> MIG_MATH["GPU Engine: Enforces Hardware NVIDIA MIG Slices (3g.40gb / 2g.20gb) on 80GB Cards"]
    end

    subgraph S4["Stage 4: Infrastructure Operator (IO) & Platform Admin (PA) Action Plan"]
        KUBE_MATH --> HORIZONS["4-Horizon Schedule: T0 (Day 0), T+6m, T+12m, T+24m"]
        CEPH_MATH --> HORIZONS
        MIG_MATH --> HORIZONS
        HORIZONS --> GATE_T0{"Gate 1: Does T0 Fit Current Rack Headroom?"}
        GATE_T0 -->|"Yes"| ACT_T0["IO Allocates Day 0 Racks + PA Applies Cluster YAML"]
        GATE_T0 -->|"No"| ACT_POC["Stage PoC / Trigger Immediate Emergency Rack Order"]
        HORIZONS --> GATE_T12{"Gate 2: Does T+12m Exceed Current Headroom?"}
        GATE_T12 -->|"Yes (9-18m Lead Time)"| ACT_PO0["TRIGGER DAY 0 EMERGENCY HARDWARE PO (Order Nodes/Ceph/GPUs Now)"]
        HORIZONS --> GATE_T24{"Gate 3: T+24m Delta vs T+12m"}
        GATE_T24 --> ACT_POM6["Schedule Month 6 Procurement Order for Month 18 Delivery"]
    end
```

<!-- slide -->

# Slide 3: Solving Problem 1 — The Two-Layer Intake Architecture
### Eliminating Technical Intimidation Without Losing Mathematical Rigor

| Layer | Target Persona | Environment | Operational Mechanism | Example Question / Mapping |
| :--- | :--- | :--- | :--- | :--- |
| **Layer 1: Spoken Conversational Script** | Mission Owners, Agency Directors, Non-Technical Stakeholders (**Track B**) | Inside Accredited SCIF (Paper/Pen Only) | Asks warm, operational questions about shift-change concurrency, document Q&A, and outage tolerance. | *"If a server rack loses power, does this system need to stay online immediately with a live copy at your backup site?"* |
| **Layer 2: Silent Facilitator Rules** | GDC Solution Architects & Systems Engineers | Section 6 Tear-Off Ledger & CLI/Web Tool | Deterministically translates spoken operational answers into strict infrastructure parameters (`[F-01]`–`[F-28]`). | Maps *"Stay online + backup site copy"* $\rightarrow$ **`[F-07] = ZONAL_HA_PLUS_DR`** (`2.0x` Site Multiplier + `3x` Ceph Quorum). |
| **Data Confidence Contingency (`[F-04B]`)** | Infrastructure Operations (IO) Risk Management | Automated Engine Multiplier | Protects IO racks from customer guesswork by automatically injecting a storage safety buffer based on data maturity. | • `MEASURED` (`+0%` / `1.00x`)<br>• `DERIVED` (`+10%` / `1.10x`)<br>• `ESTIMATED` (`+25%` / `1.25x`) |
| **Workload Lifespan Reclamation (`[F-20C]`)** | Capacity Planners | Automated Pool Tagging | Flags temporary surge workloads or off-shift dev/test environments so compute/VRAM can be reclaimed. | `SPINDOWN_ELIGIBLE` flags non-prod cores for off-shift reclamation rather than permanent hardware purchase. |

<!-- slide -->

# Slide 4: Solving Problem 2 — Multi-Tenant Isolation vs. Dedicated Tax
### Codifying Platform Services (`[F-05]`) & Hardware-Isolated GPU MIG (`[F-08]`)

```mermaid
flowchart LR
    subgraph TENANCY["Platform Tenancy Choice ([F-05])"]
        T_DEF["SHARED_DEFAULT (Recommended)<br>Multi-Tenant Shared Cluster & Platform Services<br>Isolation Tax: +0 vCPU / +0 GiB RAM"]
        T_HYB["HYBRID_DEDICATED_SVC<br>Shared Cluster + Dedicated Vault (P11) & SSO (P12)<br>Isolation Tax: +24 vCPU / +96 GiB RAM"]
        T_DED["DEDICATED_SINGLE_TENANT<br>Physically Isolated Single-Tenant Cluster<br>Isolation Tax: +32 vCPU / +128 GiB RAM / +1.05 TiB Ceph"]
    end

    subgraph MIG_ARCH["Hardware-Level NVIDIA MIG GPU Partitioning ([F-08])"]
        GPU_CARD["Physical NVIDIA A100 / H100 (80GB VRAM)"]
        GPU_CARD --> SLICE_1["Slot #1: MIG 3g.40gb (40GB VRAM)<br>Assigned: Project Alpha (Prod Gemma 26B/31B)"]
        GPU_CARD --> SLICE_2["Slot #2: MIG 3g.40gb (40GB VRAM)<br>Assigned: Project Beta (DR Standby / SQL Agent)"]
    end
```

* **Enforced Architectural Guardrails:**
  1. **Zero-Trust GPU Multi-Tenancy:** Software time-slicing is prohibited across security boundaries. The engine enforces hardware-level NVIDIA MIG profiles (`1g.10gb`, `2g.20gb`, `3g.40gb`, `7g.80gb`) with dedicated memory controllers and fault isolation per project namespace.
  2. **VRAM Out-of-Memory (OOM) Prevention:** Selecting `Gemma 4 26B/31B` (`P6 RAG` / `P7 SQL`) automatically blocks `1g.10gb` and `2g.20gb` slices and enforces **`MIG_3G_40GB` (`40GB` VRAM minimum)** to fit model weights + FP16 KV-cache.

<!-- slide -->

# Slide 5: Solving Problem 3 — The 22.2x Raw Storage Multiplier
### Why "500 GiB of Mission Data" Requires 54.60 TiB of Physical Ceph Disk on Day 0

Many air-gapped deployments fail within 90 days because sizing only accounts for raw database files. The GDC-ag Sizing Engine compounds five mandatory physical storage layers:

$$\text{Raw Physical Ceph (TiB)} = \left( \text{Primary Usable Data} \times \text{Index Factor (1.20)} \times \text{DR Site Mirror (2.0)} \times \text{Confidence Buffer (1.10)} \right) \times \left( 1 + \text{Snapshot Factor (2.70)} \right) \times \text{Ceph Replication (3.0)}$$

| Storage Multiplier Layer | Engineering Justification | Cumulative Impact (Project Sentinel Example) |
| :--- | :--- | :--- |
| **1. Baseline + Harbor Bundle (`[F-17]`)** | Blueprint `P4 + P6 + P7` usable volumes (`1,788 GiB`) + `120 GiB` air-gapped container bundle. | **`1,908 GiB` (`1.86 TiB`)** |
| **2. Vector & DB Index Overhead (`+20%`)** | HNSW vector indexes (`pgvector`), WAL logs, and B-Tree metadata require `1.20x` disk space. | **`2,290 GiB` (`2.24 TiB`)** |
| **3. Active Disaster Recovery Mirror (`×2.0`)** | `ZONAL_HA_PLUS_DR` maintains an active, real-time replicated copy at the secondary SCIF site. | **`4,580 GiB` (`4.47 TiB`)** |
| **4. Data Confidence Buffer (`[F-04B] = +10%`)** | `DERIVED` workshop sizing injects a `+10%` contingency buffer (`1.10x`). | **`5,038 GiB` (`4.92 TiB Usable`)** |
| **5. Local Snapshots (`×3.70`) & Ceph (`×3.0`)** | 14 days of daily snapshots (`5%/day` + `2` full base backups = `2.7x` backup addition $\rightarrow 3.7x$ total) stored on **3-way replicated Ceph OSDs (`×3.0`)**. | **`54.60 TiB Raw Physical Ceph Disk`** |

<!-- slide -->

# Slide 6: Solving Problem 4 — The 9–18 Month IO Hardware Procurement Gate
### Why the T+12m Forecast Dictates Day 0 Hardware Purchase Orders

```mermaid
flowchart LR
    T0["Day 0 (T0)<br>Demand: 96 vCPU | 54.6 TiB Ceph | 3 GPUs<br>Rack Headroom: 96 vCPU | 80 TiB | 3 GPUs<br>Verdict: APPROVED FROM EXISTING RACKS"]
    T6["Month 6 (T+6m)<br>Demand: 104 vCPU | 183.4 TiB Ceph | 4 GPUs<br>Status: Storage Exceeds 80 TiB Headroom!<br>(Covered ONLY if Day 0 PO was issued)"]
    T12["Month 12 (T+12m Gate)<br>Demand: 128 vCPU | 315.7 TiB Ceph | 5 GPUs<br>Net Deficit: +32 vCPU | +235.7 TiB | +2 GPUs<br>Action: MUST ORDER ON DAY 0 (9-18m Lead Time)"]
    T24["Month 24 (T+24m Gate)<br>Demand: 160 vCPU | 576.9 TiB Ceph | 9 GPUs<br>Delta vs T+12m: +32 vCPU | +261.1 TiB | +4 GPUs<br>Action: ORDER AT MONTH 6 FOR M18 RACKING"]

    T0 ==>|"Immediate Allocation"| T6
    T0 -.->|"9-18m Supply Chain Lead Time<br>DAY 0 EMERGENCY PO"| T12
    T6 -.->|"Scheduled Expansion PO"| T24
```

* **Operational Takeaway for Infrastructure Operators (IOs):**
  * Even when a workload fits 100% inside existing unallocated racks on **Day 0 (`T0`)**, continuous daily data ingestion (`25 GiB/day` $\rightarrow 22.2\times$ raw multiplier) and user ramp-up will exhaust rack storage by **Month 5**.
  * Because GDC-ag hardware procurement and SCIF accreditation take **9 to 18 months**, the IO team **must execute the `T+12m` deficit Purchase Order on Day 0**.

<!-- slide -->

# Slide 7: Toolchain Demonstration — Offline Guide, CLI & Web Visualizer
### Unified Workflow Across Disconnected and Connected Environments

| Tool Component | File Path in Repository | Primary User & Execution Mode | Key Output Artifacts |
| :--- | :--- | :--- | :--- |
| **1. Two-Layer Offline Questionnaire** | `docs/capacity-sizing/gdc_ag_offline_interview_questionnaire.md` | **Facilitator inside SCIF** (Printed booklet, zero electronic devices). | Completed **Section 6 Tear-Off Transcription Ledger** (`[F-01]`–`[F-28]` checkboxes). |
| **2. Interactive Web Visualizer** | `docs/capacity-sizing/index.html` (`gdc_ag_sizing_calculator.html`) | **Architect / Customer Workshop** (`python3 -m http.server 8080`). | • Live Plain-English $\leftrightarrow$ Coded Mode Toggle<br>• Visual NVIDIA 80GB MIG Card Slot Layout<br>• Rack Headroom Comparison Bars<br>• Declarative Kubernetes `Cluster` YAML |
| **3. Zero-Dependency CLI Engine** | `docs/capacity-sizing/gdc_ag_sizing_cli.py` | **IO / CI-CD Automation** (`python3 gdc_ag_sizing_cli.py --input ...`). | • Formatted ASCII Executive IO Action Plan<br>• Automated Day 0 & Month 6 Purchase Order Quantities<br>• Structured JSON for GitOps Pipelines |
````
