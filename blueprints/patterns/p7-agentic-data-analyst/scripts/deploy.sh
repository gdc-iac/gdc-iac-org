#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

PROJECT_ID=$(gcloud config get-value project)
REGISTRY_HOST="us-central1-docker.pkg.dev/${PROJECT_ID}/blueprint-images"

echo "Deploying Pattern 7 with REGISTRY_HOST=${REGISTRY_HOST}..."

# Deploy Emulated DB (no substitution needed)
echo "Deploying Postgres..."
kubectl apply -f manifests/gcp/emulation-db.yaml
kubectl apply -f manifests/gcp/statefulset-postgres.yaml


# Deploy Agent (needs substitution)
echo "Deploying SQL Agent..."
sed "s|\${REGISTRY_HOST}|${REGISTRY_HOST}|g" manifests/apps/sql-agent.yaml | kubectl apply -f -

echo "Deployment complete. Checking pods..."
kubectl get pods -n test-project -l 'app in (sql-agent,postgres)'
