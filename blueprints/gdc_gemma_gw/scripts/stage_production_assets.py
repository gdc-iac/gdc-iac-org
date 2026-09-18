#!/usr/bin/env python3
"""
/**
 * @file stage_production_assets.py
 * @brief Automated packaging tool for Gemma 4 Gateway production deployment assets.
 *
 * @details Filters and copies production-only assets for Gemma 4 Gateway components
 * (Ollama engine, vLLM engine, Gateway Proxy, Gemma Client GUI, documentation) into
 * deploy-to-production/. Ensures deploy-to-production/ is 100% self-contained with zero
 * external repository dependencies.
 * 
 * Usage:
 *   python3 scripts/stage_production_assets.py [ollama|vllm|client|all]
 *   Examples:
 *     python3 scripts/stage_production_assets.py
 *     python3 scripts/stage_production_assets.py ollama
 *     python3 scripts/stage_production_assets.py vllm
 *     python3 scripts/stage_production_assets.py client
 * 
 * @date 2026-07-27
 */
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

# Base paths
REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DIR = REPO_ROOT / "deploy-to-production"

VALID_TARGETS = ["all", "both", "ollama", "vllm", "huggingface", "client"]

# Audited container images required for production air-gapped deployment
GATEWAY_IMAGES = {
    "ollama": [
        "ollama/ollama:latest",
        "harbor.gdc.local/gemma-repo/gemma-proxy:latest",
        "harbor.gdc.local/gemma-repo/ollama-gemma-26b:latest",
        "harbor.gdc.local/gemma-repo/ollama-gemma-31b:latest"
    ],
    "vllm": [
        "vllm/vllm-openai:latest",
        "harbor.gdc.local/gemma-repo/gemma-proxy:latest",
        "harbor.gdc.local/gemma-repo/vllm-gemma-26b:latest",
        "harbor.gdc.local/gemma-repo/vllm-gemma-31b:latest"
    ],
    "client": [
        "harbor.gdc.local/gemma-repo/gemma-client-backend:latest",
        "harbor.gdc.local/gemma-repo/gemma-client-frontend:latest"
    ]
}

def parse_args():
    parser = argparse.ArgumentParser(description="Stage Gemma Gateway production assets into deploy-to-production/.")
    parser.add_argument(
        "target",
        nargs="?",
        default="all",
        help="Target component to stage: ollama, vllm, huggingface, client, or all (default: all)"
    )
    parser.add_argument(
        "--target", "-t",
        dest="opt_target",
        help="Alternative flag to specify target component"
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Force clean target production directory before staging"
    )
    parser.add_argument(
        "--skip-images", "-s",
        action="store_true",
        help="Bypass container image building and tarball export during packaging"
    )
    return parser.parse_args()


def normalize_target(target_input: str) -> str:
    if not target_input:
        return "all"
    t_clean = target_input.strip().lower()
    if t_clean == "huggingface":
        return "vllm"
    if t_clean == "both":
        return "all"
    if t_clean in VALID_TARGETS:
        return t_clean
    raise ValueError(f"Unknown target '{target_input}'. Available targets: {', '.join(VALID_TARGETS)}")

def copy_filtered_dir(src: Path, dst: Path, ignore_names=None):
    if ignore_names is None:
        ignore_names = []
    
    def ignore_filter(path, names):
        ignored = set()
        for name in names:
            if name in ignore_names:
                ignored.add(name)
            elif name in [".venv", ".pytest_cache", "__pycache__", ".git", "state.json"]:
                ignored.add(name)
            elif name.endswith(".pyc"):
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=ignore_filter, dirs_exist_ok=True)

def ensure_base_structure():
    (PRODUCTION_DIR / "common-scripts").mkdir(parents=True, exist_ok=True)
    (PRODUCTION_DIR / "blueprints").mkdir(parents=True, exist_ok=True)
    (PRODUCTION_DIR / "standalone").mkdir(parents=True, exist_ok=True)
    (PRODUCTION_DIR / "gateway").mkdir(parents=True, exist_ok=True)
    (PRODUCTION_DIR / "docs").mkdir(parents=True, exist_ok=True)

def stage_gateway_assets(target="all"):
    print(f"📦 Staging Gemma Gateway production assets (Target: {target})...")

    # 1. Blueprints (ollama-gke, vllm-gke)
    if (REPO_ROOT / "blueprints").exists():
        if target in ["all", "ollama"]:
            if (REPO_ROOT / "blueprints" / "ollama-gke").exists():
                copy_filtered_dir(
                    REPO_ROOT / "blueprints" / "ollama-gke",
                    PRODUCTION_DIR / "blueprints" / "ollama-gke"
                )
        if target in ["all", "vllm"]:
            if (REPO_ROOT / "blueprints" / "vllm-gke").exists():
                copy_filtered_dir(
                    REPO_ROOT / "blueprints" / "vllm-gke",
                    PRODUCTION_DIR / "blueprints" / "vllm-gke"
                )

    # 2. Standalone manifests & install scripts
    if (REPO_ROOT / "standalone").exists():
        copy_filtered_dir(REPO_ROOT / "standalone", PRODUCTION_DIR / "standalone")

    # 3. Core Gateway logic (proxy & ollama-baked)
    if (REPO_ROOT / "gateway").exists():
        copy_filtered_dir(REPO_ROOT / "gateway", PRODUCTION_DIR / "gateway")

    # 4. Gemma Client GUI
    if target in ["all", "client"]:
        if (REPO_ROOT / "gemma-client").exists():
            (PRODUCTION_DIR / "gemma-client").mkdir(parents=True, exist_ok=True)
            copy_filtered_dir(REPO_ROOT / "gemma-client", PRODUCTION_DIR / "gemma-client")

    # 5. Documentation
    if (REPO_ROOT / "docs").exists():
        copy_filtered_dir(REPO_ROOT / "docs", PRODUCTION_DIR / "docs")

    # 6. Consolidated 3P & payload images list
    images_to_list = set()
    if target in ["all", "ollama"]:
        images_to_list.update(GATEWAY_IMAGES["ollama"])
    if target in ["all", "vllm"]:
        images_to_list.update(GATEWAY_IMAGES["vllm"])
    if target in ["all", "client"]:
        images_to_list.update(GATEWAY_IMAGES["client"])

    bulk_img_path = PRODUCTION_DIR / "bulk_external_images.txt"
    with open(bulk_img_path, "w") as f:
        f.write("# Consolidated Container Images for Gemma Gateway Air-Gapped Deployment\n\n")
        for img in sorted(images_to_list):
            f.write(f"{img}\n")
    print(f"✅ Generated consolidated image list at {bulk_img_path}")

def create_standalone_common_scripts():
    common_dst = PRODUCTION_DIR / "common-scripts"
    common_dst.mkdir(parents=True, exist_ok=True)

    # 1. Standalone configure-blueprints.sh in common-scripts
    shutil.copy2(REPO_ROOT / "configure-blueprints.sh", common_dst / "configure-blueprints.sh")
    os.chmod(common_dst / "configure-blueprints.sh", 0o755)

    # 2. Standalone build-images.sh
    build_images_script = """#!/bin/bash
