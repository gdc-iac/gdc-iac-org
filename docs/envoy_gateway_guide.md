Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.


# Envoy API Gateway 101 Guide for GDC Air-Gapped

This guide explains how to use the Envoy API Gateway with the `p1-resilient-3-tier-webapp` pattern on Google Distributed Cloud (GDC)  air-gapped environments.

> [!NOTE]
> While this guide uses `p1-resilient-3-tier-webapp` as a concrete example, the principles and configuration steps for Envoy Gateway apply generally to other patterns and applications on GDC.

## What is Envoy API Gateway?

Envoy is a high-performance open-source edge and service proxy. In the context of GDC and this pattern, it serves as the **API Gateway** managing incoming traffic to your application. It acts as a single entry point, handling routing, load balancing, and security.

We use the **Kubernetes Gateway API** to configure Envoy. This is a modern standard for service networking in Kubernetes, providing a more expressive and extensible way to define routing rules compared to the traditional Ingress API.

## Architecture

The following diagram illustrates how traffic flows through the components:

```
+----------------+      +-------------------------------+
| User / Client  | ---> | Envoy Gateway (Load Balancer) |
+----------------+      +-------------------------------+
                                  |
                                  | HTTP/80
                                  v
                        +-------------------------------+
                        |   Web Service (web-lb)        |
                        +-------------------------------+
                                  |
                                  | Internal Traffic
                                  v
                        +-------------------------------+
                        |          App Service          |
                        +-------------------------------+
                                  |
                                  | Database Traffic
                                  v
                        +-------------------------------+
                        |           Database            |
                        +-------------------------------+
```

## Key Components

1.  **GatewayClass (`p1-resilient-3-tier-webapp/manifests/apps/gateway-class.yaml`)**:
    -   Defines the type of controller that will manage the Gateway.
    -   We use `gateway.envoyproxy.io/gatewayclass-controller`.

2.  **Gateway (`p1-resilient-3-tier-webapp/manifests/apps/gateway.yaml`)**:
    -   Instantiates the load balancer.
    -   Listens on port `80` for HTTP traffic.
    -   Associated with the `eg` GatewayClass.

3.  **HTTPRoute (`p1-resilient-3-tier-webapp/manifests/apps/gateway.yaml` path)**:
    -   Defines the routing logic.
    -   Matches traffic with path prefix `/` and forwards it to the `web-lb` service on port `80`.

## Configuration for GDC Air-Gapped Environments

> [!IMPORTANT]
> **Follow Pattern Instructions:** If you are deploying the Envoy Gateway as part of a specific blueprint (like `p1-resilient-3-tier-webapp`), you should follow the **Day 0 Prerequisites** and **Packaging** instructions in that pattern's `README.md`. Those instructions are optimized for the integrated deployment.
>
> The steps below provide **standalone manual guidance** to help you understand the underlying process of preparing and transferring manifests and images.

Operating in a GDC air-gapped environment requires that all container images and Kubernetes manifests be transferred manually. This repository provides helper scripts to simplify this process.

### Day 0 Prerequisites (Air-Gap Transfer)

Before deploying Envoy Gateway to a GDC air-gapped environment, you must package the required artifacts on an internet-connected machine and transfer them.

1.  **Hydrate Manifests (Connected Machine - Standalone Guidance):**
    The manifests use `kpt` for package management. You must "hydrate" them to replace placeholders (like `${namespace}`) with actual values **before** transfer. If you are following a pattern's automated configuration script, this step is handled for you.
    ```bash
    # Set your desired namespace using kpt (ONLY on connected machine)
    kpt fn eval ./p1-resilient-3-tier-webapp/manifests --image gcr.io/kpt-fn/apply-setters:v0.2.0 -- namespace=my-app-namespace
    ```

2.  **Package Artifacts (Connected Machine):**
    Use the provided packaging script to create the transfer bundles. This script automatically identifies the required Envoy Gateway images (e.g., `envoyproxy/gateway-dev`, `envoyproxy/envoy`) and bundles them with the manifests.
    ```bash
    # Run from the root of the repository
    ./scripts/package-for-gdc.sh p1-resilient-3-tier-webapp
    ```
    This will create:
    *   `p1-resilient-3-tier-webapp-gdc-manifests.tar.gz`
    *   `p1-resilient-3-tier-webapp-gdc-images.tar`

3.  **Transfer Artifacts (Sneakernet):**
    Physically move both tarballs to your GDC air-gapped environment using your organization's approved secure transfer mechanism (e.g., data diode, secure USB).

### Deploying on GDC Air-Gapped Target

On the GDC environment, use the unpacking script to extract the manifests and load the images.

1.  **Unpack and Load:**
    ```bash
    # Run from the root of the repository
    ./scripts/unpack-for-gdc.sh p1-resilient-3-tier-webapp
    ```
    This extracts the manifests and loads the container images into your local Docker daemon.

2.  **Push to Internal Registry:**
    You must push the loaded images to your internal GDC registry (e.g., Harbor) so the GKE cluster can pull them.
    ```bash
    # Example for Harbor
    docker tag envoyproxy/gateway-dev:latest harbor.gdc.local/my-project/envoyproxy/gateway-dev:latest
    docker push harbor.gdc.local/my-project/envoyproxy/gateway-dev:latest
    ```

3.  **Apply Manifests:**
    Apply the hydrated manifests to your cluster:
    ```bash
    kubectl apply -f ./p1-resilient-3-tier-webapp/manifests/apps/
    ```

## Verifying the Deployment

1.  **Check the Gateway Status**:
    ```bash
    kubectl get gateway -n my-app-namespace
    ```
    The `PROGRAMMED` status should be `True`. If it's `False` or `Unknown`, check the events:
    ```bash
    kubectl describe gateway web-gateway -n my-app-namespace
    ```

2.  **Check the Route Status**:
    ```bash
    kubectl get httproute -n my-app-namespace
    ```
    This confirms if the route has been accepted by the Gateway.

3.  **Test Connectivity**:
    Find the external IP of the Gateway:
    ```bash
    kubectl get gateway web-gateway -n my-app-namespace -o jsonpath='{.status.addresses[0].value}'
    ```
    Then, `curl` the IP:
    ```bash
    curl http://<GATEWAY_IP>/
    ```
    You should see the response from your web application.

## Troubleshooting

-   **"Example app not found" (404)**: Check if the `HTTPRoute` correctly points to the `web-lb` service and that the service exists in the same namespace.
-   **Connection Refused**: Ensure the Gateway Service (LoadBalancer) has been assigned an IP address. On GDC, this might require a configured MetalLB or similar load balancer controller.
-   **ImagePullBackOff**: In air-gapped environments, this almost always means the image is not in the local registry or the path is incorrect. Verify the image reference in the Envoy Gateway controller deployment.
