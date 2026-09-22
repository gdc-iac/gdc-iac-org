#!/bin/bash
set -e

# Default values
DEFAULT_PROJECT="my-gdc-project"
DEFAULT_REGISTRY=${REGISTRY_HOST:-"harbor.gdc.local"}
TARGET_DIR="."

# Usage
usage() {
    echo "Usage: $0 -p <project-id> -r <registry-url> [-n <namespace>] [-d <directory>] [-h]"
    echo "  -p  Target GDC Project ID (default: $DEFAULT_PROJECT)"
    echo "  -r  Target Registry URL (default: $DEFAULT_REGISTRY)"
    echo "  -n  Target Namespace (optional, defaults to Project ID if not set)"
    echo "  -d  Target Directory (default: current directory)"
    echo "  -h  Show this help message"
    exit 1
}

# Parse arguments
PROJECT_ID=""
REGISTRY_URL=""
TARGET_NAMESPACE=""

while getopts "p:r:n:d:h" opt; do
    case $opt in
        p) PROJECT_ID="$OPTARG" ;;
        r) REGISTRY_URL="$OPTARG" ;;
        n) TARGET_NAMESPACE="$OPTARG" ;;
        d) TARGET_DIR="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# Prompt if not provided
if [ -z "$PROJECT_ID" ]; then
    read -p "Enter Target GDC Project ID [$DEFAULT_PROJECT]: " INPUT_PROJECT
    PROJECT_ID=${INPUT_PROJECT:-$DEFAULT_PROJECT}
fi

if [ -z "$REGISTRY_URL" ]; then
    read -p "Enter Target Registry URL [$DEFAULT_REGISTRY]: " INPUT_REGISTRY
    REGISTRY_URL=${INPUT_REGISTRY:-$DEFAULT_REGISTRY}
fi

echo "Configuring blueprints..."
echo "  Project ID: $PROJECT_ID"
echo "  Registry:   $REGISTRY_URL"
echo "  Directory:  $TARGET_DIR"
echo ""

# Check if directory exists
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory '$TARGET_DIR' does not exist."
    exit 1
fi

# Set the TARGET_NAMESPACE if the user didn't provide one
if [ -z "$TARGET_NAMESPACE" ]; then
    TARGET_NAMESPACE="gemma-inference"
fi

# Find all YAML files in subdirectories
find "$TARGET_DIR" -type f \( -name "*.yaml" -o -name "*.yml" \) -not -path "*/.*" -not -path "*/chart/*" -not -path "*/charts/*" -not -path "*/blueprints/ollama-gke/*" -not -path "*/blueprints/vllm-gke/*" | while read -r file; do
    echo "Processing $file..."
    
    NS_PLACEHOLDER="___NAMESPACE_PLACEHOLDER___"
    
    # Protect exact namespace string usages
    sed -i.bak "s|namespace: test-project|namespace: $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|namespace: gemma-inference|namespace: $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|\.test-project\.svc|\.$NS_PLACEHOLDER.svc|g" "$file"
    sed -i.bak "s|\.gemma-inference\.svc|\.$NS_PLACEHOLDER.svc|g" "$file"

    # Replace Registry URL (Longer matches first)
    sed -i.bak "s|us-central1-docker.pkg.dev/test-project/blueprint-images/p10-backend:latest|$REGISTRY_URL/gemma-client-backend:latest|g" "$file"
    sed -i.bak "s|us-central1-docker.pkg.dev/test-project/blueprint-images/p10-frontend:latest|$REGISTRY_URL/gemma-client-frontend:latest|g" "$file"
    sed -i.bak "s|us-central1-docker.pkg.dev/test-project/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|us-central1-docker.pkg.dev/your-project-id/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|harbor.gdc.local|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|test-registry.local|$REGISTRY_URL|g" "$file"
    
    # Replace Project ID 
    sed -i.bak "s|test-project|$PROJECT_ID|g" "$file"
    sed -i.bak "s|your-project-id|$PROJECT_ID|g" "$file"
    sed -i.bak "s|my-gdc-project|$PROJECT_ID|g" "$file"
    
    # Handle GCS Bucket hardcoding
    sed -i.bak "s|gemini-gui-files-test-project|gemma-client-files-$PROJECT_ID|g" "$file"
    sed -i.bak "s|gemma-client-files-test-project|gemma-client-files-$PROJECT_ID|g" "$file"
    
    # Restore Namespace from placeholder
    sed -i.bak "s|$NS_PLACEHOLDER|$TARGET_NAMESPACE|g" "$file"
    
    rm "${file}.bak"
done

# Also update manual scripts if they exist
find "$TARGET_DIR" -type f -name "*.sh" -not -name "configure-blueprints.sh" -not -path "*/.*" -not -path "*/chart/*" -not -path "*/charts/*" -not -path "*/blueprints/ollama-gke/*" -not -path "*/blueprints/vllm-gke/*" | while read -r file; do
    echo "Processing script $file..."
    
    NS_PLACEHOLDER="___NAMESPACE_PLACEHOLDER___"
    
    sed -i.bak "s|namespace: test-project|namespace: $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|namespace: gemma-inference|namespace: $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|-n test-project|-n $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|-n gemma-inference|-n $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|\.test-project\.svc|\.$NS_PLACEHOLDER.svc|g" "$file"
    sed -i.bak "s|\.gemma-inference\.svc|\.$NS_PLACEHOLDER.svc|g" "$file"
    
    sed -i.bak "s|NAMESPACE=\"test-project\"|NAMESPACE=\"$NS_PLACEHOLDER\"|g" "$file"
    sed -i.bak "s|NAMESPACE=\"gemma-inference\"|NAMESPACE=\"$NS_PLACEHOLDER\"|g" "$file"
    sed -i.bak "s|\${NAMESPACE:-test-project}|\${NAMESPACE:-$NS_PLACEHOLDER}|g" "$file"
    sed -i.bak "s|\${NAMESPACE:-gemma-inference}|\${NAMESPACE:-$NS_PLACEHOLDER}|g" "$file"

    sed -i.bak "s|us-central1-docker.pkg.dev/test-project/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|harbor.gdc.local|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|test-registry.local|$REGISTRY_URL|g" "$file"
    
    sed -i.bak "s|test-project|$PROJECT_ID|g" "$file"
    sed -i.bak "s|your-project-id|$PROJECT_ID|g" "$file"
    sed -i.bak "s|my-gdc-project|$PROJECT_ID|g" "$file"

    sed -i.bak "s|$NS_PLACEHOLDER|$TARGET_NAMESPACE|g" "$file"
    
    rm "${file}.bak"
done

echo ""
echo "Done! Blueprints configured for project '$PROJECT_ID' in target '$TARGET_NAMESPACE' (Directory: '$TARGET_DIR')."
