#!/bin/bash
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
