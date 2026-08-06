#!/bin/bash
# Step 1: Provision Data Tier (HA Database)
gdcloud database clusters create tier3-db \
  --project=test-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=2 --memory=8Gi --storage-size=50Gi
