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

# Step 1: Deploy MLOps Toolchain

# 1. Deploy Prometheus Monitoring Stack
# This command installs the kube-prometheus-stack, including Prometheus and Alertmanager.
helm install prometheus oci://test-registry.local/charts/kube-prometheus-stack \
  -n monitoring --create-namespace

# 2. Deploy Argo Rollouts for Canary Deployments
# This command installs Argo Rollouts, which provides advanced deployment capabilities.
helm install argo-rollouts oci://test-registry.local/charts/argo-rollouts \
  -n argo-rollouts --create-namespace