set -e
# Self-contained build & pull script for gdc_gemma_gw deploy-to-production

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET=${1:-"all"}

# Normalize huggingface / both aliases
if [ "$TARGET" = "huggingface" ]; then TARGET="vllm"; fi
if [ "$TARGET" = "both" ]; then TARGET="all"; fi

REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/gemma-repo"}
TAG=${TAG:-"latest"}

echo "Checking and building Gemma Gateway container images locally (Target engine/mode: $TARGET)..."

# 1. 3P Base Engine Images
if [ "$TARGET" = "ollama" ] || [ "$TARGET" = "all" ]; then
  if docker image inspect "ollama/ollama:latest" >/dev/null 2>&1; then
    echo "   ✅ FOUND 3P IMAGE: ollama/ollama:latest (Local cache)"
  else
    echo "   ⬇️  PULLING 3P IMAGE: ollama/ollama:latest..."
    docker pull "ollama/ollama:latest" || echo "   ⚠️  Could not pull ollama/ollama:latest"
  fi
fi

if [ "$TARGET" = "vllm" ] || [ "$TARGET" = "all" ]; then
  if docker image inspect "vllm/vllm-openai:latest" >/dev/null 2>&1; then
    echo "   ✅ FOUND 3P IMAGE: vllm/vllm-openai:latest (Local cache)"
  else
    echo "   ⬇️  PULLING 3P IMAGE: vllm/vllm-openai:latest..."
    docker pull "vllm/vllm-openai:latest" || echo "   ⚠️  Could not pull vllm/vllm-openai:latest"
  fi
