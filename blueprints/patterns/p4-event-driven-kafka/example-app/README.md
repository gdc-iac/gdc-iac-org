Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: Event-Driven Pipeline (Kafka)

This example demonstrates an event-driven architecture using Kafka as the message bus.

## Architecture

- **Producer**: Python script that generates random orders and publishes them to a Kafka topic.
- **Kafka**: The event bus (using Confluent images for local mocking).
- **Consumer**: Python script that subscribes to the Kafka topic and persists orders to a database.
- **Database**: PostgreSQL.

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
   
   You will see logs from the `producer` sending messages and the `consumer` receiving them and saving to the DB.

## GDC Deployment Resources

### Resource Requirements

| Component | Replicas | CPU | Memory | Storage |
|-----------|----------|-----|--------|---------|
| **Kafka Cluster** | 3 | 1 | 4G | 100GB (per broker) |
| **Zookeeper** | 3 | 500m | 1G | 10GB (per node) |
| **Producer** | 1 | 250m | 256MB | - |
| **Consumer** | 2 | 500m | 512MB | - |
| **Database** | 1 (HA) | 2 | 8G | 50GB |

> [!NOTE]
> Kafka requires persistent storage for durability. Ensure your StorageClass is configured correctly.

## Production Deployment

To deploy this example to GDC:

1. **Build and Push Images**
   ```bash
   export REGISTRY="harbor.gdc.local/my-project"

   # Producer
   docker build -t $REGISTRY/kafka-producer:v1 ./producer
   docker push $REGISTRY/kafka-producer:v1

   # Consumer
   docker build -t $REGISTRY/kafka-consumer:v1 ./consumer
   docker push $REGISTRY/kafka-consumer:v1
   ```

2. **Update Manifests**
   - In `../manifests/apps/consumer.yaml`: Update `image:` to `$REGISTRY/kafka-consumer:v1`.
   - You will need to create a similar manifest for the **Producer** if you want to run it in the cluster (or run it as a Job).

3. **Deploy**
   Follow the [Main README](../README.md) to deploy Kafka (via Helm) and the Consumer application.
