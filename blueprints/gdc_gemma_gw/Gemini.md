This consolidated document serves as the comprehensive guidance for developing the **Gemma 4 Dedicated Inference Gateway** on **Google Distributed Cloud air-gapped (GDC-ag)**. It integrates both the high-level requirements and the specific technical competencies required for an agentic coding system to execute the build, accounting for both GitOps and manual testing workflows.

---

**Note that GKE, kubectl, helm and gdcloud are not available on this laptop and all testing will need to be undertaken against a GKE  GPU enabled cluster accessible via a Google cloud workstation**

**You can undertake all non destructive commands on thsi laptop such as grep, find etc togather with using the AI tools such as Gemini to help with development. You may not use them to test any infrastructure changes.**

Create sample apps to showcase hw to use this gateway . Use python and emulate access to GDC services as per the  ../GDC-blueprints/ .

**Refer to ../GDC-blueprints/ for guidance on what needs doing . 
Provide commands to set up the testing environment as part of this standalone repo and instructions on how to configure on GDC-air-gapped.**

* Solution reference docs assume that the end user will be taking only what is requireed to deploy to the production GDC-ag platform so there should be no reference to gotchas encountered on the testing GCP emulation environment in those documents

# Blueprint: Gemma 4 Dedicated Inference Gateway (GDC-ag)

## 1\. Project Overview & Guiding Principles

This project delivers a resilient, secure, and high-performance inference gateway specifically for Gemma 4 variants. It is designed to operate in high-security, air-gapped environments.

* **Security First:** Strictly follows DevSecOps principles and GDC-ag hardening guidelines.  
* **Architectural Flexibility:** Supports both **Ollama** (default/testing) and **vLLM** (high-performance) inference backends.  
* **Dual-Path Deployment:** Supports **GitOps** (GitLab \+ ConfigSync) or **Direct-to-Cluster** (Manual `kubectl` \+ Helm) for testing environments lacking a private GitLab.
* **Add additional unit tests and update the integration tests after new functionality or major code changes to ensure no regressions** 
* **Ensure unit tests and integration tests using pytest as preference or shell or python scripts as required - create examples for testing purposes** 
* **if using python locally on this laptop use virtualenv**
* **Record any lessons learned and keep track of progress** 
* **You can carry out non destructive actions such as reading files without seeking approval**

---

## 2\. Software Requirements Specification (SRS)

### 2.1 Functional Requirements

* **Model Variant Support:**  
  * **Gemma 4 26B A4B (MoE):** Default for balanced efficiency.  
  * **Gemma 4 31B (Dense):** Selectable for complex reasoning.  
* **Multimodal Capabilities:** Support for Text (256K context) and Vision/Video.  
* **Admin Control Plane:** A web interface to adjust:  
  * **Model Parameters:** Temperature, Top-P, Frequency Penalty.  
  * **Vision Token Budgets:** Variable resolution selection (70, 140, 280, 560, or 1120 tokens).  
* **Scaling:** Automated scaling via GKE to manage GPU-intensive workloads.

### 2.2 Technical & GDC-ag Constraints

* **Air-Gapped Sideloading:** All container images and model weights must be imported into the local `gdcloud` registry and local Persistent Volumes.  
* **Dual Inference Engines:**  
  * **Ollama:** Standardized API for rapid agentic integration.  
  * **vLLM:** Advanced PagedAttention support for high-throughput requirements.  
* **Networking:** Integration with GDC-ag hardware load balancers and internal Ingress Controllers.

### 2.3 Deployment Paths

| Feature | Path A: Production (GitOps) | Path B: Testing (D2C) |
| :---- | :---- | :---- |
| **Source of Truth** | GitLab Enterprise | Local Filesystem / `kubectl` |
| **Sync Mechanism** | ConfigSync | Manual `helm install` |
| **Configuration** | Git-based Manifests | `values-testing.yaml` |

---

## 3\. Skills & Competencies Ledger

### 3.1 Infrastructure & Orchestration

* **GDC-ag Native Tooling:** Mastery of `gdcloud` CLI, `kubectl`, and `helm`.  
* **Storage Management:** Provisioning and managing local Persistent Volume Claims (PVCs) for model weight persistence.  
* **GPU Orchestration:** Configuring NVIDIA runtime classes and resource limits within GKE.

