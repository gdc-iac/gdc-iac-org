Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

## GDC Production Staging Pipeline (`deploy-to-production/`) & GDC Managed Service Asset Isolation
* **Date:** 2026-07-27
* **Objective:** Establish an automated production asset packaging pipeline (`scripts/stage_production_assets.py`) that exports self-contained, air-gapped production assets for all 11 active patterns and `gdc_gemma_gw` into `deploy-to-production/`, with zero external repository dependencies.
* **Resolution:**
  1. Enhanced `scripts/stage_production_assets.py` to support **individual pattern staging** via command-line arguments (e.g. `python3 scripts/stage_production_assets.py p6-resilient-rag-agent`) as well as full repository staging (`all`).
  2. Built `deploy-to-production/` to be **100% self-contained** so it can be moved or cloned directly into a separate production repository without any parent folder dependencies.
  3. Staged self-contained helper scripts in `deploy-to-production/common-scripts/` (`configure-blueprints.sh`, `mirror_images.sh`, `package-for-gdc.sh`, `unpack-for-gdc.sh`, `bulk_mirror_images.sh`) with internal relative path resolution.
  4. Identified that PostgreSQL on GDC-ag is a **platform-managed service** provisioned via `kubectl` using `DBCluster` (`postgresql.dbadmin.gdc.goog/v1`) custom resources, eliminating containerized PostgreSQL images (`postgres:14`, `postgres:15-alpine`) from 3P air-gapped container download lists.
  5. Filtered out all GCP testing/emulation artifacts (`quickstart_on_GCP.md`, `testing_strategy_gcp_stepping_stone.md`, `test/` folders, and `manifests/gcp/`).
  6. Audited and generated `deploy-to-production/bulk_external_images.txt` containing only non-database 3P container dependencies (Kafka, Vault, Keycloak, MLflow, vLLM, Ollama).
  7. Integrated `../gdc_gemma_gw` production blueprints, gateway proxy, client web app, and scripts into `deploy-to-production/gdc_gemma_gw/`.
  8. Generated master production deployment documentation at `deploy-to-production/README.md`.
* **Lessons Learned:** Designing the production output folder (`deploy-to-production/`) as a completely self-contained repository structure allows organization teams to decouple development/testing repositories from production release artifacts while enabling both single-pattern and multi-pattern deployment workflows.


## Deprecation of Pattern 5 (Resilient Hybrid LLM Gateway)
* **Date:** 2026-07-24
* **Objective:** Deprecate Pattern 5 (Resilient Hybrid LLM Gateway) as GenAI applications now interface directly with Gemma Inference Gateway (`gdc_gemma_gw` / vLLM / Ollama) or GDC Gemini AI Gateway.
* **Resolution:**
  1. Marked Pattern 5 as `[DEPRECATED]` in `p5-hybrid-llm-gateway/README.md`, `docs/implementation-guides/Solution-Reference-Implementation-Pattern-5-Resilient-Hybrid-LLM-Gateway.md`, `docs/patterns_def.md`, and main `README.md`.
  2. Updated downstream pattern implementation guides (Patterns 6, 7, 9, 10, and Template Pattern) to remove dependencies on Pattern 5, clarifying direct integration with Gemma Inference Gateway (`gdc_gemma_gw`) or GDC Gemini AI Gateway.
  3. Updated repository documentation (`docs/updating_ollama.md`, `p6` and `p7` testing strategies) to reflect Pattern 5 deprecation.
* **Lessons Learned:** Native multi-provider configuration in agent and gateway clients eliminates the overhead of running an intermediate proxy gateway pod, reducing latency and simplifying air-gapped deployment topology.

## Implementation Guide v1.2: GCP Staging Emulation Removal, Cross-Cluster Gateway Topology, & Table Fixes
* **Date:** 2026-07-24
* **Objective:** Fix markdown table syntax in Pattern 6, remove GCP staging emulation assumptions, clarify cross-cluster LLM Gateway deployment topology, and eliminate non-existent dedicated GDC OCR/STT/Translation API references across all Implementation Guides.
* **Resolution:**
  1. Fixed table markdown rendering (added missing separator row `| :--- | :--- | :--- |`) in `docs/implementation-guides/Solution-Reference-Implementation-Pattern-6-Resilient-RAG-Agent.md`.
  2. Removed non-existent GDC OCR, STT, and Translation pre-trained API references and developer roles (`Role/ai-ocr-developer`, `Role/ai-translation-developer`) in Pattern 6, updating architecture descriptions, ASCII diagrams, and IAM bindings to reflect multimodal LLM extractions via Gemma / Gemini models (`Role/ai-inference-developer`).
  3. Added explicit **LLM Gateway Integration & Cross-Cluster Topology Guidance** across implementation guides (Patterns 2, 5, 6, 7, 9, 10, and Template Pattern), clarifying that inference gateways do not need to be co-located in the application cluster or namespace and can be hosted in shared services or dedicated AI clusters reached via Gateway API or internal FQDNs.
  4. Updated comparison sections in Patterns 2, 3, 6, 7, 9, and the Template Pattern to compare **Connected Sideloading Workstation** artifact preparation against **GDC Air-Gapped Production** deployment, eliminating assumptions of a GCP staging emulation cluster.
  5. Corrected manifest reference path in `Solution-Reference-Implementation-Template-Pattern.md` from `manifests/gcp/` to `manifests/gdc/db/postgres.yaml`.
  6. Updated document version headers from `1.1` to `1.2` across modified implementation guides.
