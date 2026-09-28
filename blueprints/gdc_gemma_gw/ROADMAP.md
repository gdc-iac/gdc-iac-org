# Development Roadmap: Gemma 4 Gateway Scale-Out

## Phase 1: Gateway Streaming Optimization [x]
- **Status**: Complete
- **Goal**: Fix perceived latency via SSE pass-through in the Python Gateway.
- **Accomplished**: Refactored proxy for streaming SSE, and updated the client to stream tokens live.

## Phase 2: Ollama Serving and Air-Gapped Packaging [x]
- **Status**: Complete
- **Goal**: Build and package baked Ollama images for air-gapped GDC deployment.
- **Accomplished**: Added baked images (`26b`, `31b`), disabled persistence shadowing, created `package-for-gdc.sh` to build blueprint-compliant bundles, and added the GDC Testing Methodology.

## Phase 3: Multi-User Client & Auth Emulation [x]
- **Status**: Complete
- **Goal**: Build a full multi-user client interface and simulate tenant identity workflows.
- **Accomplished**: Built `gemma-client`, connected to gateway, set up database and storage emulators, implemented Workload Identity, provided full automated cleanup, and added a thinking toggle.

## Phase 4: vLLM High-Throughput Swap (Morning - Day 2) [x]
- **Status**: Complete
- **Goal**: Graduate from the Ollama testing backend to the high-performance vLLM production backend.
- **Accomplished**: Deployed the vLLM serving stack unquantized in GKE using standard-rwo dynamially provisioned storage, bypassed HuggingFace gatedHub authorization secrets, resolved Multimodal batch parameters, and verified direct prompt response streams.

## Phase 5: Advanced Admin Features [x]
- **Status**: Complete
- **Goal**: Provide platform administrators with fine-grained management capabilities over tenant traffic.
- **Steps**:
  - **Performance Monitoring**: Provide CPU/GPU metrics for the model serving layer and database.
  - **User Management**: Add features to create, list, and delete client users, and assign standard or admin RBAC access.
  - **Session Oversight**: Monitor active sessions and disconnect individual users instantly via a kill switch.

## Phase 6: Sideloading & Scaling, Sizing (Late Afternoon - Day 2) [x]
- **Status**: Complete
- **Goal**: Guidance for sideloading and scaling up for production enterprise scale AI serving.
- **Accomplished**: Documented unquantized weights GDC staging/packaging pipelines, mapped GKE dynamic standard-rwo volume parameters, and established extensive operations and troubleshooting matrices across quickstarts and sideloading guides.

## Phase 7: Automated Quality Assurance & Testing Matrix [x]
- **Status**: Complete
- **Goal**: Establish a comprehensive unit, integration, and regression testing matrix leveraging Python `pytest`.
- **Steps**:
  - **FastAPI Endpoint Unit Tests**: Write modular unit tests against `gateway/proxy` to assert proxy parameter routing, SSE stream conversions, handling of quantization tags, and vision budget validation without calling real inference servers.
  - **Live Serving Integration Tests**: Build connection validation test scripts implementing `pytest-asyncio` to fire concurrent queries against running Ollama and vLLM server endpoints to secure against upstream API breakages.
  - **Performance Regression Locusts**: Package Locust templates inside the repository to automate streaming response load-testing, enabling testing teams to trigger in-cluster horizontal auto-scaling metrics manually in any cloud workstation or sandbox environment.

## Phase 8: vLLM Simultaneous Dual-Model Orchestration & Staging Mocks [x]
- **Status**: Complete
- **Goal**: Host both Gemma 4 models (26B MoE and 31B Dense) simultaneously using concurrently active vLLM pipelines and enable complexity-aware routing gates.
- **Steps**:
  - **Concurrent Serving Pipelines**: Configure GKE dual-serving Helm matrices to run simultaneous latency-optimized and reasoning-optimized backends.
  - **Prompt Routing Classifier**: Implement a python proxy gateway gatekeeper checking logic tags in inbound requests (such as code, reasoning, mathematics) to dynamically direct user batches.
  - **Testing Mock Fallbacks (GCP GKE Staging)**: Provide a testing mode deploying smaller variants (e.g. Gemma 2B or 7B) as drop-in substitutes on resource-constrained test clusters, preserving routing and parameter evaluation without triggering hardware OOM failures.
  - **Test Rig GPU Scale-Up**: Add guidelines to expand the GCP GKE test rig with another GPU hardware node pool to facilitate live, isolated concurrency testing in the staging phase.

