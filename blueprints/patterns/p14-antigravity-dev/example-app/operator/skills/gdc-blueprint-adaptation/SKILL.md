---
name: gdc-blueprint-adaptation
description: Adapts GDC-blueprints applications across manifests/gdc/ and chart/ with air-gapped Harbor registries and GDC CRDs.
---

# GDC Blueprint Adaptation Skill (`gdc-blueprint-adaptation`)

Use this skill when adapting any application pattern under `~/src/GDC-blueprints` (`p01` through `p14`) for Google Distributed Cloud Air-Gapped (`GDC-ag`).

## 1. Dual-Path Synchronization Rule (`manifests/gdc/` + `chart/`)

Every blueprint in `GDC-blueprints` maintains two deployment representations that MUST remain synchronized:
1. **Static Kustomize / YAML Manifests (`manifests/gdc/`)**: Direct Zonal/User cluster manifests for standalone testing and offline review.
2. **Helm Wrapper Chart (`chart/`)**: Parameterized Helm chart (`Chart.yaml`, `values.yaml`, `values.schema.json`, `templates/apps/workloads.yaml`, `templates/gdc/resources.yaml`) consumed by Stage 5 (`5-workload-factory`).

Whenever you modify a port, environment variable, volume mount, or `NetworkPolicy` in `manifests/gdc/`, you MUST propagate the equivalent parameterized change to `chart/templates/apps/workloads.yaml` and `chart/values.yaml`.

## 2. Air-Gapped Container Registry Rewriting

Public registries (`docker.io`, `gcr.io`, `ghcr.io`, `quay.io`) are unreachable on GDC-ag.
- Rewrite all container `image:` references to `{{ include "<pattern>.registry" . }}/<image-name>:<tag>` in Helm templates or `harbor.gdc.local/blueprint-images/<image-name>:<tag>` in static manifests.
- Ensure `imagePullPolicy: IfNotPresent` is configured for offline Harbor caching.

## 3. Managed GDC Backing Services vs. In-Cluster Containers

- **Stage 2 (`2-resources`) Zonal Services**: Production relational databases (`DBCluster` PostgreSQL / AlloyDB Omni), object storage (`Bucket`), and VM workloads (`VirtualMachine`) are provisioned via core `charts/gdc-dbs` and `charts/gdc-vm` when `gdc.enabled=true`.
- **Stage 5 (`5-workload-factory`) User Cluster Workloads**: Application `Deployment`, `StatefulSet`, `Service`, `HTTPRoute`, and `NetworkPolicy` resources are gated behind `{{- if .Values.apps.enabled }}`.