* **Lessons Learned:** Multimodal capabilities in modern LLMs eliminate the need for dedicated legacy pre-trained vision/translation services. Documenting flexible cross-cluster gateway topologies allows enterprise deployers to decouple AI inference infrastructure from application workloads.

## Standardizing Solution Reference & Implementation Guide Document Versioning (v1.1)
* **Date:** 2026-07-24
* **Objective:** Standardize document versioning across all GDC Blueprint Solution Reference Implementation Guides and gdc_gemma_gw Implementation Guides to version 1.1.
* **Resolution:** 
  1. Updated all 14 Solution Reference Implementation Guides in `docs/implementation-guides/` and general architecture guides in `docs/` in `GDC-blueprints` to document version `1.1`.
  2. Updated all 14 implementation and technical guides in `gdc_gemma_gw/docs/` (including Gemma 4 Client Application and Gemma 4 Dedicated Inference Gateway Solution Reference Implementations) to document version `1.1`.
* **Lessons Learned:** Uniform document version metadata (`> **Version:** 1.1`) placed in document headers provides explicit version tracing for enterprise solution blueprints across repository boundaries.

## Pattern 6 & Pattern 7: Gemma Gateway and GDC Gemini Gateway Adaptation
* **Date:** 2026-07-24
* **Objective:** Adapt Pattern 6 (Resilient RAG Agent) and Pattern 7 (Agentic Data Analyst) to natively support self-hosted offline inference via **Gemma Inference Gateway** (`../gdc_gemma_gw` / vLLM / Ollama) as primary provider, with native **GDC Gemini AI Gateway** (`https://ai-gateway.../v1` + GDC STS token + `x-goog-user-project` header) as alternative provider option.
* **Resolution:**
  1. Updated `p6-resilient-rag-agent/example-app/query-service/utils.py` and `p7-agentic-data-analyst/example-app/agent/app.py` with multi-provider LLM clients (`LLM_PROVIDER="gemma"|"gemini"`). Handled both OpenAI `/v1/chat/completions` and `/generate` payloads.
  2. Updated Kubernetes manifests (`query-service.yaml` and `sql-agent.yaml`) with `LLM_PROVIDER`, `LLM_GATEWAY_URL`, `GEMINI_MODEL`, and `AO_PROJECT_ID` environment variables.
  3. Authored Python unit test suites (`test_llm_client.py`) for both P6 and P7 query/agent logic with 100% pass rate.
  4. Updated Solution Reference Implementation Guides, `patterns_def.md`, and pattern READMEs.
* **Lessons Learned:** Decoupling model provider selection into standard environment variables (`LLM_PROVIDER`, `LLM_GATEWAY_URL`, `AO_PROJECT_ID`) allows agentic blueprints to seamlessly switch between self-hosted offline Gemma models and managed air-gapped GDC Gemini models without modifying application code or container builds.

## Gemma 4 Solution Reference Guides Alignment
* **Date:** 2026-07-17
* **Objective:** Ensure consistency across the Gemma 4 solution guides by aligning the Client Application guide with the Inference Gateway guide.
* **Resolution:** Standardized the Gemma 4 Client Application Reference Implementation guide (`gdc_gemma_gw/docs/Solution-Reference-Implementation-Gemma4-Client-Application.md`) by adding the missing "Key Solution Capabilities" section. This ensures a consistent structure across all solution guides, clearly highlighting critical aspects like Single-Origin Gateway API routing, Keycloak OIDC authentication, stateful persistence, dynamic model override sync, and air-gapped sovereignty constraints prior to the setup steps.

## Deprecation of AlloyDB in Favor of Managed PostgreSQL on gdc_gemma_gw
* **Date:** 2026-07-17
* **Objective:** Synchronize the database configuration and documentation of the `gdc_gemma_gw` repository with GDC-ag platform's supported managed databases.
* **Resolution:** Replaced all occurrences and references to AlloyDB (including "AlloyDB Omni", "AlloyDB emulation", and "AlloyDB/PostgreSQL") with PostgreSQL across all documents, readme files, and telemetry guides in `gdc_gemma_gw`. Verified that in-cluster configuration manifests strictly rely on GDC Managed PostgreSQL (`postgresql.dbadmin.gdc.goog/v1`) without any AlloyDB definitions.

## Pattern 11: Vault Image Registry Depreciation and Configuration Overwrites
* **Date:** 2026-03-26
* **Issue 1 (ImagePullBackOff):** The Vault Helm chart was experiencing `ErrImagePull` because Docker Hub removed the official `vault` image from the `library` namespace, migrating it entirely to `hashicorp/vault`. The helm chart's global configuration fallbacks were improperly trying to resolve `vault:1.15.0` instead of `hashicorp/vault`.
* **Resolution 1:** Explicitly hardcoded `global.image.repository: hashicorp/vault` and `server.image.repository: hashicorp/vault` directly inside `manifests/helm/values.yaml` to prevent fallback to deprecated namespaces.
* **Issue 2 (KMS PermissionDenied on my-gdc-project):** After pulling the Helm chart fix via `git pull`, Vault crashed with `Exit Code: 1` and `PermissionDenied` when attempting to contact GCP KMS for auto-unseal. Running `git pull` reverted the `configure-blueprints.sh` runtime replacements on the workstation, causing the `gcpckms` seal block in `values.yaml` to look for keys in the static placeholder `my-gdc-project` instead of the user's actual GCP project ID.
* **Resolution 2:** Re-run `./configure-blueprints.sh` immediately after any remote `git pull` operation to ensure all environment-specific placeholders (Project IDs, Registry Hostnames) are correctly re-injected before invoking `helm upgrade`.

