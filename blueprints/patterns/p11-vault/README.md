Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 11: Resilient Secret Management with HashiCorp Vault

**Use Case:** Provides a centralized, highly available, and secure enclave for managing secrets on GDC Air-Gapped, avoiding the use of plain-text environment variables or loosely secured Kubernetes Secrets.

## Architecture Schematic

```text
[ GDC Network ] -------------------------------------------------------------------------
                                            |
        ┌───────────────────────────────────▼───────────────────────────────────┐
        │                          GDC Project Zone                             │
        │                                                                       │
        │  ┌────────────────────────┐         ┌──────────────────────────────┐  │
        │  │                        │         │                              │  │
        │  │       GDC KMS          ◄─────────┤     HashiCorp Vault          │  │
        │  │    (Auto-Unseal)       │  gRPC   │   (Raft HA Cluster - 3 pod)  │  │
        │  │                        │         │                              │  │
        │  └────────────────────────┘         └──────▲───────────────────────┘  │
        │                                            │                          │
        │                                            │ Vault API / Injector     │
        │                                            │                          │
        │  ┌────────────────────────┐         ┌──────▼───────────────────────┐  │
        │  │                        │         │                              │  │
        │  │ Pattern 1: Web Tier    │         │ Pattern 5/6: LLM Gateway/RAG │  │
        │  │ (Inject Secrets)       │         │ (Fetch Gemini Keys)          │  │
        │  │                        │         │                              │  │
        │  └────────────────────────┘         └──────────────────────────────┘  │
        └───────────────────────────────────────────────────────────────────────┘
                                            |
[ Isolated Environment ] ----------------------------------------------------------------
```

## Design & Resilience Strategy

1.  **Dynamic Secret Store:** Vault is deployed inside the GDC environment instead of static K8s secrets.
2.  **Auto-Unseal via Hardware KMS:** Uses GDC KMS to implement auto-unseal, removing the need for manual key entering during pod rotation. Highly resilient as it leverages Google Cloud KMS API endpoints hosted internally on the Air-Gapped hardware.
3.  **Availability:** Raft Consensus backed by PVC storage allows a 3-pod highly available deployment. Loss of a single pod does not impact read/write availability. 
4.  **Network Isolation:** Network policies isolate Vault strictly to its Raft peers and the egress required to communicate with GDC KMS.
5.  **Integration Options:** Works seamlessly via Sidecar Injection (Vault Agent Mutating Webhook) or External Secrets Operator for other applications inside the GDC environment.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The `hashicorp/vault:1.15.0` image must be pulled, optionally hardened, and pushed to the internal GDC registry.
2.  **Helm Charts:** The HashiCorp Vault Helm chart must be downloaded and transferred.
3.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
4.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** High Availability Core Service, minimal footprint capable of servicing the entire project.

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Vault Server (x3)** | `n2-standard-4-gdc` | 4 | 16Gi | 50Gi (Raft) | No |
| **GDC KMS** | Managed Service | N/A | N/A| N/A | No |

**Scaling & Upgrades:**
*   **Storage:** Monitor the Raft storage PVC (`/vault/data`). Resize when >70% utilized.
*   **Compute:** Vertical scaling of Vault nodes may be necessary based on the number of concurrent encryption transit queries. Currently configured for HA (3 replicas) for consensus safety.

## Configuration

