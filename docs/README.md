Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GDC-ag Resilient Architecture Blueprints — Documentation Hub

Welcome to the master documentation index for **GDC-blueprints**. All documentation is consolidated under `docs/` by topic so architects, Infrastructure Operators (`IO`), Application Operators (`AO`), and developers can quickly locate the right guide.

---

## Directory Structure (`docs/`)

```text
docs/
├── README.md                                              # Master Documentation Hub (this file)
├── tutorials/                                             # Step-by-Step E2E Tutorials & Interactive Demo Playbooks
│   ├── ai_enabled_e2e_gdc_production_iac_guide.md         # Full AI-Enabled Blueprint E2E Deployment on GDC-ag (gdc-iac-org)
│   ├── gui_demo_walkthrough_and_prompts.md                # Interactive Browser Walkthrough & Copy-Paste Demo Prompts (Ports 8080–8084)
│   └── e2e_zero_tweak_validation_runbook.md               # Automated IO/AO 17-Test Upgrade & Functional Verification Runbook
├── implementation-guides/                                 # Solution Reference Implementations (Patterns 1–14 & Synthesis)
│   ├── Solution-Reference-Implementation-Multi-Blueprint-Intelligence-Synthesis.md
│   ├── Solution-Reference-Implementation-Pattern-1-Resilient-3-Tier-Web-Application.md
│   ├── Solution-Reference-Implementation-Pattern-2-High-Availability-ML-AI-Inference.md
│   ├── Solution-Reference-Implementation-Pattern-3-Legacy-VM-Modern-Database.md
│   ├── Solution-Reference-Implementation-Pattern-4-Event-Driven-Pipeline-Kafka.md
│   ├── Solution-Reference-Implementation-Pattern-5-Resilient-Hybrid-LLM-Gateway.md
│   ├── Solution-Reference-Implementation-Pattern-6-Resilient-RAG-Agent.md
│   ├── Solution-Reference-Implementation-Pattern-7-Agentic-Data-Analyst.md
│   ├── Solution-Reference-Implementation-Pattern-8-Closed-Loop-MLOps.md
│   ├── Solution-Reference-Implementation-Pattern-9-Sovereign-Notebook.md
│   ├── Solution-Reference-Implementation-Pattern-10-Gemini-GUI-Chatbot.md
│   ├── Solution-Reference-Implementation-Pattern-11-Resilient-Secret-Management-Vault.md
│   ├── Solution-Reference-Implementation-Pattern-12-Identity-Keycloak.md
│   ├── Solution-Reference-Implementation-Pattern-13-GDC-Dev.md
│   ├── Solution-Reference-Implementation-Pattern-14-Antigravity-Dev.md
│   └── Solution-Reference-Implementation-Template-Pattern.md
├── architecture/                                          # Cross-Pattern Architecture, Security & Governance
│   ├── patterns_def.md                                    # Blueprint Pattern Catalogue & Architectural Definitions
│   ├── integration_plan.md                                # Cross-Pattern Integration Architecture (P4, P6, P7, P11, P12, P13, Gemma GW)
│   ├── security-vulnerability-management.md               # Container Hardening & Vulnerability Management
│   └── dependabot-remediation-status.md                   # CVE & Supply Chain Dependency Remediation Ledger
├── operations/                                            # Packaging, 3-Step Replication, Day-2 Admin & Integrations
│   ├── script_usage_guide.md                              # Unified Script Usage & 3-Step Production Replication Guide
│   ├── gdc_airgap_guide.md                                # Air-Gapped Packaging, Transfer & Harbor Mirroring Guide
│   ├── operational-administration-and-data-ingestion-guide.md # Day-2 Admin Console & Data Ingestion Guide
│   ├── customizing-developer-workspace-images.md          # Customizing Pattern 13 (gdc-dev) Developer Workspace Images
│   ├── keycloak_integration_guide.md                      # Pattern 12 Keycloak OIDC SSO Integration Guide
│   ├── vault_integration_guide.md                         # Pattern 11 HashiCorp Vault Secret Management Guide
│   ├── envoy_gateway_guide.md                             # Envoy Gateway & Inference Pool Guide
│   └── updating_ollama.md                                 # Updating Ollama & Sideloaded Model Weights
└── testing/                                               # Testing, GCP Stepping-Stone Emulation & Developer Guides
    ├── testing_plan.md                                    # Blueprint Testing & Validation Plan
    ├── how-to-add-pattern.md                              # Authoring & Onboarding a New Blueprint Pattern
    ├── potential-gotchas-on-gdc-ag.md                     # GDC-ag Operational Gotchas & Best Practices
    ├── verification-results.md                            # Pattern Verification & Benchmark Ledger
    └── lessons-learned.md                                 # Engineering Retrospectives & Lessons Learned
```

