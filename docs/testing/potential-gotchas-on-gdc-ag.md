Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Potential Gotchas for GDC Air-Gapped Deployments

This document outlines common pitfalls and unexpected behaviors encountered when moving applications from a connected environment (Cloud Workstation/GKE) to a strictly air-gapped Google Distributed Cloud (GDC) environment. Addressing these points *before* your deployment window can save significant debugging time.

## 1. Container Images & Registries

### Hardcoded Registry References
*   **The Issue:** Applications often fail because a secondary image (e.g., an init container, a sidecar, or a default value in a Helm chart) still points to `docker.io`, `gcr.io`, or `quay.io`.
*   **The Symptom:** Pods stuck in `ImagePullBackOff`.
*   **The Fix:** 
    *   Audit **all** `values.yaml` files and manifests.
    *   Ensure *every* image is prefixed with your local registry address (e.g., `harbor.gdc.local/library/`).
    *   Don't forget "hidden" images like `busybox` used for init scripts or `postgres-exporter` sidecars.
*   **What Good Looks Like (`values.yaml`):**
    ```yaml
    image:
      registry: harbor.gdc.local
      repository: library/my-app
      tag: v1.0.0
    
    # Check sub-charts and sidecars!
    initContainer:
      image: harbor.gdc.local/library/busybox:latest
    ```

### Image Pull Secrets
*   **The Issue:** The default ServiceAccount in your namespace may not have permission to pull from your local project registry without explicit credentials.
*   **The Symptom:** `ErrImagePull` or `ImagePullBackOff` despite the image existing in the registry.
*   **The Fix:** 
    *   Ensure your deployment manifests reference a specific `imagePullSecret`.
    *   Alternatively, patch the `default` ServiceAccount to include the secret automatically.
*   **What Good Looks Like (`deployment.yaml`):**
    ```yaml
    spec:
      imagePullSecrets:
        - name: private-registry-creds
      containers:
        - name: my-app
          image: harbor.gdc.local/library/app:latest
    ```

### Mismatched Architectures (AMD64 vs ARM64)
*   **The Issue:** Building images on an ARM64 machine (like a local MacBook) and trying to run them on AMD64 GDC hardware without specifying `--platform linux/amd64`.
*   **The Symptom:** `Exec format error` in the pod logs.
*   **The Fix:** Always build with `docker build --platform linux/amd64 ...` or ensure your build environment (Cloud Workstation) matches the target.
*   **What Good Looks Like (Build Command):**
    ```bash
    docker build --platform linux/amd64 -t my-app:latest .
    ```

## 2. Helm Charts & Dependencies

### Remote Repository dependencies
*   **The Issue:** `helm install` tries to download dependencies defined in `Chart.yaml` from the internet.
*   **The Symptom:** `Error: failed to download "..."` during installation.
*   **The Fix:** 
    *   Run `helm dependency update` on an internet-connected machine *before* transferring.
    *   Ensure the `charts/` directory (containing `.tgz` archives of dependencies) is included in the transfer.
    *   Deploy using the local chart path: `helm install my-app ./my-chart-folder`.
*   **What Good Looks Like (Chart structure):**
    ```text
    my-pattern/
    ├── charts/
    │   ├── postgresql-12.1.0.tgz
    │   └── kafka-3.7.0.tgz
    ├── Chart.yaml
    └── values.yaml
    ```

## 3. Networking & DNS

### Public DNS Resolution
*   **The Issue:** Applications trying to reach public APIs (e.g., `api.openai.com`, external weather services) or verifying SSL certificates via OCSP.
*   **The Symptom:** Connection timeouts, DNS resolution errors.
*   **The Fix:** 
    *   Mock all external services (hence the `mock-llm` containers in our patterns).
    *   Ensure application logic has a "disconnected mode" or fallback.

### Ingress & Load Balancers
*   **The Issue:** GDC LoadBalancers might require specific annotations to function correctly, or might not assign external IPs in the same way as standard GCP.
*   **The Symptom:** Service stays in `<pending>` state for External IP.
*   **The Fix:** 
    *   Verify if you need specific annotations (e.g., `networking.gke.io/load-balancer-type`).
    *   Use `ClusterIP` or `NodePort` if an external LoadBalancer is not strictly available or configured in the air-gapped environment.

## 4. Storage & Databases

### StorageClass Names
*   **The Issue:** The Helm chart or manifest requests a StorageClass named `standard` or `gp2`, but the GDC environment uses `standard-rwo` or a custom name.
*   **The Symptom:** PVCs stuck in `Pending`.
*   **The Fix:** 
    *   Check `kubectl get sc` in the air-gapped environment immediately upon access.
    *   Update your `values.yaml` to match the available StorageClass.
*   **What Good Looks Like (`values.yaml`):**
    ```yaml
    persistence:
      enabled: true
      storageClass: "standard-rwo" # Matched to `kubectl get sc`
      size: 10Gi
    ```