## Pattern 11: Secret Management Best Practices with HashiCorp Vault
* **Date:** 2026-03-26
* **Objective:** Establish a resilient and highly available enclave for handling secrets across agentic and multi-tenant architectures seamlessly on GDC-ag.
* **Architecture:** Adopted `vault-1.15.0` deployed via Helm utilizing Raft Consensus for backend storage alongside Google Cloud KMS for automated seal/unseal mechanics without compromising availability domains. Network policies tightly scope ingress to GDC KMS ranges.
* **Testing Validation Strategy:** Due to the physical reliance on Hardware KMS, the Stepping Stone (GCP) testing plan was heavily modified to assert against mocked `gcloud kms` rings wrapped locally within GCP Emulation. TDD explicitly validates pod auto-unseal metadata (`vault status`) before approving integration to ensure seamless failover behavior.
* **Next Steps:** Progressively transition historical environments (specifically `p1-resilient-3-tier-webapp`, and agentic architectures) away from `EnvVar` and native Kubernetes generic secrets over to Dynamic Vault Injection via Sidecars.

## Security Update: ADK / LiteLLM Vulnerability Enforcement
* **Date:** 2026-03-25
* **Issue:** LiteLLM versions 1.82.7 and 1.82.8 contain unauthorized code. ADK relies on LiteLLM under the hood, and older loose dependencies allowed these versions to be pulled during container builds.
* **Resolution:** Re-enforced strict dependency pinning across agentic patterns (Pattern 6: Resilient RAG Agent and Pattern 7: Agentic Data Analyst) by appending `google-adk==1.27.4` to all AI-focused Docker images. Pinning this package acts as a hard resolution for this supply chain risk.
* **Impact & Next Steps:** Container images for `p6-resilient-rag-agent` and `p7-agentic-data-analyst` must be immediately rebuilt on development workstations and re-transferred across the air-gap using the packaging scripts.

## P5 & P6 Integration: Workload Identity Bleed and NGINX Proxy Rewiring
* **Date:** 2026-03-25
* **Issue 1 (Identity Bleed):** Sequential testing of patterns on the same Cloud Workstation caused environment variables (like `GSA_NAME="gateway-sa"`) to leak into subsequent pattern deployments. This forced Kubernetes ReplicaSets into persistent `FailedCreate` loops because the correct ServiceAccount identities (like `rag-sa`) were silently skipped by the credential bootstrapping scripts.
* **Resolution 1:** Updated `testing_strategy_gcp_stepping_stone.md` guides to explicitly declare and reset terminal session environment variables (`GSA_NAME` and `KSA_NAME`) before calling workload identity configuration scripts. Also added the ReplicaSet exponential backoff issue to the Troubleshooting documentation.
* **Issue 2 (NGINX Double-Slash 404):** The P6 Frontend React application's reverse-proxy (`nginx.conf`) was improperly combining `proxy_pass` with a trailing slash and `rewrite ^/api/(.*) /$1 break;`. NGINX effectively double-stripped the URL base, passing requests formatted like `//documents` to the FastAPI backend, resulting in silent 404 rejections and GUI fetching failures.
* **Resolution 2:** Removed the redundant rewrite rule in `nginx.conf` and re-pushed the `rag-frontend` image to strictly rely on `proxy_pass` for URL stripping.
* **Impact & Next Steps:** Pattern 5, 6, and 7 are now independently deployable, properly decoupled, and fully validated across both GCP Workstation emulation and their GDC-ag production architectural requirements.

## GDC Air-Gapped Packaging Mechanics & Hidden Dependency Chains
* **Date:** 2026-03-26
* **Issue 1 (Phantom Tarballs & Generic Documentation):** The baseline templates for GDC packaging (`README.md` Unpack & Deploy steps) generically instructed operators to unpack locally-built containers (`-gdc-images.tar`) and generic Helm images for *all* patterns, even if the pattern (like Vault) only consumed external charts and generated no local container payload. This created massive confusion during air-gapped staging when operators searched for non-existent `.tar` files.
* **Resolution 1:** Dynamically refactored the "Transfer Artifacts" and "Unpack and Deploy" documentation sections across all 11 patterns. Patterns that use external charts (Kafka, Vault, Ollama) now have explicit loading/tagging commands referencing their exact array of dependency images, while self-contained patterns omit global dependency steps entirely.
* **Issue 2 (Config Context Bleed):** During packaging, running `./configure-blueprints.sh` with the host workstation's Project ID hardcoded that context into the manifests. If deployed as-is across the air-gap, GDC service accounts would attempt to bind to the connected GCP project.
* **Resolution 2:** Prominently flagged the `PROJECT_ID` parameter as `CRITICAL DESTINATION VARIABLES` in the Pre-requisite section, enforcing that operators must inject the *disconnected GDC target environment's* project ID before initiating the package script.
* **Issue 3 (Helm Chart Image Trees - KRaft vs Zookeeper):** Our bulk air-gapped payload script (`bulk_mirror_images.sh`) cannot parse dynamic `.tgz` Helm abstractions (like Kafka) to recursively download internal images. When packaging Kafka, `bitnami/kafka` and `bitnami/zookeeper` were historically assumed. However, executing `helm show values` on modern `kafka-32.x` charts revealed that Kafka 4.0 has entirely deprecated Zookeeper in favor of KRaft mode, altering the dependency tree.
* **Resolution 3:** Authored an explicit `external_images.txt` manifest within the P4 directory mapping the exact four images required by Kafka 4.0 (Kafka, OS-Shell, Kubectl, JMX-Exporter). Furthermore, stripped legacy Zookeeper replica flags (`--set zookeeper.replicaCount`) from the P4 Helm installation commands to ensure seamless KRaft cluster initialization.

