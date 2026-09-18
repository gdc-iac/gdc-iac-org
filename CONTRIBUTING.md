# Contributing to Google Distributed Cloud Infrastructure Automation

Thank you for your interest in contributing to the Google Distributed Cloud Infrastructure Automation project! We welcome contributions, bug reports, and suggestions from the community.

---
## Before you begin

### Sign our Contributor License Agreement

Contributions to this project must be accompanied by a
[Contributor License Agreement](https://cla.developers.google.com/about) (CLA).
You (or your employer) retain the copyright to your contribution; this simply
gives us permission to use and redistribute your contributions as part of the
project.

If you or your current employer have already signed the Google CLA (even if it
was for a different project), you probably don't need to do it again.

Visit <https://cla.developers.google.com/> to see your current agreements or to
sign a new one.

### Review our community guidelines

This project follows
[Google's Open Source Community Guidelines](https://opensource.google/conduct/).

> [!IMPORTANT]
> When submitting a pull request, ensure that the email address associated with your Git commits matches the email address you used to sign the CLA. If the emails do not match, the automated CLA check will fail.
---

## How to Contribute

### 1. Discuss Your Proposed Changes First
Before investing significant time into implementing a major feature, refactoring existing charts, or proposing architectural changes, please [open an issue](https://github.com/majduk/gdc-iac-org/issues) to discuss your proposal with the maintainers. This ensures your contribution aligns with the project roadmap and architectural goals.

For small fixes (e.g. typos, minor bugfixes, documentation improvements), opening a pull request directly is welcome.

### 2. Set Up Your Local Development Environment
To validate charts and run offline tests locally, install the following tools:
- **Git**
- **Helm 3** (v3.10+)
- **helm-unittest** plugin (`helm plugin install https://github.com/helm-unittest/helm-unittest`)
- **kubeconform** (for Kubernetes schema validation)
- **conftest** (for OPA Rego policy evaluation)
- **chart-testing (ct)** (v3.11+)
- **Python 3.9+**
- **Docker** (optional, required if running `scripts/helm-docs.sh`)

### 3. Fork and Branch
1. Fork the repository on GitHub.
2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/gdc-iac-org.git
   cd gdc-iac-org
   ```
3. Create a feature branch off `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```

### 4. Make Your Changes
Adhere to the repository-specific guidelines detailed below when making your changes.

---

## Repository Guidelines & Standards

### 1. Chart Versioning Guidelines
All Helm charts in the `charts/` directory adhere to [Semantic Versioning (SemVer)](https://semver.org/):
- **Patch release (`0.0.X`):** Bug fixes, documentation updates, or non-functional modifications.
- **Minor release (`0.X.0`):** New features, backward-compatible additions to `values.yaml`, or new optional templates.
- **Major release (`X.0.0`):** Breaking changes, removed or renamed values without fallbacks, or incompatible resource schema updates.

Always increment the `version` field in `charts/<chart-name>/Chart.yaml` whenever you modify a chart.

### 2. Documentation Guidelines
- Chart documentation (including parameter tables in `charts/<chart-name>/README.md`) is generated using `helm-docs`.
- When modifying `values.yaml` or `Chart.yaml`, regenerate the documentation using:
  ```bash
  ./scripts/helm-docs.sh
  ```
- Keep configuration descriptions, examples in `examples/`, and tool guides up to date.

### 3. Changelog Guidelines
- Maintain a changelog for chart modifications.
- In each pull request, summarize the user-impacting changes in the PR description and update chart release notes where appropriate.

### 4. Compatibility & Values Standards
- All new configuration values added to `values.yaml` must be backward compatible and define sensible, production-ready defaults.
- Default values must not break existing deployments or cause insecure default configurations.
- Update `values.schema.json` to enforce typing and validation. You can regenerate baseline schemas using:
  ```bash
  python3 scripts/generate_schemas.py
  ```

### 5. License & Copyright Headers
All new source code files (Python, shell scripts, Rego policies, etc.) should include an Apache 2.0 license and copyright header:

```text
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Local Testing & Pre-Deployment Validation

All charts submitted to this repository must pass offline validation across four validation layers before submitting a pull request.

### The 4 Validation Layers
1. **Helm Syntax & Schema Validation:** Verifies Helm syntax (`helm lint`) and typed input schemas (`values.schema.json`).
2. **Logic Validation (`helm-unittest`):** Executes unit tests ensuring Go templating renders expected Kubernetes resources without requiring a live cluster.
3. **Structural Validation (`kubeconform`):** Validates rendered manifests against Kubernetes OpenAPI specifications.
4. **Policy & Security Compliance (`conftest` / OPA):** Asserts that rendered resources comply with organization security policies (such as `policy/security.rego` denying permissive `0.0.0.0/0` network policies).

### Running Tests Locally
Run the test suite across all charts from the repository root:

```bash
./scripts/test-charts.sh
```

Run chart-testing linter (matching GitHub Actions CI):

```bash
ct lint --debug --config ./.github/configs/ct-lint.yaml --lint-conf ./.github/configs/lintconf.yaml
```

---

## Submitting a Pull Request

1. **Commit your changes:**
   Write clear and concise commit messages.
   ```bash
   git commit -s -m "feat(gdc-buckets): add support for storage class configuration"
   ```
2. **Push to your fork:**
   ```bash
   git push origin feature/my-new-feature
   ```
3. **Open a Pull Request:**
   - Target the `main` branch.
   - Provide a clear title and description explaining what the PR changes and why.
   - Reference any related issues (e.g., `Fixes #123`).
4. **Complete the PR Checklist:**
   Ensure all items in the pull request checklist are satisfied:
   - [x] **Versioning:** Chart version has been incremented per versioning guidelines.
   - [x] **Documentation:** Relevant documentation has been updated per documentation guidelines.
   - [x] **Changelog:** Chart changelog reflects all changes in this PR per changelog guidelines.
   - [x] **Compatibility:** New values are backward compatible and/or have sensible defaults.
5. **Pass Automated Checks:**
   - Verify that all CI workflows (linting, testing, and Google CLA check) pass successfully.
6. **Code Review:**
   - Maintainers will review your PR and may request changes. Respond to feedback promptly. Once approved, a maintainer will merge your pull request.

