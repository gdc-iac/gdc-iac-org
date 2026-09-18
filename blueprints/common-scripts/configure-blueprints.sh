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
# We default to 'test-project' so that by default, the script only changes the Project IDs
if [ -z "$TARGET_NAMESPACE" ]; then
    TARGET_NAMESPACE="test-project"
fi

# Find all YAML files in subdirectories (including testing)
find "$TARGET_DIR" -type f \( -name "*.yaml" -o -name "*.yml" \) -not -path "*/.*" | while read -r file; do
    echo "Processing $file..."
    
    NS_PLACEHOLDER="___NAMESPACE_PLACEHOLDER___"
    
    # Protect exact namespace string usages
    sed -i.bak "s|namespace: test-project|namespace: $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|\.test-project\.svc|\.$NS_PLACEHOLDER.svc|g" "$file"

    # Replace Registry URL (Longer matches first)
    sed -i.bak "s|us-central1-docker.pkg.dev/test-project/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|us-central1-docker.pkg.dev/your-project-id/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|harbor.gdc.local|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|test-registry.local|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|gcr.io/gdc-airgap|$REGISTRY_URL|g" "$file"
    
    # Replace Project ID 
    # Because we protected standard namespace strings above, any remaining
    # 'test-project' strings are acting as a Project ID placeholder.
    sed -i.bak "s|test-project|$PROJECT_ID|g" "$file"
    sed -i.bak "s|your-project-id|$PROJECT_ID|g" "$file"
    sed -i.bak "s|my-gdc-project|$PROJECT_ID|g" "$file"
    
    # Handle GCS Bucket hardcoding
    sed -i.bak "s|raw-docs-your-project-id|raw-docs-$PROJECT_ID|g" "$file"
    
    # Restore Namespace from placeholder
    sed -i.bak "s|$NS_PLACEHOLDER|$TARGET_NAMESPACE|g" "$file"
    
    rm "${file}.bak"
done

# Also update manual scripts if they exist
find "$TARGET_DIR" -type f -name "*.sh" -not -name "configure-blueprints.sh" -not -path "*/.*" | while read -r file; do
    echo "Processing script $file..."
    
    NS_PLACEHOLDER="___NAMESPACE_PLACEHOLDER___"
    
    # Protect exact namespace string usages in bash variables and parameters
    sed -i.bak "s|namespace: test-project|namespace: $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|-n test-project|-n $NS_PLACEHOLDER|g" "$file"
    sed -i.bak "s|\.test-project\.svc|\.$NS_PLACEHOLDER.svc|g" "$file"
    sed -i.bak "s| test-project namespace| $NS_PLACEHOLDER namespace|g" "$file"
    sed -i.bak "s|'test-project'|'$NS_PLACEHOLDER'|g" "$file"
    
    # Protect exact variable assignments and explicit string conditionals 
    sed -i.bak "s|NAMESPACE=\"test-project\"|NAMESPACE=\"$NS_PLACEHOLDER\"|g" "$file"
    sed -i.bak "s|NAMESPACE=\"\${NAMESPACE:-test-project}\"|NAMESPACE=\"\${NAMESPACE:-$NS_PLACEHOLDER}\"|g" "$file"
    sed -i.bak "s|\${NAMESPACE:-test-project}|\${NAMESPACE:-$NS_PLACEHOLDER}|g" "$file"
    sed -i.bak "s|\"test-project\"|\"$NS_PLACEHOLDER\"|g" "$file"

    # Important Edge Case: P10 Backend hardcodes value: "test-project" # Placeholder
    # This matches the regex above precisely `"$NS_PLACEHOLDER"`, shielding it from PROJECT_ID replacement!
    # Let's forcibly unshield the specific env var rows back so they get converted
    sed -i.bak "s|value: \"$NS_PLACEHOLDER\" # Placeholder|value: \"$PROJECT_ID\" # Placeholder|g" "$file"
    sed -i.bak "s|gs://gemini-gui-files-$NS_PLACEHOLDER|gs://gemini-gui-files-$PROJECT_ID|g" "$file"

    # Replace Registry URL
    sed -i.bak "s|us-central1-docker.pkg.dev/test-project/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|us-central1-docker.pkg.dev/your-project-id/blueprint-images|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|harbor.gdc.local|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|test-registry.local|$REGISTRY_URL|g" "$file"
    sed -i.bak "s|gcr.io/gdc-airgap|$REGISTRY_URL|g" "$file"
    
    # Replace Project ID
    sed -i.bak "s|test-project|$PROJECT_ID|g" "$file"
    sed -i.bak "s|your-project-id|$PROJECT_ID|g" "$file"
    sed -i.bak "s|my-gdc-project|$PROJECT_ID|g" "$file"

    # Restore Namespace from placeholder
    sed -i.bak "s|$NS_PLACEHOLDER|$TARGET_NAMESPACE|g" "$file"
    
    rm "${file}.bak"
done

echo ""
echo "Done! Blueprints in '$TARGET_DIR' configured for project '$PROJECT_ID'."

# Save configuration state for packaging
echo "OLD_PROJECT=\"${PROJECT_ID}\"" > .configure_state
echo "OLD_NAMESPACE=\"${TARGET_NAMESPACE}\"" >> .configure_state
echo "OLD_REGISTRY=\"${REGISTRY_URL}\"" >> .configure_state
