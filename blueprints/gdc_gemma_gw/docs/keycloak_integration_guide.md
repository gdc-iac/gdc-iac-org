Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Keycloak Integration Guide for GDC

> **Version:** 1.1

This guide outlines how to transition the P6 Resilient RAG Agent and Gemma Client from the current "Mock Auth" (header-based) to a production-grade OIDC authentication system using Keycloak on Google Distributed Cloud (GDC).

## Architecture Overview

*   **Identity Provider (IdP):** Keycloak (running on GDC).
*   **Frontend (React):** Uses OIDC Authorization Code Flow with PKCE to obtain a JWT (Access Token).
*   **Backend (FastAPI):** Validates the JWT signature and claims (roles, user ID) to enforce RBAC.

## 1. Keycloak Configuration

1.  **Create a Realm:** e.g., `gdc-rag-realm`.
2.  **Create a Client:**
    *   **Client ID:** `rag-frontend`
    *   **Client Protocol:** `openid-connect`
    *   **Access Type:** `public` (since it's a SPA)
    *   **Valid Redirect URIs:** `https://<your-frontend-url>/*`
    *   **Web Origins:** `https://<your-frontend-url>`
3.  **Create Roles:**
    *   `admin`
    *   `user`
4.  **Create Users:** Assign roles to users.

### GDC Ingress & Gateway Configuration (Gateway API Standard)
> [!WARNING]
> **CRITICAL GDC COMPLIANCE REQUIREMENT:**
> The legacy Nginx Ingress Controller standard (`networking.k8s.io/v1 Ingress`) is **RETIRING** from GDC production racks. Physical environments utilize the modern **Kubernetes Gateway API** standard (`gateway.networking.k8s.io/v1`). You must expose Keycloak in production using an `HTTPRoute` resource mapped to the shared platform gateway:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: keycloak-route
  namespace: gemma-inference
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: gemma-inference # References shared platform gateway
  hostnames:
  - "app.gdc.local" # Production enterprise FQDN domain target
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /auth
    backendRefs:
    - name: keycloak-svc
      port: 8080
```

## 2. Frontend Integration (React)

We recommend using `react-oidc-context` (which wraps `oidc-client-ts`).

### Installation
```bash
npm install react-oidc-context oidc-client-ts
```

### Implementation (`src/AuthProvider.jsx`)

Replace the `UserContext.jsx` mock provider with a real OIDC provider.

```jsx
import { AuthProvider } from "react-oidc-context";

const oidcConfig = {
  authority: "https://<keycloak-url>/realms/gdc-rag-realm",
  client_id: "rag-frontend",
  redirect_uri: window.location.origin,
  onSigninCallback: () => {
    // Remove query params after login
    window.history.replaceState({}, document.title, window.location.pathname);
  }
};

export const AppAuthProvider = ({ children }) => (
  <AuthProvider {...oidcConfig}>
    {children}
  </AuthProvider>
);
```

### Accessing User Info

```jsx
import { useAuth } from "react-oidc-context";

const MyComponent = () => {
  const auth = useAuth();

  if (auth.isLoading) return <div>Loading...</div>;
  if (!auth.isAuthenticated) return <button onClick={() => auth.signinRedirect()}>Log in</button>;

  const user = auth.user?.profile;
  const token = auth.user?.access_token;

  return <div>Hello, {user.preferred_username}</div>;
};
```

### Passing Token to Backend

Update `axios` interceptors to attach the token:

```javascript
axios.interceptors.request.use(config => {
  const token = auth.user?.access_token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

## 3. Backend Integration (FastAPI)

Use `python-jose` to validate the JWT.

### Installation
```bash
pip install python-jose[cryptography] requests
```

### Implementation (`auth.py`)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import requests

OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")
KEYCLOAK_URL = "https://<keycloak-url>/realms/gdc-rag-realm"
ALGORITHMS = ["RS256"]

# Cache public keys
jwks = requests.get(f"{KEYCLOAK_URL}/protocol/openid-connect/certs").json()

async def get_current_user(token: str = Depends(OAUTH2_SCHEME)):
    try:
        payload = jwt.decode(token, jwks, algorithms=ALGORITHMS, audience="account")
        user_id = payload.get("sub")
        roles = payload.get("realm_access", {}).get("roles", [])
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token claims")
            
        return {"id": user_id, "roles": roles, "username": payload.get("preferred_username")}
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
```

### RBAC Enforcement

Update endpoints to check roles from the validated token instead of headers.

```python
@app.post("/upload")
async def upload(user = Depends(get_current_user)):
    if "admin" not in user["roles"]:
        # ...
```

## 4. Migration Steps

1.  Deploy Keycloak on GDC.
2.  Update Frontend to use `react-oidc-context`.
3.  Update Backend to validate Bearer tokens.
4.  Remove `X-User-ID` header logic.

## 5. Step-by-Step Example: Replacing "Fake Users" in P6/P7
By default, patterns like **P6 (Resilient RAG Agent)** and **P7 (Agentic Data Analyst)** utilize a lightweight "Mock Auth" system intended strictly for feature validation. This means the UI features a dropdown allowing you to select "Fake Users" (e.g., Alice, Bob, Admin) which simply sets an `X-User-ID` header.

**To execute this Advanced Test:**

### Step A: Do Not Break the Base Deployment
First, completely deploy P6/P7 normally and verify the mocked multiple users work (e.g., verify Alice can't see Bob's SQL graphs). Only proceed once the baseline architecture passes verification. This guarantees the architectural dependencies (like the Vector DB or Text-to-SQL logic) are functioning on their own!

### Step B: Provision Keycloak Identically to the Mock Users
Using the P12 blueprint, deploy Keycloak. Go to the Keycloak Admin Console (`localhost:8082`) and strictly recreate the mock entities to avoid rewriting backend logic:
1. Create a Keycloak Realm: `gdc-rag-realm`.
2. **Create the OIDC Client:** Go to 'Clients' -> 'Create Client':
   * **Client ID:** `rag-frontend`
   * **Valid Redirect URIs:** `*` (or your explicit `https://8081-w-.../*` P6 frontend URL)
   * **Web Origins:** `*` (Crucial: without this, Keycloak blocks React via CORS!)
3. Create Roles (under Realm Roles): `user` and `admin`.
4. **Replicate the Fake Users:** Go to 'Users' -> 'Add User':
   * **Username:** `alice` | **Role:** `user` (Assign via Role Mapping)
   * *Important:* Click the "Credentials" tab, set a password (e.g., `password`), and toggle "Temporary" to **OFF**.

### Step C: Patch the Frontend (React)
The absolute cleanest way to integrate Keycloak into Pattern 6 without breaking the application's structure is to completely replace the mock logic inside `p6-resilient-rag-agent/example-app/frontend/src/UserContext.jsx` with a Keycloak wrapper. 

1. **Install OIDC Libraries:**
   Navigate your terminal into `p6-resilient-rag-agent/example-app/frontend` and run:
   ```bash
   npm install react-oidc-context oidc-client-ts
   ```

2. **Replace `UserContext.jsx`:**
   Open the file and completely replace its contents with this elegant interceptor (ensure you update the target `authority` URL to match your Workstation/Ingress):

```javascript
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useAuth, AuthProvider } from 'react-oidc-context';

const UserContext = createContext();
export const useUser = () => useContext(UserContext);

const oidcConfig = {
  // TODO: Replace with your actual Keycloak URL 
  authority: "https://<your-keycloak-ingress-or-workstation-url>/realms/gdc-rag-realm",
  client_id: "rag-frontend",
  redirect_uri: window.location.origin,
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  }
};

// This internal wrapper waits for Keycloak to authorize, then bridges 
// the Keycloak JWT straight into the standard P6 context variables!
const KeycloakBridge = ({ children }) => {
  const auth = useAuth();
  const [user, setUser] = useState(null);

  useEffect(() => {
    if (auth.isAuthenticated && auth.user) {
      // Decode Keycloak roles out of the token
      const isAdmin = auth.user.profile.realm_access?.roles?.includes("admin");
      setUser({
        id: auth.user.profile.preferred_username,
        role: isAdmin ? 'admin' : 'user',
        name: auth.user.profile.preferred_username,
        token: auth.user.access_token // Save token to send to FastAPI!
      });
    }
  }, [auth.isAuthenticated, auth.user]);

  if (auth.isLoading) return <div className="p-10 text-white">Loading Secure Identity Boundary...</div>;
  if (!auth.isAuthenticated) return (
    <div className="flex h-screen bg-gray-900 items-center justify-center">
      <button onClick={() => auth.signinRedirect()} className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-lg font-bold">
        Authenticate via Keycloak
      </button>
    </div>
  );
  if (!user) return null;

  // We return empty personas/login functions so the old Sidebar dropdown silently breaks without crashing
  return (
    <UserContext.Provider value={{ user, login: () => {}, personas: [] }}>
      {children}
    </UserContext.Provider>
  );
};

export const UserProvider = ({ children }) => {
  return (
    <AuthProvider {...oidcConfig}>
      <KeycloakBridge>{children}</KeycloakBridge>
    </AuthProvider>
  );
};
```

3. **Cleanup:** If you want perfection, open `src/components/Sidebar.jsx` and delete the `<select>` dropdown block that previously let you switch mock users.

4. **Rebuild the Container & Bounce the Pod:** 
   Because the P6 frontend is a compiled React application baked tightly inside an NGINX Docker container, simply editing `UserContext.jsx` on your Workstation's physical disk doesn't update the active Kubernetes pod. You must physically recompile the container!
   ```bash
   # 1. Rebuild and push the updated frontend image
   ./p6-resilient-rag-agent/scripts/build.sh
   
   # 2. Tell Kubernetes to violently kill the old mock-auth frontend
   kubectl rollout restart deployment frontend -n test-project
   ```
   Now, when you port-forward your frontend (`kubectl port-forward svc/frontend 8081:80`), you will see the authentic secure Identity Gateway!

> [!WARNING]
> **Testing Caveat: The Google Cloud Workstations Proxy Anomaly**
> If you are deploying and testing this OIDC overlay inside a Google Cloud Workstation Web Preview environment, you may experience a "flashing screen" loop when clicking the Authenticate button, alongside browser F12 Console red ink citing `Access to fetch ... has been blocked by CORS policy ..._workstation/forwardAuthCookie`.
> 
> **Why this happens (The Sandboxed Iframe Trap):** 
> Keycloak's React-based master administration console is designed to initialize a session-tracking iframe (`login-status-iframe.html`). To prevent clickjacking, this iframe is running under strict sandboxing (`sandbox="allow-scripts allow-same-origin"`). Modern secure browsers (Chrome 120+ / Brave) strictly enforce that **requests generated inside sandboxed iframes do not transmit session credentials**.
> 
> Because the request to `/login-status-iframe.html/init` is fired inside this sandboxed iframe, the browser does not attach the Google Cloud Workstations secure preview session authentication cookie (`forwardAuthCookie`). The Workstation secure proxy intercepts this anonymous request, immediately **rejects it and returns a `403 Forbidden`**, causing Keycloak's master admin dashboard to hang on the loading spinner permanently!
> 
> **The Staging Staging Verdict:** 
> *   **You cannot access Keycloak's Master Admin UI inside standard Cloud Workstation preview tabs.** This is expected behavior under GCP IAM controls, as private/incognito windows (which bypass caching issues) are blocked with `401 Permission Denied` due to missing Google authentication headers.
> *   **The GitOps Solution (Absolute Staging Parity):** To bypass this block completely and align with GDC physical rack GitOps standards, **do not manually click console screens to register realms!** We implement an **Automated Realm Import Strategy**.
> *   By packaging the target realm (`gdc-rag-realm`), OIDC clients (`rag-frontend`), roles (`user`/`admin`), and staging personas (`alice`/`charlie` preloaded with the correct passwords) inside a GKE ConfigMap, Keycloak reads the JSON and **boots up 100% pre-configured on startup!** Your React app redirects directly to the dynamic login screen, completely bypassing the master admin iframe checks!
> *   In an authentic GDC Air-Gapped deployment, both the frontend, backend, and Keycloak sit securely behind a unified Kubernetes Ingress origin (`https://gdc-app.local` and `https://gdc-app.local/auth`), completely eliminating token-exchange and sandbox cookie failures!

### Step D: Patch the Backend
Because standard A2A/FastAPI gateways are used, edit the `auth.py` or middleware dependency.
1. Remove `user_id = Header(default="alice")`.
2. Adopt the `get_current_user(token: str = Depends(OAUTH2_SCHEME))` snippet (from Section 3) which validates the Keycloak JWT.
3. Your agent functions fundamentally do not change—they still receive a string `user_id`, only now it is cryptographically signed rather than mock-injected!

This approach maintains the decoupled integrity of applications while providing a structured path for PA personas to test authentic identity overlay using Keycloak!

---

## ⚖️ GCP Staging vs. GDC-ag Production: Structural Differentiations

To maintain operational compliance, you must separate the emulated staging sandbox configurations from the physical GDC air-gapped production setup:

| Operational Dimension | GCP GKE Staging Sandbox VM (Cloud Workstations) | GDC Air-Gapped Physical Production Racks |
| :--- | :--- | :--- |
| **Unified Exposure Gateway** | Temporary **NGINX Reverse Proxy Pod** (`gemma-ingress-gateway`) | Platform **Hardware Load Balancers & Ingress Controller Gateway** |
| **Exposure Entry Port** | Port-forwarded unified preview port **Port `8081`** | Native HTTPS **Port `443`** (SSL/TLS terminated natively at platform entry) |
| **Domain Host Target** | Dynamic browser subdomain mapping (`8081-w-...cloudworkstations.dev`) | Secure, Unified Enterprise Domain FQDN (e.g. `https://app.gdc.local`) |
| **K8s API Standard** | Developer-custom NGINX sidecar mapping | GDC standard: **Kubernetes Gateway API** (`gateway.networking.k8s.io`) |
| **Dynamic Key Resolution** | Internal KubeDNS lookup mapping on sandbox namespace | Hardened service-to-service routing utilizing GDC internal DNS |

---

## 🛠️ Sandbox Troubleshooting & Hardening Gotchas

### 1. In-Memory Database Recycles (Table Not Found Errors)
*   **The Symptom**: Keycloak boots successfully, but during welcome page redirects or login handshakes, it crashes with `JdbcSQLSyntaxErrorException: Table "USER_ENTITY" not found (this database is empty)`.
*   **The Cause**: H2 in-memory databases (`dev-mem` vendor) discard their dynamic RAM schemas as soon as the active connection count drops to `0`. Keycloak's connection pool (Agroal pool) has a minimum pool size of `0`, causing the database to be wiped during idle start handovers.
*   **The Fix**: Force the GKE connection pool to keep at least one connection active permanently by setting:
    `KC_DB_POOL_MIN_SIZE=1`
    This preserves your tables across transient startup recycles and boot events.

### 2. Command-Line Truncation Loops (Picocli Crashes on Startup)
*   **The Symptom**: Keycloak terminates with `Exit Code 1` at 41 seconds during the `Updating the configuration...` phase, printing no Quarkus logs.
*   **The Cause**: Keycloak's startup shell wrapper `kc.sh` evaluates configurations using `eval` blocks. Passing connection URL strings containing semi-colons (`;DB_CLOSE_DELAY=-1;...`) splits the command stream, truncating the Java start command and crashing the container boot.
*   **The Fix**: Avoid using `KC_DB_URL` with semi-colons inside the YAML env array! Use `KC_DB_POOL_MIN_SIZE=1` to keep memory DBs alive instead, or pass H2 parameters under `KC_DB_URL_PROPERTIES`.

### 3. Evicting the Static Browser Cache (Chrome Hard Reload Trick)
*   **The Symptom**: Bouncing frontend pods has "no effect", and the old Mock dropdown switcher continues to render.
*   **The Cause**: Chromium browsers aggressively cache static Vite/React Javascript and CSS bundles. Standard reloads fail to evict this disk cache.
*   **The Fix**: Evict the cache directly inside your standard, authenticated browser window using Chrome's hidden context menu:
    1. Open the browser tab targeting port 8081 (loading the chatbot app).
    2. Open Developer Tools by pressing **`F12`** (keep the panel open!).
    3. **Right-Click** (or Click and Hold) on the browser's **Reload (Refresh) button** next to the URL bar.
    4. A context menu will appear. Click the third option: **"Empty Cache and Hard Reload"**!

## 6. Finalizing for GDC Air-Gapped Production (GDC-ag)

When migrating your tested OIDC architecture into actual production deployment on physical GDC Air-Gapped rack hardware, you must harden four critical boundaries:

### 1. Transition to Kubernetes Gateway API
Do not deploy the Nginx sidecar proxy container inside GDC production. Expose Keycloak, RAG backend services, and static UI bundles using the GDC-ag dynamic Gateway API standard:

```yaml
# production-gateway-routing.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gemma-unified-routes
  namespace: gemma-inference
  labels:
    app.kubernetes.io/part-of: gemma-client
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: gemma-inference # References shared platform gateway
  hostnames:
  - "app.gdc.local" # Production enterprise FQDN target
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /auth
    backendRefs:
    - name: keycloak-svc
      port: 8080
  - matches:
    - path:
        type: PathPrefix
        value: /api
    filters:
    - type: URLRewrite
      urlRewrite:
        path:
          type: ReplacePrefixMatch
          replacePrefixMatch: /
    backendRefs:
    - name: backend-svc
      port: 8000
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: frontend-svc
      port: 80
```

### 2. Lock Down the OIDC Client Gatekeepers
Leaving `*` inside your Client settings on GDC-ag constitutes a catastrophic security vulnerability, as it allows arbitrary external websites to maliciously initiate login handshakes against your realm.
* Open the Keycloak Admin Console inside GDC-ag and edit your `rag-frontend` client. 
* Change **Valid Redirect URIs** from `*` physically to: `https://app.gdc.local/*` (or whatever your absolute native physical ingress URL is).
* Change **Web Origins** from `*` physically to: `https://app.gdc.local`.

### 3. Update the Reachable `App.jsx` Authority
Inside your compiled React image, configure the static environment block (`VITE_OIDC_AUTHORITY`) to point strictly at your physical DNS routing path:
```javascript
VITE_OIDC_AUTHORITY="https://app.gdc.local/auth/realms/gdc-rag-realm"
```

### 4. Optimize the FastAPI Backend JWT Callbacks (Internal KubeDNS resolution)
When the Python FastAPI backend inside GDC-ag evaluates the JWT token extracted from the Header, it must rapidly query Keycloak's open-source `.well-known` endpoints to cryptographically verify the RSA signature. 
Rather than forcing your FastAPI backend to execute an expensive network call bouncing all the way out to the public GDC Load Balancer FQDN and back (which requires complex internal physical DNS routing as well as negating the security boundaries of an air-gapped platform), point your backend Python `auth.py` dependency strictly to the **internal Kubernetes Service DNS inside the unified `gemma-inference` namespace**:

```python
# auth.py (Targeting native K8s internal API routing instead of public DNS)
KEYCLOAK_URL = "http://keycloak-svc.gemma-inference.svc.cluster.local:8080/auth/realms/gdc-rag-realm"
```
This forces the token-signature validation to run blazingly fast physically inside your cluster nodes on the internal KubeDNS namespace, drastically increasing identity resolution resilience!

### 5. Architectural Distinction: Application Identity vs. GDC Platform Identity
This blueprint deploys Keycloak entirely as an **Application-Level Identity Provider (IdP)**. It is specifically designed for Platform Administrators (PAs) who need to provide robust, federated authentication boundaries strictly to the end users accessing their deployed applications (such as the Gemma Client chatbot).

**Distinction from GDC Platform Identity:** 
Do not confuse this localized application authentication overlay with deploying a foundational GDC Organizational IdP! 
Wiring identities for logging natively into the physical GDC Organization platform (e.g., accessing the local GDC Cloud Console UI or utilizing the `gdcloud` CLI) is the strict responsibility of Infrastructure Operators (IOs) configuring a centralized Customer IdP directly on the GDC physical infrastructure layer. 

If you are an IO attempting to configure control-plane organizational platform access for your tenant, do not use this PA blueprint. Refer strictly to the official Google operating manual instead:
* [GDC Air-Gapped: Connect a Customer IdP to an Organization](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/infrastructure/io-operations-30/create-customer-org#connect-customer-idp-to-org)
