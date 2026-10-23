---
name: gdc-e2e-iac-knitting
description: Knits multi-pattern GDC-blueprints solutions into the 5-stage gdc-iac-org GitOps hierarchy (0-bootstrap to 5-workload-factory).
---

# GDC End-to-End IaC Knitting Skill (`gdc-e2e-iac-knitting`)

Use this skill when composing multiple `GDC-blueprints` patterns (e.g., `p02-genai-rag`, `p12-keycloak`, `gdc_gemma_gw`, `p14-antigravity-dev`) into an end-to-end production topology aligned with `ai_enabled_e2e_gdc_production_iac_guide.md`.

## 1. The 5-Stage GDC IaC Hierarchy

1. **Stage 0 (`0-bootstrap`)**: Initializes Harbor OCI registries, GitLab repositories, and ArgoCD / Config Sync roots.
2. **Stage 1 (`1-org`)**: Declares GDC `Project` namespaces, IAM bindings, and cross-project `ProjectNetworkPolicy` egress/ingress rules.
3. **Stage 2 (`2-resources`)**: Provisions Zonal stateful resources (`DBCluster`, `Bucket`, `VirtualMachine`, `PersistentVolumeClaim` for shared model weights).
4. **Stage 3 (`3-clusters`)**: Configures User Cluster node pools, GPU taints/tolerations (`nvidia.com/gpu`), and StorageClasses (`standard-rwo`, `standard-rwx`).
5. **Stage 4 (`4-platform`)**: Deploys shared platform services (`p12-keycloak` OIDC, `gdc_gemma_gw` Gemma 4 Inference Gateway, `cert-manager` / `pki.security.gdc.goog/v1` `CertificateRequest`, Native GDC `aiplatform.gdc.goog/v1` `Notebook` CRDs).
6. **Stage 5 (`5-workload-factory`)**: Deploys tenant application blueprints via `deployment-config.yaml` and Helmfile.

## 2. Cross-Project Service Discovery & Networking

- In-cluster AI inference requests route to `http://gemma-gateway.gemma-inference.svc.cluster.local/v1` (`NO_PROXY` must include `*.gemma-inference.svc.cluster.local,*.svc.cluster.local,localhost,127.0.0.1`).
- Keycloak OIDC discovery and JWKS validation route to `https://keycloak.gdc.local/realms/gdc-dev-realm`.
- Every cross-namespace dependency requires an explicit `NetworkPolicy` egress rule permitting TCP traffic to the target namespace (`gemma-inference`, `platform`, `kube-system` UDP/TCP 53).