## Phase 9: Production Keycloak OIDC Integration & Staging Validation [x]
- **Status**: Complete
- **Goal**: Address P0 Security Audit Vulnerability #1 (Header-Based Auth Bypass) by implementing production-grade OIDC Keycloak authentication.
- **Accomplished**:
  - **Staging Blueprints & Rollout Plan**: Developed the detailed [gcp-sandbox-keycloak-testing-strategy.md](file:///Users/gmollison/GitHub/gdc_gemma_gw/docs/gcp-sandbox-keycloak-testing-strategy.md) and [keycloak-implementation-rollout-plan.md](file:///Users/gmollison/GitHub/gdc_gemma_gw/docs/keycloak-implementation-rollout-plan.md) blueprints, ensuring dynamic and modular code overrides.
  - **GitOps Auto-Imports & In-Cluster Sandbox Manifests**: Created [keycloak-staging.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/manifests/gcp/keycloak-staging.yaml) and [nginx-ingress-staging.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/manifests/gcp/nginx-ingress-staging.yaml) (resolving liveness probe loops, memory DB discards, and workstation proxy cookie blocks). Exposed and loaded all components under a unified single-origin Port 8081.
  - **Interactive Identity Configurator**: Engineered **[configure-keycloak.sh](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/scripts/configure-keycloak.sh)** to dynamically discover workstation preview subdomains, stage hydrated manifests, and write frontend environment variables without any hardcoded personal settings.
  - **Standardized Production Exposures**: Formulated high-performance GDC-ag compliant Gateway API manifests ([production-gateway-routing.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/manifests/gdc/production-gateway-routing.yaml) template) utilizing new non-retired `HTTPRoute` resources. Standardized all lookups to `gemma-inference` namespace.
  - **Completed Live Verification**: Successfully compiled the React client with baked environment targets, set backend `ENABLE_OIDC="true"`, initiated secure browser redirects, verified dynamic jwt access tokens, and validated active RBAC scopes (Regular User Alice restricted, Admin Charlie bypassed) with 100% green test suite continuity.

## Phase 10: Hardening & Scaling for Disconnected GDC Production (Future Development)
- **Goal**: Deploy true MoE and Dense unquantized weights on multi-GPU disconnected racks and establish zero-trust access boundaries.
- **Steps**:
  - **Production GDC Weights Deploy**: Sideload unquantized Gemma 4 weights persistence mappings onto host-local storage and execute multi-GPU server mounts.
  - **Multi-Node GPU Affinity Gates**: Hardcode taints, tolerations, and GKE NodeAffinity boundaries within standard Helm values to ensure high availability serving across distinct NVIDIA H100/A100 hardware pools.
  - **Service Account Boundary Isolation**: Revoke all direct network/CLI paths to in-cluster storage and PostgreSQL, enforcing transactions to validate securely through dedicated Workload Identity overlays.
  - **OIDC Robustness & Token Resiliency**: Resolve sandbox clock-drift and token validation failures ("Signature has expired") by incorporating configurable clock-skew leeway (e.g., 60s verification leeway in python-jose JWT validator) and extending staging token lifetimes in realm configuration templates.
  - **Dynamic Session-State Routing & Reset Gates**: Resolve the routing "sticky state" issue where queries do not swap back from 31B Dense to 26B MoE within an active chat session. Since the classifier aggregates all past user prompts in the conversation history, old complexity keywords remain active. Refactor the prompt complexity engine to classify either strictly the *last* inbound user prompt or implement dynamic context decay rules.