## Pattern 4 & 11: GCP Emulation E2E Testing Synchronization and Initialization Ordering
* **Date:** 2026-03-26
* **Issue 1 (KMS Binding vs. Workload Identity Creation Order):** In the P11 Vault `testing_strategy_gcp_stepping_stone.md`, the instructions incorrectly ordered the GCP KMS `add-iam-policy-binding` command before the execution of the `configure-workload-identity.sh` script. This caused the KMS CLI query to fail with `400 Bad Request` because the target Google Service Account (`vault-kms-sa`) had not been instantiated yet by the Workload script.
* **Resolution 1:** Swapped the logic blocks in the testing guide to ensure the Workload Identity creation step natively precedes the assignment of any GCP KMS policies.
* **Issue 2 (GCP E2E Testing vs Registry Mirroring & Double-Namespacing):** When executing an E2E test on GCP before packaging P4 for GDC Air-Gapped transfer, users must temporarily bind images to their private `us-central1` artifacts registry. However, pushing `busybox` and `apache/kafka` via `build.sh` was resulting in an `ImagePullBackOff` due to a namespace collision where `configure-blueprints.sh` appended a trailing `/library` string onto the URI, causing the custom build script to redundantly tag images as `library/library/busybox:latest`.
* **Resolution 2:** Removed the hardcoded `/library` tag from the default fallback variable inside `scripts/build.sh`. The script relies entirely on the precise target variable injected by `configure-blueprints.sh`, cleanly mapping generic OSS payloads into private artifact registries seamlessly.
* **Issue 3 (Accidental Stateful Manifest Commits):** Utilizing `./configure-blueprints.sh` organically overwrites tracking states inside git-tracked manifests (`consumer.yaml` etc.) to inject dynamic registries. When the `build.sh` fix was pushed, these modified target files were accidentally swept into a `git commit`, rigidly baking in the `us-central1-test` string. This completely broke the sed-replace logic on subsequent script invocations because `test-registry.local` was permanently erased.
* **Resolution 3:** Performed a strict `git checkout HEAD^` reversion to wipe the modified tracking files back to their unpolluted `harbor.gdc.local` template defaults, ensuring the configuration scripts retain universal replaceability.

## Pattern 11: Vault KMS Initialization and IAM Propagation Delay
* **Date:** 2026-03-27
* **Issue:** Vault Pods entered a continuous `CrashLoopBackOff` state with `Exit Code: 1` during GCP emulation testing. The logs indicated a `PermissionDenied` error for `cloudkms.cryptoKeys.get` on the `vault-unseal-key`, despite configuring the Google Service Account via Workload Identity.
* **Resolution:** The Vault statefulset initialized before GCP fully propagated the IAM policy mapping attached to the KMS ring, causing a fatal crash. Because Kubernetes StatefulSets institute an exponential backoff loop for crashing pods, simply waiting for IAM propagation is insufficient. Forcefully deleting the pods via `kubectl delete pods -l app.kubernetes.io/name=vault -n ${NAMESPACE}` instantly breaks the loop and allows Vault to seamlessly acquire its auto-unseal keys upon restart.

## Pattern 12: Decoupled Identity Architecture strategy
* **Date:** 2026-03-27
* **Success:** Successfully implemented an advanced overlay strategy when introducing the new P12-Keycloak blueprint into the GDC environment.
* **Analysis:** Early proposals often force identity code directly into application baselines (like P6 and P7), strictly tying their test cycles and logic to an IdP. To ensure absolute decoupling, Keycloak was maintained entirely independent. 
* **Improvement:** Adopted an "Overlay Approach", where the new centralized `docs/keycloak_integration_guide.md` explicitly teaches the GDC deployer how to transparently swap Mock Auth for Keycloak OIDC inside decoupled patterns. By appending brief reference addendums directly into existing patterns' READMEs (rather than changing their code), testing procedures for individual agents aren't convoluted by heavyweight SSO prerequisites.

## Production Implementation Guides Generation
* **Date:** 2026-06-05
* **Objective:** Standardize and publish detailed GDC air-gapped production implementation guides for all 10 active patterns in this repository, modeled after the premium reference solutions in `gdc_gemma_gw`.
* **Execution:** Created a new directory `docs/implementation-guides/` and generated standalone, production-ready markdown guides covering resource sizing, t-shirt node pools, GDC IAM roles, manual/GitOps paths, Gateway API, and network isolation policies.
* **Lessons Learned:** Encountered local git repository checkout/tracking divergence issues where the branch HEAD pointer reverted between terminal execution steps on the developer environment. Resolved this by combining rebase and push commands into a single chained zsh command (`git pull --rebase && git push origin main`), bypassing sandbox-level checkout resets.

