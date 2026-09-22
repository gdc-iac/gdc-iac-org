# Gemma 4 Dedicated Inference Gateway - GDC Air-Gapped Production Package

This repository/directory is **100% self-contained** and contains production-ready deployment assets for the **Gemma 4 Dedicated Inference Gateway** on Google Distributed Cloud (GDC) air-gapped environments.

---

## Directory Overview

- **`common-scripts/`**: Self-contained helper scripts:
  - `configure-blueprints.sh`: Parameter injection script (Project ID, Registry Host, Namespace).
  - `build-images.sh`: Automatically checks, builds custom containers, and pulls 3P images locally.
  - `package-for-gdc.sh`: Packaging tool for air-gapped transfer (`ollama`, `vllm`, `client`, or `all`).
  - `model-prep.sh`: Formats and loads Gemma 4 model weights to GDC Persistent Volume Claims (PVCs).
  - `load-images.sh`: Imports container payloads into local `gdcloud` / Harbor registries.
  - `smoke-test.sh`: End-to-end API inference test suite.
- **`blueprints/`**: Helm charts for Ollama (`blueprints/ollama-gke/`) and GPU-accelerated vLLM (`blueprints/vllm-gke/`).
- **`standalone/`**: Direct-to-Cluster (D2C) pre-rendered manifests and `install-all.sh` installation script.
- **`gateway/`**: Gateway proxy router source code (`gateway/proxy/`) and baked model definitions (`gateway/ollama-baked/`).
- **`gemma-client/`**: Gemma 4 GUI web client frontend, backend API, and deployment manifests.
- **`docs/`**: Comprehensive technical guides (vLLM serving, sideloading, admin dashboard, security).
- **`bulk_external_images.txt`**: Consolidated list of container images required for air-gapped registry import.

---

## Standalone Production Deployment Workflow

### Step 1: Configure Target Environment Parameters
Configure target GDC project, container registry, and namespace settings:

```bash
./common-scripts/configure-blueprints.sh -p <target-gdc-project-id> -r harbor.gdc.local/gemma-repo -n gemma-inference
```

### Step 2: Verify and Build Local Container Images
Before packaging or sideloading, build gateway/client containers and pull required 3P images locally (supported targets: `ollama`, `vllm`, `huggingface`, `client`, or `all`):

```bash
# Check, build, and pull images locally by model format
./common-scripts/build-images.sh ollama        # Ollama model images only
./common-scripts/build-images.sh vllm          # vLLM / HuggingFace model images only
./common-scripts/build-images.sh client        # Web GUI Client containers only
./common-scripts/build-images.sh all           # All gateway and client containers
```

### Step 3: Package Gateway Payloads for Air-Gapped Transfer
Package Gemma Gateway manifests and container images into transfer payload tarballs:

```bash
# Package specific backend engine or client GUI
./common-scripts/package-for-gdc.sh ollama        # Ollama model payload
./common-scripts/package-for-gdc.sh vllm          # vLLM / HuggingFace model payload
./common-scripts/package-for-gdc.sh client        # Gemma GUI Client payload
./common-scripts/package-for-gdc.sh all           # Full dual-backend gateway suite

# Fast manifest-only packaging (skips image builds/pulls):
./common-scripts/package-for-gdc.sh --skip-images all
```



### Step 4: Prepare Model Weights & Sideload Container Images
On a connected workstation, stage model weights and import containers:

```bash
# Format and bind model weights to PVCs
./common-scripts/model-prep.sh

# Import container images to GDC registry
./common-scripts/load-images.sh
```

### Step 5: Deploy Inference Gateway (Helm or Direct-to-Cluster)

#### Option A: Direct-to-Cluster (D2C Manifests)
```bash
kubectl create namespace gemma-inference
kubectl apply -f standalone/manifests/ -n gemma-inference
```

#### Option B: Helm Blueprint (Ollama or vLLM)
```bash
# Deploy Ollama Backend
helm upgrade --install gemma-ollama ./blueprints/ollama-gke/ -n gemma-inference

# Deploy vLLM Backend (High Performance GPU)
helm upgrade --install gemma-vllm ./blueprints/vllm-gke/ -n gemma-inference
```

### Step 6: Deploy Gemma GUI Client Application
```bash
kubectl apply -f gemma-client/manifests/ -n gemma-inference
```

### Step 7: Verify Gateway Functionality
Execute the automated smoke test suite:

```bash
./common-scripts/smoke-test.sh
```

---

## Post-Packaging / Post-Unpack Configuration Adjustments

If target GDC Project ID, Harbor container registry URL, or Kubernetes namespace details require changing **after packaging** or **after unpacking** on the target air-gapped environment:

1. Re-execute `configure-blueprints.sh` inside the target directory or unpacked helper directory:
   ```bash
   ./common-scripts/configure-blueprints.sh -p <NEW_PROJECT_ID> -r <NEW_REGISTRY_URL> -n <NEW_NAMESPACE>
   ```
2. This script reads previous parameters from `.configure_state` and dynamically updates all Project IDs, Registry URL hostnames, and Namespace definitions across all K8s YAMLs, Helm values, and deployment scripts without requiring re-building from source.
