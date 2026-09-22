# GDC Air-Gapped (GDC-ag) Facilitator Interview Guide & Deterministic Capture Form (v2.1)

> **WHICH INTERVIEW TOOL SHOULD YOU USE? (READ FIRST)**
> This directory provides **two ways** to conduct the Customer Discovery Interview (`[F-01]` to `[F-28]`):
>
> | Scenario | Recommended Tool | How Data Reaches the Sizing Calculator |
> | :--- | :--- | :--- |
> | **Laptop / Tablet Permitted in Session**<br>*(Standard workshop, video call, or accredited laptop)* | **[`gdc_ag_interview_form.html`](./gdc_ag_interview_form.html)**<br>*(Interactive Browser Form)* | Form automatically collates all `[F-01]`–`[F-28]` answers as you click. Click **`🚀 Pass to Web Calculator`** (opens `gdc_ag_sizing_calculator.html` pre-filled) or **`💾 Download Intake JSON`**. |
> | **Strict Paper-Only SCIF**<br>*(No electronic devices permitted inside the room)* | **This Document (`gdc_ag_offline_interview_questionnaire.md`)**<br>*(Print to Paper / PDF)* | Circle the `[F-01]`–`[F-28]` checkboxes on paper during the interview, record them on the **Blank Tear-Off Sheet (Section 6A)**, and after leaving the SCIF enter them into `gdc_ag_interview_form.html` or `gdc_ag_sizing_calculator.html` (see **Section 6B**). |

---

### How to Open & Run the HTML Files (`gdc_ag_interview_form.html` & `gdc_ag_sizing_calculator.html`)

Both HTML files are **100% self-contained** (zero backend database or build step required) and can be run in three ways depending on your device:

1. **Files Copied Locally to a Mac (Finder):**
   * **Direct Double-Click (Simplest):** Open **Finder**, navigate to the `docs/capacity-sizing/` folder, and double-click `gdc_ag_interview_form.html` or `gdc_ag_sizing_calculator.html`. It opens directly in Chrome/Safari (`file:///...`). Clicking **`🚀 Pass to Web Calculator`** automatically passes your answers via the URL hash (`#intake=...`) even without a web server.
   * **Optional Local Web Server (Terminal):** Open `Terminal.app`, `cd` into the folder, and run:
     ```bash
     python3 -m http.server 8765
     # Then open http://localhost:8765/gdc_ag_interview_form.html in Chrome/Safari
     ```

2. **Files Copied Locally to a Chromebook (ChromeOS):**
   * **Direct Double-Click (`Files` App):** Open the ChromeOS **Files** app, locate the downloaded `docs/capacity-sizing/` folder under *My Files / Downloads*, and double-click `gdc_ag_interview_form.html` or `gdc_ag_sizing_calculator.html` to open it directly in a Chrome tab.
   * **Linux Development Environment (Crostini Terminal):** If your repo is inside the Chromebook Linux container (`~/GitHub/GDC-blueprints/docs/capacity-sizing`), run:
     ```bash
     python3 -m http.server 8765
     # Then open http://localhost:8765/gdc_ag_interview_form.html in Chrome
     ```

3. **Google Cloud Workstation or Remote Linux Server (`~/GitHub/GDC-blueprints`):**
   * In your Cloud Workstation terminal, start the HTTP server:
     ```bash
     cd ~/GitHub/GDC-blueprints/docs/capacity-sizing
     python3 -m http.server 8765 --bind 0.0.0.0
     ```
   * **To view in your browser:**
     * **Cloud Workstation Web Preview:** Click the **Web Preview / Port Forward** icon in your Cloud Workstation IDE, enter port **`8765`**, and append `/gdc_ag_interview_form.html` or `/gdc_ag_sizing_calculator.html`.
     * **SSH Port Forward (From your local laptop terminal to Cloudtop/Workstation):**
       ```bash
       ssh -L 8765:localhost:8765 <your-user>@<workstation-or-cloudtop-host>
       # Then open http://localhost:8765/gdc_ag_interview_form.html locally
       ```

---

> **HOW THIS PAPER GUIDE WORKS — TWO-LAYER ARCHITECTURE:**  
> Non-technical mission owners feel intimidated when asked about Kubernetes pod requests, vCPU overcommit ratios, or NVIDIA MIG slice geometries (`3g.40gb`). Conversely, Infrastructure Operations (IO) teams cannot order physical racks from vague prose notes.  
> 
> This guide solves both problems by separating **what you say aloud** from **how you code the math**:
> 1. **🗣️ Customer-Facing Conversational Prompts (*Italicized text*):** Read these plain-English, non-technical questions aloud. Customers answer purely in terms of **their mission, users, documents, shift patterns, downtime impact, and rollout dates**.
> 2. **🔒 Facilitator Silent Translation Rules (Shaded Boxes — DO NOT READ ALOUD):** Underneath each conversational question is a deterministic translation rule. As the customer speaks, you silently check the corresponding **`[F-01]` – `[F-28]`** code box.
> 3. **📋 Facilitator Close-Out (After Customer Leaves):** Transfer your checked `[F-xx]` codes onto the **Blank Section 6A Tear-Off Worksheet** and follow **Section 6B** to load them into the calculator. *(See **Section 7** for a pre-populated reference example).*

---

## Section 0: Engagement Scope, Confidence & Lifespan (`[AB]`)