### Blueprint Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -n <YOUR_NAMESPACE> -r <YOUR_REGISTRY_URL> -d p11-vault
```

## Required IAM Permissions

To deploy the resources for this pattern, your user account will need the following roles granted in your target project:

*   **KMS Admin:** To create the KeyRing and CryptoKeys.
    *   `roles/cloudkms.admin`
*   **Encrypter/Decrypter:** To bind to the Vault ServiceAccount for Auto-Unseal.
    *   `roles/cloudkms.encrypterDecrypter`
*   **GKE Developer:** To deploy Vault pods and Vault Agent Sidecar configurations.
    *   `roles/gke.developer`

## Implementation

### Step 1: Air-Gapped Preparation (Connected Workstation)

1.  **Hardening and Pulling Image:**
    If you wish to harden the image by removing unused shell tools, establish a custom block. For standard mirrors:
    ```bash
    docker pull hashicorp/vault:1.15.0
    docker tag hashicorp/vault:1.15.0 harbor.gdc.local/security-artifacts/vault:1.15.0
    ```
2.  **Download Helm Charts:**
    *   **Vault:** Download the chart to `p11-vault/charts/vault` (using `helm pull ... --untar`).

### Step 2: Configure IAM and KMS (GDC Production)

Use the `gdcloud` CLI to prepare the project-level resources for Vault Auto-Unseal.

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>
export NAMESPACE=<YOUR_NAMESPACE>

# Create KeyRing
gdcloud kms key-rings create vault-ring --location=zone-1

# Create Unseal Key
gdcloud kms keys create vault-unseal-key --key-ring=vault-ring --purpose=encryption

# Bind IAM Policy for EncrypterDecrypter
gdcloud kms keys add-iam-policy-binding vault-unseal-key \
    --key-ring=vault-ring \
    --location=zone-1 \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog/${NAMESPACE}/vault-kms-sa" \
    --role="roles/cloudkms.encrypterDecrypter"

# Bind IAM Policy for Viewer (Required to verify key existence)
gdcloud kms keys add-iam-policy-binding vault-unseal-key \
    --key-ring=vault-ring \
    --location=zone-1 \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog/${NAMESPACE}/vault-kms-sa" \
    --role="roles/cloudkms.viewer"
```

### Step 3: Deploy Vault via Helm

Deploy Vault into your cluster using the localized artifacts.

```bash
# Install from local chart directory using Air-gapped Registry
helm upgrade --install vault ./p11-vault/charts/vault \
  --namespace ${NAMESPACE} \
  -f p11-vault/manifests/helm/values.yaml
```

### Step 4: Initialize Vault Cluster

For a completely fresh production deployment inside GDC, you must initialize the backend storage. 

```bash
kubectl exec vault-0 -n ${NAMESPACE} -- vault operator init
```
> **CRITICAL SECURITY NOTE:** Securely copy and store the `Recovery Keys` and `Initial Root Token` output by the init command into your organization's highest-tier offline vault! Once recorded, Vault will automatically unseal itself using the KMS integration.

### Step 5: Security Hardening (NetworkPolicy)

Apply the NetworkPolicy to restrict traffic to only Raft peers and GDC KMS.

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/security/network-policy.yaml
```

**Option B: GitOps**

Sync the `manifests/security/network-policy.yaml` file to your cluster.

### Step 6: Disaster Recovery (DR)

**Raft Snapshots**
Automate this via a CronJob to save snapshots to a GDC storage bucket.
```bash
kubectl exec vault-0 -n [PROJECT_ID] -- \
  vault operator raft snapshot save /vault/data/backup.snapshot
```

**Restoration Procedure**
1. **Redeploy:** Install a fresh cluster using the same `values.yaml` and GDC KMS key.
2. **Initialize:** Perform a new `vault operator init` to obtain temporary keys.
3. **Restore:**
```bash
kubectl cp backup.snapshot [PROJECT_ID]/vault-0:/vault/data/restore.snapshot
kubectl exec vault-0 -n [PROJECT_ID] -- \
  vault operator raft snapshot restore /vault/data/restore.snapshot
```
4. **Verify:** The cluster will restart and auto-unseal using the GDC KMS key.

## Testing

### Standard Testing
This pattern includes scripts to help validate the artifacts and verify a successful deployment. The scripts are located in the `test/` directory.

To run the validation:
```bash
cd test/
chmod +x validate.sh
./validate.sh
```

### Verification (Post-deployment)

The `verify.sh` script checks the status of the deployed Vault resources, explicitly asserting the unseal status via the KMS integration.

To run the verification:
```bash
cd test/
chmod +x verify.sh
./verify.sh
```

### Local Testing

You can run the validation and verification scripts locally using the provided test runner, which mocks the GDC and Kubernetes CLI commands.

```bash
# Run from the root of the repository
bash tests/run-local.sh
```

## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p11-vault
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p11-vault
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p11-vault-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p11-vault-BOM.txt` and `p11-vault-manifest.txt` (Integrity checksums)
    *   `p11-vault-README.md` (Standalone deployment instructions)
    *   *(Note: p11-vault does not generate a `-gdc-images.tar` because the Vault service relies externally on the Hashicorp image bundled below).*
*   **Global Dependencies (Generated in the `artifacts/` directory):**
    *   `artifacts/external-dependencies/charts/vault-*.tgz` (The HashiCorp Vault Helm chart)
    *   `artifacts/external-dependencies/images/hashicorp_vault_*.tar` (The Vault container image extracted from the external image hooks)
