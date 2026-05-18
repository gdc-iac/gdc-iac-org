# Workstation Onboarding & Tool Setup Guide

This guide helps operators prepare their local workstation to deploy and manage the GDC Hosted `gdc-ag-foundations` IaC repository.

---

## 1. Tool Requirements & Installation

The following versions are verified and recommended for secure, air-gapped GDC Hosted operations:

| Tool | Recommended Version | Installation Command |
| :--- | :--- | :--- |
| **kubectl** | `v1.32.x` | `curl -LO "https://dl.k8s.io/release/v1.32.0/bin/linux/amd64/kubectl" && sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl` |
| **helm** | `v3.17.x` | `curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 && chmod 700 get_helm.sh && ./get_helm.sh` |
| **helmfile** | `v1.2.1` | Download binary release from [Helmfile Releases](https://github.com/helmfile/helmfile/releases) and copy to `/usr/local/bin/helmfile` |
| **sops** | `v3.9.x` | Download binary release from [SOPS Releases](https://github.com/getsops/sops/releases) and copy to `/usr/local/bin/sops` |
| **age** | `v1.2.x` | `sudo apt-get install age` (or direct binary placement from Age GitHub) |

### Required Helm Plugins
Install the critical plugins for dynamic secrets handling and diff checks:
```bash
# Install Helm Diff plugin (required for helmfile diff)
helm plugin install https://github.com/databus23/helm-diff

# Install Helm Secrets plugin (required for SOPS decryptions)
helm plugin install https://github.com/jkroepke/helm-secrets
```

---

## 2. GDC Hosted CLI Authentication

GDC Hosted enforces multi-context administration. Operators must authenticate and toggle between two target control planes:

### A. Global Control Plane (Global Admin Services)
* Scope: Declaring organizational policies, billing bindings, and projects creation.
* Target API endpoint: `global-api.<gdc-system-domain>`

To authenticate your kubecontext:
```bash
# Pull GDC Hosted login CLI tools (provided in your regional operator partition)
gdch-auth login --domain=<gdc-system-domain> --username=<admin-username>

# Verify connection to Global API Server
kubectl config use-context global-api-context
kubectl get projects --all-namespaces
```

### B. Zonal Control Plane (Zonal Workload Services)
* Scope: Declaring applications resources, databases, storage, clusters, and notebooks inside projects.
* Target API endpoint: `zone-api.<gdc-system-domain>`

```bash
# Verify connection to Zonal API Server
kubectl config use-context zone-api-context
kubectl get clusters -n platform
```

---

## 3. Local GitOps Validation

Before committing any changes or triggering execution pipelines, run the local validation harness from the repository root:
```bash
# Syntactically lint and template-validate all environment configurations
./scripts/validate.sh dev
```
This will verify that all dynamic templates render safely and validate perfectly against strict `values.schema.json` rules.