| Question & Spoken Conversational Prompt (*Read Aloud*) | 🔒 Facilitator Silent Translation & Coding Rule (*Do Not Read Aloud*) |
| :--- | :--- |
| **0.1 Mission & Ownership**<br>*"To kick off, what is the name of this project or system, which operational team owns it, and when do you need initial go-live?"* | **`[F-01]` Project / Namespace ID:** `_________________________`<br>**`[F-02]` Sponsoring Directorate:** `_________________________`<br>**`[F-04]` Target Day 0 Go-Live Date (`YYYY-MM`):** `_____________` |
| **0.2 Technical Specification Readiness (Track Selector)**<br>*"Do you already have a concrete bill of materials — exact VM shapes, container CPU/memory requests, or vendor hardware sizing sheets — that you trust for this deployment, or would you prefer we size the infrastructure together based on what the application does?"* | **`[F-03]` Sizing Entry Path:**<br>• `[ ] PATH_A` — Customer has trusted VM/K8s/DB sizing specs (Use Section 3A).<br>• `[ ] PATH_B` — Customer knows the operational problem/scale, not the hardware specs (Use Section 3B). |
| **0.3 Data Source & Sizing Confidence**<br>*"For the usage numbers we discuss today (user counts, data volumes), are these measured from an existing system running today, derived from vendor benchmarks, or early planning estimates?"* | **`[F-04B]` Data Confidence Class (Sets IO Contingency Buffer):**<br>• `[ ] MEASURED` — Exported from live system (`+0%` IO contingency buffer)<br>• `[ ] BENCHMARKED` — Vendor / reference benchmark (`+5%` IO buffer)<br>• `[ ] DERIVED` — Calculated together today (`+10%` IO buffer)<br>• `[ ] ESTIMATED` — Early planning estimate / guess (`+25%` IO safety buffer) |
| **0.4 Workload Lifespan & Operating Schedule**<br>*"Once deployed, does this system run 24×7 year-round, or are parts of it (like test environments or training jobs) only active during business hours or specific exercises where they could be paused/spun down when idle?"* | **`[F-20C]` Operating Lifespan Class:**<br>• `[ ] STATIC_24X7` — Runs 24×7×365 continuously.<br>• `[ ] SPINDOWN_ELIGIBLE` — Non-Prod / Batch / Dev workspaces can hibernate or spin down outside active shifts (flags reclaimable compute for IO). |

---

## Section 1: Mission Criticality, Security Enclave & Continuity (`[AB]`)

*Keep the conversation focused on operational risk, security rules, and outage tolerance.*

| Question & Spoken Conversational Prompt (*Read Aloud*) | 🔒 Facilitator Silent Translation & Coding Rule (*Do Not Read Aloud*) |
| :--- | :--- |
| **1.1 Security Enclave & Multi-Tenancy Rules**<br>*"Within this air-gapped classification enclave, does your security accreditor allow your application to share foundational building services — like a central login portal and central security vault — with other projects on the same network, or do your accreditation rules mandate physically walled-off infrastructure just for your team?"* | **`[F-05]` Cluster & Platform Service Tenancy Mode:**<br>• `[ ] SHARED_DEFAULT` — **Shared Multi-Tenant Enclave** *(Default: Reuses shared `Keycloak P12` & `Vault P11`; `$0` extra control-plane tax).*<br>• `[ ] HYBRID_DEDICATED_SVC` — **Shared Cluster + Dedicated Project Vault/SSO** *(Adds `+24 vCPU / 96 GiB RAM` dedicated quorum tax).*<br>• `[ ] DEDICATED_SINGLE_TENANT` — **Isolated Single-Tenant Cluster + Services** *(Accreditor mandates full physical isolation; adds **`+32 Physical vCPU / +128 GiB RAM / +1.05 TiB Raw Ceph`** quorum tax).* |
| **1.2 Noisy-Neighbor / Dedicated Core Mandate**<br>*"For your live production environment, does your security accreditor require strict dedicated physical processor cores (so no other project shares the same physical CPU chip at the same time), or is standard cloud resource sharing acceptable?"* | **`[F-06]` CPU Reservation & Overcommit Policy:**<br>• `[ ] PROD_1_TO_1` — **1:1 Dedicated Physical Cores in Prod; 2:1 Overcommit in Non-Prod** *(Standard High-Side Defence Default).*<br>• `[ ] ALL_1_TO_1` — **Strict 1:1 Physical Cores in BOTH Prod and Non-Prod.**<br>• `[ ] OVERCOMMIT_2_TO_1` — **2:1 vCPU Overcommit Permitted Everywhere** *(RAM is always 1:1 physical).* |
| **1.3 Outage Impact & Disaster Recovery**<br>*"What happens to your mission if a server rack loses power or undergoes maintenance? Does the app need to stay online seamlessly without interruption? And if the entire primary facility goes dark, do you need a live copy running at a second Disaster Recovery (DR) site?"* | **`[F-07]` Fault Domain & Disaster Recovery Topology:**<br>• `[ ] ZONAL_HA_ONLY` — **Seamless Multi-Rack HA inside Primary Site (`ZONAL_HA`)** *(Min 2–3 nodes + Primary/Standby DB; no secondary DR site).*<br>• `[ ] ZONAL_HA_PLUS_DR` — **`ZONAL_HA` in Primary Site + Active/Warm Disaster Recovery Site** *(**Warning:** Multiplies total physical compute & Ceph storage by `2.0x` across sites + adds DR replication link).*<br>• `[ ] SINGLE_ZONE` — **Single Fault Domain / Non-HA** *(Lab / PoC only; hardware maintenance causes downtime).* |

