#!/bin/bash
# Step 1: Deploy MLOps Toolchain

# 1. Deploy Prometheus Monitoring Stack
# This command installs the kube-prometheus-stack, including Prometheus and Alertmanager.
helm install prometheus oci://test-registry.local/charts/kube-prometheus-stack \
  -n monitoring --create-namespace

# 2. Deploy Argo Rollouts for Canary Deployments
# This command installs Argo Rollouts, which provides advanced deployment capabilities.
helm install argo-rollouts oci://test-registry.local/charts/argo-rollouts \
  -n argo-rollouts --create-namespace
