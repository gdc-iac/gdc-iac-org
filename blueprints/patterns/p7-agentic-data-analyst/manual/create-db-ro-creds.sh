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

# Step 1: Create Read-Only Credentials
# Security Note: Never give an LLM agent admin DB credentials.
NAMESPACE=${1:-test-project}
kubectl create secret generic db-ro-creds \
  --namespace=$NAMESPACE \
  --from-literal=host=postgres-svc \
  --from-literal=username=analyst_ro \
  --from-literal=password='<SECURE_PASSWORD>' \
  --from-literal=db_name=postgres