---

## Section 2: Plain-English Workload Shape & AI Needs (`[AB]`)

*Never ask the customer to choose an NVIDIA MIG slice (`1g.10gb` vs `3g.40gb`) or inference engine (`vLLM` vs `Ollama`). Ask how their users interact with AI and let the translation rules select the hardware.*

| Question & Spoken Conversational Prompt (*Read Aloud*) | 🔒 Facilitator Silent Translation & Coding Rule (*Do Not Read Aloud*) |
| :--- | :--- |
| **2.1 Runtime Form (Containers vs. Legacy Servers)**<br>*"Is this a modern cloud/container application, or does it include existing Windows or Linux server software that needs to be lifted and shifted as full virtual machines?"* | **Platform Runtime Checklist (`[F-10]` to `[F-16]`):**<br>• **`[F-10]` GKE Containers:** `[ ] YES` `[ ] NO`<br>• **`[F-11]` GDC VM Runtime (`VirtualMachine`):** `[ ] YES` `[ ] NO` *(OS: Linux/Win)*<br>• **`[F-12]` Managed PostgreSQL DB (`DBCluster`):** `[ ] YES` `[ ] NO`<br>• **`[F-13]` Object Storage Buckets (`Bucket`):** `[ ] YES` `[ ] NO`<br>• **`[F-14]` Web/API Ingress (`Gateway API`):** `[ ] YES` `[ ] NO`<br>• **`[F-15]` Vault Secret Mgmt:** `[ ] VAULT_SHARED` \| `[ ] VAULT_DEDICATED` \| `[ ] KMS_ONLY`<br>• **`[F-16]` Keycloak SSO:** `[ ] KEYCLOAK_SHARED` \| `[ ] KEYCLOAK_DEDICATED` \| `[ ] NONE` |
| **2.2 AI / Language Model Interaction Mode**<br>*"Does your application use AI or language models? If so, how do people use it:<br>1. Just searching documents or translating/extracting text in the background?<br>2. Live interactive chat, summarization, or coding assistance where users wait on screen for instant answers?<br>3. Feeding massive 500-page reports, full codebases, or raw sensor captures in a single prompt?"* | **`[F-08]` Hardware-Isolated NVIDIA MIG Profile & `[F-09]` AI Engine:**<br>*(Facilitator Rule: Self-hosted open-weights (`Gemma 4`) use NVIDIA MIG on A100/H100 80GB cards. **GDC Native Gemini is delivered via NVIDIA B300 (288GB HBM3e) ONLY** and cannot run on A100/H100/L4. L4 GPUs do NOT support MIG).*<br><br>• **If No AI:**<br>  `[ ] F08 = NO_GPU` & `[ ] F09 = ENGINE_NONE`<br>• **If Background OCR / Document Embedding / Small Task (`<5` users):**<br>  `[ ] F08 = MIG_1G_10GB` *(10GB VRAM slice, A100/H100 80GB, 7/card)* & `[ ] F09 = ENGINE_BATCH_CRON`<br>• **If Light Chat / Small Model (`7B–9B`, `<10` concurrent users):**<br>  `[ ] F08 = MIG_2G_20GB` *(20GB VRAM slice, A100/H100 80GB, 3/card)* & `[ ] F09 = ENGINE_VLLM_PROD`<br>• **If Standard Enterprise RAG / SQL / Code Assist (`Gemma 26B/31B`, `10–25` concurrent streams):**<br>  `[ ] F08 = MIG_3G_40GB` *(40GB VRAM slice, A100/H100 80GB, max 2/card — **mandatory minimum for 26B/31B**)* & `[ ] F09 = ENGINE_VLLM_PROD`<br>• **If High-Concurrency Command Center (`>25` streams) or Fine-Tuning (`P8`):**<br>  `[ ] F08 = MIG_7G_80GB` *(Full 80GB A100/H100 per replica)* & `[ ] F09 = ENGINE_VLLM_PROD`<br>• **If Massive Context (`100k–1M tokens`, 500-page PDFs) or Native Gemini (`P9/P10`):**<br>  `[ ] F08 = NATIVE_GEMINI_ENDPOINT` *(Dedicated **NVIDIA B300 288GB HBM3e ONLY** — cannot use A100/H100/L4)*<br>• **If Single-Tenant Demo / PoC on L4 Workstation/Node:**<br>  `[ ] F08 = L4_24GB_FULL` & `[ ] F09 = ENGINE_OLLAMA_PILOT` |
| **2.3 Day 0 Software & Model Delivery Bundle**<br>*"Roughly how much software — application containers, operating system images, or AI model files — will your team bring across the air gap on Day 0?"* | **`[F-17]` Day 0 Harbor Registry Sideload Bundle (`GiB`):**<br>• Enter customer estimate, OR apply Facilitator Default:<br>  `50 GiB` (Standard App) + `100 GiB` per custom LLM weight bundle = `_______ GiB` |

---

## Section 3: Workload Sizing Capture (Complete Section 3A OR Section 3B)

### SECTION 3A: Direct Technical Specification (`[F-03] = PATH_A`)
*Use ONLY when the customer brings a concrete infrastructure Bill of Materials.*