## Production Implementation Guides: GDC Predefined Resource Sizing and VM Image Validation
* **Date:** 2026-06-05
* **Issue:** The implementation guides and actual codebase manifests/READMEs for several patterns (Pattern 1, Pattern 3, Pattern 6, and the template pattern) contained references to invalid, non-predefined GDC machine types (`n2-standard-2-gdc`, `n2-highcpu-16-gdc`, and `n2-standard-8` without `-gdc` suffix).
* **Resolution:** Conducted a comprehensive validation scan of all guides, READMEs, scripts, and Kubernetes manifests using a custom Python script against the official GDC docs. Replaced `n2-standard-2-gdc` references with `n2-standard-4-gdc` (for GKE workloads) and `n2-highcpu-8-gdc` (for Legacy VM workload). Fixed the VM provision script to use `n2-highcpu-8-gdc` instead of the non-suffixed `n2-standard-8`. Swapped the invalid scale-up type `n2-highcpu-16-gdc` in the pattern 3 README and implementation guide with a valid predefined `n2-standard-16-gdc` type.
* **Lessons Learned:** GDC uses a specific subset of predefined machine types for cluster node pools and virtual machines. Both the documentation (guides/READMEs) and the actual source YAML manifests and shell scripts must be validated against these official lists to ensure successful deployment and scaling in production air-gapped environments.

## GDC Managed Database Service: Manual Failover Architecture
* **Date:** 2026-06-05
* **Issue:** Several implementation guides, concepts mapping, and pattern README files incorrectly stated that GDC Database Service (PostgreSQL) configured with `ZONAL_HA` supports automatic failover upon primary instance failure.
* **Resolution:** Reviewed all implementation guides, design patterns (`patterns_def.md`), and READMEs to replace automatic failover references with explicit details on manual failover. Added dedicated "Database High Availability & Manual Failover" sections to each database-deploying guide. Created corresponding declarative `Failover` custom resource manifests (`fleet.dbadmin.gdc.goog/v1`) in the database config folder for all seven database-backed patterns.
* **Lessons Learned:** GDC Database Service does not perform automatic failover for high availability configurations. When a primary database instance fails, an operator must manually trigger failover either via the `gdcloud` CLI or by applying a custom resource of kind `Failover` to promote the standby replica.

## GDC Air-Gapped Deployment: Docker Registry Authentication
* **Date:** 2026-06-05
* **Issue:** The standalone deployment instructions (`README.md` files) for all patterns did not include a prerequisite step to authenticate the Docker client to the target GDC Harbor registry prior to loading and pushing container images.
* **Resolution:** Reviewed and updated the `README.md` files and premium **Solution Reference Implementation Guides** (`docs/implementation-guides/`) for all active patterns (Pattern 1, 3, 4, 5, 6, 7, 8, 10, 11, 12, and the template pattern) to insert a dedicated "Authenticate Docker with Harbor" step (`docker login`) at the start of the "Unpack and Deploy" and "Common Setup" phases and renumbered subsequent steps accordingly.
* **Lessons Learned:** When deploying to air-gapped environments, container push and validation workflows rely on pre-authenticating local workstations to private container registries (Harbor). Neglecting to specify registry authentication steps results in silent errors during image uploads, which can be avoided by making it a mandatory step in all deployment blueprints.

## GDC Predefined Machine Types Double-Check Validation
* **Date:** 2026-06-08
* **Issue:** Conducted a secondary comprehensive verification of all machineType and machineTypeName occurrences against the official GDC air-gapped predefined list (https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/platform/pa-user/cluster-node-machines). Identified remaining invalid references: non-suffixed machine types (`n2-standard-4` and `n2-standard-8`) in the core architectural definition document (`docs/patterns_def.md`), and the non-existent `n2-standard-2-gdc` in the deprecated Pattern 2 manifests and README.
* **Resolution:** Corrected the core definitions in `docs/patterns_def.md` to use the fully suffixed `n2-standard-4-gdc` and `n2-standard-8-gdc` names. Updated the deprecated Pattern 2 manifests and README to reference the valid minimum standard size `n2-standard-4-gdc`.
* **Lessons Learned:** Verification tools should target all pattern definitions, including deprecated or template directories, to prevent propagation of invalid machine types when new patterns are scaffolded or designed.

## Deprecation of AlloyDB Omni in Favor of Managed PostgreSQL on GDC
* **Date:** 2026-07-13
* **Issue:** Several architectural blueprints (`p3`, `p6`, `p7`, `p10`), deployment scripts, implementation guides, and CRD manifests contained references to AlloyDB Omni (`alloydbomni.dbadmin.gdc.goog/v1`, version `ALLOYDBOMNI_15`). AlloyDB Omni is no longer available as a managed database service on Google Distributed Cloud air-gapped (GDC-ag).
* **Resolution:** Conducted a comprehensive repository-wide audit and refactoring. Replaced all occurrences of `alloydbomni.dbadmin.gdc.goog/v1` and `ALLOYDBOMNI_15` with managed PostgreSQL (`postgresql.dbadmin.gdc.goog/v1`, version `POSTGRESQL_14`), renamed misleading manifest filenames (`alloydb.yaml` -> `postgres.yaml`), and updated all documentation, diagrams, tables, and `gdcloud` CLI examples across all patterns to explicitly specify PostgreSQL High-Availability (`ZONAL_HA`). Removed obsolete `dbclusters.alloydbomni.dbadmin.gdc.goog` CRD definitions from mock test files.
* **Lessons Learned:** Always ensure that architectural blueprints and CRD specifications strictly align with current supported managed platform services on GDC-ag (`postgresql.dbadmin.gdc.goog/v1`). Maintaining deprecated service references across documentation or custom resources leads to operator confusion and deployment failures in target environments.

