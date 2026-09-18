# Set Org Admin cluster context
kubectl set-context gdchservices-admin-us-east70-b-gdch_console-gdchservices-us-east70-b-google-gdch-test_gdchservices-admin

# Prepare cluster definition
export K8S_VERSION=$( kubectl get userclustermetadata.upgrade.private.gdc.goog -o=custom-columns=K8S-VERSION:.spec.kubernetesVersion | sort -n | tail -n1 )
export MACHINE_TYPE=$( kubectl get virtualmachinetypes.virtualmachine.gdc.goog -n vm-system --no-headers | awk '$2 == "true" && $1 ~ /-standard-/ {print $1}' | sort -V | head -n 1 )


cat <<EOF > argocd-cluster.yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: argocd-cluster
  namespace: iac-root
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: "${K8S_VERSION}"
  nodePools:
  - name: default-node-pool
    machineTypeName: "${MACHINE_TYPE}"
    nodeCount: 3
  releaseChannel:
    channel: UNSPECIFIED
EOF

#  Apply the configuration
kubectl apply -f argocd-cluster.yaml

# Monitor progress
kubectl get cluster -niac-root --watch
NAME             STATE         K8S VERSION
argocd-cluster   Reconciling   1.32.13-gke.100

