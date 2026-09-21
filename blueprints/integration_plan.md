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