### 4. Unpack and Deploy
Once transferred to your secure GDC environment, you must unpack and deploy the assets logically:

> **Optional: Hot-Patching Manifests Offline**
> If you need to deploy this pattern to a *different* namespace, project ID, or registry host than the one you originally injected during the pre-packaging step, you do not need to resend the payload across the air-gap. You can dynamically hot-patch the extracted manifests locally:
> ```bash
> # Define your old (packaged) and new (target) variables
> OLD_PROJECT="<PACKAGED_PROJECT_ID>"
> NEW_PROJECT="<NEW_PROJECT_ID>"
> OLD_NAMESPACE="<PACKAGED_NAMESPACE>"
> NEW_NAMESPACE="<NEW_NAMESPACE>"
> OLD_REGISTRY="<PACKAGED_REGISTRY_HOST>"
> NEW_REGISTRY="<NEW_REGISTRY_HOST>"
> 
> # Recursively execute string replacement across all extracted YAML files
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_PROJECT}|${NEW_PROJECT}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_NAMESPACE}|${NEW_NAMESPACE}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_REGISTRY}|${NEW_REGISTRY}|g" {} +
> ```


1. **Authenticate Docker with Harbor:** Log in to your target GDC environment's Harbor registry:
   ```bash
   export REGISTRY_HOST="harbor.gdc.local"
   export ROBOT_NAME="robot\$puller"  # Escape the $ character
   export ROBOT_SECRET="your-robot-secret"

   docker login ${REGISTRY_HOST} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
   ```

2. **Load and Push Vault Image:** Vault relies strictly on its core external image. Load and tag the artifact to your local registry:
   ```bash
   docker load -i artifacts/external-dependencies/images/hashicorp_vault_*.tar
   docker tag hashicorp/vault:1.15.0 harbor.gdc.local/library/hashicorp/vault:1.15.0
   docker push harbor.gdc.local/library/hashicorp/vault:1.15.0
   ```

3. **Extract API Manifests:** Extract the `-d` injected blueprints exactly:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf p11-vault-gdc-manifests.tar.gz -C ./gdc-manifests/
   ```

4. **Deploy Vault Helm Chart:** Unpack the official HashiCorp Vault Suite from `artifacts/` using `--untar` and install it referencing the configurations we extracted above:
   ```bash
   tar -xzf artifacts/external-dependencies/charts/vault-*.tgz -C ./
   helm upgrade --install vault ./vault \
     --namespace ${NAMESPACE} \
     -f ./gdc-manifests/manifests/helm/values.yaml
   ```

5. **Apply Network Hardening:**
   ```bash
   kubectl apply -f ./gdc-manifests/manifests/security/network-policy.yaml
   ```

---

## Updating Existing Patterns to Use Vault

Once Vault is deployed via this pattern, you must update existing workloads (e.g. `p1`, `p5`, `p6`) to eliminate plaintext environment variables or plain kubernetes secrets.

### Option A: Vault Agent Sidecar Injector (Recommended)
This approach leverages the Vault Agent mutating webhook to inject secrets directly into the pod's filesystem, making them available without altering application code.

1. **Enable Kubernetes Auth in Vault:**
   ```bash
   vault auth enable kubernetes
   vault write auth/kubernetes/config \
       kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443"
   ```
2. **Create a Vault Role & Policy:** Target the exact namespace and service account used by your pattern.
3. **Annotate Pattern Pods:** Update the pattern's Deployment manifests (`manifests/apps/`) to include Vault annotations.
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: tier3-app
   spec:
     template:
       metadata:
         annotations:
           vault.hashicorp.com/agent-inject: "true"
           vault.hashicorp.com/role: "db-credentials-role"
           vault.hashicorp.com/agent-inject-secret-config: "secret/data/db/creds"
           vault.hashicorp.com/agent-inject-template-config: |
             {{- with secret "secret/data/db/creds" -}}
             export DB_PASS="{{ .Data.data.password }}"
             {{- end -}}
   ```
4. **Consume the Secret:** Applications execute `source /vault/secrets/config` before starting their main process.

### Option B: External Secrets Operator (ESO)
If your framework requires native Kubernetes Secrets natively (e.g. Helm charts lacking Vault injection support):
1. Install ESO and map a `SecretStore` to HashiCorp Vault.
2. Replace static `kind: Secret` resources with `kind: ExternalSecret` definitions in the pattern's manifest directory. ESO will dynamically provision standard k8s secrets synced securely from Vault.