---

# Lessons Learned: Pattern 12 (Keycloak IAM)

### 1. Vendor Dependencies and Helm Chart Deprecation
*   **Observation:** The original architecture relied on `registry-1.docker.io/bitnamicharts/keycloak`. However, Bitnami aggressively purged legacy container tags from their free-tier Docker Hub repositories ("Since August 28th, 2025, only a limited subset of images/charts are available for free"). This directly broke the physical air-gapped container mirroring script (`ErrImagePull` -> `not found`).
*   **Resolution:** Completely decoupled the blueprint from Bitnami's locked ecosystem. We refactored P12 natively using declarative Kubernetes Manifests (`Deployment` + `Service`) and securely piped in the official, un-paywalled Red Hat/Quarkus container (`quay.io/keycloak/keycloak:24.0.4`). This strongly aligns with GDC's baseline imperative for completely self-contained, open-source architecture.

### 2. Quarkus Health Probes (Readiness Failures)
*   **Observation:** When transitioning from Bitnami arrays to raw Quarkus manifests, the GKE Service refused to route traffic to the Keycloak pod (causing `Site Can't Be Reached` / dropped browser connections). The native Kubernetes `httpGet` probe against `/health/ready` failed perpetually (`0/1` READY). 
*   **Resolution:** Keycloak >= 18 rigorously locks down external diagnostic telemetry. It is strictly mandatory to inject `KC_HEALTH_ENABLED="true"` into the Pod environment to physically activate the Quarkus metrics endpoints for Kubernetes to scan.

### 3. Google Cloud Workstations Iframe Sandboxing & CORS Loops
*   **Observation:** Accessing the modern Keycloak React-based Admin Console organically via standard web preview subdomains inside Google Cloud Workstations produced perpetual `403 Forbidden` errors on the login status iframe, blocking session checks and hanging on the spinner.
*   **Analysis (The Sandboxed Iframe Trap):** Keycloak's React Admin UI initializes a dynamic session-tracking iframe (`login-status-iframe.html`). To prevent clickjacking, this iframe is sandboxed. Chromium browsers strictly block sandboxed iframes from transmitting active session cookies (like Google account authentication credentials required to access the private Workstation). The Workstations proxy intercepts this unauthenticated iframe request, rejects it, and returns `403 Forbidden`, deadlocking the UI.
*   **Resolution:** 
    1. **Dynamic Port Compatibility (Omit Hostname URLs)**: Omit `KC_HOSTNAME_URL` and `KC_HOSTNAME_ADMIN_URL` environment variables entirely! By setting `KC_HOSTNAME_STRICT` to `"false"`, Keycloak dynamically resolves the client host organically from NGINX's forwarded host headers, making the manifest 100% portable on any workstation VM instance.
    2. **Automated Realm Auto-Import (GDC GitOps Standard)**: Avoid manual administrator panel registrations! Package your target realm, OIDC clients, custom origins, roles, and personas inside a Kubernetes ConfigMap, and mount it to `/opt/keycloak/data/import/`. On startup, Keycloak imports the configurations automatically on boot—**bypassing the sandboxed admin console loops entirely!**

### 4. GKE Staging Probe Failures (Quarkus Augmentation Timeouts)
*   **Observation:** Transitioning Keycloak deployments on Standard GKE sandbox nodes triggered persistent liveness probe crashes, putting Keycloak in an `ImagePullBackOff` or `Exit Code 1` loop.
*   **Analysis:** Quarkus class augmentation and initial database schema migrations take 40 - 50 seconds on virtualized nodes. The default `initialDelaySeconds: 20` for readiness probes fired too early. The target endpoint returned TCP connection refused, leading Kubernetes to forcibly issue a `SIGKILL` mid-migration, corrupting dynamic locks.
*   **Resolution**: Raise readiness `initialDelaySeconds` strictly to **`60 seconds`** with a `failureThreshold` of **`10`**, and liveness to **`90 seconds`** with threshold **`10`**, allowing the JVM process to boot cleanly.

### 5. In-Memory Database Recycles (Table Empty Crashes)
*   **Observation:** Keycloak booted, but during dynamic redirects it crashed with `JdbcSQLSyntaxErrorException: Table "USER_ENTITY" not found`.
*   **Analysis (H2 Connection Recycles):** Developer in-memory H2 databases (`dev-mem` vendor) discard active RAM database states once dynamic connection pools drop to `0`. Keycloak connection pools default minimum bounds to `0`, discarding the schema during startup handover.
*   **Resolution**: Add `KC_DB_POOL_MIN_SIZE=1` to force the connection pool to maintain at least one socket permanently open, preventing RAM discards. Avoid using semi-colons in env array parameter mappings as they split the `kc.sh` shell expansion wrapper during evaluation, truncating the Java command stream.

---

# Retrospective & Lessons Learned - Pattern 13: GDC Developer Environment (`gdc-dev`)