| Field ID | Infrastructure Metric | Non-Prod (Dev/Test) | Prod (Day 0 Active) | DR Site (If `[F-07]` = DR) |
| :---: | :--- | :--- | :--- | :--- |
| **`[F-18A]`** | **Container `vCPU` (Total Pod Requests)** | `________ vCPU` | `________ vCPU` | `________ vCPU` |
| **`[F-19A]`** | **Container `RAM` (Total Pod Requests in `GiB`)** | `________ GiB` | `________ GiB` | `________ GiB` |
| **`[F-20A]`** | **Virtual Machines (`Total vCPU` / `Total GiB RAM`)** | `____ vCPU` / `____ GiB` | `____ vCPU` / `____ GiB` | `____ vCPU` / `____ GiB` |
| **`[F-21A]`** | **Managed PostgreSQL DB (`Primary vCPU` / `GiB RAM`)**<br>*(Calculator auto-doubles Prod if `ZONAL_HA` is checked)* | `____ vCPU` / `____ GiB` | `____ vCPU` / `____ GiB` | `____ vCPU` / `____ GiB` |
| **`[F-22A]`** | **Day 0 Usable Block Storage (`GiB` — PVCs + VMs + DB)** | `________ GiB` | `________ GiB` | `________ GiB` |
| **`[F-23A]`** | **Day 0 Usable Object Storage (`GiB` — Buckets/Files)** | `________ GiB` | `________ GiB` | `________ GiB` |
| **`[F-24A]`** | **Day 0 GPU / MIG Units Requested** *(Profile in `[F-08]`)* | `________ Units` | `________ Units` | `________ Units` |

---

### SECTION 3B: Plain-English Archetype Cards & T-Shirt Derivation (`[F-03] = PATH_B`)
*Use when the customer describes what their system does in plain English. Show the customer the middle column ("Plain-English One-Line Test") and check the matching blueprint code(s) on the right.*

#### `[F-18B]` Match Customer Description to GDC Blueprint Archetype(s)

| Customer Archetype Name | 🗣️ Plain-English One-Line Test (*Show / Read to Customer*) | 🔒 Facilitator Blueprint Code (`[F-18B]`) |
| :--- | :--- | :--- |
| **Web Portal / Transactional App** | *"Users open a web UI or call an API to view dashboards, submit forms, or update database records."* | `[ ] P1_WEB_3TIER`<br>*(2x `n2-standard-4/8/16` + Postgres HA)* |
| **Legacy Server Lift-and-Shift** | *"It is an existing Windows or Linux server application we need to run as-is without rewriting into containers, connected to a database."* | `[ ] P3_LEGACY_VM_DB`<br>*(GDC VM Runtime + Managed Postgres HA)* |
| **Live Sensor / Event Stream Pipeline** | *"High-volume data arrives continuously from sensors, radars, logs, or message feeds and must be buffered and processed in real time without drops."* | `[ ] P4_KAFKA_EVENT`<br>*(3-Node Kafka Broker Quorum Floor + DB)* |
| **Document Q&A / Intelligence Search (RAG)** | *"Users upload private PDFs, SOPs, SITREPs, or imagery and ask natural-language questions to get cited summaries and answers."* | `[ ] P6_RAG_AGENT`<br>*(Object Bucket + 15m Cron + `pgvector` HA DB)* |
| **Natural Language Database Analyst** | *"Commanders or analysts ask questions in plain English against live operational SQL tables (readiness, logistics, inventory) without writing SQL queries."* | `[ ] P7_SQL_AGENT`<br>*(Read-Only ADK SQL Agent + Postgres HA)* |
| **AI Model Training & MLOps Lab** | *"Data scientists continuously fine-tune or train machine learning models on new air-gapped datasets and push updated models to production."* | `[ ] P8_MLOPS_LOOP`<br>*(Dedicated Training + Serving GPUs + MLflow)* |
| **Interactive Research Notebook / Chat** | *"Researchers organize private source documents into interactive notebooks (NotebookLM style) or use a general multi-turn AI chat interface."* | `[ ] P9_P10_NOTEBOOK_CHAT`<br>*(Sovereign Notebook / Gemini GUI + DB)* |
| **Software Developer Cloud Workspaces** | *"Software engineers need browser-based coding IDEs, container build tools, and an AI coding assistant inside the air gap."* | `[ ] P13_GDC_DEV`<br>*(Scale-to-Zero Dev Pods + 20Gi PVC/dev)* |
| **Shared AI Gateway (Standalone)** | *"We are standing up a central model-serving API gateway to serve multiple downstream applications."* | `[ ] P2_P5_AI_GATEWAY`<br>*(Standalone `gdc_gemma_gw` proxy + GPU pool)* |
| **Integrated Command Center (C2 Synthesis)** | *"An all-in-one operational command center combining live sensor feeds (Kafka), document intelligence search (RAG), and live database analytics (SQL)."* | `[ ] P_MULTI_SYNTHESIS`<br>*(Integrated `P4 + P6 + P7 + P5 + P10 + P12`)* |

#### `[F-19B]` Select Operational Scale (User & Stream Concurrency T-Shirt Size)
* **Spoken Prompt:** *"On a busy day at peak shift handover, roughly how many people are actively clicking, searching, or running queries at the exact same moment?"*
  * `[ ] TIER_S` — **Small (Team / Pilot Scale):** `< 50` active concurrent users \| `10` active developers (`P13`) \| `< 10` simultaneous AI prompt streams \| `< 5,000` events/sec (`P4`).
  * `[ ] TIER_M` — **Medium (Department Production):** `50 – 250` active concurrent users \| `25` active developers (`P13`) \| `10 – 50` simultaneous AI prompt streams \| `5k – 25k` events/sec (`P4`).
  * `[ ] TIER_L` — **Large (Enterprise / Command Scale):** `250 – 1,000+` active concurrent users \| `50+` active developers (`P13`) \| `50 – 150+` simultaneous AI prompt streams \| `25k – 100k+` events/sec (`P4`).

