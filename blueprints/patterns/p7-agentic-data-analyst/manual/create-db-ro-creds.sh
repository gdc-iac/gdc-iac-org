#!/bin/bash
# Step 1: Create Read-Only Credentials
# Security Note: Never give an LLM agent admin DB credentials.
NAMESPACE=${1:-test-project}
kubectl create secret generic db-ro-creds \
  --namespace=$NAMESPACE \
  --from-literal=host=postgres-svc \
  --from-literal=username=analyst_ro \
  --from-literal=password='<SECURE_PASSWORD>' \
  --from-literal=db_name=postgres
