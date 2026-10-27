Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: Closed-Loop MLOps

This example simulates a training pipeline that produces a model and uploads it to a registry.

## Architecture

- **Training Job**: Python script simulating a model training process.
- **Model Registry**: Object Storage (MinIO) where artifacts are stored.

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
   
   The `training-job` will run, print training logs, and upload a JSON "model" to MinIO.

3. **Verify Artifact**:
   - Access MinIO Console: `http://localhost:9001` (User: `minioadmin`, Pass: `minioadmin`)
   - Check the `model-registry` bucket for the uploaded file.

## GDC Deployment Resources

### Resource Requirements

| Component | Replicas | CPU | Memory | Storage | Accelerator |
|-----------|----------|-----|--------|---------|-------------|
| **Training Job** | 1 | 8 | 32G | - | NVIDIA A100 / H100 |
| **Model Registry** (GCS) | - | - | - | 1TB | - |

> [!NOTE]
> Training jobs are typically transient (Jobs or TFJobs) rather than long-running Services.

## Production Deployment

To deploy this example to GDC:

1. **Build and Push Training Image**
   ```bash
   export REGISTRY="harbor.gdc.local/my-project"
   docker build -t $REGISTRY/training-job:v1 ./training-pipeline
   docker push $REGISTRY/training-job:v1
   ```

2. **Update Manifests**
   - Update your Job or TFJob manifest to use `$REGISTRY/training-job:v1`.
   - Ensure the job has permissions/credentials to write to GDC Storage (S3/GCS).

3. **Deploy**
   Follow the [Main README](../README.md) to submit the training job.
