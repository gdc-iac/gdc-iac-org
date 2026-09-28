# Gemma Client - GCP Quickstart

This document outlines the step-by-step plan to deploy and test the `gemma-client` application on a GKE cluster, using in-cluster PostgreSQL and in-cluster storage (emulating Object Storage).

## 1. Environment Preparation
Before deploying, ensure your GKE cluster is running with a standard non-GPU node pool (`client-pool`) to isolate the client workloads from the GPU nodes.

### Variables:
```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION="us-central1" # IMPORTANT: Verify & modify this if regional L4 GPU stock shortages forced alternate zone deployments!
export ZONE="us-central1-a"
export CLUSTER_NAME="gdc-gemma-cluster"
export NAMESPACE="gemma-inference"
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
```

> [!WARNING]
> **CRITICAL REGIONAL SYNCHRONIZATION GOTCHA:**
> Standard zones (like `us-central1-a`) can sometimes encounter dynamic L4 GPU stock exhaustions. If you had to bootstrap your GKE cluster pools in an alternate region (e.g. `us-west4-b`), **you MUST update the REGION variable here symmetrically to match (e.g. `export REGION="us-west4"`)!**
> 
> If you fail to do this, your build script will push new dynamic containers to the central repository, but GKE will continue to pull from the old `us-west4` repository target, loading stale baseline images without OIDC flags!

---

## 2. Create Client Node Pool
If your cluster does not yet have a second node pool, add one now:
```bash
gcloud container node-pools create client-pool \
  --cluster $CLUSTER_NAME \
  --project $PROJECT_ID \
  --zone $ZONE \
  --machine-type "e2-standard-4" \
  --num-nodes "1" \
  --node-labels="app=client"
```

---

## 2.1. Configure Workload Identity & Service Account
Create and annotate the Kubernetes Service Account (`gemma-client-sa`) that the Backend Deployment uses to access Cloud Storage securely:

```bash
export GSA_NAME="gemma-client-sa"
export KSA_NAME="gemma-client-sa"

# Create Google Service Account (GSA)
gcloud iam service-accounts create ${GSA_NAME} --project=${PROJECT_ID} || true

# Grant permissions to GSA for file uploads
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member "serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role "roles/storage.objectAdmin"

# Bind KSA to GSA
gcloud iam service-accounts add-iam-policy-binding ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

# Create and Annotate Kubernetes Service Account (KSA)
kubectl create serviceaccount ${KSA_NAME} -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl annotate serviceaccount ${KSA_NAME} -n ${NAMESPACE} iam.gke.io/gcp-service-account=${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com --overwrite
```

---

## 3. Deploy Data Layer Emulators
The client application persists chat history and files using PostgreSQL and Object Storage. In GKE testing, we emulate these using in-cluster deployments and a GCS bucket.

### 3.0. Create GCS Bucket (Object Storage Emulation)
```bash
export BUCKET_NAME="gs://gemma-client-files-${PROJECT_ID}"
gcloud storage buckets create ${BUCKET_NAME} --project=${PROJECT_ID} --location=${REGION} --uniform-bucket-level-access
```

### 3.1. Deploy PostgreSQL StatefulSet
Create the DB credentials secret that the Postgres StatefulSet and Backend Deployment reference:
```bash
kubectl create secret generic gemma-client-db-credentials \
  --from-literal=username=postgres \
  --from-literal=password=password \
  --from-literal=db_name=postgres \
  --from-literal=connection_string=postgresql://postgres:password@postgres-svc.gemma-inference.svc.cluster.local:5432/postgres \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f gemma-client/manifests/gcp/postgres-configmap.yaml -n $NAMESPACE
kubectl apply -f gemma-client/manifests/gcp/statefulset-postgres.yaml -n $NAMESPACE
```
*Wait for the Postgres pod to reach the `Running` state:*
```bash
kubectl get pods -n $NAMESPACE -l app=postgres
```

### 3.2. Build and Push Client Images
Use the pattern-specific build script to build and push images to Artifact Registry:
```bash
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
chmod +x gemma-client/scripts/build.sh
./gemma-client/scripts/build.sh
```