#### `[F-20B]` Non-Production Environment Footprint
* **Spoken Prompt:** *"For your Dev and Test environments, is a half-sized environment sufficient, or do you require a full 100% scale replica of Production for load testing?"*
  * `[ ] NONPROD_HALF` — **Standard Non-Prod (50% of Prod Compute, Single-Zone DB, 1x MIG Slice, 2:1 Overcommit)**
  * `[ ] NONPROD_MIRROR` — **Full 100% Production Scale Mirror**
  * `[ ] NONPROD_NONE` — **No Non-Prod Environment Required on GDC-ag**

---

## Section 4: Data Velocity, Retention & 4-Horizon Growth Roadmap (`[AB]`)

> **Why Facilitators Must Ask This (The 9–18 Month IO Procurement Gate):**  
> Customers think about today's pilot. However, physical GDC-ag expansion racks and GPU chassis take **9 to 18 months** to manufacture, accredit, and install.  
> * If the customer's **12-Month (`T+12m`)** growth crosses a physical rack or storage boundary, the **IO Team must submit the hardware purchase order on Day 0**.

| Question & Spoken Conversational Prompt (*Read Aloud*) | 🔒 Facilitator Silent Translation & Coding Rule (*Do Not Read Aloud*) |
| :--- | :--- |
| **4.1 Starting Data & Daily Ingestion Velocity**<br>*"How much existing historical data (databases, PDFs, imagery) will you load on Day 0? Once live, roughly how many gigabytes of new data (sensor feeds, daily reports, logs) flow into the system every day, and how many years must you keep it online before purging?"* | **`[F-25]` Storage & Retention Parameters:**<br>• **`[F-25.1]` Day 0 Baseline Data (`GiB`):** `_________ GiB` *(Default: derived from Blueprints)*<br>• **`[F-25.2]` Daily Net-New Ingestion (`GiB/day`):** `_________ GiB/day`<br>• **`[F-25.3]` Mandatory Retention Cap (`Days`):** `_________ Days` *(e.g., `365` = 1 yr, `730` = 2 yrs)* |
| **4.2 Backup & Recovery Policy**<br>*"How many days of daily backup snapshots do you need kept locally on the appliance for quick rollback?"* | • **`[F-25.4]` Daily Change Rate (`Decimal`):** `_____` *(Default `0.05` for 5% daily change)*<br>• **`[F-25.5]` Local Snapshot Retention (`Days`):** `_____ Days` *(Default `14` days)*<br>• **`[F-25.6]` Base Full Backups Retained:** `_____` *(Default `2`)*<br>• **`[F-25.7]` DR Replication Window (`Hours`):** `_____ Hours` *(Default `4` hours if DR enabled)* |
| **4.3 Rollout Milestones & Step-Function Growth**<br>*"Looking ahead after Day 0 go-live, how does adoption grow at **6 months**, **12 months**, and **24 months**? For example, do additional squadrons, sites, or data feeds onboard that double or triple your user traffic or AI usage?"* | **4-Stage Compute & GPU Ramp-Up Multipliers (Relative to Day 0 = `1.0x`):**<br>• **T0 (Day 0 Go-Live):** Compute = `1.0x` \| GPU/AI = `1.0x` *(Baseline)*<br>• **`[F-26]` T+6 Months Ramp:**<br>  Compute: `[ ] 1.0x` `[ ] 1.25x` `[ ] 1.5x` `[ ] 2.0x` (Custom: `____x`)<br>  GPU/AI:  `[ ] 1.0x` `[ ] 1.5x`  `[ ] 2.0x` `[ ] 3.0x` (Custom: `____x`)<br>• **`[F-27]` T+12 Months Ramp (**CRITICAL DAY 0 IO ORDER GATE**):**<br>  Compute: `[ ] 1.0x` `[ ] 1.5x`  `[ ] 2.0x` `[ ] 3.0x` (Custom: `____x`)<br>  GPU/AI:  `[ ] 1.0x` `[ ] 2.0x`  `[ ] 3.0x` `[ ] 4.0x` (Custom: `____x`)<br>• **`[F-28]` T+24 Months Ramp (**MONTH 6 IO ORDER GATE**):**<br>  Compute: `[ ] 1.5x` `[ ] 2.0x`  `[ ] 3.0x` `[ ] 5.0x` (Custom: `____x`)<br>  GPU/AI:  `[ ] 1.5x` `[ ] 2.0x`  `[ ] 4.0x` `[ ] 6.0x` (Custom: `____x`) |

---

## Section 5: Facilitator Post-Interview Close-Out Checklist (Not With Customer)

Before transcribing the codes into Section 6, perform these 4 facilitator sanity checks:
1. **De-Duplication Check:** If the customer checked multiple blueprints in `[F-18B]` (e.g., `P6_RAG_AGENT` + `P7_SQL_AGENT`), verify whether their data can live in a **single consolidated PostgreSQL HA cluster** (`CONSOLIDATED`, default in calculator) rather than provisioning separate database clusters.
2. **MIG VRAM & B300 Hardware SKU Guardrail Check:**
   * If the workload requires **GDC Native Gemini**, set **`[F-08] = NATIVE_GEMINI_ENDPOINT`** (**NVIDIA B300 `288GB HBM3e` Exclusive**).
   * If the workload uses self-hosted `Gemma 26B/27B/31B` (`P6_RAG_AGENT`, `P7_SQL_AGENT`) and you selected `MIG_1G_10GB` or `MIG_2G_20GB`, **override `[F-08]` to `MIG_3G_40GB`** (`40GB` VRAM slice on A100/H100).
