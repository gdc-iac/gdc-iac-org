Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Vault Integration Guide for GDC

> **Version:** 1.1

This guide outlines how to transition the existing architectural blueprints (P1, P5, and P6) from using insecure plaintext environment variables or plain Kubernetes Secrets to a production-grade, centralized secret management model leveraging HashiCorp Vault (Pattern 11) on Google Distributed Cloud (GDC).

## Architecture Overview

*   **Secret Manager:** HashiCorp Vault (deployed via P11), configured with GDC KMS Auto-Unseal.
*   **Authentication:** Vault Kubernetes Auth Method. Vault authenticates pods by verifying their Kubernetes Service Account (KSA) JWT against the GKE/GDC API Server.
*   **Delivery:** Vault Agent Mutating Webhook (Sidecar Injector). The sidecar fetches secrets and writes them to an in-memory volume (`/vault/secrets/`) accessible to the application container.

---

## 1. Vault Preparation (Production & Emulation)

Before adapting the patterns, the Vault cluster must be configured to accept Kubernetes authentications and policies must be established.

### 1.1 Enable Kubernetes Authentication

Execute this on the active Vault cluster (e.g., via `kubectl exec` into `vault-0`):

```bash
vault auth enable kubernetes
vault write auth/kubernetes/config \
    kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443"
```

### 1.2 Create Policies & Write Secrets

Create granular read-only policies for each pattern.

**For P1 (3-Tier Webapp):**
```bash
vault policy write p1-db-policy - <<EOF
path "secret/data/p1/database" { capabilities = ["read"] }
EOF

vault kv put secret/p1/database POSTGRES_USER="admin" POSTGRES_PASSWORD="secure_password"
```

**For P5 (LLM Gateway):**
```bash
vault policy write p5-gateway-policy - <<EOF
path "secret/data/p5/api-keys" { capabilities = ["read"] }
EOF

vault kv put secret/p5/api-keys GEMINI_API_KEY="AIzaSy..."
```

**For P6 (RAG Agent):**
```bash
vault policy write p6-rag-policy - <<EOF
path "secret/data/p6/datastores" { capabilities = ["read"] }
EOF

vault kv put secret/p6/datastores QDRANT_API_KEY="qdrant-secret" PG_PASS="rag-db-pass"
```

### 1.3 Map Kubernetes Service Accounts to Vault Roles

Bind the specific ServiceAccounts used by the patterns to the Vault roles.

```bash
# P1 Identity
vault write auth/kubernetes/role/p1-backend-role \
    bound_service_account_names="p1-backend-sa" \
    bound_service_account_namespaces="p1-namespace" \
    policies="p1-db-policy" \
    ttl=24h

# P5 Identity
vault write auth/kubernetes/role/p5-gateway-role \
    bound_service_account_names="gateway-sa" \
    bound_service_account_namespaces="p5-gateway" \
    policies="p5-gateway-policy" \
    ttl=24h

# P6 Identity
vault write auth/kubernetes/role/p6-rag-role \
    bound_service_account_names="rag-sa" \
    bound_service_account_namespaces="p6-rag" \
    policies="p6-rag-policy" \
    ttl=24h
```

---

## 2. Blueprint Modifications

To integrate Vault into the existing patterns, we must update their `Deployment` manifests to include Vault Agent annotations.

### Updating P1: Resilient 3-Tier Webapp

In `p1-resilient-3-tier-webapp/manifests/apps/backend.yaml`, replace the env blocks referencing K8s secrets with Vault annotations.

**Before:**
```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
```

**After (Vault Injected):**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "p1-backend-role"
        vault.hashicorp.com/agent-inject-secret-config.env: "secret/data/p1/database"
        vault.hashicorp.com/agent-inject-template-config.env: |
          {{- with secret "secret/data/p1/database" -}}
          export DB_USER="{{ .Data.data.POSTGRES_USER }}"
          export DB_PASSWORD="{{ .Data.data.POSTGRES_PASSWORD }}"
          {{- end -}}
    spec:
      serviceAccountName: p1-backend-sa
      containers:
      - name: backend
        # App executes the injected script before starting to load env vars
        command: ["/bin/sh", "-c"]
        args: ["source /vault/secrets/config.env && npm start"]
