import os
import yaml
import pytest

MANIFEST_DIR = os.path.join(os.path.dirname(__file__), "../gemma-client/manifests")

def get_all_yaml_files(root_dir):
    yaml_files = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith((".yaml", ".yml")):
                yaml_files.append(os.path.join(root, file))
    return yaml_files

@pytest.mark.parametrize("file_path", get_all_yaml_files(MANIFEST_DIR))
def test_manifest_yaml_syntax(file_path):
    """Verify that every Kubernetes manifest file is syntactically valid YAML."""
    assert os.path.exists(file_path)
    with open(file_path, "r") as f:
        try:
            # Multi-document manifests
            docs = list(yaml.safe_load_all(f))
            assert len(docs) > 0
            for doc in docs:
                if doc is not None:
                    assert isinstance(doc, dict)
                    assert "apiVersion" in doc
                    assert "kind" in doc
        except Exception as e:
            pytest.fail(f"Failed to parse YAML for file {file_path}: {e}")

def test_gdc_backend_model_environment_variable():
    """Verify that gemma-client/manifests/gdc/apps/backend.yaml doesn't use gemini-2.5-flash."""
    backend_manifest = os.path.join(MANIFEST_DIR, "gdc/apps/backend.yaml")
    if not os.path.exists(backend_manifest):
        pytest.skip("GDC backend manifest not found.")
        
    with open(backend_manifest, "r") as f:
        docs = list(yaml.safe_load_all(f))
        
    backend_deployment = None
    for doc in docs:
        if doc and doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == "backend":
            backend_deployment = doc
            break
            
    assert backend_deployment is not None, "Backend Deployment manifest not found in GDC backend.yaml"
    
    containers = backend_deployment["spec"]["template"]["spec"]["containers"]
    assert len(containers) > 0
    
    backend_container = containers[0]
    envs = backend_container.get("env", [])
    
    gemma_model_found = False
    gemini_model_found = False
    
    for env in envs:
        if env.get("name") == "GEMMA_MODEL":
            gemma_model_found = True
            assert env.get("value") == "gemma4:26b", "GEMMA_MODEL must be set to gemma4:26b"
        if env.get("name") == "GEMINI_MODEL":
            gemini_model_found = True
            assert env.get("value") != "gemini-2.5-flash", "GEMINI_MODEL should not be set to gemini-2.5-flash"
            
    # Either it should have GEMMA_MODEL or if it uses GEMINI_MODEL it shouldn't be gemini-2.5-flash
    assert gemma_model_found or not gemini_model_found, "Should have transitioned from Gemini to Gemma model environment variables."