3. **Storage Multiplier Reality Check:** Warn the IO team if `[F-07] = ZONAL_HA_PLUS_DR` is selected with high daily ingestion (`>20 GiB/day`). Active DR + 14-day local snapshots + 3x Ceph replication creates a **~22x–26x Raw Physical Disk Multiplier** relative to primary usable data.
4. **Confidence Buffer Check:** If `[F-04B] = ESTIMATED`, note that the calculator adds a `+25%` safety margin to physical core and storage procurement recommendations.

---

## Section 6: Blank Tear-Off Transcription Sheet & Calculator Handoff Instructions

> **IMPORTANT — THIS SECTION IS INTENTIONALLY BLANK FOR YOUR INTERVIEW:**
> When you print this guide for a paper-only SCIF interview, write your circled codes into **Section 6A** below, tear off this single sheet when leaving the SCIF, and follow **Section 6B** to pass the data into the calculator.
> *(Looking for the pre-populated `tactical-c2-prod` example? See **Section 7** below.)*

### Section 6A: Blank Printable Tear-Off Worksheet (Fill In With Pen During/After Interview)

| Code | Field Name | Write Your Captured Value Here | Allowed Codes / Format |
| :--- | :--- | :--- | :--- |
| **`F01_PROJECT_ID`** | Project / Namespace ID | `[______________________________]` | Lowercase slug, e.g. `mission-alpha-prod` |
| **`F03_ENTRY_PATH`** | Sizing Entry Track | `[______________________________]` | `PATH_B` (Blueprints) \| `PATH_A` (Direct BOM) |
| **`F04B_CONFIDENCE_LEVEL`** | Data Confidence Class | `[______________________________]` | `MEASURED` \| `BENCHMARKED` \| `DERIVED` \| `ESTIMATED` |
| **`F05_TENANCY_MODE`** | Enclave Sharing Mode | `[______________________________]` | `SHARED_DEFAULT` \| `HYBRID_DEDICATED_SVC` \| `DEDICATED_SINGLE_TENANT` |
| **`F06_OVERCOMMIT_POLICY`** | CPU Overcommit Policy | `[______________________________]` | `PROD_1_TO_1` \| `ALL_1_TO_1` \| `OVERCOMMIT_2_TO_1` |
| **`F07_HA_DR_TOPOLOGY`** | Fault Domain & DR | `[______________________________]` | `ZONAL_HA_ONLY` \| `ZONAL_HA_PLUS_DR` \| `SINGLE_ZONE` |
| **`F08_GPU_MIG_PROFILE`** | GPU Hardware & MIG | `[______________________________]` | `NO_GPU` \| `MIG_1G_10GB` \| `MIG_2G_20GB` \| `MIG_3G_40GB` \| `MIG_7G_80GB` \| `L4_24GB_FULL` \| `NATIVE_GEMINI_ENDPOINT` *(B300 Only)* |
| **`F09_INFERENCE_ENGINE`** | AI Serving Engine | `[______________________________]` | `ENGINE_VLLM_PROD` \| `ENGINE_GEMINI_MANAGED` \| `ENGINE_OLLAMA_PILOT` |
| **`F17_HARBOR_BUNDLE_GIB`** | Day 0 Harbor Bundle | `[_______________________ GiB   ]` | Number in GiB (e.g. `120`) |
| **`F18B_BLUEPRINT_PATTERNS`** | Selected Blueprints | `[______________________________]` | Comma-separated codes, e.g. `P4_KAFKA_EVENT, P6_RAG_AGENT, P7_SQL_AGENT` |
| **`F19B_TSHIRT_TIER`** | User Concurrency Tier | `[______________________________]` | `TIER_S` \| `TIER_M` \| `TIER_L` \| `TIER_XL` |
| **`F20B_NONPROD_POLICY`** | Non-Prod Staging Size | `[______________________________]` | `NONPROD_HALF` \| `NONPROD_MIRROR` \| `NONPROD_NONE` |
| **`F20C_LIFESPAN_CLASS`** | Operating Lifespan | `[______________________________]` | `STATIC_24X7` \| `SPINDOWN_ELIGIBLE` |
| **`F25.daily_ingest_gib`** | Daily Data Ingest | `[__________________ GiB / day  ]` | Number in GiB/day (e.g. `25`) |
| **`F26_RAMP_M6_COMPUTE_GPU`** | Month 6 Growth (`[CPU, GPU]`) | `[ CPU: _____x  ,  GPU: _____x  ]` | e.g. `[1.25, 1.5]` |
| **`F27_RAMP_M12_COMPUTE_GPU`** | Month 12 Gate (`[CPU, GPU]`) | `[ CPU: _____x  ,  GPU: _____x  ]` | e.g. `[2.0, 2.0]` *(Drives Day 0 Hardware PO)* |
| **`F28_RAMP_M24_COMPUTE_GPU`** | Month 24 Full (`[CPU, GPU]`) | `[ CPU: _____x  ,  GPU: _____x  ]` | e.g. `[3.0, 4.0]` |
| **`IO_AVAILABLE_RACK_HEADROOM`** | Existing Floor Headroom | `[ ___c / ___Gi / ___TiB / ___GPU ]` | Physical Cores / RAM GiB / Raw Ceph TiB / Physical GPUs |

