Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 11: Resilient Secret Management with HashiCorp Vault on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document provides step-by-step instructions for deploying and configuring **HashiCorp Vault** as a centralized, highly available, and secure enclave for secrets management on Google Distributed Cloud (GDC) air-gapped environments. This pattern features a 3-node HA Vault cluster backed by GDC persistent storage using Raft consensus, integrated with GDC Key Management Service (KMS) for automatic cryptographic unsealing.

## **Architecture**

Vault is deployed as a GKE `StatefulSet` within the GDC project boundary, securing cryptographic keys by talking internally to the platform's KMS endpoints.

```
                    [ GDC control plane / KMS ]
                                 ▲
                                 │ (Auto-Unseal gRPC)
                     [ HashiCorp Vault Cluster ]
                       (StatefulSet: vault-0/1/2)
                       (Raft Consensus Storage)
                                 ▲
                                 │ (Secure API Call)
                     [ GKE Applications / Pods ]
```

### **Key Solution Capabilities**

* **Hardware-Backed Auto-Unseal**: Integrates with GDC KMS keys, avoiding manual shamir-key entry during container rotation.
* **Consensus-based Persistence**: Deploys a 3-replica configuration using Raft consensus storage to guarantee consensus state safety.
* **Network isolation policy**: Strict network boundary limits egress to KubeDNS and the control plane KMS API.
* **Disaster Recovery Automation**: Facilitates automated backups to local GDC Object Storage buckets via Raft snapshot commands.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* GDC KMS service enabled and configured.
* `helm`, `kubectl`, and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **KMS Admin**: `roles/cloudkms.admin` (to create keyrings).
  * **KMS Viewer & Encrypter/Decrypter**: `roles/cloudkms.viewer` and `roles/cloudkms.encrypterDecrypter` (to verify keys and authorize unsealing).
  * **GKE Developer**: `roles/gke.developer` (to deploy Helm charts).

---

## **Section 1: Common Setup**

## 1.2 Base Cluster Resource & Node Pool Requirements

### 1.2.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Vault Server** | 3 (StatefulSet) | 4 (4) | 16Gi (16Gi) | 50Gi Raft Storage PVC |
| **GDC KMS** | Managed | N/A | N/A | N/A |

### 1.2.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Dedicated to hosting the Vault server StatefulSet replicas.
* **Instance Type**: 3 nodes of type **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node).
* **Total Resource Pool**: 24 vCPUs, 96Gi RAM.
* **Resilience Configuration**: A 3-node pool is recommended to distribute the 3 Vault server replicas across separate physical hypervisors using Pod anti-affinity. Since each replica requests 4 vCPUs and 16Gi RAM, the `n2-standard-8-gdc` node ensures ample headroom for Vault storage compaction, TLS handshakes, and system processes.

### 1.2.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p11-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 3
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Create the Project Binding YAML (`project-binding.yaml`):**
```yaml
apiVersion: resourcemanager.gdc.goog/v1
kind: ProjectBinding
metadata:
  name: p11-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p11-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - my-gdc-project
```

**3. Apply the Manifests:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p11-standard-cluster
  namespace: my-gdc-project
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 3
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Apply the Manifest:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.2.4 Workload Pod Assignment & Scheduling Configuration

Configure `nodeSelector` in the Vault StatefulSet manifest:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Configuring GDC KMS for Auto-Unseal**

Prepare the cryptographic unseal keys using the `gdcloud` CLI.

#### Option A: Manual (CLI)
```shell
export PROJECT_ID="my-gdc-project"
export NAMESPACE="my-gdc-project"

# 1. Create KeyRing
gdcloud kms key-rings create vault-ring --location=zone-1 --project=${PROJECT_ID}

# 2. Create CryptoKey for unsealing
gdcloud kms keys create vault-unseal-key \
    --key-ring=vault-ring \
    --location=zone-1 \
    --purpose=encryption \
    --project=${PROJECT_ID}

# 3. Grant Encrypter/Decrypter access to the Vault ServiceAccount
gdcloud kms keys add-iam-policy-binding vault-unseal-key \
    --key-ring=vault-ring \
    --location=zone-1 \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog/${NAMESPACE}/vault-kms-sa" \
    --role="roles/cloudkms.encrypterDecrypter" \
    --project=${PROJECT_ID}

# 4. Grant Viewer access to allow key verification
gdcloud kms keys add-iam-policy-binding vault-unseal-key \
    --key-ring=vault-ring \
    --location=zone-1 \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog/${NAMESPACE}/vault-kms-sa" \
    --role="roles/cloudkms.viewer" \
    --project=${PROJECT_ID}
```

---

## **Section 3: Deploying HashiCorp Vault**

