#!/usr/bin/env python3
import os
import gzip
import sys
import argparse
import re
import subprocess

try:
    import docker
except ImportError:
    print("Error: The 'docker' Python library is not installed.")
    print("Please install it using: pip install docker")
    sys.exit(1)

def extract_images_from_manifest(manifest_path):
    """Extracts image names from the manifest file by looking for image: references."""
    images = set()
    if not os.path.exists(manifest_path):
        print(f"Warning: Manifest file not found: {manifest_path}")
        return []
        
    try:
        with open(manifest_path, 'r') as f:
            content = f.read()
            # Find all occurrences of image: followed by a non-whitespace string on the same line
            matches = re.findall(r'image:[ \t]+([^\s]+)', content)
            for match in matches:
                img = match.split('/')[-1]
                if img and ':' in img:
                    images.add(img)
    except Exception as e:
        print(f"Error reading manifest {manifest_path}: {e}")
        
    return list(images)

def main():
    parser = argparse.ArgumentParser(description="Push Config Sync images to Harbor.")
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the Config Sync manifest YAML file."
    )
    parser.add_argument(
        "--img-dir",
        required=True,
        help="Directory where images are stored."
    )
    parser.add_argument(
        "--harbor-registry",
        required=True,
        help="Harbor registry URL/host (e.g., registry.example.com)."
    )
    parser.add_argument(
        "--project",
        default="data-ets-mhs",
        help="Harbor project name (default: data-ets-mhs)."
    )
    
    args = parser.parse_args()
    
    print(f"Loading manifest: {args.manifest}")
    extracted_images = extract_images_from_manifest(args.manifest)
    
    if not extracted_images:
        print("No valid image references found in manifest or file not found.")
        sys.exit(1)
        
    print(f"Found {len(extracted_images)} unique images in manifest.")
    print(f"Images: {extracted_images}")
    
    try:
        client = docker.from_env()
    except Exception as e:
        print(f"Error connecting to Docker: {e}")
        print("Please ensure Docker is running and accessible.")
        sys.exit(1)
        
    for img in extracted_images:
        safe_filename = img.replace(':', '_')
        tar_path = os.path.join(args.img_dir, f"{safe_filename}.tar.gz")
        
        if not os.path.exists(tar_path):
            print(f"Warning: Tarball not found for {img} at {tar_path}")
            continue
            
        print("=" * 40)
        print(f"Processing: {img}")
        
        # Load image using docker library (this worked)
        print(f" -> Loading from: {tar_path}")
        try:
            with gzip.open(tar_path, 'rb') as f:
                loaded_images = client.images.load(f.read())
                if not loaded_images:
                    print(f"Warning: No images loaded from {tar_path}")
                    continue
                print(f" -> Loaded image.")
        except Exception as e:
            print(f"Error loading image {img}: {e}")
            continue
            
        # Tag image using docker library (this worked)
        source_image_name = f"gcr.io/config-management-release/{img}"
        target_image = f"{args.harbor_registry}/{args.project}/{img}"
        
        print(f" -> Tagging as: {target_image}")
        try:
            image = client.images.get(source_image_name)
            image.tag(target_image)
        except Exception as e:
            print(f"Error tagging image {img}: {e}")
            continue
            
        # Push image using subprocess (fallback because helper fails in Python)
        print(f" -> Pushing to Harbor...")
        try:
            # We use subprocess here because the Python library's interaction with
            # the custom credential helper 'docker-credential-mhs' fails with
            # an error about missing audience annotations, whereas the CLI works.
            subprocess.run(["docker", "push", target_image], check=True)
            print("    Pushed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error pushing image {target_image}: {e}")
            continue
            
    print("=" * 40)
    print("All images processed!")

if __name__ == "__main__":
    main()
