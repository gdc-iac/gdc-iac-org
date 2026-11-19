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
NAMESPACE="test-project"

echo "Cleaning up Pattern 4 resources..."

# 1. Delete Kubernetes Resources
kubectl delete -f p4-event-driven-kafka/manifests/apps/ --ignore-not-found=true
kubectl delete -f p4-event-driven-kafka/manifests/gcp/ --ignore-not-found=true


# Cleanup Persistent Volumes
kubectl delete pvc -l app=postgres -n ${NAMESPACE} --ignore-not-found=true

# Cleanup temporary test producer pod if it still exists
kubectl delete pod kafka-producer-test -n ${NAMESPACE} --ignore-not-found=true

# 2. Delete Secrets
kubectl delete secret event-db-credentials -n ${NAMESPACE} --ignore-not-found=true

echo "Cleanup complete!"
