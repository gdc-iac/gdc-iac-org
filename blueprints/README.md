Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GDC Air-Gapped Production Deployment Package

This repository/directory is **100% self-contained** and contains production-ready deployment assets for Google Distributed Cloud (GDC) air-gapped environments. It can be moved or copied into an independent repository with zero external dependencies.

> **Note on Managed Services**: On GDC-ag, PostgreSQL databases and object storage are **platform-managed services** provisioned declaratively via Kubernetes Custom Resources (e.g. `DBCluster` via `postgresql.dbadmin.gdc.goog/v1`). Standalone PostgreSQL container images are not required.

---

## Directory Overview

- **`common-scripts/`**: Helper scripts for parameter configuration (`configure-blueprints.sh`), image building (`build-images.sh`), image mirroring (`bulk_mirror_images.sh`), individual pattern packaging (`package-for-gdc.sh`), and unpacking (`unpack-for-gdc.sh`).
- **`patterns/`**: Production manifests, Helm charts, application source code, and implementation guides for individual reference architectures.
- **`gdc_gemma_gw/`**: Self-contained Gemma LLM Gateway blueprints (Ollama & vLLM serving, proxy router, client web app).
- **`docs/implementation-guides/`**: Comprehensive end-to-end architectural implementation guides for target GDC environments.
- **`bulk_external_images.txt`**: Consolidated manifest of all required 3P container images to pull and transfer into air-gapped container registries.

## Standalone Production Deployment Workflow

### Step 1: Configure Target Environment Parameters
Before building images, packaging tarballs, or applying Kubernetes manifests, configure target GDC environment settings (Project ID, Registry Host, Target Namespace):

```bash
./common-scripts/configure-blueprints.sh -p <target-gdc-project-id> -r <target-registry-url> -n <target-namespace>
```
*Example:*
```bash
./common-scripts/configure-blueprints.sh -p my-prod-project -r harbor.gdc.local -n prod-namespace
```

### Step 2: Verify and Build Local Container Images
Before packaging or mirroring, build custom application containers and pull missing 3P images locally. For LLM patterns (e.g. Pattern 5), you can specify model engine filters (`--engine ollama`, `vllm`, `huggingface`, or `both`):

```bash
# Check, build, and pull images for Pattern 5 (Ollama only, vLLM only, or both)
./common-scripts/build-images.sh --engine ollama p5-hybrid-llm-gateway
./common-scripts/build-images.sh --engine vllm p5-hybrid-llm-gateway
./common-scripts/build-images.sh --engine both p5-hybrid-llm-gateway
```

### Step 3: Package Patterns for Air-Gapped Transfer
Package patterns into standalone transfer payload tarballs, supporting **bulk packaging all patterns**, engine selection, and model image omission:

```bash
# Option A: Bulk Package ALL Patterns
./common-scripts/package-for-gdc.sh all                                    # Package ALL patterns (both engines, all images)
./common-scripts/package-for-gdc.sh --engine ollama all                   # Package ALL patterns with Ollama LLM models
./common-scripts/package-for-gdc.sh --skip-llm-models all                 # Package ALL patterns, omitting heavy LLM model images
./common-scripts/package-for-gdc.sh --skip-images all                     # Fast manifest-only packaging for ALL patterns

# Option B: Package a Single Pattern
./common-scripts/package-for-gdc.sh p6-resilient-rag-agent              # Single pattern (RAG Agent)
./common-scripts/package-for-gdc.sh --engine ollama p5-hybrid-llm-gateway # Single pattern with Ollama models
```
This generates standalone payload bundles in `packages/<pattern-name>/` containing manifests, checksums, Bill of Materials (BOM), and container image payloads.




### Step 4: Air-Gapped Image Mirroring & Registry Push
On a connected workstation, mirror 3P container images into tarball archives:

```bash
./common-scripts/bulk_mirror_images.sh ./artifacts/mirrored-images
```
Transfer the `.tar` payloads to your air-gapped environment and push them into your internal GDC registry (e.g. Harbor or Artifact Registry):

```bash
export REGISTRY="harbor.gdc.local/library"
docker load -i ./artifacts/mirrored-images/<image-tarball>.tar
docker tag <image> ${REGISTRY}/<image-name>:latest
docker push ${REGISTRY}/<image-name>:latest
```

### Step 5: Deploy GDC Managed Services & Application Workloads
Provision GDC Managed Services (PostgreSQL DBClusters, Networks, IAM) and application workloads on target GDC clusters:

```bash
# 1. Apply GDC Managed Service CRDs (PostgreSQL DBCluster, Networks)
kubectl apply -f patterns/<pattern-name>/manifests/gdc/db/

# 2. Apply application manifests and services
kubectl apply -f patterns/<pattern-name>/manifests/apps/
```

For Gemma LLM Gateway deployment, navigate to `gdc_gemma_gw/` and follow `gdc_gemma_gw/README.md`.

---

## Post-Packaging / Post-Unpack Configuration Adjustments

If target GDC Project ID, Harbor container registry URL, or Kubernetes namespace details require changing **after packaging** or **after unpacking** on the target air-gapped environment:

1. Re-execute `configure-blueprints.sh` inside the target directory or unpacked helper directory:
   ```bash
   ./common-scripts/configure-blueprints.sh -p <NEW_PROJECT_ID> -r <NEW_REGISTRY_URL> -n <NEW_NAMESPACE>
   ```
2. This script reads previous parameters from `.configure_state` and dynamically updates all Project IDs, Registry URL hostnames, and Namespace definitions across all K8s YAMLs, Helm values, and deployment scripts without requiring re-building from source.