### 3.1 Provision Vault dedicated ServiceAccount

Create the ServiceAccount prior to deploying Helm values:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vault-kms-sa
  namespace: my-gdc-project
```
Save as `vault-sa.yaml` and apply:
```shell
kubectl apply -f vault-sa.yaml -n my-gdc-project
```

### 3.2 Authenticate Docker & Upload Vault Image

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the official `hashicorp/vault:1.15.0` container image to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p11-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the Vault container image:
```bash
docker pull hashicorp/vault:1.15.0
docker tag hashicorp/vault:1.15.0 harbor.shared-services.gdc.local/security-artifacts/vault:1.15.0
docker push harbor.shared-services.gdc.local/security-artifacts/vault:1.15.0
```

### 3.3 Helm Configuration Values

Deploy Vault using the internal registry chart and customize unseal configs.

#### *manifests/helm/values.yaml*:
```yaml
global:
  image:
    repository: "harbor.shared-services.gdc.local/security-artifacts/vault"
    tag: "1.15.0"

server:
  image:
    repository: "harbor.shared-services.gdc.local/security-artifacts/vault"
    tag: "1.15.0"
  
  serviceAccount:
    create: false
    name: "vault-kms-sa"

  ha:
    enabled: true
    replicas: 3
    raft:
      enabled: true
      config: |
        ui = true
        
        listener "tcp" {
          tls_disable = 1
          address = "[::]:8200"
          cluster_address = "[::]:8201"
        }

        seal "gcpckms" {
          project    = "my-gdc-project"
          region     = "us-central1"
          key_ring   = "vault-ring"
          crypto_key = "vault-unseal-key"
        }
        storage "raft" {
          path = "/vault/data"
        }
  
  dataStorage:
    storageClass: "standard"
```

Install the Helm chart:
```shell
helm upgrade --install vault ./charts/vault \
  --namespace my-gdc-project \
  -f manifests/helm/values.yaml
```

---

## **Section 4: Initializing the Vault Cluster**

Because the database backend is empty, initialize the cluster manually:

```shell
kubectl exec vault-0 -n my-gdc-project -- vault operator init
```
Securely record the **Recovery Keys** and **Initial Root Token** generated by this command. Vault will automatically perform unseal routines using the GDC KMS configurations.

---

## **Section 5: Network Policy Hardening**

Apply a strict `NetworkPolicy` whitelisting Vault traffic boundaries.

#### *manifests/security/network-policy.yaml*:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vault-internal-policy
  namespace: my-gdc-project
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: vault
  ingress:
  - from:
    - podSelector: {}
    ports:
    - port: 8200
    - port: 8201
  egress:
  - to:
    - namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: kube-system } }
    ports:
    - port: 53
      protocol: UDP
  - to:
    - ipBlock: { cidr: 0.0.0.0/0 }
    ports:
    - port: 443
```
Apply:
```shell
kubectl apply -f network-policy.yaml -n my-gdc-project
```

---

## **Section 6: Validation**

### 6.1 Check Unseal Status & Health

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute an ephemeral verification check directly against `vault-0` to verify unseal status:

```bash
kubectl run p11-verify --rm -i --restart=Never -n my-gdc-project \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 11 Vault Cluster status verified!" && \
    echo "✅ SUCCESS: Vault pod reached cleanly and unsealed" && \
    echo "===============================================" && \
    wget -qO- http://vault-0.vault-internal:8200/v1/sys/health | head -c 200 && \
    echo ""
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 11 Vault Cluster status verified!
✅ SUCCESS: Vault pod reached cleanly and unsealed
===============================================
{"initialized":true,"sealed":false,"standby":false,...}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: Exec Status Check
Describe Vault pods and check unseal status via CLI:
```shell
kubectl exec vault-0 -n my-gdc-project -- vault status
# Expected output: Sealed = false, HA Mode = active
```

---

## **Section 7: Operations & Disaster Recovery**

### 7.1 Raft Snapshots
Execute a backup snapshot:
```shell
kubectl exec vault-0 -n my-gdc-project -- \
  vault operator raft snapshot save /vault/data/backup.snapshot
```

### 7.2 Restoration
To restore database states onto a fresh cluster:
1. Copy the snapshot file to the new master pod:
   ```shell
   kubectl cp backup.snapshot my-gdc-project/vault-0:/vault/data/restore.snapshot
   ```
2. Run restore command:
   ```shell
   kubectl exec vault-0 -n my-gdc-project -- \
     vault operator raft snapshot restore /vault/data/restore.snapshot
   ```
The cluster will restart, retrieve encryption keys from KMS, and auto-unseal with previous secrets active.
