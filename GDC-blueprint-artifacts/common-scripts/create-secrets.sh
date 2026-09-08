#!/bin/bash
set -e

# Configuration
NAMESPACE="${NAMESPACE:-test-project}"

echo "Creating Secrets in Namespace: ${NAMESPACE}..."

# Helper function to create a generic db secret
create_db_secret() {
    local SECRET_NAME=$1
    local USERNAME=$2
    local PASSWORD=$3
    local HOST=$4

    echo "Creating secret: ${SECRET_NAME}..."
    
    # Check if secret exists
    if kubectl get secret "${SECRET_NAME}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo "  Secret ${SECRET_NAME} already exists. Deleting to update..."
        kubectl delete secret "${SECRET_NAME}" -n "${NAMESPACE}"
    fi

    kubectl create secret generic "${SECRET_NAME}" \
        --namespace "${NAMESPACE}" \
        --from-literal=username="${USERNAME}" \
        --from-literal=password="${PASSWORD}" \
        --from-literal=host="${HOST}" \
        --from-literal=db_name="postgres" \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "  Secret ${SECRET_NAME} created."
}

# Ensure namespace exists
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# --- P1: Resilient 3-Tier Webapp ---
# Requires: tier3-db-credentials (username, password)
create_db_secret "tier3-db-credentials" "postgres" "password" "postgres-svc"

# --- P4: Event Driven Kafka ---
# Requires: event-db-credentials (username, password)
create_db_secret "event-db-credentials" "postgres" "password" "postgres-svc"

# --- P6: Resilient RAG Agent ---
# Requires: rag-db-credentials (username, password, host)
create_db_secret "rag-db-credentials" "postgres" "password" "postgres-svc"

# --- P7: Agentic Data Analyst ---
# Requires: db-ro-creds (username, password)
create_db_secret "db-ro-creds" "postgres" "password" "postgres-postgresql"

# --- Gemini Secrets (Optional if using Workload Identity) ---
# P6 supports 'gemini-secrets' but it's optional.
# We DO NOT create a placeholder by default because if the env var is present (even with a placeholder),
# the app will try to use it and fail, instead of falling back to Workload Identity.
#
# If you need to use an API Key, create it manually:
# kubectl create secret generic gemini-secrets --namespace "${NAMESPACE}" --from-literal=api-key="YOUR_KEY"
echo "Skipping gemini-secrets (using Workload Identity by default)."

echo "Secrets creation complete."
