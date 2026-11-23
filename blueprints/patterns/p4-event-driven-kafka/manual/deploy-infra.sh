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

# Step 1: Deploy Kafka & Persistence
# 1. Durable storage for final results
gdcloud database clusters create event-db \
  --project=test-project \
  --database-version=POSTGRESQL_15 \
  --availability-type=zonal_ha \
  --admin-password="${DB_ADMIN_PASSWORD:?Set DB_ADMIN_PASSWORD}" \
  --cpu=2 --memory=8Gi --storage-size=50Gi

# 2. Kafka Cluster (KRaft StatefulSet on User Cluster)
# Ensure manifests have been parameterized with your internal Harbor registry URL
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG:?Set USER_CLUSTER_KUBECONFIG}" \
  apply -f manifests/gdc/kafka/kafka.yaml
