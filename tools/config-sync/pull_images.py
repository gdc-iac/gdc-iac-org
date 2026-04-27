#!/usr/bin/env python3
import os
import gzip
import sys
import argparse
import re

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
            # [ \t]+ matches spaces and tabs, preventing matching newlines
            matches = re.findall(r'image:[ \t]+([^\s]+)', content)
            for match in matches:
                # Extract the image name and tag (the part after the last slash)
                img = match.split('/')[-1]
                # Ensure it has a tag (contains :) and is not empty
                if img and ':' in img:
                    images.add(img)
    except Exception as e:
        print(f"Error reading manifest {manifest_path}: {e}")
        
    return list(images)

def main():
    parser = argparse.ArgumentParser(description="Pull and save Config Sync images based on a manifest.")
    parser.add_argument(
        "--manifest",
        default="config-sync-manifest.yaml",
        help="Path to the Config Sync manifest YAML file (default: config-sync-manifest.yaml)"
    )
    parser.add_argument(
        "--out-dir",
        default="/tmp/docker_images/",
        help="Directory to save the downloaded images (default: /tmp/docker_images/)"
    )
    
    args = parser.parse_args()
    
    out_dir = args.out_dir
    manifest_path = args.manifest
    
    print(f"Loading manifest: {manifest_path}")
    extracted_images = extract_images_from_manifest(manifest_path)
    
    if not extracted_images:
        print("No valid image references found in manifest or file not found.")
        print("Please ensure the manifest file exists and contains valid image references.")
        print("Example usage: ./pull_images.py --manifest config-sync-manifest-gdc.yaml")
        sys.exit(1)
        
    print(f"Found {len(extracted_images)} unique images in manifest.")
    print(f"Images: {extracted_images}")
    
    # Reconstruct full image names for pulling
    source_registry = "gcr.io/config-management-release/"
    images_to_pull = [source_registry + img for img in extracted_images]
    os.makedirs(out_dir, exist_ok=True)

    # Initialize Docker client
    try:
        client = docker.from_env()
    except Exception as e:
        print(f"Error connecting to Docker daemon: {e}")
        print("Please ensure Docker is running and accessible.")
        sys.exit(1)
    
    for image_name in images_to_pull:
        # Extract just the filename and format it safely
        file_base = image_name.split('/')[-1]
        safe_filename = file_base.replace(':', '_')
        
        print(f"Processing: {image_name}")
        out_file = os.path.join(out_dir, f"{safe_filename}.tar.gz")
        
        # Pull the image
        try:
            print(f" -> Pulling {image_name}...")
            image = client.images.pull(image_name)
        except Exception as e:
            print(f"Error pulling image {image_name}: {e}")
            continue
            
        # Save and compress the image
        try:
            print(f" -> Saving to: {out_file}")
            with open(out_file, 'wb') as f_out:
                with gzip.GzipFile(fileobj=f_out, mode='wb') as gz_out:
                    for chunk in image.save():
                        gz_out.write(chunk)
        except Exception as e:
            print(f"Error saving image {image_name}: {e}")
            if os.path.exists(out_file):
                os.remove(out_file)
            continue
            
        print(" -> Done.")
        print("-" * 40)
        
    print("All images have been downloaded and saved successfully!")

if __name__ == "__main__":
    main()
