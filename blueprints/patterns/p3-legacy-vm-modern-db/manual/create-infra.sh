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