### 3.2 Inference Engineering

* **MoE Optimization:** Deep understanding of Mixture-of-Experts routing logic to optimize 26B A4B performance.  
* **API Design:** Implementation of OpenAI-compatible endpoints with custom extensions for Gemma 4 vision token budgets.

### 3.3 DevSecOps & Troubleshooting

* **Image Hardening:** Creating secure, rootless container images compatible with GDC-ag security policies.  
* **Air-Gapped Debugging:** Ability to diagnose pod failures, driver mismatches, and networking bottlenecks using `kubectl logs` and `describe` without external telemetry.

---

## 4\. Repository Structure (Template-Pattern)

```
/gemma4-inference-gateway
├── README.md                 # Top-level instructions, assumptions, and GDC-ag logic
├── blueprints/
│   ├── ollama-gke/           # Primary: Ollama deployment charts
│   └── vllm-gke/             # Alternative: vLLM GPU-optimized charts
├── standalone/               # Direct-to-Cluster (D2C) Testing Path
│   ├── manifests/            # Pre-rendered YAMLs for 'kubectl apply'
│   └── install-all.sh        # Deployment script for non-GitLab environments
├── gateway/
│   ├── admin-ui/             # React/Next.js dashboard for Gemma 4 parameters
│   └── proxy/                # Python/Go routing layer
├── docs/
│   ├── testing-methodology.md# GKE validation steps for air-gapped clusters
│   └── sideloading-guide.md  # Instructions for importing images/weights
└── scripts/
    ├── load-images.sh        # Pushes images to local GDC-ag registry
    └── model-prep.sh         # Formats and loads Gemma 4 weights to PVCs
```

---

## 5\. Deployment Instructions (Direct-to-Cluster Fallback)

In environments without GitLab, the agent shall execute the following:

1. **Hydrate Manifests:** Use `helm template ./blueprints/ollama-gke > standalone/manifests/deploy.yaml`.  
2. **Import Artifacts:** Use `gdcloud container images import` for the gateway and inference engine images.  
3. **Bootstrap Storage:** Apply storage manifests and ensure PVs are bound to host-local or shared GDC-ag storage.  
4. **Execute Deployment:**

```shell
kubectl create namespace gemma-inference
kubectl apply -f standalone/manifests/ -n gemma-inference
```

5. **Verify & Tune:** Access the Admin UI via the GDC-ag LoadBalancer IP to configure the 26B/31B model parameters.

---

## 6\. Final Compliance Check

* **Zero External Dependencies:** No `github.com` or `docker.io` references in final manifests.  
* **Consistency:** All paths (GitOps or Manual) use the same underlying Helm charts to ensure parity between testing and production.
* **Production Export Bundle & Re-Staging Workflow:**
  * Ensure that all updates to `blueprints/ollama-gke`, `blueprints/vllm-gke`, `standalone/` (`manifests/` and `chart/`), `gemma-client/` (`manifests/` and `chart/`), gateway proxy, admin UI, or docs keep the Helm wrapper charts (`chart/`) and raw `manifests/` synchronized.
  * Keep `standalone/chart/values.yaml` and `gemma-client/chart/values.yaml` defaulted to `gdc.enabled: false` and `apps.enabled: true` for Stage 5 (`foundations/releases/5-workload-factory`) Helmfile orchestration, while preserving `manifests/gcp/` for GCP Stepping-Stone testing.
  * Update the self-contained production bundle in `deploy-to-production/` and propagate downstream using the 3-step sequence:
    1. Re-stage `gdc_gemma_gw`:
       ```bash
       cd ~/src/gdc_gemma_gw
       python3 scripts/stage_production_assets.py all --skip-images
       ```
    2. Re-stage `GDC-blueprints` (which ingests `../gdc_gemma_gw/deploy-to-production/` into `GDC-blueprints/deploy-to-production/gdc_gemma_gw/`):
       ```bash
       cd ~/src/GDC-blueprints
       python3 scripts/stage_production_assets.py all --skip-images
       ```
    3. Propagate into `gdc-iac-org/blueprints/`:
       ```bash
       rsync -av --exclude='README.md' ~/src/GDC-blueprints/deploy-to-production/ ~/src/gdc-iac-org/blueprints/
       ```



