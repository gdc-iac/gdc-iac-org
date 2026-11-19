Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Troubleshooting

## Workload Identity Issues

### "Service account gemini-gui-sa already exists"
If you see an error like:
```
ERROR: (gcloud.iam.service-accounts.create) Resource in projects [PROJECT_ID] is the subject of a conflict: Service account gemini-gui-sa already exists within project projects/PROJECT_ID.
```
This is expected if you have run the setup script before. The script attempts to create the GSA, but if it exists, it will fail safely. You can ignore this error and proceed to the binding steps.

### "serviceaccounts 'gemini-gui-sa' not found"
If you see this error during the binding step:
```
Error from server (NotFound): serviceaccounts "gemini-gui-sa" not found
```
It means the **Kubernetes Service Account (KSA)** has not been created in the cluster yet.

**Resolution:**
Run the following command to explicitly create the KSA before attempting to bind it:

```bash
kubectl create serviceaccount gemini-gui-sa -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
```

Then retry the binding command:
```bash
gcloud iam service-accounts add-iam-policy-binding gemini-gui-sa@${PROJECT_ID}.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/gemini-gui-sa]"
```

### "Unexpected args: [Create the Namespace]"
If you see this error, it likely means you copy-pasted a comment line along with a command in a way that confused the shell. Ensure you copy only the command lines or paste them carefully.

## Database Issues

### "relation 'chats' does not exist"
If the backend logs show errors about missing tables, the `init.sql` might not have run.
**Resolution:**
1.  Check the Postgres logs: `kubectl logs -l app=postgres -n ${NAMESPACE}`
2.  Delete the Postgres pod to force a restart (if using a PVC, data persists, but init scripts only run on fresh volume creation usually. For emulation, you might need to delete the PVC to reset).
    ```bash
    kubectl delete statefulset postgres -n ${NAMESPACE}
    kubectl delete pvc -l app=postgres -n ${NAMESPACE}
    kubectl apply -f manifests/gcp/statefulset-postgres.yaml
    ```

## Model Availability & Configuration

### "404 Publisher Model not found"
This error occurs when the selected Gemini model ID is invalid or not available in your GCP region (`us-central1`).

**Resolution:**
1.  **Check Available Models**: Visit the [Vertex AI Model Garden](https://console.cloud.google.com/vertex-ai/model-garden) or [Model Versions Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions) to confirm the correct Model IDs for your region.
2.  **Update Frontend**:
    *   Open `src/frontend/src/components/Header.jsx`.
    *   Update the `models` array with valid IDs:
        ```javascript
        const models = [
          { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
          { id: 'gemini-3.5-pro', name: 'Gemini 3.5 Pro' },
          // Add/Remove models here
        ];
        ```
3.  **Rebuild & Redeploy**:
    ```bash
    ./p10-gemini-gui/scripts/build.sh -p ${PROJECT_ID} -r ${REGISTRY_HOST}
    kubectl rollout restart deployment frontend -n ${NAMESPACE}
    ```

### "404 Publisher Model not found" (Endpoint Issue)
If you are using preview models (e.g., Gemini 3.0) that require a specific or global endpoint:
1.  **Set GEMINI_ENDPOINT**: Edit `manifests/apps/backend.yaml` to uncomment and set `GEMINI_ENDPOINT`.
    ```yaml
    - name: GEMINI_ENDPOINT
      value: "us-central1-aiplatform.googleapis.com" # or your specific endpoint
    ```
2.  **Redeploy Backend**:
    ```bash
    kubectl apply -f manifests/apps/backend.yaml
    kubectl rollout restart deployment backend -n ${NAMESPACE}
    ```

## Checking Logs

If you encounter errors (e.g., "I encountered an error processing your request" or 500 status codes), check the backend logs to see the specific error message from Vertex AI or the database.

```bash
# Check Backend Logs
kubectl logs -l app=backend -n ${NAMESPACE} --tail=50 -f

# Check Frontend Logs (for Nginx/Proxy issues)
kubectl logs -l app=frontend -n ${NAMESPACE} --tail=50 -f

# Check Database Logs
kubectl logs -l app=postgres -n ${NAMESPACE} --tail=50 -f
```
