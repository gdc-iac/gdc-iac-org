#!/bin/bash
# Uninstallation script for the GDC-ag Gemma Gateway Standalone deployment

NAMESPACE="gemma-inference"

echo "🧹 Tearing down the Gemma Gateway infrastructure..."

# Delete the entire namespace (this removes the gateway, Ollama/vLLM, services, and PVCs)
kubectl delete namespace $NAMESPACE

echo "✅ Cleanup complete. (Note: Persistent Disks provisioned by the PVCs have been released)."