```

### Updating P5: LLM Gateway

In `p5-llm-gateway/manifests/gateway.yaml`, securely inject the AI provider/Gemini API keys.

```yaml
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "p5-gateway-role"
        vault.hashicorp.com/agent-inject-secret-keys.env: "secret/data/p5/api-keys"
        vault.hashicorp.com/agent-inject-template-keys.env: |
          {{- with secret "secret/data/p5/api-keys" -}}
          GEMINI_API_KEY={{ .Data.data.GEMINI_API_KEY }}
          {{- end -}}
    spec:
      serviceAccountName: gateway-sa
      containers:
      - name: litellm-gateway
        env:
        # LiteLLM supports loading env files natively 
        - name: ENV_FILE_PATH
          value: "/vault/secrets/keys.env"
```

### Updating P6: Resilient RAG Agent

In `p6-rag-agent/manifests/query-service.yaml`, inject database credentials directly to the container environment.

```yaml
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "p6-rag-role"
        vault.hashicorp.com/agent-inject-secret-api-config: "secret/data/p6/datastores"
        vault.hashicorp.com/agent-inject-template-api-config: |
          {{- with secret "secret/data/p6/datastores" -}}
          export QDRANT_API_KEY="{{ .Data.data.QDRANT_API_KEY }}"
          export DB_PASSWORD="{{ .Data.data.PG_PASS }}"
          {{- end -}}
    spec:
      serviceAccountName: rag-sa
      containers:
      - name: rag-api
        command: ["/bin/sh", "-c"]
        args: ["source /vault/secrets/api-config && uvicorn main:app --host 0.0.0.0 --port 8000"]
```

---

## 3. Testing Methodology Integration

Following our structured testing methodology, the Vault integration must be thoroughly verified before production rollout.

### 3.1 Test-Driven Development (TDD)
Before making the manifest changes, write failing unit tests in the respective application codebases to assert that the applications intuitively crash or mock-fail when critical environment variables (e.g., `DB_PASSWORD`, `GEMINI_API_KEY`) are missing or null.

### 3.2 Stage 1: Local / Isolated Testing
1. **Mock Dependencies:** When running unit tests via `pytest` or `jest`, mock the file system read of `/vault/secrets/` to ensure the core logic handles the credentials correctly, isolated from the actual Vault server.

### 3.3 Stage 2: Structural Verification (GCP/Emulation)
Deploy the P11 Vault pattern first in the GCP Emulator cluster. Then deploy the updated P1, P5, or P6 pattern.
**Verification Check:**
```bash
kubectl get pods -n <target-namespace>
```
*   You must verify that the pod lists `2/2` Ready containers (Application + `vault-agent` sidecar). 
*   If it is `0/2` or `1/2` `CrashLoopBackOff`, inspect the sidecar logs: `kubectl logs <pod-name> -c vault-agent-init`. This generally indicates a Vault policy, role mismatch, or token authorization failure.

### 3.4 Regression Awareness
After successfully deploying P6 with the Vault integration, re-run the `p6-rag-agent/test/verify.sh` functional smoke tests. The application should behave exactly as it did with k8s secrets. The transition to Vault must be entirely transparent to the end-user workflow.

---

## 4. Production Security Posture (GDC Air-Gapped)

When deploying these updated patterns to the ultimate GDC Air-Gapped production environment, the following principles apply:

1. **Principle of Least Privilege:** Do not reuse Vault roles. As shown in this guide, `p1-backend-role` is fiercely separate from `p6-rag-role`. A compromised P1 web pod cannot evaluate or read P6's Vector Database credentials.
2. **KSA Enforcement:** In GDC-ag, the Kubernetes Service Account (KSA) acts as the primary intra-cluster security boundary. The Vault auth mapping relies exclusively on `--bound_service_account_names`. Ensure deployment manifests explicitly declare their unique `serviceAccountName`.
3. **No Credential Persistence:** Because the Vault Injector writes to an in-memory `emptyDir` volume at `/vault/secrets/`, secrets are never committed to the underlying GDC disk/node storage, and the credentials instantly vanish if the pod is killed or scheduled elsewhere.