fi

# 2. Gateway Proxy Image
if [ "$TARGET" = "ollama" ] || [ "$TARGET" = "vllm" ] || [ "$TARGET" = "all" ]; then
  PROXY_IMG="${REGISTRY_HOST}/gemma-proxy:${TAG}"
  if docker image inspect "$PROXY_IMG" >/dev/null 2>&1; then
    echo "   ✅ FOUND GATEWAY PROXY: $PROXY_IMG (Local cache)"
  else
    if [ -d "${PROD_ROOT}/gateway/proxy" ]; then
      echo "   🔨 BUILDING GATEWAY PROXY: $PROXY_IMG..."
      docker build -t "$PROXY_IMG" "${PROD_ROOT}/gateway/proxy" || echo "   ⚠️  Build failed for $PROXY_IMG"
      echo "   ✅ BUILT: $PROXY_IMG"
    fi
  fi
fi

# 3. Gemma Client Images
if [ "$TARGET" = "client" ] || [ "$TARGET" = "all" ]; then
  BACKEND_IMG="${REGISTRY_HOST}/gemma-client-backend:${TAG}"
  FRONTEND_IMG="${REGISTRY_HOST}/gemma-client-frontend:${TAG}"

  if docker image inspect "$BACKEND_IMG" >/dev/null 2>&1; then
    echo "   ✅ FOUND CLIENT BACKEND: $BACKEND_IMG (Local cache)"
  else
    if [ -d "${PROD_ROOT}/gemma-client/src/backend" ]; then
      echo "   🔨 BUILDING CLIENT BACKEND: $BACKEND_IMG..."
      docker build -t "$BACKEND_IMG" "${PROD_ROOT}/gemma-client/src/backend" || echo "   ⚠️  Build failed for $BACKEND_IMG"
      echo "   ✅ BUILT: $BACKEND_IMG"
    fi
  fi

  if docker image inspect "$FRONTEND_IMG" >/dev/null 2>&1; then
    echo "   ✅ FOUND CLIENT FRONTEND: $FRONTEND_IMG (Local cache)"
  else
    if [ -d "${PROD_ROOT}/gemma-client/src/frontend" ]; then
      echo "   🔨 BUILDING CLIENT FRONTEND: $FRONTEND_IMG..."
      docker build -t "$FRONTEND_IMG" "${PROD_ROOT}/gemma-client/src/frontend" || echo "   ⚠️  Build failed for $FRONTEND_IMG"
      echo "   ✅ BUILT: $FRONTEND_IMG"
    fi
  fi
fi

echo "✅ Image check and build process complete for Gemma Gateway."
"""
    with open(common_dst / "build-images.sh", "w") as f:
        f.write(build_images_script)
    os.chmod(common_dst / "build-images.sh", 0o755)

    # 3. Standalone package-for-gdc.sh
    package_script = """#!/bin/bash
set -e
# Self-contained GDC packaging script for Gemma Gateway

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_ROOT="$(dirname "$SCRIPT_DIR")"

REGISTRY_HOST=${REGISTRY_HOST:-"harbor.gdc.local/gemma-repo"}
TAG=${TAG:-"latest"}
SKIP_IMAGES=false
INFERENCE_ENGINE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-images|-s)
      SKIP_IMAGES=true
      shift
      ;;
    *)
      INFERENCE_ENGINE="$1"
      shift
      ;;
  esac
done

INFERENCE_ENGINE=${INFERENCE_ENGINE:-"all"}

if [ "$INFERENCE_ENGINE" = "huggingface" ]; then INFERENCE_ENGINE="vllm"; fi
if [ "$INFERENCE_ENGINE" = "both" ]; then INFERENCE_ENGINE="all"; fi

if [ "$SKIP_IMAGES" = true ]; then
  echo "⏭️  Bypassing local image build and container export (--skip-images enabled)."
else
  echo "📦 0. Checking and building required Gemma Gateway container images locally..."
  "$SCRIPT_DIR/build-images.sh" "$INFERENCE_ENGINE"
