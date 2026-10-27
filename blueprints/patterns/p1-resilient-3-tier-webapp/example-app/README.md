Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: 3-Tier Todo App

This is a simple 3-tier application (Frontend, Backend, Database) to demonstrate the **Resilient 3-Tier Web Application** blueprint.

## Architecture

- **Frontend**: Web Server serving a static HTML/JS Single Page Application.
- **Backend**: Python Flask API.
- **Database**: PostgreSQL.

## Local Development (Mocking)

You can run this application locally using Docker Compose to simulate the GDC environment.

### Prerequisites
- Docker
- Docker Compose

### Running Locally

1. Navigate to this directory:
   ```bash
   cd example-app
   ```

2. Start the application:
   ```bash
   docker-compose up --build
   ```

3. Access the application at `http://localhost`.

## GDC Deployment Resources

When deploying this application to the GDC platform using the blueprint, the following resources are estimated:

### Resource Requirements

| Component | Replicas | CPU (per replica) | Memory (per replica) | Storage |
|-----------|----------|-------------------|----------------------|---------|
| **Web Tier** (Web Server) | 3 | 100m | 128MB | - |
| **Logic Tier** (Flask) | 2 | 250m | 512MB | - |
| **Data Tier** (Postgres) | 1 (HA) | 2 | 8G | 50GB |

> [!NOTE]
> These are estimated resources for a production-like deployment. You can adjust them based on your actual load.

## Production Deployment

To deploy this example application to the GDC environment:

1. **Build and Push Images**
   You need to build the Docker images and push them to your project's Harbor registry.
   ```bash
   # Set your registry project URL
   export REGISTRY="harbor.gdc.local/my-project"

   # Build and Push Backend
   docker build -t $REGISTRY/todo-backend:v1 ./src/backend
   docker push $REGISTRY/todo-backend:v1

   # Build and Push Frontend
   docker build -t $REGISTRY/todo-frontend:v1 ./src/frontend
   docker push $REGISTRY/todo-frontend:v1
   ```

2. **Update Manifests**
   Update the Kubernetes manifests in the `../manifests` directory to use your new images:
   - In `../manifests/apps/app-tier.yaml`: Update `image:` to `$REGISTRY/todo-backend:v1`
   - In `../manifests/apps/web-tier.yaml`: Update `image:` to `$REGISTRY/todo-frontend:v1`

3. **Deploy**
   Follow the [Main README](../README.md) instructions to apply the manifests using `kubectl` or GitOps.