### Managed Service Credentials
*   **The Issue:** GDC Managed Services (PostgreSQL) expose credentials via Kubernetes Secrets. The strict format of these secrets (keys like `username`, `password`, `host`) might differ from what your application expects (e.g., a single connection string `DATABASE_URL`).
*   **The Symptom:** `CrashLoopBackOff` with "Authentication failed" or "Connection refused".
*   **The Fix:** 
    *   Verify the secret structure of the created managed resource.
    *   Use `env` configurations in your Deployment to map specific secret keys to the environment variables your app expects.
*   **What Good Looks Like (`deployment.yaml`):**
    ```yaml
    env:
      - name: DB_USER      # App expects this
        valueFrom:
          secretKeyRef:
            name: my-db-connection
            key: username  # Secret provides this
      - name: DB_PASS
        valueFrom:
          secretKeyRef:
            name: my-db-connection
            key: password
    ```

## 5. Security & Permissions

### Strict Network Policies
*   **The Issue:** Air-gapped environments often have "Default Deny" network policies in place for security.
*   **The Symptom:** Services cannot talk to each other (e.g., Frontend → Backend timeouts) even though DNS works.
*   **The Fix:** 
    *   Ensure you have defined `NetworkPolicy` resources that explicitly allow traffic between your specific components.

### Security Contexts (Root vs Non-Root)
*   **The Issue:** GDC clusters often enforce strict Pod Security Standards (PSS) that forbid running containers as root (UID 0).
*   **The Symptom:** Pods fail to start with `CreateContainerConfigError` or permission denied on mounted volumes.
*   **The Fix:** 
    *   Ensure all Dockerfiles use a non-root `USER`.
    *   Set `securityContext.runAsNonRoot: true` in your manifests.
    *   Ensure volume mounts are writable by the specific UID.
*   **What Good Looks Like (`Dockerfile` & `deployment.yaml`):**
    ```dockerfile
    # Dockerfile
    RUN adduser -D -u 1000 appuser
    USER 1000
    ```
    ```yaml
    # Deployment
    securityContext:
      runAsUser: 1000
      runAsGroup: 3000
      fsGroup: 2000
      runAsNonRoot: true
    ```

## 6. Pattern-Specific Expectations

### Patterns 1, 3, 7, 10 (Web App & Standard DB)
*   **Database:** These patterns rely on the **GDC Managed Service for PostgreSQL**.
*   **Expectation:** You do not deploy a Postgres pod. You create a `PostgreSQLInstance` custom resource.
*   **Gotcha (Secret Keys):** The operator creates a Kubernetes Secret with specific keys: `username`, `password`, `database`, `host`.
    *   *Check:* Verify your application code (e.g., `config.py`, `settings.js`) reads these exact keys or maps them correctly. If your app expects `DB_USER` but the secret provides `username`, the pod will crash.
*   **Validation:** Run `kubectl get secret <db-instance-name>-connection -o yaml` to confirm the keys match your app's expectations.

### Pattern 4 (Event-Driven Kafka)
*   **Chart Dependencies:** This uses the Bitnami Kafka Helm chart.
*   **Gotcha (Hidden Images):** The chart references multiple images beyond just Kafka: `zookeeper`, `kafka-exporter`, `bitnami-shell`, etc.
    *   *Fix:* You must override `global.imageRegistry` and potentially specific repository paths in your `values.yaml` to point to your local Harbor registry. Failing to override even one (like the exporter) will cause partial deployment failure.
*   **Validation:** Render the template locally before deploying: `helm template my-kafka ./charts/kafka | grep "image:"`.

### Pattern 5 (Hybrid LLM Gateway) & Pattern 6 (RAG Agent)
*   **Model Weights (Critical):**
    *   **The Issue:** In a connected environment, tools like Ollama or vLLM pull models (e.g., `gemma:2b`) on demand. **This will fail in air-gapped.**
    *   **The Fix:** You must treat model weights as artifacts.
        *   *Option A (Baked Image):* Create a custom Docker image extending the base LLM image that includes the model files in `/root/.ollama`.
        *   *Option B (Volume Mount):* Manually transfer model files to a PVC in the air-gapped environment and mount that PVC to your inference server pod.
    *   **What Good Looks Like (Option A - Dockerfile):**
        ```dockerfile
        FROM ollama/ollama:latest
        
        # Start server in background, pull model, then cleanup
        RUN ollama serve & \
            sleep 5 && \
            ollama pull gemma:2b
            
        ENTRYPOINT ["/bin/ollama"]
        CMD ["serve"]
        ```
*   **Vector Database (P6):**
    *   **Gotcha:** P6 uses **PostgreSQL HA**. Ensure the `pgvector` extension is enabled manually or via setup scripts inside your PostgreSQL database instance, as standard application credentials may not have `SUPERUSER` privileges.

### Pattern 8 (Closed-Loop MLOps)
*   **Argo Rollouts & Prometheus:**
    *   **Gotcha (CRD Timing):** This pattern installs Custom Resource Definitions (CRDs). Helm sometimes struggles with CRD installation order in air-gapped scenarios if hooks fail.
    *   *Fix:* Apply CRDs manually first if `helm install` hangs.
    *   **Dashboard Access:** The Argo Rollouts dashboard service usually defaults to `ClusterIP`. To view it, you must patch the service to `LoadBalancer` (if supported) or configure an Ingress rule valid for your GDC environment's gateway.
