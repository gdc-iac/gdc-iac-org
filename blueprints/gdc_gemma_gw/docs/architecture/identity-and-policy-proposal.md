# Identity, Group-Aware Prompt Policy, and Quota Proposal

## Objective

This proposal defines the minimum set of code and configuration changes needed to:

1. keep OIDC identity verification trustable across both the gateway and the gemma-client,
2. support per-user or per-group prompt policy decisions at the client layer,
3. apply shared quota enforcement at the gateway or Envoy layer so clients cannot bypass the policy.

This recommendation is based on the current repo architecture: the gateway already authenticates and routes requests, the client backend builds the application-specific prompt context, and the Envoy InferencePool chart already supports per-user token rate limiting.

---

## Design Principles

- Identity enforcement belongs at the trust boundary: the gateway must verify JWTs and reject spoofed headers.
- User/group policy belongs where the application semantics live: the gemma-client backend is the correct place to decide what system prompt or guardrails apply for a user or group.
- Shared quotas belong at the inference enforcement layer: gateway or Envoy, not inside the client, because a client-side quota can be bypassed.
- Stable identities must be keyed on a canonical subject, not on mutable usernames.

---

## Current State Review

### 1. Gateway OIDC validation is the enforcement layer

The gateway verifies bearer JWTs via Keycloak JWKS and stores the resulting identity on request state in [`gateway/proxy/main.py`](../gateway/proxy/main.py). It then forwards a user ID using the `X-User-ID` header to the downstream inference backend in the chat route.

Why this matters:

- This is the point where the repo already centralizes trust and access decisions.
- This is also the correct place to enforce rate limits and token budgets because every request passes through it.

### 2. gemma-client is the policy composer

The client backend authenticates the user in [`gemma-client/src/backend/auth.py`](../gemma-client/src/backend/auth.py), and the actual prompt composition happens in [`gemma-client/src/backend/chat.py`](../gemma-client/src/backend/chat.py).

Why this matters:

- The client already assembles the system instruction, file/source context, and user history.
- That makes it the best place to choose a system prompt variation or application policy based on a verified group or role.

### 3. Envoy already contains quota logic

The optional Envoy chart in [`blueprints/envoy-inference-pool/templates/aigatewayroute.yaml`](../blueprints/envoy-inference-pool/templates/aigatewayroute.yaml) sets `llmRequestCosts` and a `BackendTrafficPolicy` rate limit keyed off `X-User-ID` with a default value of 50,000 tokens/hour in [`blueprints/envoy-inference-pool/values.yaml`](../blueprints/envoy-inference-pool/values.yaml).

Why this matters:

- A quota mechanism already exists in the repo and aligns with the gateway’s role as the enforcement boundary.
- The proposal should extend this mechanism rather than re-create a new quota system in the client.

---

## Proposed Changes

### Change 1: Harden OIDC validation across both gateway and gemma-client

Proposed modification:

- Require `iss` and `aud` validation in both the gateway and `gemma-client` JWT validation code.
- Normalize an authenticated user identity as a stable subject pair such as `iss + sub`, and keep `preferred_username` as a display label only.
- Accept forwarded identity headers only when the header is from a trusted internal hop and the request is otherwise trusted; otherwise reject it.

Files to update:

- [`gateway/proxy/main.py`](../gateway/proxy/main.py)
- [`gemma-client/src/backend/auth.py`](../gemma-client/src/backend/auth.py)

Why this change is recommended:

- The current gateway code explicitly disables `verify_aud` and then prefers the username over the stable subject. That makes policy input mutable and weakens auditability.
- The current client auth path follows the same pattern; it is suitable for demo mode but not for production policy enforcement.
- Stable subject-based identity is required to support individual-user quotas and per-user/group policy decisions without collisions or username reuse.

Expected behavior after change:

- A token must match the expected Keycloak issuer and client audience.
- User quota keys must be stable across reauth and username changes.
- If a request lacks a verified JWT, only a trusted security boundary may set identity headers, and those values must be sanitized.

Verification criteria:

- Unit tests verifying valid JWT acceptance and invalid/mismatched `aud` or `iss` rejection.
- Integration test showing the same user identity is used consistently across calls.

---

### Change 2: Add a shared user/group identity model to the client backend

Proposed modification:

- Extend the `User` model to include `subject`, `groups`, and `preferred_username` if needed.
- Parse `realm_access.roles` plus a Keycloak groups claim from the verified JWT token.
- Store these values in the request auth context for use by the client policy layer.

Files to update:

- [`gemma-client/src/backend/models.py`](../gemma-client/src/backend/models.py)
- [`gemma-client/src/backend/auth.py`](../gemma-client/src/backend/auth.py)
- optionally [`gemma-client/src/backend/main.py`](../gemma-client/src/backend/main.py) if a policy context is exposed outside the direct chat path

Why this change is recommended:

- The client backend is where the app-specific prompt logic already lives.
- Group-aware prompts are an application policy decision, not an inference-engine decision.
- Without a structured user context, a prompt policy can only be based on usernames or ad hoc headers, which is brittle and not portable.

Expected behavior after change:

- Authenticated requests expose both role and groups.
- Prompt selection logic can check `groups`, `role`, or `subject` in a deterministic way.
- The client backend can decide whether to inject a stricter system instruction for a specific group.

