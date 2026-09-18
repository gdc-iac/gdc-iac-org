#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Step 2: Provision VM
# Prerequisite: Run `gdcloud compute images list` to find your exact image name.
gdcloud compute instances create app-vm-01 \
  --project=test-project \
  --zone=zone-1 \
  --machine-type=n2-highcpu-8-gdc \
  --image-project=gradec-images --image-family=ubuntu-2004 \
  --subnet=vm-subnet
