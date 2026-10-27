Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# User Journeys & Persona Specifications

This directory contains the catalog of **User Journeys** for the **Google Distributed Cloud air-gapped (GDCag)** Infrastructure as Code repository.

User journeys define what a given persona is looking to accomplish, detailing their operational intent, required inputs, tool interactions, failure modes, and definitions of done across the Day-0, Day-1, and Day-2 lifecycle.

---

## Directory Organization

Each document in this directory represents a **single user persona** and houses **multiple user journeys** specific to that persona:

```text
docs/user-journeys/
├── README.md                      # Directory overview, persona taxonomy, and authoring guidelines
├── template.md                    # Canonical template for authoring a persona and its journeys
├── platform-administrator.md      # Platform SRE / Org Admin journeys (Bootstrap, Ingestion, Upgrades)
├── application-developer.md       # Workload Engineer journeys (Blueprint hydration, GitOps, DB integration)
├── ai-ml-engineer.md              # AI/ML Practitioner journeys (LLM Gateway, Model serving, RAG agents)
├── security-compliance-auditor.md # Information Assurance journeys (SBOM audit, OPA policy, Keycloak RBAC)
└── mission-analyst.md             # End-User / SCIF Analyst journeys (Mission UI, RAG queries, Chatbots)
```

---

## Core Persona Taxonomy for GDCag

| Persona Identifier | Role / Persona Title | Typical Focus & Responsibilities | Key Cluster Scope |
| :--- | :--- | :--- | :--- |
| **`PER-PLATFORM-ADMIN`** | **Platform Administrator / SRE** | Bootstrapping landing zones, ingesting air-gap bundles into Harbor, managing cluster quotas, maintaining core platform services (Keycloak, Vault, Prometheus). | Global API Cluster & Org Admin / Zone Cluster |
| **`PER-APP-DEV`** | **Application / Workload Developer** | Selecting and hydrating reference architecture blueprints (P1–P13), pushing manifests to GitOps repos, integrating with managed PostgreSQL and storage. | Standard / User Clusters |
| **`PER-AI-ML-ENG`** | **AI/ML Engineer & Data Scientist** | Deploying inference engines (Gemma Gateway, vLLM, Ollama), importing model weights to GDC Object Storage, deploying sovereign notebooks and multi-agent swarms. | Standard / User Clusters (GPU nodes) |
| **`PER-SEC-AUDITOR`** | **Security & Compliance Auditor** | Auditing supply chain provenance (Cosign signatures, SPDX SBOMs), validating OPA/Gatekeeper admission policies, reviewing IAM least-privilege. | All Clusters & Compliance Logging |
| **`PER-MISSION-ANALYST`** | **Mission / Operations Analyst** | Accessing mission frontends, running RAG intelligence queries, interacting with LLM chat interfaces under air-gapped SCIF constraints. | Workload Ingress / HTTPRoutes (End-User) |

---

## Structure of a Persona Document

Every persona file created from `template.md` contains two primary levels of detail:

1. **Persona Profile (Single User)**
   * **Role & Mission:** Purpose and scope within the organization.
   * **Cluster Context:** Specific GDC cluster tiers accessed (Global, Zone, User).
   * **Air-Gap Profile:** Understanding of air-gapped constraints and transfer mechanisms.
   * **Tooling & Credentials:** CLIs (`gdcloud`, `kubectl`, `helmfile`), registries (Harbor), identity providers (Keycloak), and secrets engines (Vault).
   * **Motivations & Frustrations:** Drivers for success and operational bottlenecks.

2. **Persona Journey Catalog & Multi-Journey Details**
   * **Journey Index:** Summary table of all journeys belonging to this user.
   * **Individual Journey Blocks (`[UJ-PER-XX]`):**
     * **User Story:** *"As a [persona], I want to [action], so that [outcome]"*
     * **Preconditions & Inputs:** Prerequisite cluster states, Harbor images, credentials.
     * **Step-by-Step Flow:** Sequential actions, CLI/UI tools, expected system responses, and health checks.
     * **Decision Points & Failure Recovery:** Common failure conditions (e.g., ImagePullBackOff, OPA rejection) and remediations.
     * **Definition of Done:** Objective criteria for journey completion.
     * **Friction Points:** Operational toil and opportunities for IaC/blueprint enhancement.
   * **Traceability Matrix:** Cross-journey hand-offs and dependencies.

---

## How to Create a New User Journey Document

1. **Copy the Template:**
   ```bash
   cp docs/user-journeys/template.md docs/user-journeys/<persona-kebab-case>.md
   ```
2. **Populate the Persona Profile:**
   Define the role, responsibilities, cluster scopes, and tooling in Section 1.
3. **List the Journeys in the Index:**
   Add all target journeys to the summary table in Section 2.
4. **Draft Each Journey:**
   Fill in the journey details for each item in the index. Duplicate the journey block for as many journeys as the user performs.
5. **Cross-Reference:**
   Ensure referenced Helm charts, blueprints, and operational guides link to existing assets in the repository.