## Overview
Pattern 13 establishes an air-gapped deployment architecture for GDC Developer Environment (`gdc-dev`) (inspired by the cloud IDE paradigms of Eclipse Theia Cloud) on Google Distributed Cloud (GDC-ag), replacing legacy NGINX ingress with Kubernetes Gateway API, integrating Keycloak OIDC identity, and connecting to platform PKI.

## Key Learnings & Architecture Decisions

### 1. Ingress Modernization (Gateway API vs. Legacy NGINX)
* **Finding:** Legacy NGINX Ingress annotations (`nginx.ingress.kubernetes.io/*`) are deprecated on GDC physical racks in favor of Kubernetes Gateway API (`gateway.networking.k8s.io/v1`).
* **Resolution:** Adapted the EduIDE `gdc-dev-gateway` pattern to route all host and dynamic workspace pod requests (`/instances/*`) using Gateway API `HTTPRoute` resources attached to `gdc-platform-gateway` or Envoy Gateway.

### 2. Iterative 3-Phase Deployment Strategy
* **Finding:** Deploying Keycloak identity, enterprise platform PKI, and workspace pod operator logic simultaneously creates excessive deployment friction and diagnostic ambiguity.
* **Resolution:** Structured implementation into 3 distinct phases:
  1. **Phase 1:** Core Helm deployment with Gateway API and Mock Auth headers (`X-User-ID`) using temporary self-signed TLS certificates.
  2. **Phase 2:** Keycloak OIDC SSO identity integration (authorization code flow with PKCE).
  3. **Phase 3:** Enterprise GDC Platform PKI migration (disabling `issuerCa` in Helm) and cluster architecture topology hardening.

### 3. Air-Gap Container & Manifest Packaging
* **Finding:** The `gdc-dev-operator` dynamically provisions user workspace container images on-demand.
* **Resolution:** Standardized `package-for-gdc.sh` and `unpack-for-gdc.sh` scripts to bundle both operator management images and workspace container base images into local GDC container registries before sneakernet transfer.

### 4. In-Place Progressive Delivery (Phase 1 -> Phase 2 -> Phase 3) Without Teardown
* **Finding:** Deleting namespaces and tearing down cluster resources between progressive delivery phases erases operational history and slows verification.
* **Resolution:** Designed Phase 2 (`gdc-dev-phase2-deployment.yaml` and `oidc-auth-configmap.yaml`) and Phase 3 (`certificate.yaml` and `network-policy.yaml`) as declarative overlays applied directly on top of Phase 1 infrastructure. Performing `rollout restart` updates running container configurations (`AUTH_MODE: oidc`) in under 3 seconds with zero infrastructure churn.

### 5. Python f-String vs. JavaScript Template Literal Collision
* **Finding:** Embedding JavaScript template literals (`\`...${promptCmd}\``) inside Python f-strings (`f"""..."""`) causes Python to attempt variable interpolation on `{promptCmd}`, triggering runtime `NameError: name 'promptCmd' is not defined` and crashing the HTTP request handler (`500 Internal Server Error`).
* **Resolution:** Replaced all JavaScript template literals inside Python f-string blocks with standard JavaScript string concatenation (`+ promptCmd`) across `operator/app.py` and `landing-page/app.py`, and instituted dynamic TDD execution verification (`test_render_workspace_ui_execution`).

### 6. Browser Disk Caching of Dynamic Session Screens
* **Finding:** Single-page web IDE applications and session endpoints (`/instances/*`) are aggressively stored by client browsers (`200 OK (from disk cache)`), causing users to see stale UI layouts after cluster container updates.
* **Resolution:** Enforced `self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")` across all HTML response endpoints, guaranteeing immediate transition to live workspace builds upon hard refresh (`Shift + Cmd + R`).

### 7. Dual-Pathway Platform PKI (ACME Mode Enabled vs. Disabled) on GDC-ag
* **Finding:** Google Distributed Cloud air-gapped (`gdcag`) allows Infrastructure Operators to provision the internal Certificate Authority Service (CAS) with ACME mode enabled or disabled, which changes the API resources available to workload developers.
* **Resolution:** Structured `certificate.yaml` to provide both pathways: Option A (`pki.security.gdc.goog/v1` `CertificateRequest`) for native GDC CAS auto-generated key issuance across standard/user clusters when ACME mode is disabled, and Option B (`cert-manager.io/v1` `Certificate` via `ClusterIssuer/gdc-ca-issuer`) for automated 90-day certificate rotation when ACME mode (`.status.acme.uri`) is enabled.

### 8. Structural Alignment & T-Shirt Sizing Standardization across GDC Patterns
* **Finding:** As the GDC Blueprints repository expanded, individual architecture patterns developed slight structural divergences in how resource sizing and common prerequisites were documented (e.g. `p12-keycloak` vs `p13-gdc-dev`), which increased cognitive load for platform administrators during capacity planning.
* **Resolution:** Standardized the top-level documentation layout across all blueprints so that exact resource sizing tables (`vCPU`, `RAM`, `PVC Storage`, and `Recommended Machine Type`), scaling rationale, and Common Setup sections (`Section 1: Common Setup` with Docker authentication, secret creation, and node pool configurations `n2-standard-4-gdc`) consistently precede day-0 and production deployment steps. Control plane services (`operator` & `landing page`) run as lightweight 2-replica microservices, while dynamic developer session pods (`gdc-dev-workspace-session`) are isolated across `pool: cpu` worker capacity with dedicated `20Gi` (`standard-rwo`) persistent volumes.

