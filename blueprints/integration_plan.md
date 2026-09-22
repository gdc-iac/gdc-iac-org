# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Plan: Integrating GDC Blueprint Patterns with IaC Framework (Issue #54)

## Objective
Align `blueprints/patterns` (`p1` through `p13`) with the core IaC orchestration framework (`foundations/` and `charts/`) while preserving standalone deployments (`kubectl apply -f manifests/`).

## Scope
- **Patterns**: `blueprints/patterns/p*/chart/` (`p1`, `p3`, `p4`, `p5`, `p6`, `p7`, `p8`, `p10`, `p11`, `p12`, `p13`)
- **Foundations Orchestration**: `foundations/releases/5-patterns/` (`helmfile.yaml.gotmpl`, `patterns.yaml.gotmpl`), `foundations/helmfile.yaml`, `foundations/bases/environments/*/charts.yaml`
- **Validation & Tooling**: `scripts/test-charts.sh`, `blueprints/common-scripts/configure-blueprints.sh`
- **Documentation**: `blueprints/patterns/p*/README.md`, `blueprints/docs/implementation-guides/*.md`, `foundations/README.md`

## Architecture & Control-Plane Separation

### 1. Wrapper Charts (`blueprints/patterns/<pattern>/chart/`)
Each pattern includes a lightweight Helm chart wrapping its resources into two gated template groups:
- **User Cluster Workloads (`templates/apps/workloads.yaml`, gated by `apps.enabled: true`)**:
  Deploys standard Kubernetes resources (`Deployment`, `StatefulSet`, `Service`, `GatewayClass`, `Gateway`, `HTTPRoute`, `CronJob`, `ConfigMap`, `Secret`, `ServiceAccount`, `NetworkPolicy`) to the target User Cluster context in Stage 5 (`5-patterns`).
- **Zonal GDC Resources (`templates/gdc/resources.yaml`, gated by `gdc.enabled: false`)**:
  In the layered IaC framework, Stage 2 (`2-resources`) provisions Zonal managed databases (`DBCluster`), Virtual Machines (`VirtualMachine`), and Buckets (`Bucket`) via the core `charts/gdc-dbs`, `charts/gdc-vm`, and `charts/gdc-buckets` charts. Consequently, `gdc.enabled` defaults to `false` for Stage 5 User Cluster deployments, while remaining available (`--set gdc.enabled=true`) for operators who want to deploy Zonal CRDs directly from the wrapper chart.
- **Day-2 Failover Protection (`templates/gdc/failover.yaml`, gated by `gdc.failover.enabled: false`)**:
  Prevents `fleet.dbadmin.gdc.goog/v1/Failover` resources from triggering unintended database failovers during automated Helmfile / ArgoCD syncs.

### 2. Zero Regression on Standalone `manifests/`
- All `blueprints/patterns/*/manifests/` directories remain untouched for `kubectl apply -f manifests/`.
- `blueprints/common-scripts/configure-blueprints.sh` excludes `*/chart/*` and `*/charts/*` paths so `sed` replacements on standalone manifests never mutate Helm templates or `values.yaml`.

---

## 3. Stepping-Stone Validation vs. GDC-ag Confidence Boundaries

### 3.1 Verified on GCP / GKE Stepping-Stone (`gke-l7-rilb` + Dataplane V2)
- **Kubernetes Gateway API Routing (`gateway.networking.k8s.io/v1`)**: Validated `Gateway/gdc-platform-gateway` (`gke-l7-rilb`), `HTTPRoute/gemma-gateway-route`, and `HTTPRoute/gemma-unified-routes` with `RequestHeaderModifier` (`X-Forwarded-Proto: https`) for edge TLS termination.
- **Keycloak OIDC SSO (`gdc-rag-realm`)**: Validated RS256 token issuance, `/auth/realms/master` readiness probing on port `8080`, and backend JWT verification.
- **High-Concurrency RAG & SQL Analyst Resilience**: Configured `Deployment/backend` with 4 Uvicorn workers (`--workers 4`), offloaded synchronous OpenAI client calls via `asyncio.to_thread`, and attached 300s `GCPBackendPolicy` + `/health` `HealthCheckPolicy` definitions to prevent health-check starvation (`503 Service Unavailable`) during multi-document RAG synthesis.
- **Auto-Initialized Database Schema**: Added idempotent `Database._init_schema()` inside `gemma-client/src/backend/database.py` so all 9 tables (`chats`, `messages`, `files`, `sensor_telemetry`, `military_units`, `equipment_inventory`, `fuel_and_supplies`, `convoy_routes`, `intelligence_reports`) are automatically created on startup even when connected to a fresh GDC `DBCluster`.
- **Side-by-Side Gemma 4 Inference (`ollama-26b` + `ollama-31b`)**: Validated simultaneous L4 GPU serving and dynamic prompt classification behind `gemma-gateway`.