---

## 1. End-to-End Tutorials & Interactive Demo Runbooks (`docs/tutorials/`)

| Guide | Target Environment | Description |
| :--- | :--- | :--- |
| **[AI-Enabled Blueprint E2E Deployment (GDC-ag Production)](./tutorials/ai_enabled_e2e_gdc_production_iac_guide.md)** | GDC-ag Production (`gdc-iac-org`) | Production deployment runbook across Stage 1 (`1-project-factory`), Stage 2 (`2-resources`), Stage 3 (`3-clusters`), and Stage 5 (`5-workload-factory`). |
| **[GUI Demo Walkthrough & Prompts](./tutorials/gui_demo_walkthrough_and_prompts.md)** | Both (Ports `8080`–`8084`) | Interactive browser walkthrough and copy-paste prompts across all 5 ports (`8080` Control Plane, `8081`/`8082` Client, `8083`/`8084` `gdc-dev`). |
| **[E2E Zero-Tweak Validation Runbook](./tutorials/e2e_zero_tweak_validation_runbook.md)** | Both (`IO` & `AO`) | Automated 17-test functional verification suite (`verify-e2e-gcp-staging.py` and `verify-e2e-gdc-ag.py`). |

---

## 2. Solution Reference Implementations (`docs/implementation-guides/`)

| Pattern | Guide |
| :--- | :--- |
| **Multi-Blueprint Synthesis** | [Multi-Blueprint Intelligence Synthesis (`P4` + `P6` + `P7` + `P11` + `P12` + `P13` + `gdc_gemma_gw`)](./implementation-guides/Solution-Reference-Implementation-Multi-Blueprint-Intelligence-Synthesis.md) |
| **Pattern 1** | [Resilient 3-Tier Web Application](./implementation-guides/Solution-Reference-Implementation-Pattern-1-Resilient-3-Tier-Web-Application.md) |
| **Pattern 2** | [High-Availability ML/AI Inference](./implementation-guides/Solution-Reference-Implementation-Pattern-2-High-Availability-ML-AI-Inference.md) |
| **Pattern 3** | [Legacy VM & Modern Managed PostgreSQL Database](./implementation-guides/Solution-Reference-Implementation-Pattern-3-Legacy-VM-Modern-Database.md) |
| **Pattern 4** | [Event-Driven Pipeline (Apache Kafka KRaft)](./implementation-guides/Solution-Reference-Implementation-Pattern-4-Event-Driven-Pipeline-Kafka.md) |
| **Pattern 5** | [Resilient Hybrid LLM Gateway (Deprecated — see `gdc_gemma_gw`)](./implementation-guides/Solution-Reference-Implementation-Pattern-5-Resilient-Hybrid-LLM-Gateway.md) |
| **Pattern 6** | [Resilient RAG Agent (`pgvector` + S3/GCS + Gemma 4)](./implementation-guides/Solution-Reference-Implementation-Pattern-6-Resilient-RAG-Agent.md) |
| **Pattern 7** | [Agentic Data Analyst (Text-to-SQL with Security Gate)](./implementation-guides/Solution-Reference-Implementation-Pattern-7-Agentic-Data-Analyst.md) |
| **Pattern 8** | [Closed-Loop MLOps (MLflow + Kubeflow)](./implementation-guides/Solution-Reference-Implementation-Pattern-8-Closed-Loop-MLOps.md) |
| **Pattern 9** | [Sovereign Notebook](./implementation-guides/Solution-Reference-Implementation-Pattern-9-Sovereign-Notebook.md) |
| **Pattern 10** | [Gemini / Gemma Conversational GUI Chatbot](./implementation-guides/Solution-Reference-Implementation-Pattern-10-Gemini-GUI-Chatbot.md) |
| **Pattern 11** | [Resilient Secret Management (HashiCorp Vault + KMS Auto-Unseal)](./implementation-guides/Solution-Reference-Implementation-Pattern-11-Resilient-Secret-Management-Vault.md) |
| **Pattern 12** | [Centralized Identity & Access Management (Keycloak OIDC SSO)](./implementation-guides/Solution-Reference-Implementation-Pattern-12-Identity-Keycloak.md) |
| **Pattern 13** | [Resilient GDC Developer Environment (`gdc-dev` + 3-Agent AI Swarm)](./implementation-guides/Solution-Reference-Implementation-Pattern-13-GDC-Dev.md) |
| **Pattern 14** | [GDC-ag Antigravity SDK & Integrated Notebooks Developer IDE Platform (`p14-antigravity-dev`)](./implementation-guides/Solution-Reference-Implementation-Pattern-14-Antigravity-Dev.md) |
| **Template** | [Blueprint Reference Implementation Template](./implementation-guides/Solution-Reference-Implementation-Template-Pattern.md) |