Verification criteria:

- Unit tests covering users with one role, multiple roles, and several groups.
- Negative tests where the groups claim is missing or malformed.

---

### Change 3: Implement a group-aware prompt policy in the client backend

Proposed modification:

- Centralize prompt decision logic in a helper, for example `resolve_system_policy(user, context)` or `select_system_instruction_for_user(user, file_context, mode)`.
- Apply precedence rules such as:
  1. explicit admin override,
  2. specific group policy,
  3. default role-based policy,
  4. no override.
- Keep user-provided system or override instructions as a lower-priority layer unless an admin explicitly enables them.

Files to update:

- [`gemma-client/src/backend/chat.py`](../gemma-client/src/backend/chat.py)
- optionally a new helper module under `gemma-client/src/backend/` if the current chat file becomes too large

Why this change is recommended:

- The current code injects a single app-wide system instruction directly in the client. That is the correct place to vary behavior by group, but it should be explicit and centralized rather than spread across multiple route handlers.
- Group-specific prompts are not general inference enforcement; they are application behavior and should avoid hard-coding policy into the gateway.
- This keeps the prompting logic portable and easy to unit-test without a dependency on a particular backend runtime.

Expected behavior after change:

- A user in a `research` or `analyst` group gets a different system prompt than a general user.
- A user in a `support` group can be limited to grounded responses or stricter source constraints.
- Security-critical instructions remain server-authoritative rather than client-supplied.

Verification criteria:

- Prompt selection tests for group, role, and default behavior.
- Regression checks ensuring user-provided custom system instructions cannot bypass the server policy.

---

### Change 4: Keep quota enforcement at the gateway/Envoy layer

Proposed modification:

- Keep the existing Envoy `BackendTrafficPolicy` as the shared enforcement point and extend it with per-user or per-group policy classes where needed.
- Use the gateway’s verified identity context to populate the `X-User-ID` or a derived quota key; do not let the client decide the quota key.
- If the deployment needs distinct quotas for different user segments, add a quota table or policy map keyed by verified `sub` or `group` in the gateway control plane.

Files to update:

- [`gateway/proxy/main.py`](../gateway/proxy/main.py)
- [`blueprints/envoy-inference-pool/templates/aigatewayroute.yaml`](../blueprints/envoy-inference-pool/templates/aigatewayroute.yaml)
- [`blueprints/envoy-inference-pool/values.yaml`](../blueprints/envoy-inference-pool/values.yaml)

Why this change is recommended:

- Quota enforcement is a capacity control, not a user-experience feature. It must be applied once at the shared entry point.
- The client backend is not an authoritative trust boundary and can be bypassed by direct API calls or alternate clients.
- The repo already has quota primitives in Envoy, so extending them is lower-risk than introducing a second quota system in the client.

Expected behavior after change:

- Different user tiers or groups can map to different token budgets.
- The gateway still forwards a stable identity and the proxy remains the only place where trust is enforced.
- Direct calls without a verified identity fail before the quota layer is reached.

Verification criteria:

- Integration tests confirming that anonymous or spoofed requests are rejected before quota is applied.
- Policy tests checking that a user in a higher-tier group gets a higher limit.

---

### Change 5: Add a policy-and-identity verification checklist to the documentation

Proposed modification:

- Add a short authoritative section in the docs explaining which responsibilities live in the gateway, the client backend, and the Envoy rate limit layer.
- State explicit precedence rules for identity, prompt policy, and quota enforcement.

Recommended documentation touchpoints:

- [`docs/README.md`](../docs/README.md)
- [`docs/architecture/security-performance-guide.md`](../docs/architecture/security-performance-guide.md)
- [`docs/operations/keycloak_integration_guide.md`](../docs/operations/keycloak_integration_guide.md)

Why this change is recommended:

- This repo already has a strong separation between architecture, operations, and testing docs.
- Without a written policy boundary, future contributors may place quotas or user prompt logic in the wrong place.
- This is especially important because the client’s backend is natural for prompt logic, but dangerous for enforcement logic.

Expected behavior after change:

- Design reviewers can quickly tell whether a new feature belongs in the gateway, client backend, or Envoy policy.
- Feature requests around quotas or authentication will be routed to the correct layer.

Verification criteria:

- Doc review sign-off from engineering and security reviewers.
- No future feature request adds enforcement logic into a client-only component without explicit review.

---

## Recommended Implementation Order

1. Harden JWT validation in gateway and client.
2. Add `subject` and `groups` to the client identity model.
3. Add centralized prompt policy helpers in `gemma-client`.
4. Extend the Envoy/ gateway quota mapping to support policy-based tiers.
5. Update docs and approval gates.

This ordering reduces risk: the trust boundary is corrected first, then application policy is added, and only after that are quotas extended.

---

## Final Recommendation

The correct split is:

- gateway: authentication, trust enforcement, shared quota enforcement
- gemma-client backend: group-aware prompt composition and application policy
- Envoy: shared token-budget enforcement for vLLM traffic

This architecture is the safest and most maintainable because it matches the current repo structure, preserves separation of concerns, and prevents a client-only workaround from bypassing the real inference policy boundary.
