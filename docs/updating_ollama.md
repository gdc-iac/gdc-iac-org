Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# How to Update Ollama and LLM Models in Pattern 5 [DEPRECATED]

> **Version:** 1.2  
> **Status:** DEPRECATED

> [!CAUTION]
> **DEPRECATED**: Pattern 5 (Resilient Hybrid LLM Gateway) has been **deprecated**. For offline model serving, refer to the **Gemma Inference Gateway** (`gdc_gemma_gw` / vLLM / Ollama) documentation.

This guide provides step-by-step instructions for updating the version of Ollama and swapping the underlying Large Language Model (LLM) used as the failover backend in the legacy **P5: Resilient Hybrid LLM Gateway** pattern.

The default configuration uses `ollama/ollama:latest` with the `gemma:7b` model baked in. We will update this to a specific Ollama version and a newer model, for example, `gemma4`.

## Prerequisites

- You have a local copy of the `GDC-blueprints` repository.
- You have Docker, `kubectl`, and `helm` installed and configured to interact with your Kubernetes cluster.

## Step 1: Update the Ollama Dockerfile

The core of the failover LLM is a "baked" container image that includes the Ollama server and the model weights. To update it, you need to modify its Dockerfile.

1.  Open the following file: `p5-hybrid-llm-gateway/example-app/ollama-baked/Dockerfile`.

2.  Modify the `FROM` instruction to specify a fixed version of Ollama. Using a specific version tag instead of `latest` is a best practice for production environments to ensure reproducible builds. Releases available can be checked at : https://github.com/ollama/ollama/releases

