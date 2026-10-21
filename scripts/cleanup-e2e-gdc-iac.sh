#!/usr/bin/env bash
# Declarative IaC E2E Workload Cleanup Script for Google Distributed Cloud Air-Gapped (GDC-ag)
# Tears down Stage 5 (5-workload-factory) AI-enabled blueprint releases via Helmfile
# while strictly PRESERVING Stage 3 GPU Clusters, Stage 2 Harbor/SAN Model Weights, and Stage 1 Projects.
#
# Optional Flags:
#   --empty-bucket             Deletes all objects inside s3://gemma-rag-bucket while keeping the Bucket CR
#   --delete-bucket            Empties and completely removes the gemma-rag-bucket Bucket CR
#   --include-zonal-resources  Also destroys Stage 2 Zonal Resources (stage=2-resources)

set -euo pipefail

ENV="${ENV:-prd}"
NAMESPACE="${NAMESPACE:-gemma-inference}"
GDC_DEV_NAMESPACE="${GDC_DEV_NAMESPACE:-gdc-dev}"
BUCKET_NAME="${BUCKET_NAME:-gemma-rag-bucket}"
S3_ENDPOINT="${S3_ENDPOINT:-https://objectstorage.gdc.goog}"
BUCKET_ACTION="${BUCKET_ACTION:-preserve}"
INCLUDE_ZONAL_RESOURCES="false"

for arg in "$@"; do
  case "${arg}" in
    --empty-bucket)
      BUCKET_ACTION="empty"
      ;;
    --delete-bucket)
      BUCKET_ACTION="delete"
      ;;
    --include-zonal-resources)
      INCLUDE_ZONAL_RESOURCES="true"
      ;;
    -h|--help)
      echo "Usage: $0 [--empty-bucket | --delete-bucket] [--include-zonal-resources]"
      echo "  (default)                  Preserves ${BUCKET_NAME} and Stage 2/3 resources"
      echo "  --empty-bucket             Deletes all objects inside s3://${BUCKET_NAME} but keeps the bucket"
      echo "  --delete-bucket            Empties and completely deletes the ${BUCKET_NAME} Bucket resource"
      echo "  --include-zonal-resources  Destroys all Stage 2 Zonal Resources (stage=2-resources)"
      exit 0
      ;;
    *)
      echo "Unknown option: ${arg}" >&2
      echo "Usage: $0 [--empty-bucket | --delete-bucket] [--include-zonal-resources]" >&2
      exit 1
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}/foundations"

echo "=================================================================="
echo "🧹 Starting Declarative GDC-ag IaC Cleanup (Environment: ${ENV})"
echo "   Stage 5 Workloads (AI Gateway, vLLM, E2E, gdc-dev) : DESTROY"
echo "   GDC Object Storage Bucket (${BUCKET_NAME})         : ${BUCKET_ACTION}"
echo "   Stage 3 Shared GPU Cluster (gpu-moe / gpu-dense)   : PRESERVED"
echo "   Stage 2 Harbor Registry & SAN Model Weight PVCs    : PRESERVED"
echo "=================================================================="

# 1. Destroy all Stage 5 (5-workload-factory) Helmfile releases across gemma-inference & gdc-dev
echo "[1/5] Running helmfile destroy for stage=5-workload-factory..."
helmfile -e "${ENV}" -l stage=5-workload-factory destroy

# 2. Clean up dynamic per-developer IDE workspace PVCs in gdc-dev (preserving shared SAN model weights in gemma-inference)
echo "[2/5] Cleaning up dynamic developer workspace PVCs in ${GDC_DEV_NAMESPACE}..."
for pvc in $(kubectl get pvc -n "${GDC_DEV_NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true); do
  kubectl patch pvc "${pvc}" -n "${GDC_DEV_NAMESPACE}" -p '{"metadata":{"finalizers":null}}' --type=merge 2>/dev/null || true
  kubectl delete pvc "${pvc}" -n "${GDC_DEV_NAMESPACE}" --ignore-not-found
done

# 3. Clean up cluster-scoped RBAC & GatewayClass created by p13-gdc-dev
echo "[3/5] Removing cluster-scoped p13-gdc-dev RBAC & GatewayClass..."
kubectl delete clusterrolebinding gdc-dev-operator-binding --ignore-not-found
kubectl delete clusterrole gdc-dev-operator-role --ignore-not-found
kubectl delete gatewayclass gdc-dev-gateway-class --ignore-not-found

# 4. Optional GDC Object Storage bucket cleanup (--empty-bucket or --delete-bucket)
if [ "${BUCKET_ACTION}" = "empty" ]; then
  echo "[4/5] Emptying all objects from s3://${BUCKET_NAME} (keeping Bucket CR)..."
  aws --endpoint-url="${S3_ENDPOINT}" s3 rm "s3://${BUCKET_NAME}" --recursive 2>/dev/null || \
    gcloud storage rm "gs://${BUCKET_NAME}/**" 2>/dev/null || \
    echo "   Bucket ${BUCKET_NAME} is already empty or endpoint unreachable."
elif [ "${BUCKET_ACTION}" = "delete" ]; then
  echo "[4/5] Emptying and completely removing Bucket '${BUCKET_NAME}' in namespace '${NAMESPACE}'..."
  aws --endpoint-url="${S3_ENDPOINT}" s3 rm "s3://${BUCKET_NAME}" --recursive 2>/dev/null || \
    gcloud storage rm --recursive "gs://${BUCKET_NAME}" 2>/dev/null || true
  kubectl delete buckets.object.gdc.goog "${BUCKET_NAME}" -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
  helm uninstall "${NAMESPACE}-buckets" -n "${NAMESPACE}" 2>/dev/null || true
else
  echo "[4/5] Preserving GDC Object Storage bucket '${BUCKET_NAME}' (pass --empty-bucket or --delete-bucket to clean up)."
fi

# 5. Optional: Tear down Stage 2 Zonal Resources only if '--include-zonal-resources' flag is explicitly passed
if [ "${INCLUDE_ZONAL_RESOURCES}" = "true" ]; then
  echo "[5/5] Flag --include-zonal-resources detected: destroying stage=2-resources..."
  helmfile -e "${ENV}" -l stage=2-resources destroy
else
  echo "[5/5] Skipping Stage 2 (Harbor, DBCluster, Buckets) & Stage 3 (GPU Clusters) to preserve air-gap assets."
fi

echo "=================================================================="
echo "✅ GDC-ag Stage 5 workload cleanup complete!"
echo "   To re-deploy the full AI-enabled E2E stack, run:"
echo "   cd ${REPO_ROOT}/foundations && helmfile -e ${ENV} -l stage=5-workload-factory apply"
echo "=================================================================="
