Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: Resilient Hybrid LLM Gateway

This example demonstrates a gateway service that routes requests to a primary LLM (Gemini) and fails over to a secondary local LLM (Gemma) if the primary is unavailable.

## Architecture

- **Gateway**: FastAPI service that handles routing and failover logic.
- **Primary LLM**: Mock service simulating Gemini (configured to fail randomly).
- **Failover LLM**: Mock service simulating Gemma (reliable).

## Local Development (Mocking)

### Prerequisites
- Docker
- Docker Compose

### Running Locally

1. Navigate to this directory:
   ```bash
   cd example-app
   ```

2. Start the stack:
   ```bash
   docker-compose up --build
   ```

3. Test the gateway:
   ```bash
   curl -X POST http://localhost:8080/generate \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Hello GDC"}'
   ```
   
   Repeat the request multiple times. You should see responses from "Gemini-Mock" (Primary) when it succeeds, and "Gemma-Mock" (Failover) when Primary fails (simulated 50% failure rate).

## GDC Deployment Resources

### Resource Requirements

| Component | Replicas | CPU | Memory | Storage | Accelerator |
|-----------|----------|-----|--------|---------|-------------|
| **Gateway** | 2 | 500m | 512MB | - | - |
| **Gemma Model** (Vertex AI) | 1 (min) | 4 | 16G | - | NVIDIA T4 / L4 |

> [!NOTE]
> The Primary LLM (Gemini) is a platform service and does not consume user project resources (other than quota).

## Production Deployment

To deploy this example to GDC:

1. **Build and Push Gateway Image**
   ```bash
   export REGISTRY="harbor.gdc.local/my-project"
   docker build -t $REGISTRY/llm-gateway:v1 ./gateway
   docker push $REGISTRY/llm-gateway:v1
   ```

2. **Deploy Failover Model (Gemma)**
   - Follow **Pattern 2** instructions to upload and deploy the Gemma model to Vertex AI.
   - Note the endpoint URL (e.g., `http://gemma-failover.my-gdc-project.svc.cluster.local`).

3. **Update Manifests**
   - In `../manifests/apps/llm-gateway.yaml`:
     - Update `image:` to `$REGISTRY/llm-gateway:v1`.
     - Update the `ConfigMap` to point `FAILOVER_URL` to your actual Gemma endpoint.
     - Update `PRIMARY_URL` to the real Gemini API endpoint in GDC.

4. **Deploy**
   Follow the [Main README](../README.md) to deploy the Gateway.