---

## 3. Architecture, Security & Governance (`docs/architecture/`)

| Document | Focus Area |
| :--- | :--- |
| **[Blueprint Pattern Definitions](./architecture/patterns_def.md)** | Architectural taxonomy, GDC-ag service dependencies, and T-shirt sizing across all patterns. |
| **[Cross-Pattern Integration Plan](./architecture/integration_plan.md)** | How Identity (`P12`), Secrets (`P11`), Streaming (`P4`), RAG (`P6`), SQL (`P7`), IDE (`P13`), and `gdc_gemma_gw` interconnect. |
| **[Security & Vulnerability Management](./architecture/security-vulnerability-management.md)** | Rootless container hardening, SQL security gates, OIDC JWT verification, and dependency pinning. |
| **[Dependabot & CVE Remediation Status](./architecture/dependabot-remediation-status.md)** | Supply-chain CVE tracking and remediation ledger across Python, Node.js, and base container images. |

---

## 4. Packaging, 3-Step Replication & Operations (`docs/operations/`)

| Document | Focus Area |
| :--- | :--- |
| **[Unified Script Usage & 3-Step Replication Guide](./operations/script_usage_guide.md)** | Complete CLI reference including the 3-step `stage_production_assets.py` + `rsync --delete` pipeline to `gdc-iac-org`. |
| **[Air-Gap Packaging & Delivery Guide](./operations/gdc_airgap_guide.md)** | Building, exporting, transferring, and loading offline `.tar` bundles into GDC Managed Harbor. |
| **[Operational Administration & Data Ingestion Guide](./operations/operational-administration-and-data-ingestion-guide.md)** | Day-2 operational runbook for Kafka telemetry simulation, RAG document ingestion, and PostgreSQL seeding. |
| **[Customizing Developer Workspace Images](./operations/customizing-developer-workspace-images.md)** | Extending Pattern 13 (`gdc-dev`) workspace containers with custom compilers, SDKs, and internal CA certs. |
| **[Keycloak OIDC Integration Guide](./operations/keycloak_integration_guide.md)** | Configuring Keycloak realms, OIDC PKCE clients, and JWT validation across blueprints. |
| **[HashiCorp Vault Integration Guide](./operations/vault_integration_guide.md)** | Integrating dynamic Vault secrets and KMS auto-unseal with application workloads. |
| **[Envoy Gateway & Inference Pool Guide](./operations/envoy_gateway_guide.md)** | Configuring Kubernetes Gateway API (`HTTPRoute`) and Envoy AI Gateway `InferencePool` routing. |
| **[Updating Ollama & Model Weights](./operations/updating_ollama.md)** | Updating Ollama base images and sideloaded LLM model weights in disconnected clusters. |

---

## 5. Testing, Emulation & Developer Guidance (`docs/testing/`)

| Document | Focus Area |
| :--- | :--- |
| **[Testing & Validation Plan](./testing/testing_plan.md)** | Multi-stage unit, integration, and live cluster smoke-testing methodology. |
| **[How to Add a New Blueprint Pattern](./testing/how-to-add-pattern.md)** | Developer checklist for scaffolding `manifests/`, `chart/`, `test/`, and `stage_production_assets.py` entries. |
| **[Potential Gotchas on GDC-ag](./testing/potential-gotchas-on-gdc-ag.md)** | Field-tested GDC-ag platform constraints (manual DB failover, predefined machine types, Harbor TLS trust). |
| **[Verification Results Ledger](./testing/verification-results.md)** | Historical verification logs across patterns. |
| **[Engineering Lessons Learned](./testing/lessons-learned.md)** | Architectural retrospectives and root-cause resolutions across Patterns 1–13 and `gdc_gemma_gw`. |

