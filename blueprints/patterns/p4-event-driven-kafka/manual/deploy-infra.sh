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
  --project=test-project --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA

# 2. Kafka Cluster (Helm)
# Ensure you point to your INTERNAL registry for the chart and images
helm install kafka oci://registry-1.docker.io/bitnamicharts/kafka \
  --namespace test-project \
  --version 26.4.0 \
  --set replicaCount=3 \
  --set zookeeper.replicaCount=3 \
  --set persistence.enabled=true \
  --set persistence.storageClass=standard-rwo \
  --set persistence.size=50Gi \
  --set image.registry=docker.io \
  --set image.repository=bitnami/kafka \
  --set image.tag=3.6.0
