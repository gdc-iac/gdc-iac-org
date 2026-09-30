#!/usr/bin/env python3
import os
import gzip
import sys
import argparse
import re
import subprocess

def extract_images_from_manifest(manifest_path):
    """Extracts image names from the manifest file by looking for image: references."""
    images = set()
    if not os.path.exists(manifest_path):
        print(f"Warning: Manifest file not found: {manifest_path}")
        return []
        
    try:
        with open(manifest_path, 'r') as f:
            content = f.read()
            matches = re.findall(r'image:[ \t]+([^\s]+)', content)
            for match in matches:
                if match and ':' in match:
                    images.add(match)
    except Exception as e:
        print(f"Error reading manifest {manifest_path}: {e}")
        
    return list(images)

def main():
    parser = argparse.ArgumentParser(description="Pull and save container images based on a manifest.")
    parser.add_argument(
        "--manifest",
        default="manifest.yaml",
        help="Path to the container images manifest YAML file (default: manifest.yaml)"
    )
    parser.add_argument(
        "--registry",
        required=True,
        help="Registry URL"
    )
    args = parser.parse_args()
    
    manifest_path = args.manifest
    registry = args.registry

    print(f"Loading manifest: {manifest_path}")
    extracted_images = extract_images_from_manifest(manifest_path)
    
    if not extracted_images:
        print("No valid image references found in manifest or file not found.")
        print("Please ensure the manifest file exists and contains valid image references.")
        print("Example usage: ./pull_images.py --manifest manifest.yaml")
        sys.exit(1)
        
    print(f"Found {len(extracted_images)} unique images in manifest.")
    print(f"Images: {extracted_images}")
    
    images_to_pull = [f"{img}" for img in extracted_images]
    images_pushed = []
    
    for image_name in images_to_pull:
        image_base = image_name.split('/')[-1]
        print(f" ->  {image_name}...")
        try:
            subprocess.run(["docker", "pull", image_name], check=True)
            subprocess.run(["docker", "tag", image_name, f"{registry}/{image_base}"], check=True)
            subprocess.run(["docker", "push", f"{registry}/{image_base}"], check=True)
            images_pushed.append(image_name)
        except subprocess.CalledProcessError as e:
            print(f"Error pulling image {image_name}: {e}")
            continue            
    if len(images_pushed) == len(images_to_pull):
        print("All images have been mirrored successfully!")
    else:
        failed_images = [i for i in images_to_pull if i not in images_pushed]
        print(f"Error: Failed to mirror {len(failed_images)} images: {failed_images}")
        sys.exit(1)

if __name__ == "__main__":
    main()