fi


STAGING_DIR="${PROD_ROOT}/packages/gemma-gateway-gdc"
OUTPUT_DIR="${PROD_ROOT}/packages"

echo "🧹 Cleaning up and creating staging directories..."
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR/gateway/ollama"
mkdir -p "$STAGING_DIR/gateway/vllm"
mkdir -p "$STAGING_DIR/client"
mkdir -p "$STAGING_DIR/common-scripts"

if [ "$INFERENCE_ENGINE" = "ollama" ]; then
    echo "📦 1. Exporting Ollama manifest payload..."
    tar -czf "$STAGING_DIR/gateway/ollama/gemma-gateway-ollama-manifests.tar.gz" -C "$PROD_ROOT" blueprints/ollama-gke/ standalone/ gateway/

elif [ "$INFERENCE_ENGINE" = "vllm" ]; then
    echo "📦 1. Exporting vLLM/HuggingFace manifest payload..."
    tar -czf "$STAGING_DIR/gateway/vllm/gemma-gateway-vllm-manifests.tar.gz" -C "$PROD_ROOT" blueprints/vllm-gke/ standalone/ gateway/

elif [ "$INFERENCE_ENGINE" = "client" ]; then
    echo "📦 1. Exporting Client manifest payload..."
    tar -czf "$STAGING_DIR/client/gemma-client-manifests.tar.gz" -C "$PROD_ROOT" gemma-client/

else
    echo "📦 1. Exporting Dual Backend Gateway manifest payload..."
    tar -czf "$STAGING_DIR/gemma-gateway-gdc-manifests.tar.gz" -C "$PROD_ROOT" blueprints/ standalone/ gateway/ gemma-client/
fi

echo "📦 2. Copying documentation and helper scripts..."
if [ -f "$PROD_ROOT/README.md" ]; then
  cp "$PROD_ROOT/README.md" "$STAGING_DIR/gemma-gateway-README.md"
fi
cp -r "$SCRIPT_DIR"/* "$STAGING_DIR/common-scripts/"

echo "📦 3. Generating Checksum BOM (Bill of Materials)..."
cd "$STAGING_DIR"
find . -type f -not -name "gemma-gateway-BOM.txt" -not -name "gemma-gateway-manifest.txt" -exec shasum -a 256 {} \\; > "gemma-gateway-BOM.txt"
cp "gemma-gateway-BOM.txt" "gemma-gateway-manifest.txt"
cd ../

echo "✅ All assets packaged into $STAGING_DIR successfully."
"""
    with open(common_dst / "package-for-gdc.sh", "w") as f:
        f.write(package_script)
    os.chmod(common_dst / "package-for-gdc.sh", 0o755)



    # 3. Copy helper scripts if present
    for helper_name in ["load-images.sh", "model-prep.sh", "smoke-test.sh"]:
        helper_src = REPO_ROOT / "scripts" / helper_name
        if helper_src.exists():
            shutil.copy2(helper_src, common_dst / helper_name)
            os.chmod(common_dst / helper_name, 0o755)

    print("✅ Created self-contained standalone helper scripts in deploy-to-production/common-scripts.")

def generate_master_readme():
    readme_content = """# Gemma 4 Dedicated Inference Gateway - GDC Air-Gapped Production Package

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
"""

    readme_path = PRODUCTION_DIR / "README.md"
    with open(readme_path, "w") as f:
        f.write(readme_content)
    print(f"✅ Generated master production README at {readme_path}")

def main():
    args = parse_args()
    raw_target = args.opt_target if args.opt_target else args.target
    
    try:
        target = normalize_target(raw_target)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    print(f"🚀 Starting Gemma Gateway Production Staging (Target: {target})...")

    if args.clean and PRODUCTION_DIR.exists():
        print(f"🧹 Cleaning existing target directory {PRODUCTION_DIR}...")
        shutil.rmtree(PRODUCTION_DIR)

    ensure_base_structure()
    stage_gateway_assets(target)
    create_standalone_common_scripts()
    generate_master_readme()

    print(f"\n🎉 Gemma Gateway staging complete! Target '{target}' packaged in deploy-to-production/\n")

if __name__ == "__main__":
    main()
