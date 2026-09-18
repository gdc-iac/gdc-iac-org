#!/bin/bash
# Step 1: Create Infrastructure
# Network for the VM
gdcloud compute networks create vm-net --project=test-project --subnet-mode=custom
gdcloud compute networks subnets create vm-subnet --network=vm-net --range=10.1.0.0/24 --region=region-1

# High Performance HA Database
gdcloud database clusters create legacy-db \
  --project=test-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=4 --memory=16Gi --storage-size=100Gi