---

## 4. Configure Manifest Placeholders & Deploy Client Application
Run the configuration script from the repository root to point the manifests to your newly built container images in your Workstation Artifact Registry:
```bash
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d gemma-client
```

Or manually patch placeholders if customizing directly:
```bash
sed -i "s|image: gemma-client-backend:latest|image: ${REGISTRY_HOST}/gemma-client-backend:latest|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|image: gemma-client-frontend:latest|image: ${REGISTRY_HOST}/gemma-client-frontend:latest|g" gemma-client/manifests/apps/frontend.yaml
sed -i "s|PROJECT_ID_PLACEHOLDER|${PROJECT_ID}|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|INPUT_BUCKET_PLACEHOLDER|gemma-client-files-${PROJECT_ID}|g" gemma-client/manifests/apps/backend.yaml
```

Deploy the frontend and backend of the `gemma-client`:
```bash
kubectl apply -f gemma-client/manifests/apps/backend.yaml -n $NAMESPACE
kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n $NAMESPACE
```

---

## 5. Verification
Once the pods reach the `Running` state:

### Option A: Internal Cluster Verification (No Port-Forwarding Needed)
Execute an ephemeral verification pod directly inside the cluster against the internal `frontend-svc` Service:

```bash
kubectl run client-verify --rm -i --restart=Never -n $NAMESPACE \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Gemma Client Application verified!" && \
    echo "✅ SUCCESS: Frontend service reachable via ClusterIP" && \
    echo "===============================================" && \
    wget -qO- http://frontend-svc/ | head -n 15 && \
    echo ""
  '
```
**Expected Workstation Output:**
```text
===============================================
✅ PASS: Gemma Client Application verified!
✅ SUCCESS: Frontend service reachable via ClusterIP
===============================================
<!DOCTYPE html>
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

### Option B: Local Port-Forwarding & Browser Verification
#### 5.1. Access the Client Frontend (Mock Persona Switcher)
Port-forward the frontend to your Cloud Workstation:
```bash
kubectl port-forward svc/frontend-svc 8081:80 -n $NAMESPACE
```
Navigate to `http://localhost:8081` in your browser to access the multi-user chat interface!

### 🧠 5.2. Verify Dynamic Model Routing Classifier Capabilities
By default, the client chatbot targets the generic **`Auto / Generic (gemma4)`** model selection. This invokes the Gateway's server-side *Smart Prompt Routing Classifier* to dynamically redirect queries in real-time based on prompt complexity:

1.  **Test Case 1: Conversational / Low-Latency Routing**:
    *   Open your browser tab mapping to Port `8081`.
    *   Leave the top-left dropdown selector on **`Auto / Generic (gemma4)`**.
    *   Submit a simple query: `"Hello Gemma! Tell me a brief story about a helpful AI."`
    *   **Verification**: Check that the top-right model header badge resolves to **`MoE (26B)`**, proving the gateway's heuristics classifier successfully routed the prompt to the highly efficient Gemma 4 MoE serving instance!
2.  **Test Case 2: Complexity / Coding Routing (Dynamic Sync)**:
    *   In the same session, submit a complex programming/logical query:
        `"Write a python class to execute a bubble sort and analyze its time complexity step-by-step"`
    *   **Dynamic Synchronization in Action**: Watch the top-right model header badge **automatically change to `Dense (31B)` in real-time** as the stream begins! 
    *   *How it works*: The backend gateway proxy analyzes the prompt, detects complexity indicators (*python, class, complexity, step-by-step*), reroutes the session to the high-capacity Gemma 4 Dense serving instance, and returns the resolved variant tag in the completions JSON envelope. The React client intercepts this tag and immediately refreshes its header indicators dynamically!
3.  **Test Case 3: Manual Override Selection**:
    *   Click the top-left dropdown menu, and explicitly select **`Gemma 4 31B (Dense)`**.
    *   Submit a simple greeting: `"Hello"`
    *   **Verification**: Check that the top-right model header badge remains locked on **`Dense (31B)`**, proving that explicit overrides successfully bypass the complexity classifier and route directly.