---

### Section 6B: How to Pass Your Tear-Off Sheet into the Calculator (Pick Any of 3 Ways)

Once you are at a computer outside the SCIF:

* **Way 1 — Use the HTML Interview Collator (`gdc_ag_interview_form.html`) [Easiest]:**
  1. Open `gdc_ag_interview_form.html` in your browser.
  2. Click the **"⚡ Transcribing from the Offline Paper Questionnaire?"** bar in Domain 0 to paste your comma-separated blueprint codes (`F18B`), and select your dropdown values from Section 6A.
  3. Click **`🚀 Pass to Web Calculator`** (to open `gdc_ag_sizing_calculator.html` pre-populated) **OR** click **`💾 Download Intake JSON`** (to save `<project>_intake.json`).

* **Way 2 — Direct Copy-Paste into the Web Calculator (`Import / Export [F-01]–[F-28]` Modal):**
  1. Copy the template below (either as JSON or `KEY: VALUE` lines), fill in the values from your Section 6A worksheet, open `gdc_ag_sizing_calculator.html`, click the blue **`Import / Export [F-01]–[F-28]`** button in the top bar, paste, and click **Apply**:
     ```json
     {
       "F01_PROJECT_ID": "REPLACE_WITH_PROJECT_ID",
       "F03_ENTRY_PATH": "PATH_B",
       "F04B_CONFIDENCE_LEVEL": "DERIVED",
       "F05_TENANCY_MODE": "SHARED_DEFAULT",
       "F06_OVERCOMMIT_POLICY": "PROD_1_TO_1",
       "F07_HA_DR_TOPOLOGY": "ZONAL_HA_PLUS_DR",
       "F08_GPU_MIG_PROFILE": "MIG_3G_40GB",
       "F09_INFERENCE_ENGINE": "ENGINE_VLLM_PROD",
       "F17_HARBOR_BUNDLE_GIB": 120,
       "F18B_BLUEPRINT_PATTERNS": ["P6_RAG_AGENT"],
       "F19B_TSHIRT_TIER": "TIER_M",
       "F20B_NONPROD_POLICY": "NONPROD_HALF",
       "F20C_LIFESPAN_CLASS": "STATIC_24X7",
       "F25_STORAGE_PARAMS": { "daily_ingest_gib": 25 },
       "F26_RAMP_M6_COMPUTE_GPU": [1.25, 1.5],
       "F27_RAMP_M12_COMPUTE_GPU": [2.0, 2.0],
       "F28_RAMP_M24_COMPUTE_GPU": [3.0, 4.0],
       "IO_AVAILABLE_RACK_HEADROOM": {
         "physical_vcpu": 96,
         "physical_ram_gib": 384,
         "raw_ceph_tib": 80,
         "physical_gpu_cards": 3
       }
     }
     ```

* **Way 3 — Pass `.json` File to the Offline Python CLI (`gdc_ag_sizing_cli.py`):**
  Save the JSON block above as `my_project_intake.json` and run:
  ```bash
  python3 docs/capacity-sizing/gdc_ag_sizing_cli.py --input my_project_intake.json --yaml-out cluster.yaml
  ```

---

## Section 7: Completed Reference Example (`tactical-c2-prod` — J3 Operations Directorate)

*This section shows a **completed, pre-populated example** of how a Facilitator conducts an interview with a non-technical mission owner (`J3 Operations Directorate`), translates their answers into the Section 6 ledger (`customer_intake_example.json`), and feeds it into the calculator.*

### Step 1: Scenario & Plain-English Offline Interview (Inside the SCIF)
* **Customer Spoken Need:** *"We need an air-gapped system to ingest continuous tactical sensor feeds (`25 GiB/day`), index daily SITREP PDFs so analysts can ask questions and get summaries, and let commanders ask plain-English questions about unit readiness tables. Around 100 people will use it at shift change. It can share the enclave login/vault, but it must stay up if a rack fails and have a live copy at our DR site."*
* **Completed Reference Ledger (`docs/capacity-sizing/customer_intake_example.json`):**
  ```json
  {
    "F01_PROJECT_ID": "tactical-c2-prod",
    "F03_ENTRY_PATH": "PATH_B",
    "F04B_CONFIDENCE_LEVEL": "DERIVED",
    "F05_TENANCY_MODE": "SHARED_DEFAULT",
    "F06_OVERCOMMIT_POLICY": "PROD_1_TO_1",
    "F07_HA_DR_TOPOLOGY": "ZONAL_HA_PLUS_DR",
    "F08_GPU_MIG_PROFILE": "MIG_3G_40GB",
    "F09_INFERENCE_ENGINE": "ENGINE_VLLM_PROD",
    "F17_HARBOR_BUNDLE_GIB": 120,
    "F18B_BLUEPRINT_PATTERNS": ["P4_KAFKA_EVENT", "P6_RAG_AGENT", "P7_SQL_AGENT"],
    "F19B_TSHIRT_TIER": "TIER_M",
    "F20B_NONPROD_POLICY": "NONPROD_HALF",
    "F20C_LIFESPAN_CLASS": "STATIC_24X7",
    "F25_STORAGE_PARAMS": { "daily_ingest_gib": 25 },
    "F26_RAMP_M6_COMPUTE_GPU": [1.25, 1.5],
    "F27_RAMP_M12_COMPUTE_GPU": [2.0, 2.0],
    "F28_RAMP_M24_COMPUTE_GPU": [3.0, 4.0],
    "IO_AVAILABLE_RACK_HEADROOM": {
      "physical_vcpu": 96,
      "physical_ram_gib": 384,
      "raw_ceph_tib": 80,
      "physical_gpu_cards": 3
    }
  }
  ```

