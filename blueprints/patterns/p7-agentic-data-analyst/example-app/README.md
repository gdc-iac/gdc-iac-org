Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: Agentic Data Analyst

This example demonstrates an agent that autonomously queries a database to answer analytical questions.

## Architecture

- **Agent**: Python application that orchestrates the analysis (LLM -> SQL -> Plot).
- **Database**: PostgreSQL (managed high-availability database).
- **LLM**: Mock service returning pre-canned SQL queries.

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
   
   The agent will run automatically, query the mock database, and generate a plot.

3. **View Results**:
   Check the `output` directory (created in the current folder) for `sales_trend.png`.

## GDC Deployment Resources

### Resource Requirements

| Component | Replicas | CPU | Memory | Storage |
|-----------|----------|-----|--------|---------|
| **Agent** | 1 | 1 | 2G | - |
| **Database** (PostgreSQL) | 1 (HA) | 4 | 16G | 100GB |
| **LLM** (Vertex AI) | - | - | - | - |

> [!NOTE]
> Agents often require significant memory if processing large datasets in-memory (e.g., pandas).

## Production Deployment

To deploy this example to GDC:

1. **Build and Push Agent Image**
   ```bash
   export REGISTRY="harbor.gdc.local/my-project"
   docker build -t $REGISTRY/data-agent:v1 ./agent
   docker push $REGISTRY/data-agent:v1
   ```

2. **Update Manifests**
   - Create or update a Deployment manifest for the agent using `$REGISTRY/data-agent:v1`.
   - Ensure the agent has environment variables configured for:
     - `DB_HOST`: Pointing to your PostgreSQL instance.
     - `LLM_URL`: Pointing to the real Gemini API.

3. **Deploy**
   Follow the [Main README](../README.md) to deploy the PostgreSQL database and the Agent application.