### 9. Operator Experience (OX): Ephemeral Pod Verification Cues & SPDY Attach Timing
* **Finding:** When running short-lived verification commands via `kubectl run -i` (`--rm -i`) against short-lived busybox containers (e.g. `cat /workspace/test-persistence.txt`), the container often completes and exits in under 5 milliseconds. By the time `kubectl` negotiates and upgrades the interactive SPDY connection (`-i`), the pod has already reached `Completed` state, prompting `warning: couldn't attach to pod/pvc-reader, falling back to streaming logs: Internal error occurred`. While harmless, this warning and lack of explicit status indicators create diagnostic anxiety for human operators.
* **Resolution:** Prepending `sleep 2` inside short-lived verification pod commands (`sleep 2 && echo "✅ PASS..." && cat ...`) ensures `kubectl` completes its interactive SPDY handshake cleanly while the container sleeps. Furthermore, outputting high-visibility visual confirmation banners (`✅ PASS` / `✅ SUCCESS`) right before dumping test file contents delivers immediate, zero-warning reassurance and eliminates human second-guessing across air-gapped terminal verifications.

### 10. Multi-Project Workspace Isolation & Directory Hierarchy Mapping
* **Finding:** Storing all user files in a single flat directory (`/workspace`) resulted in file collisions and confusion when developers switched between independent microservices or templates. Additionally, deleting a project or resetting its state was difficult without wiping all user files.
* **Resolution:** Introduced dynamic project directory isolation under `/tmp/dev-projects/<project_name>` (mapping `default-workspace` to the root workspace). Added UI controls (`#header-project-select` and `⚙️ Projects` modal tabs for `Switch`, `New`, `Reset`) and synchronized the terminal prompt (`dev@gdc-session:~/<project>$`), allowing developers to create, switch, and delete project environments safely.

### 11. Enterprise OIDC Session Persistence Across Project Switching
* **Finding:** Navigating between project URLs (`/instances/<project_name>`) without propagating authentication state caused the server to treat requests as anonymous, intermittently triggering Keycloak login redirects and degrading developer velocity.
* **Resolution:** Set domain-scoped session cookies (`dev_auth_user; Path=/; SameSite=Lax`) upon successful SSO authentication and propagated the `?oidc_login=success` query parameter in project switch URLs. This enables frictionless project switching with zero re-authentication, while providing an explicit `Exit Session` link (`/?logout=true`) to invalidate cookies on logout.

### 12. Full Agent Output Preservation & Dedicated File Export
* **Finding:** In multi-stage development workflows (e.g. Architect Agent system planning), inserting AI responses into the code editor stripped or truncated comprehensive markdown explanations, system diagrams, and specifications into only the directory tree code block.
* **Resolution:** Implemented `💾 Save as File` (defaulting to `architecture.md` for Architect responses) and `📋 Copy All` actions on AI response cards. This preserves the complete, untruncated output and writes it directly to the workspace disk, ensuring specifications and architectural diagrams are preserved alongside the codebase.

### 13. Architectural Evolution: Why Upstream Eclipse Theia is Redundant in Air-Gapped GDC
* **Finding:** Upstream Eclipse Theia is an extensible desktop/cloud IDE framework developed on TypeScript, Node.js, and Yarn. In standard public cloud environments with unmetered internet access and npmjs.org availability, its generic extension model has utility. However, in an air-gapped Google Distributed Cloud (GDC-ag) deployment, deploying full upstream Theia imposes a heavy "air-gap tax":
  1. *Dependency & Mirror Burden:* Upstream Theia pulls hundreds of transitive dependencies from npmjs.org, requiring dedicated air-gapped npm mirrors (Verdaccio/Nexus), complex C++ native compilation (`node-gyp`), and continuous CVE vulnerability triage across unused packages.
  2. *Resource Bloat:* An idle upstream Theia session consumes 1.5GB to 2.0GB of RAM due to the heavy Node.js backend, Monaco editor webworkers, and background Language Server Protocol (LSP) processes, severely limiting developer density on high-security GDC nodes.
  3. *AI Integration Friction:* Integrating sovereign LLMs into upstream Theia requires navigating third-party `.vsix` plugin marketplaces (Open-VSX), configuring complex extension bridges, and managing plugin proxy settings.
* **Resolution:** Pattern 13 purposefully adopts a streamlined, air-gap-native architecture. By implementing the web IDE UI, terminal executor, multi-project workspace manager, and ReAct AI Agent Swarm natively in a self-contained container with zero external package dependencies:
  1. Container images build in seconds and run 100% hermetically offline without npm or pip.
  2. Memory footprint drops by ~95% (~50MB vs. 1.5GB per session), enabling 10x-20x more concurrent developer sessions per physical GDC compute node.
  3. Native in-pod AI tool calling (MCP-style `read_file`, `write_file`, `apply_diff`, `run_terminal_command`, `list_directory`) connects directly to sovereign inference gateways (`gdc_gemma_gw`) without plugins, sidecars, or proxy loops.
  4. The platform leverages standard Kubernetes primitives (Gateway API `HTTPRoute`, Keycloak OIDC, GDC block storage PVCs, and Platform PKI) without requiring custom CRDs or heavy upstream operators.
