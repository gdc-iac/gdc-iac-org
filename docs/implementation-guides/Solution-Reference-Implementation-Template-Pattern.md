Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Template Pattern: [Pattern Name] on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring **[Pattern Name]** on Google Distributed Cloud (GDC) air-gapped environments. This reference implementation outlines the architecture, deployment options, least-privilege security policies, and operational verification procedures for the blueprint.

## **Architecture**

```
                  ┌─────────────────────────────────────────┐
                  │          [ GDC Gateway API ]            │
                  │        (gdc-shared-gateway)             │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ (Port 80/443)
                  ┌─────────────────────────────────────────┐
                  │           [ Workload App ]              │
                  │       (Stateless GKE Replicas)          │
                  └────────────┬───────────────┬────────────┘
                               │               │
                               ▼               ▼
          ┌──────────────────────────┐   ┌──────────────────────────┐
          │   [ GDC Storage / DB ]   │   │   [ GDC AI Gateway ]     │
          │ (PostgreSQL / GCS Bucket)│   │  (Gemma / Gemini Model)  │
          └──────────────────────────┘   └──────────────────────────┘
```

### **Key Solution Capabilities**

* **GDC Platform Integration**: Utilizes native, offline GDC services (Object Storage, Database Service, AI Inference Gateway) without external internet egress.
* **Dual Gateway & Fallback Support**: Compatible with self-hosted **Gemma Inference Gateway** (`../gdc_gemma_gw`) on port 80 and native **GDC Gemini AI Gateway**.
* **Least-Privilege Security Policy**: Restricts container capabilities using a dedicated `ServiceAccount` and binds IAM roles explicitly via `ProjectPolicy`.
* **Configurable Blueprint Hydration**: Hydrates manifests with target Project ID, Registry Host, and Namespace using `./configure-blueprints.sh`.

---

## **LLM Gateway Integration & Cross-Cluster Topology Guidance**

> [!NOTE]
> **Cross-Cluster & Shared-Services Gateway Access**:
> When integrating with an inference gateway (Gemma Gateway or GDC Gemini AI Gateway), the gateway does **not** need to be co-located in the same cluster or namespace as the application workloads. Endpoint configuration (`LLM_GATEWAY_URL`) can point to local namespace services, shared-services namespaces, or dedicated remote AI clusters via GDC Gateway API endpoints.

---

## **Production Deployment vs Connected Artifact Preparation**

| Dimension | **Connected Sideloading Workstation** | **GDC Air-Gapped Production** |
| :--- | :--- | :--- |
| **Object Storage** | Artifact stage / local directory (`./data/raw-docs`) for bundle prep | Native GDC Object Storage Bucket |
| **Database** | Local development container / StatefulSet for offline testing | GDC Database Service (Managed PostgreSQL HA) |
| **LLM Inference** | Container image download & model weights packaging | Gemma Gateway (`gdc_gemma_gw`) or GDC AI Inference Gateway |
| **Target Namespace** | Connected staging registry (`harbor.gdc.local`) | Organization Workload Namespace (hydrated via `-n`) |
| **Service Exposure** | Local CLI / Docker execution | GDC Gateway API (`HTTPRoute` + `gdc-shared-gateway`) |

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* A target GDC project and namespace configured.
* Necessary project-level IAM roles:
  * **IAM Admin**: `roles/iam.serviceAccountAdmin` (to manage service accounts).
  * **GKE Developer**: `roles/gke.developer` (to deploy manifests).

---

## **Section 1: Common Setup & Artifact Transfer**

### 1.1 Hydrate Blueprint Manifests

Before deploying, run the configuration script to substitute target project, namespace, and registry variables into all YAML manifests:

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d [pattern-folder-name]
```

### 1.2 Authenticate Harbor & Push Container Images

Push the required application container images to your GDC air-gapped Harbor registry:

```bash
export REGISTRY_HOST="harbor.gdc.local"
export ROBOT_NAME="robot\$puller"
export ROBOT_SECRET="your-robot-secret"

docker login ${REGISTRY_HOST} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}

# Unpack and push bundled images
./scripts/unpack-for-gdc.sh [pattern-folder-name]-gdc-images.tar ${REGISTRY_HOST}/library
```

---

## **Section 2: Infrastructure & IAM Configuration**

### 2.1 ServiceAccount & IAM ProjectPolicy

Apply the least-privilege IAM service account and policy binding manifest:

```bash
kubectl apply -f manifests/iam/permissions.yaml -n ${NAMESPACE}
```

### 2.2 Database / Storage Infrastructure

Deploy the database secret and managed infrastructure components:

```bash
kubectl apply -f manifests/security/db-secret.yaml -n ${NAMESPACE}
kubectl apply -f manifests/gdc/db/postgres.yaml -n ${NAMESPACE}
```

---

## **Section 3: Workload Deployment**

Apply the application workload manifests to the cluster:

```bash
kubectl apply -f manifests/apps/workload.yaml -n ${NAMESPACE}
kubectl rollout status deployment/[workload-name] -n ${NAMESPACE}
```

---

## **Section 4: Production Security & Observability**

### 4.1 Air-Gapped NetworkPolicies
Apply NetworkPolicies to enforce zero-trust egress and ingress isolation:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: pattern-security-policy
  namespace: <target-namespace>
spec:
  podSelector:
    matchLabels:
      app: [workload-name]
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: gemma-gateway
    ports:
    - protocol: TCP
      port: 80
```

### 4.2 Keycloak OIDC Authentication Integration
For production SSO and multi-tenancy, integrate Keycloak (Pattern 12):
1. **OIDC Provider**: Deploy Keycloak using the [P12 Keycloak Blueprint](../p12-keycloak/README.md).
2. **Token Validation**: Validate OIDC JWT tokens at the Gateway API level and forward `X-User-ID` and `X-User-Role` headers to backend workloads.
3. **Reference**: See [`docs/keycloak_integration_guide.md`](../docs/keycloak_integration_guide.md).

---

## **Section 5: Validation & Live Log Inspection**

### 5.1 Automated Cluster Verification
Verify workload health using an ephemeral curl pod:

```bash
kubectl run verify-pattern --rm -i --restart=Never -n ${NAMESPACE} \
  --image=curlimages/curl --command -- sh -c '
    sleep 2 && \
    curl -s http://[service-name]/health && \
    echo "✅ Success: Workload health check passed!"
  '
```

### 5.2 Live Operational Log Inspection
Inspect live component logs for debugging and operational verification:

```bash
# 1. View Workload Application logs
kubectl logs -l app=[workload-name] -n ${NAMESPACE} --tail=50 -f

# 2. View LLM Gateway / Gemma Gateway logs
kubectl logs -l app=gemma-gateway -n ${NAMESPACE} --tail=50 -f

# 3. View Database logs
kubectl logs postgres-0 -n ${NAMESPACE} --tail=50 -f
```

---

## **Section 6: Operations & Troubleshooting**

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `CreateContainerConfigError` | Missing secret keys in `db-ro-creds`. | Re-create secret with all required keys (`host`, `db_name`, `username`, `password`). |
| `ImagePullBackOff` | Registry URL mismatch or unhydrated image tag. | Re-run `./configure-blueprints.sh` and re-apply workload manifest. |
| `Connection Timeout (Port 8080)` | LLM Gateway port mismatch. | Verify Gemma Gateway service port is configured for port `80` (`http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`). |
