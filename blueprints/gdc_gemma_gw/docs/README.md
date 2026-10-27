Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Gemma 4 Dedicated Inference Gateway — Documentation Hub

All documentation for the **Gemma 4 Dedicated Inference Gateway (`gdc_gemma_gw`)**, **Gemma Client & Joint Intelligence Console (`gemma-client`)**, and **Envoy `InferencePool` (`blueprints/envoy-inference-pool`)** is consolidated in this `docs/` directory and organized into four subfolders by purpose.

---

## Directory Structure

```text
docs/
├── README.md                                              # Master Documentation Hub (this file)
├── tutorials/                                             # Step-by-Step End-to-End Tutorials & Interactive Demo Guides
│   ├── ai_enabled_e2e_gdc_production_iac_guide.md         # Full AI-Enabled Blueprint E2E Deployment on GDC-ag (gdc-iac-org)
│   ├── gui_demo_walkthrough_and_prompts.md                # Interactive Browser Walkthrough & Copy-Paste Demo Prompts (Ports 8080–8084)
│   ├── e2e_zero_tweak_validation_runbook.md               # Automated IO/AO Upgrade & E2E Functional Verification Runbook
├── architecture/                                          # Reference Architectures, Routing Design, Sizing & Security
│   ├── Solution-Reference-Implementation-Gemma4-Inference-Gateway.md
│   ├── Solution-Reference-Implementation-Gemma4-Client-Application.md
│   ├── Solution-Reference-Implementation-Multi-Blueprint-Intelligence-Synthesis.md
│   ├── model_routing_architecture.md
│   ├── resource-sizing-validation.md
│   ├── security-performance-guide.md
│   └── roadmap.md
├── operations/                                            # Packaging, Model Serving, OIDC, Day-2 Admin & Troubleshooting
│   ├── sideloading-guide.md
│   ├── vllm-serving-guide.md
│   ├── keycloak_integration_guide.md
│   ├── admin-dashboard-guide.md
│   ├── operational-administration-and-data-ingestion-guide.md
│   └── faq-troubleshooting.md
└── testing/                                               # Testing Strategies, Automated QA & Air-Gap Validation
    ├── automated-testing-guide.md
    ├── testing-methodology.md
```

---

## 1. Tutorials & Interactive Walkthroughs (`docs/tutorials/`)

| Guide | Target Environment | Description |
| :--- | :--- | :--- |
| **[AI-Enabled Blueprint E2E Guide (GDC-ag Production IaC)](./tutorials/ai_enabled_e2e_gdc_production_iac_guide.md)** | GDC Air-Gapped (`gdc-iac-org`) | Declarative multi-stage Helmfile (`0-bootstrap` $\rightarrow$ `5-workload-factory`) production deployment on GDC-ag. |
| **[GUI Functional Walkthrough & Live Demo Playbook](./tutorials/gui_demo_walkthrough_and_prompts.md)** | Both (GCP & GDC-ag) | Interactive browser walkthrough across all 5 ports (`8080`–`8084`) with copy-pasteable prompts to trigger `26B MoE` vs. `31B Dense` routing, RAG citations, Text-to-SQL, and `gdc-dev` IDE Swarm. |
| **[Zero-Tweak E2E Validation & IO/AO Upgrade Runbook](./tutorials/e2e_zero_tweak_validation_runbook.md)** | Both (GCP & GDC-ag) | Automated 17-check (`verify-e2e-gcp-staging.py`) and 20-check (`verify-e2e-gdc-ag.py`) verification suites for Infrastructure Operators (IO) and Application Operators (AO). |

---

## 2. Architecture & Design References (`docs/architecture/`)

| Document | Focus Area |
| :--- | :--- |
| **[Gemma 4 Inference Gateway Reference Manual](./architecture/Solution-Reference-Implementation-Gemma4-Inference-Gateway.md)** | Master architecture for the FastAPI complexity classifier, OpenAI `/v1` proxy, and dual-engine (`vLLM` / `Ollama`) serving layer. |
| **[Gemma 4 Client Application Reference Manual](./architecture/Solution-Reference-Implementation-Gemma4-Client-Application.md)** | Master architecture for the React + FastAPI multi-user chat and document grounding client, PostgreSQL schema, and Object Storage integration. |
| **[Multi-Blueprint Intelligence Synthesis Reference](./architecture/Solution-Reference-Implementation-Multi-Blueprint-Intelligence-Synthesis.md)** | Cross-blueprint integration architecture combining Kafka (`P4`), RAG (`P6`), SQL (`P7`), Keycloak (`P12`), and `gdc-dev` (`P13`). |
| **[Model Routing & Complexity Classifier Architecture](./architecture/model_routing_architecture.md)** | Deep dive into how prompts are classified and routed between Tier 1 (`gemma4:26b` MoE) and Tier 2 (`gemma4:31b` Dense), including system-role flattening. |
| **[Resource Sizing & Capacity Validation](./architecture/resource-sizing-validation.md)** | Audited NVIDIA H100/H200 GPU, vCPU, RAM, and SAN PVC T-shirt sizing benchmarks for Small (600 RPM), Medium (3,000 RPM), and Large (6,000 RPM) deployments. |
| **[Security & Performance Hardening Guide](./architecture/security-performance-guide.md)** | Remediation architecture for OIDC JWT verification, non-root containers, HTTPX connection pooling, and atomic state synchronization (`GATEWAY_STATE_FILE`). |
| **[Engineering Roadmap](./architecture/roadmap.md)** | Chronological development phases and completed capabilities ledger. |

---

## 3. Operations, Packaging & Troubleshooting (`docs/operations/`)

| Runbook | Operational Task |
| :--- | :--- |
| **[Air-Gapped Packaging & Sideloading Guide](./operations/sideloading-guide.md)** | Packaging OCI container archives, staging gated HuggingFace weights, and ingesting bundles into GDC Managed Harbor offline. |
| **[Production vLLM Serving & Envoy InferencePool Guide](./operations/vllm-serving-guide.md)** | Deploying unquantized Gemma 4 weights on `standard-rwx` PVCs with vLLM and optional Envoy `InferencePool` (`epp`) KV-cache-aware pod picking. |
| **[Keycloak OIDC Integration Guide](./operations/keycloak_integration_guide.md)** | Configuring Keycloak realms (`gdc-rag-realm`), PKCE (`S256`), JWKS RS256 validation, and Gateway API `HTTPRoute` exposure. |
| **[Admin Dashboard Operator Guide](./operations/admin-dashboard-guide.md)** | Using the Port `8080` Gateway Control Plane to monitor GPU/VRAM telemetry, tune sampling parameters, and enforce user blocklists. |
| **[Day-2 Operational Admin & Data Ingestion Guide](./operations/operational-administration-and-data-ingestion-guide.md)** | Day-2 runbook for ingesting new RAG SITREPs, managing PostgreSQL readiness tables, and operating Kafka telemetry streams. |
| **[FAQ & Operational Troubleshooting](./operations/faq-troubleshooting.md)** | Solutions for GKE GPU stock exhaustion, PVC finalizer deadlocks, Cloud Workstation proxy cookies, Workload Identity, and exec-less container diagnostics. |

---

## 4. Testing & Quality Assurance (`docs/testing/`)

| Guide | Scope |
| :--- | :--- |
| **[Automated Testing & QA Guide](./testing/automated-testing-guide.md)** | Running unit tests, integration tests (`pytest`), and streaming load tests (`Locust`). |
| **[GDC Air-Gapped Testing Methodology](./testing/testing-methodology.md)** | Terminal-only in-cluster smoke tests and KubeDNS verification for disconnected GDC-ag racks. |
