# Testing Strategy: GCP Stepping Stone (Stage 2)

> **⚠️ SECURITY WARNING:** The clusters created for these tests MUST NOT be exposed to the internet. Commonly used default passwords (e.g., `password`) and simplified configurations are implemented strictly for local/functional testing and are not secure for production.

This document outlines the "GCP Stepping Stone" testing strategy for the **Gemma Client**. In this stage, we verify the application logic on a Google Cloud Workstation using our in-cluster PostgreSQL database and GCS (Object Storage emulation).

---

## 1. Environment Variables
```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION="us-central1"
export ZONE="us-central1-a"
export CLUSTER_NAME="gdc-gemma-cluster"
export NAMESPACE="gemma-inference"
export KSA_NAME="gemma-client-sa"
export GSA_NAME="gemma-client-sa"
export BUCKET_NAME="gs://gemma-client-files-${PROJECT_ID}"
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
```

---

## 2. Infrastructure Setup
Ensure your GKE cluster is running with native GPU management and the `client-pool` node pool exists.

### 2.1. Create Client Node Pool
```bash
gcloud container node-pools create client-pool \
  --cluster $CLUSTER_NAME \
  --project $PROJECT_ID \
  --zone $ZONE \
  --machine-type "e2-standard-4" \
  --num-nodes "1" \
  --node-labels="app=client"
```

### 2.2. Create GCS Bucket
```bash
gcloud storage buckets create ${BUCKET_NAME} --project=${PROJECT_ID} --location=${REGION} --uniform-bucket-level-access
```

### 2.3. Configure Workload Identity
Configure Workload Identity to allow the Kubernetes Service Account to access GCP resources (GCS):
```bash
# Create GSA
gcloud iam service-accounts create ${GSA_NAME} --project=${PROJECT_ID} || true

# Grant Permissions to GSA
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member "serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role "roles/storage.objectAdmin"

# Bind KSA to GSA
gcloud iam service-accounts add-iam-policy-binding ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

# Annotate KSA
kubectl create serviceaccount ${KSA_NAME} -n ${NAMESPACE}
kubectl annotate serviceaccount ${KSA_NAME} -n ${NAMESPACE} iam.gke.io/gcp-service-account=${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com --overwrite
```

---

## 3. Deploy Application

### 3.1. Build and Push Client Images
```bash
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
chmod +x gemma-client/scripts/build.sh
./gemma-client/scripts/build.sh
```

### 3.2. Deploy Database
```bash
kubectl apply -f gemma-client/manifests/gcp/postgres-configmap.yaml -n ${NAMESPACE}
kubectl apply -f gemma-client/manifests/gcp/statefulset-postgres.yaml -n ${NAMESPACE}
```

### 3.3. Deploy Client Backend and Frontend
```bash
kubectl apply -f gemma-client/manifests/apps/backend.yaml -n ${NAMESPACE}
kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n ${NAMESPACE}
```

---

## 4. Verification

### 4.1. Port Forward Frontend
```bash
kubectl port-forward service/frontend-svc 8081:80 -n ${NAMESPACE}
```

### 4.2. Interactive Test
1. Open `http://localhost:8081` in your browser.
2. **Login**: Select "User 1" from the dropdown.
3. **Upload**: Upload a test document to test Object Storage emulation.
4. **Chat**: Ask a question to test dynamic model inference via the Gemma Inference Gateway!

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