### Step 2: Feeding the Completed Example into the Calculator

```bash
python3 docs/capacity-sizing/gdc_ag_sizing_cli.py --input docs/capacity-sizing/customer_intake_example.json
```

#### Calculator Structured Output:
```json
{
  "project_id": "tactical-c2-prod",
  "tenancy_mode": "SHARED_DEFAULT",
  "confidence_level": "DERIVED (+10% Contingency)",
  "lifespan_class": "STATIC_24X7",
  "isolation_tax_vcpu_ram": [0.0, 0.0],
  "mig_profile": "nvidia.com/mig-3g.40gb",
  "advisories": [],
  "horizons": [
    {
      "horizon": "T0 (Day 0)",
      "nodes_n2_standard_8": 12,
      "physical_vcpu": 96,
      "physical_ram_gib": 384,
      "usable_tib": 4.92,
      "raw_ceph_tib": 54.58,
      "mig_slices": 5,
      "physical_gpu_cards": 3
    },
    {
      "horizon": "T+6m",
      "nodes_n2_standard_8": 13,
      "physical_vcpu": 104,
      "physical_ram_gib": 416,
      "usable_tib": 15.46,
      "raw_ceph_tib": 171.63,
      "mig_slices": 7,
      "physical_gpu_cards": 4
    },
    {
      "horizon": "T+12m (Day 0 IO Order Gate)",
      "nodes_n2_standard_8": 16,
      "physical_vcpu": 128,
      "physical_ram_gib": 512,
      "usable_tib": 26.30,
      "raw_ceph_tib": 291.90,
      "mig_slices": 9,
      "physical_gpu_cards": 5
    },
    {
      "horizon": "T+24m (Month 6 IO Order Gate)",
      "nodes_n2_standard_8": 20,
      "physical_vcpu": 160,
      "physical_ram_gib": 640,
      "usable_tib": 47.68,
      "raw_ceph_tib": 529.22,
      "mig_slices": 17,
      "physical_gpu_cards": 9
    }
  ]
}
```

---

### Step 3: How the IO Team Translates Output Data Points into Hardware Actions

Suppose the IO Team currently has **Unallocated Physical Rack Headroom** of **`96 Physical Cores`**, **`384 GiB RAM`**, **`80.0 TiB Raw Ceph Storage`**, and **`3 Physical NVIDIA A100/H100 (80GB) GPUs`**:

| IO Operational Question | Calculator Data Point Used | IO Action & Technical Justification |
| :--- | :--- | :--- |
| **1. Can Day 0 (`T0`) resources be allocated immediately from existing racks?** | • `T0 Physical vCPU = 96` (`12` nodes)<br>• `T0 Physical RAM = 384 GiB`<br>• `T0 Raw Ceph = 54.58 TiB`<br>• `T0 Physical GPUs = 3` (`5x 3g.40gb` slices) | **APPROVE DAY 0 ALLOCATION:**<br>• All Day 0 metrics fit within current unallocated rack headroom (`96c / 384Gi / 80TiB / 3 GPUs`).<br>• **Why `500 GiB` baseline becomes `54.58 TiB` Raw Ceph:** `ZONAL_HA_PLUS_DR` mirrors data across Primary + DR sites (`×2`), local backups add `2.70x` (`14d × 0.05 + 2 base`), and Ceph enforces `3x` physical disk replication (`2 × 3.70 × 3 = 22.2x` raw-to-baseline ratio). |
| **2. Does IO need to order additional hardware on Day 0?** | **Compare `T+12m` vs Available Headroom:**<br>• `T+12m vCPU = 128` (*Deficit: `+32 vCPU`*)<br>• `T+12m Raw Ceph = 291.90 TiB` (*Deficit: `+211.90 TiB`*)<br>• `T+12m GPUs = 5` (*Deficit: `+2 GPUs`*) | **TRIGGER EMERGENCY DAY 0 HARDWARE PURCHASE ORDER:**<br>• Because physical rack/GPU delivery and site accreditation require **9 to 18 months**, waiting until storage runs out at Month 5 (`171.63 TiB` vs `80 TiB` available) would cause an 8-month operational outage.<br>• **Day 0 Purchase Order:** Order **`+4 Compute Nodes (`32 vCPU / 128 GiB`)`**, **`+212+ TiB Raw Ceph Storage`**, and **`+2 Physical NVIDIA A100/H100 (80GB) GPUs`** immediately on Day 0. |
| **3. What extra resources are required when for the ramp-up plan?** | **Compare `T+24m` vs `T+12m`:**<br>• `T+24m vCPU = 160` (*Delta: `+32 vCPU`*)<br>• `T+24m Raw Ceph = 529.22 TiB` (*Delta: `+237.32 TiB`*)<br>• `T+24m GPUs = 9` (*Delta: `+4 GPUs`*) | **SCHEDULE MONTH 6 PURCHASE ORDER (FOR MONTH 18 RACKING):**<br>• Issue a second hardware procurement order at **Month 6 (`T+6m`)** for **`+4 Compute Nodes`**, **`+238 TiB Raw Ceph`**, and **`+4 Physical GPUs`** so they arrive and complete accreditation before Month 18–24 ramp-up. |