3.  Update the `ollama pull` command to download the new model you want to use (e.g., `gemma4`). You can find available models on the [Ollama Library](https://ollama.com/library).

**Before:**
```dockerfile
FROM ollama/ollama:latest

# Start server silently, pull the weights, then package it into the image
RUN nohup bash -c "ollama serve &" && \
    sleep 5 && \
    ollama pull gemma:7b

ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]
```

**After (Example with Ollama v0.20.2 and Gemma4):**
```dockerfile
FROM ollama/ollama:0.20.2

# Start server silently, pull the weights, then package it into the image
RUN nohup bash -c "ollama serve &" && \
    sleep 5 && \
    ollama pull gemma4

ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]
```
> **Note:** If you wanted to use a different model like `gemma3`, you would replace `gemma4` with `gemma3` in the `ollama pull` command.

## Step 2: Update the Build Script

The build script needs to be updated to tag the new image correctly. A descriptive tag helps with version management.

1.  Open the file: `p5-hybrid-llm-gateway/scripts/build.sh`.

2.  Change the image tag to reflect the new model. For example, change `ollama-gemma:7b` to `ollama-gemma4:latest`.

**Before:**
```bash
# ...
# 2. Build Baked Ollama Gemma Image
echo "Building Baked Ollama Gemma Model (This will take a few minutes to download the weights)..."
docker build -t "${REGISTRY_HOST}/ollama-gemma:7b" p5-hybrid-llm-gateway/example-app/ollama-baked
docker push "${REGISTRY_HOST}/ollama-gemma:7b"
```

**After:**
```bash
# ...
# 2. Build Baked Ollama Gemma Image
echo "Building Baked Ollama Gemma2 Model (This will take a few minutes to download the weights)..."
docker build -t "${REGISTRY_HOST}/ollama-gemma4:latest" p5-hybrid-llm-gateway/example-app/ollama-baked
docker push "${REGISTRY_HOST}/ollama-gemma4:latest"
```

## Step 3: Update the Air-Gapped Pointer Manifest

For air-gapped deployments, a pointer file is used by the `package-for-gdc.sh` script to identify and bundle the correct image. This must be updated.

1.  Open the file: `p5-hybrid-llm-gateway/manifests/apps/ollama-gemma-pointer.yaml`.

2.  Update the `image` field to match the new image name and tag you defined in the build script.

**Before:**
```yaml
# ...
data:
  # ...
  image: "us-central1-docker.pkg.dev/your-project-id/blueprint-images/ollama-gemma:7b" # kpt-set: ${registry-host}/ollama-gemma:7b
```

**After:**
```yaml
# ...
data:
  # ...
  image: "us-central1-docker.pkg.dev/your-project-id/blueprint-images/ollama-gemma4:latest" # kpt-set: ${registry-host}/ollama-gemma4:latest
```

## Step 4: Update the LLM Gateway Configuration

The LLM Gateway needs to be told which model to request from the Ollama service.

1.  Open the file: `p5-hybrid-llm-gateway/manifests/apps/llm-gateway.yaml`.

2.  In the `gateway-conf` ConfigMap, update the `FAILOVER_MODEL` to the name of the model you pulled in the Dockerfile.

**Before:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gateway-conf
  # ...
data:
  # ...
  FAILOVER_MODEL: "gemma:7b"
```

**After:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gateway-conf
  # ...
data:
  # ...
  FAILOVER_MODEL: "gemma4"
```

## Step 5: Build and Push the New Image

Now you can run the build script to create your new container image and push it to your container registry.

```bash
# Ensure your REGISTRY_HOST environment variable is set correctly
export REGISTRY_HOST="<your-registry-url>" # e.g., harbor.gdc.local/library

# Run the build script
./p5-hybrid-llm-gateway/scripts/build.sh
```

This process will take some time as it needs to download the new model weights.

## Step 6: Deploy the Updated Model

With the new image pushed, you can deploy the updated Ollama service using Helm. The deployment command needs to point to the new image repository and tag.

The `README.md` for Pattern 5 assumes you have downloaded the Ollama helm chart to `p5-hybrid-llm-gateway/charts/ollama`.

Update the `helm upgrade` command with the new `image.repository` and `image.tag` values.

```bash
# Example deployment command
helm upgrade --install ollama ./p5-hybrid-llm-gateway/charts/ollama \
  --namespace ${NAMESPACE} \
  --set ollama.gpu.enabled=true \
  --set ollama.gpu.type=nvidia \
  --set image.repository=${REGISTRY_HOST}/ollama-gemma4 \
  --set image.tag=latest \
  --set "ollama.models.pull={}"
```
> **Note:** The image repository is derived from the tag used in the build script: `${REGISTRY_HOST}/ollama-gemma4:latest` becomes repository `${REGISTRY_HOST}/ollama-gemma4` and tag `latest`.

## Troubleshooting

### Issue 1: FailedPostStartHook (CrashLoopBackOff)
In air-gapped environments, you may encounter a `FailedPostStartHook` error causing the pod to crash loop. This happens because the Helm chart might attempt to pull models at runtime (e.g., `ollama pull`), which requires internet access.

**Fix:** Ensure you disable model pulling in your Helm command or values file. If the chart forces a pull hook despite your settings, you can manually patch the deployment to remove the hook as a fallback:

```bash
kubectl patch deployment ollama -n ${NAMESPACE} --type=json -p='[
  {"op": "remove", "path": "/spec/template/spec/containers/0/lifecycle"}
]'
```

### Issue 2: 404 Not Found from Gateway
If the gateway fails over and returns `{"detail":"All LLM providers unavailable"}` and logs show `404 Not Found` for the Ollama URL, it usually means the model requested by the gateway does not match the model available in Ollama.

**Fix:** Verify the model name in your baked image (run `ollama list` inside the pod) and update the `FAILOVER_MODEL` in your gateway configuration to match exactly.

### Issue 3: Empty Model List in Baked Image
If you run `ollama list` and see no models, but you are sure you baked them into the image, check if a volume mount is masking the directory.

**Fix:** If the Helm chart mounts an `emptyDir` or PVC on top of `/root/.ollama`, it will hide the baked data. You may need to patch the deployment to remove the volume mount or change the mount path.

```bash
kubectl patch deployment ollama -n ${NAMESPACE} --type=json -p='[
  {"op": "remove", "path": "/spec/template/spec/containers/0/volumeMounts"},
  {"op": "remove", "path": "/spec/template/spec/volumes"}
]'
```

## Step 7: Verify the Update

After deployment, you can verify that the new model is active by following the failover verification steps in the pattern's `README.md` or `testing_strategy_gcp_stepping_stone.md`.

1.  Force the gateway to failover to the secondary model.
2.  Send a request to the gateway.
3.  Check the gateway logs to confirm it is using the new failover model (e.g., `gemma4`).
```bash
kubectl logs -l app=gateway -n <YOUR_NAMESPACE>
```
The logs should show a line similar to: `Attempting Failover: http://ollama-service:11434/api/generate (Model: gemma4, Backend: ollama)`.

## Packaging for GDC

Once you have validated the update on GCP and verified that the baked image works, you need to package it for transfer to the air-gapped GDC environment.

1.  **Update the Pointer File:** Open `p5-hybrid-llm-gateway/manifests/apps/ollama-gemma-pointer.yaml` and update the `image` field to point to your new baked image. This tells the packaging script to include this large image in the bundle.
2.  **Run the Packaging Script:** Execute the packaging script from the root of the repository:
    ```bash
    ./scripts/package-for-gdc.sh p5-hybrid-llm-gateway
    ```
    This will generate the transfer tarballs in the `packages/` directory.