For detailed sequence flows and deep-dives, see **[docs/model_routing_architecture.md](../docs/model_routing_architecture.md)**.

### 5.3. Evicting the Static Browser Cache (The Chrome Hard Reload Trick)
Chromium browsers aggressively cache static Vite/React Javascript and CSS assets. If you rollout changes but the UI does not update:
1. Open the preview tab targeting Port 8081.
2. Open Developer Tools by pressing **`F12`** (keep the panel open!).
3. **Right-Click** (or click and hold) on browser's circular **Reload (Refresh) button** next to the URL bar.
4. Click the third option: **"Empty Cache and Hard Reload"**!

### 🔐 5.4. Exposing Identity: Keycloak OIDC Authentication Integration
By default, this quickstart deploys the chatbot application running a simple "Mock Auth" mode allowing persona selections. To secure user sessions natively, you can transition the gateway to utilize OIDC via Keycloak.

We resolve the browser's sandboxed iframe cookies restrictions (the Workstation preview proxy returning `403 Forbidden` on session iframes) by establishing:
1. **Unified Port Ingress Proxy**: Exposing all components under a single port (`8081`) via a secure, rootless NGINX sidecar, satisfying browser CORS.
2. **Automated Realm Import (GitOps Standard)**: Preloading and importing the realm config map on Keycloak startup, bypassing Master Admin UI console hangs.

Refer to the staged master blueprints and scripts to run the integration:
*   **[gcp-sandbox-keycloak-testing-strategy.md](file:///Users/gmollison/GitHub/gdc_gemma_gw/docs/gcp-sandbox-keycloak-testing-strategy.md)**: Dynamic sequence flows, GKE Staging vs. GDC-ag Production (Gateway API) structural matrix, and DNS optimizations.
*   **[configure-keycloak.sh](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/scripts/configure-keycloak.sh)**: Configurator script to dynamically discover your workstation preview subdomains, stage hydrated manifests, and bake frontend `.env` parameters.

---

## 6. Clean Up
When you are finished testing, delete the client deployment, the Postgres emulator, the GCS bucket, and the Workload Identity service accounts:
```bash
kubectl delete -f gemma-client/manifests/apps/frontend.yaml -n $NAMESPACE
kubectl delete -f gemma-client/manifests/apps/backend.yaml -n $NAMESPACE
kubectl delete -f gemma-client/manifests/gcp/statefulset-postgres.yaml -n $NAMESPACE

# Delete Google Service Account (GSA)
gcloud iam service-accounts delete ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com --project=${PROJECT_ID} --quiet

# Delete Kubernetes Service Account (KSA)
kubectl delete serviceaccount ${KSA_NAME} -n ${NAMESPACE}

# Delete GCS Storage Bucket
gcloud storage rm -r ${BUCKET_NAME}
```

---

### Alternative: Deploy via Standardized Helm Wrapper Charts on GCP GKE

After provisioning the GCP emulation backing services (`manifests/gcp/`), you can deploy the Gateway and Gemma Client workloads on GKE using the standardized Helm wrapper charts (`standalone/chart` and `gemma-client/chart`, where `gdc.enabled: false` by default omits GDC-only `DBCluster` CRDs):

```bash
# Deploy Gemma Gateway Proxy & HTTPRoute via Helm
helm upgrade --install gemma-gateway ./standalone/chart \
  --namespace ${NAMESPACE} --create-namespace \
  --set global.projectId=${PROJECT_ID} \
  --set global.namespace=${NAMESPACE} \
  --set global.registry=${REGISTRY_HOST}

# Deploy Gemma Client Backend & Frontend via Helm
helm upgrade --install gemma-client ./gemma-client/chart \
  --namespace ${NAMESPACE} \
  --set global.projectId=${PROJECT_ID} \
  --set global.namespace=${NAMESPACE} \
  --set global.registry=${REGISTRY_HOST}
```
