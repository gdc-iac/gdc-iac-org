Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Example Application: Legacy VM + Modern Database

This example simulates a legacy application (running on a VM) connecting to a modern, high-performance database (PostgreSQL).

## Architecture

- **Legacy App**: A Python script simulating a monolithic order processing system. In a real deployment, this would run on a VM using the GDC VM Runtime.
- **Database**: PostgreSQL (managed high-availability database).

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
   
   You will see logs indicating that the "Legacy Order Processor" is connecting to the database and inserting records.

## GDC Deployment Resources

### Resource Requirements

| Component | Replicas | CPU | Memory | Storage |
|-----------|----------|-----|--------|---------|
| **Legacy VM** | 1 | 4 | 16G | 100GB (Boot Disk) |
| **Database** (PostgreSQL) | 1 (HA) | 4 | 16G | 100GB |

> [!NOTE]
> Managed PostgreSQL with High Availability requires sufficient CPU, memory, and storage quota in your GDC project.

## Production Deployment

To deploy this example to a GDC VM:

1. **Prepare VM Image**
   Since this is a legacy application running on a VM, you typically bake the application into a VM image or use a startup script.
   
   **Option A: Startup Script**
   - Upload `legacy-app/app.py` to a GCS bucket or make it available via a startup script in the `VirtualMachine` manifest.
   
   **Option B: Custom Image**
   - Create a VM image that has Python and the application code pre-installed.
   - Import this image into GDC using `gdcloud compute images import`.

2. **Update Manifests**
   - In `../manifests/vm/app-vm.yaml`, update the `source.image` to point to your custom image.
   - Ensure the VM has network access to the PostgreSQL cluster.

3. **Deploy**
   Follow the [Main README](../README.md) to provision the PostgreSQL cluster and the VM.
