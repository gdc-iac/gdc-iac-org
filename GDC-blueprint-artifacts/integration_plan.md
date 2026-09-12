# Plan: Integrating GDC Blueprint Patterns with IaC Framework

## Objective
Align the `GDC-blueprint-artifacts/patterns` with the core IaC orchestration framework (as described in the repository `README.md`) while preserving the ability to perform standalone deployments.

## Scope
- **Patterns**: `GDC-blueprint-artifacts/patterns/`
- **Documentation**: `GDC-blueprint-artifacts/docs/implementation-guides/`

## Proposed Approach: Option A (Helm-based Integration)

### Concept
Transform patterns from static manifest collections into deployable Helm charts. This allows the patterns to be managed by the existing orchestration tools (Helmfile, ArgoCD, etc.) used in the main repository.

### How it works
1.  **Wrapper Chart**: Each pattern will include a lightweight Helm chart.
2.  **Resource Wrapping**: This chart will wrap the existing `manifests/gdc` resources.
3.  **Parameterization**: Use `values.yaml` to allow the IaC framework to inject environment-specific configurations (e.g., namespaces, labels, service accounts) into the pattern's resources.
4.  **Dual-Mode Deployment**:
    - **Standalone Mode**: Users can still use `kubectl apply -f manifests/` for quick, unmanaged testing.
    - **Orchestrated Mode**: The IaC framework (via `helmfile` or `argocd`) can deploy the pattern as a Helm release, benefiting from dependency management and automated lifecycle handling.

## Implementation Steps

### 1. Audit & Standardization
- **Audit**: Systematically review all patterns in `GDC-blueprint-artifacts/patterns` to identify all GDC-specific Custom Resources (CRDs).
- **Template Creation**: Develop a standardized Helm chart template for patterns to ensure consistency across the library.

### 2. Pilot Implementation
- **Target**: Select a representative pattern (e.g., `p1-resilient-3-tier-webapp`).
- **Execution**:
    - Create the Helm chart structure.
    - Migrate/wrap existing `manifests/gdc` into the chart's `templates/` directory.
    - Implement `values.yaml` for key parameterization points.
- **Verification**: Validate that the pattern deploys successfully via both `kubectl` (standalone) and `helmfile` (orchestrated).

### 3. Documentation Update
- **Implementation Guides**: Update all guides in `GDC-blueprint-artifacts/docs/implementation-guides/` to reflect the two deployment paths (Standalone vs. IaC-integrated).
- **Pattern READMEs**: Update individual pattern `README.md` files to include instructions for the new Helm-based deployment.

### 4. Validation & QA
- Ensure no regressions in the existing standalone deployment workflow.
- Verify that the new approach adheres to the dependency layers defined in the main repository `README.md`.

---

## Summary for Repo Owners (For Issue/Feedback)

**Proposal: Helm-based Integration for GDC Blueprint Patterns**

**Problem Statement:**
Currently, the patterns in `GDC-blueprint-artifacts/patterns` are standalone manifest collections. While functional, they are disconnected from the advanced orchestration and dependency management capabilities (Helmfile, ArgoCD, etc.) provided by the main IaC framework.

**Proposed Solution (Option A):**
We propose wrapping pattern manifests into lightweight Helm charts.

**Key Benefits:**
- **Orchestration Alignment**: Enables patterns to be part of the automated, layered deployment lifecycle (e.g., ensuring a Project exists before a Pattern's workload is deployed).
- **Dynamic Configuration**: Leverages `values.yaml` to allow the IaC framework to inject context-specific metadata (namespaces, labels, etc.) without modifying the pattern itself.
- **Zero Regression**: The existing `manifests/` directory remains intact, ensuring that the current "standalone" deployment method remains fully operational.
- **Standardization**: Provides a consistent deployment interface across all architectural patterns.

**Impact:**
Low complexity, high value for automation and scalability.