### 3.2 Remaining GDC-ag Confidence Boundaries (Pre-Flight Checklist for Air-Gapped Cutover)
Because GKE Stepping-Stone clusters emulate GDC using standard Kubernetes `StatefulSet` (`postgres-0`) and GKE Gateway controllers (`gke-l7-rilb`), operators deploying to physical **GDC Air-Gapped (`GDC-ag`)** environments via `foundations/` (`Helmfile` / `ArgoCD`) must verify the following four boundaries during cutover:

1. **Stage 2 Zonal `DBCluster` Secret Projection (`gemma-client-db-credentials`)**:
   - *Risk*: On GDC-ag, `DBCluster` (`postgresql.dbadmin.gdc.goog/v1`) is provisioned in Stage 2 (`2-resources` Zonal Management Plane), whereas `gemma-client` deploys in Stage 5 (`5-patterns` User Cluster) and reads `Secret/gemma-client-db-credentials` (key: `connection_string`).
   - *Mitigation / Check*: Confirm that `p0-dga-factory` (`dga-secret-sync`) or the operator secret-projection workflow populates `Secret/gemma-client-db-credentials` with a valid `connection_string` (`postgresql://<user>:<password>@<dbcluster-vip>:5432/<dbname>`) in the target User Cluster namespace prior to Stage 5 rollout.
2. **Parent Gateway Namespace & Hostname Binding (`gdc-platform-gateway`)**:
   - *Risk*: `HTTPRoute/gemma-unified-routes` defaults to `parentRefs: [{name: gdc-platform-gateway, namespace: gemma-inference}]` with wildcard hostname matching (`apps.hostnames: []`).
   - *Mitigation / Check*: On GDC-ag, if the platform `Gateway` resides in a central ingress namespace or enforces strict hostname matching, set `apps.hostnames: ["app.gdc.local"]` in `values.yaml` and ensure the parent `Gateway` listener sets `allowedRoutes.namespaces.from: All`.
3. **Harbor Registry Image Paths & Vite Build-Time OIDC Coordinates**:
   - *Risk*: `configure-blueprints.sh` intentionally skips `*/chart/*` directories so Helm templates remain parameterized via `.Values.global.registry`. In addition, the React frontend (`gemma-client-frontend`) compiles `.env` (`VITE_KEYCLOAK_URL`) into static assets at `docker build` time.
   - *Mitigation / Check*: Pass `global.registry` (`harbor.gdc.local/<project>`) and `global.imagePullSecrets` via Helmfile environment values, and run `./gemma-client/scripts/configure-keycloak.sh` with the target GDC-ag ingress FQDN (`https://app.gdc.local`) **before** running `./gemma-client/scripts/build.sh` and packaging images for Harbor transfer.
4. **Operational Demo Dataset Seeding against Managed `DBCluster`**:
   - *Risk*: While `Database._init_schema()` automatically creates all 9 tables on first connection to an empty `DBCluster`, it does not insert synthetic demo rows unless `scripts/populate-db.sh` is run.
   - *Mitigation / Check*: If the *Operation Vanguard Shield* demo dataset is required on GDC-ag, execute `psql "${DATABASE_URL}" -f test-data/seed_readiness_db.sql` from an admin pod or workstation with network reachability to the `DBCluster` VIP.
