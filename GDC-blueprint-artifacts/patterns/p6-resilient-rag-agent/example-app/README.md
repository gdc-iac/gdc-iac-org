Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: Resilient RAG Agent

This example demonstrates a RAG (Retrieval Augmented Generation) pipeline.

## Architecture

## Architecture

- **Ingestion Service**: Watches an Object Storage bucket (MinIO/GCS), uses **Gemini 2.5 Flash** for multimodal processing (Audio/Image/Text), creates embeddings (mocked), and stores them in a Vector DB.
- **Vector DB**: PostgreSQL with `pgvector` extension.
- **Query Service**: API that accepts a question, retrieves relevant context from Vector DB, and calls an LLM.
- **LLM**: Mock service (or Gemini in production).

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

3. **Upload a Document**:
   You need to upload a text file to the `documents` bucket in MinIO.
   - Access MinIO Console: `http://localhost:9001` (User: `minioadmin`, Pass: `minioadmin`)
   - Create bucket `documents`.
   - Upload a file named `test.txt` with some content (e.g., "The secret code is 12345").

4. **Query the Agent**:
   ```bash
   curl -X POST http://localhost:8080/query \
     -H "Content-Type: application/json" \
     -d '{"query": "What is the secret code?"}'
   ```
   
   The service should retrieve the context from `test.txt` and return an answer.

## GDC Deployment Resources

### Resource Requirements

| Component | Replicas | CPU | Memory | Storage |
|-----------|----------|-----|--------|---------|
| **Ingestion Job** | 1 | 500m | 512MB | - |
| **Query Service** | 2 | 500m | 512MB | - |
| **Vector DB** (Postgres) | 1 (HA) | 4 | 16G | 100GB |
| **Object Storage** | - | - | - | 500GB |

> [!NOTE]
> For production RAG, ensure your Vector DB has sufficient memory to cache the index.

## Production Deployment

To deploy this example to GDC:

1. **Build and Push Images**
   ```bash
   export REGISTRY="harbor.gdc.local/my-project"

   # Ingestion
   docker build -t $REGISTRY/rag-ingestion:v1 ./ingestion
   docker push $REGISTRY/rag-ingestion:v1

   # Query Service
   docker build -t $REGISTRY/rag-query:v1 ./query-service
   docker push $REGISTRY/rag-query:v1
   ```

2. **Update Manifests**
   - In `../manifests/apps/ingest-job.yaml`: Update `image:` to `$REGISTRY/rag-ingestion:v1`.
   - In `../manifests/apps/query-service.yaml` (create if needed): Update `image:` to `$REGISTRY/rag-query:v1`.

3. **Configure Services**
   - Ensure `ingestion` and `query-service` are configured (via Env Vars or ConfigMaps) to point to the real **GDC Storage** (S3 compatible) and **Postgres** (Vector DB).
   - Update `LLM_URL` to point to the real Gemini API.

4. **Deploy**
   Follow the [Main README](../README.md) to deploy the database, storage buckets, and applications.
