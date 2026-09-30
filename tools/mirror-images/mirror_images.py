#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Standardized container image mirroring utility for GDC air-gapped environments.

Supports:
1. Direct Mirroring (Connected Bastion):
   ./mirror_images.py --manifest manifest.yaml --registry <harbor_url>/<project>
   ./mirror_images.py --images-file external_images.txt --registry <harbor_url>/<project>

2. Two-Step Disconnected Air-Gap Mirroring (Low-Side Export -> High-Side Import):
   Step A (Low-Side / Internet-Connected):
     ./mirror_images.py --manifest manifest.yaml --save-dir /tmp/offline-images
   Step B (High-Side / Air-Gapped GDC Workstation):
     ./mirror_images.py --load-dir /tmp/offline-images --registry <harbor_url>/<project>
"""

import argparse
import gzip
import os
import re
import shutil
import subprocess
import sys


def extract_images_from_manifest(manifest_path):
    """Extracts image names from a Kubernetes YAML manifest by matching image: references."""
    images = []
    seen = set()
    if not os.path.exists(manifest_path):
        print(f"Warning: Manifest file not found: {manifest_path}")
        return []

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
            matches = re.findall(r"image:[ \t]+[\"']?([^\s\"']+)[\"']?", content)
            for match in matches:
                if match and ":" in match and match not in seen:
                    seen.add(match)
                    images.append(match)
    except Exception as e:
        print(f"Error reading manifest {manifest_path}: {e}")

    return images


def extract_images_from_list(images_file_path):
    """Extracts image names from a plain-text list file (e.g. external_images.txt)."""
    images = []
    seen = set()
    if not os.path.exists(images_file_path):
        print(f"Warning: Images list file not found: {images_file_path}")
        return []

    try:
        with open(images_file_path, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.split("#", 1)[0].strip()
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    images.append(cleaned)
    except Exception as e:
        print(f"Error reading images file {images_file_path}: {e}")

    return images


def sanitize_filename(image_name):
    """Converts an image reference into a safe archive filename."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", image_name)
    return f"{safe}.tar.gz"


def save_images_offline(images, save_dir):
    """Pulls images and exports them as .tar.gz archives for air-gapped transfer."""
    os.makedirs(save_dir, exist_ok=True)
    saved_images = []
    index_entries = []

    for image_name in images:
        archive_name = sanitize_filename(image_name)
        archive_path = os.path.join(save_dir, archive_name)
        print(f" -> Pulling and saving {image_name} -> {archive_path}...")
        try:
            subprocess.run(["docker", "pull", image_name], check=True)
            with subprocess.Popen(
                ["docker", "save", image_name], stdout=subprocess.PIPE
            ) as proc:
                with gzip.open(archive_path, "wb") as gz_out:
                    shutil.copyfileobj(proc.stdout, gz_out)
                ret = proc.wait()
                if ret != 0:
                    raise subprocess.CalledProcessError(ret, ["docker", "save", image_name])
            saved_images.append(image_name)
            index_entries.append(f"{archive_name}\t{image_name}\n")
        except subprocess.CalledProcessError as e:
            print(f"Error saving image {image_name}: {e}")
            continue

    index_path = os.path.join(save_dir, "images.index")
    with open(index_path, "w", encoding="utf-8") as f:
        f.writelines(index_entries)

    if len(saved_images) == len(images):
        print(f"All {len(saved_images)} images saved successfully to {save_dir}!")
    else:
        failed = [i for i in images if i not in saved_images]
        print(f"Error: Failed to save {len(failed)} images: {failed}")
        sys.exit(1)


def load_and_push_images(load_dir, registry, fallback_images=None):
    """Loads .tar.gz/.tar archives from load_dir, tags them, and pushes to registry."""
    if not os.path.isdir(load_dir):
        print(f"Error: Load directory not found: {load_dir}")
        sys.exit(1)

    registry = registry.rstrip("/")
    index_path = os.path.join(load_dir, "images.index")
    work_items = []

    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t", 1)
                if len(parts) == 2:
                    work_items.append((os.path.join(load_dir, parts[0]), parts[1]))
    else:
        archives = sorted(
            f
            for f in os.listdir(load_dir)
            if f.endswith(".tar.gz") or f.endswith(".tar")
        )
        if not archives:
            print(f"Error: No .tar or .tar.gz image archives found in {load_dir}")
            sys.exit(1)
        for archive in archives:
            work_items.append((os.path.join(load_dir, archive), None))

    pushed = []
    for archive_path, recorded_image in work_items:
        print(f" -> Loading archive {archive_path}...")
        try:
            result = subprocess.run(
                ["docker", "load", "-i", archive_path],
                check=True,
                capture_output=True,
                text=True,
            )
            loaded_image = recorded_image
            if not loaded_image:
                match = re.search(r"Loaded image:\s+(\S+)", result.stdout)
                if match:
                    loaded_image = match.group(1)
            if not loaded_image and fallback_images:
                for candidate in fallback_images:
                    if sanitize_filename(candidate) == os.path.basename(archive_path):
                        loaded_image = candidate
                        break
            if not loaded_image:
                print(f"Error: Could not determine image tag from {archive_path}")
                continue

            image_base = loaded_image.split("/")[-1]
            target_ref = f"{registry}/{image_base}"
            print(f" -> Tagging and pushing {target_ref}...")
            subprocess.run(["docker", "tag", loaded_image, target_ref], check=True)
            subprocess.run(["docker", "push", target_ref], check=True)
            pushed.append(archive_path)
        except subprocess.CalledProcessError as e:
            print(f"Error loading/pushing {archive_path}: {e}")
            continue

    if len(pushed) == len(work_items):
        print("All offline image archives loaded and mirrored successfully!")
    else:
        failed = [item[0] for item in work_items if item[0] not in pushed]
        print(f"Error: Failed to mirror {len(failed)} archives: {failed}")
        sys.exit(1)


def direct_mirror_images(images, registry):
    """Pulls, re-tags, and pushes images directly to the target registry."""
    registry = registry.rstrip("/")
    images_pushed = []

    for image_name in images:
        image_base = image_name.split("/")[-1]
        target_ref = f"{registry}/{image_base}"
        print(f" -> {image_name} -> {target_ref}...")
        try:
            subprocess.run(["docker", "pull", image_name], check=True)
            subprocess.run(["docker", "tag", image_name, target_ref], check=True)
            subprocess.run(["docker", "push", target_ref], check=True)
            images_pushed.append(image_name)
        except subprocess.CalledProcessError as e:
            print(f"Error mirroring image {image_name}: {e}")
            continue

    if len(images_pushed) == len(images):
        print("All images have been mirrored successfully!")
    else:
        failed_images = [i for i in images if i not in images_pushed]
        print(f"Error: Failed to mirror {len(failed_images)} images: {failed_images}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Pull, save, load, and mirror container images for GDC air-gapped environments."
    )
    parser.add_argument(
        "--manifest",
        default="manifest.yaml",
        help="Path to the Kubernetes manifest YAML file (default: manifest.yaml)",
    )
    parser.add_argument(
        "--images-file",
        default=None,
        help="Path to a plain-text file containing one image reference per line (e.g., external_images.txt)",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Target Harbor registry URL including project path (e.g., harbor001-iac-root.../iac)",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        help="Directory to save pulled images as .tar.gz archives (low-side air-gap export mode)",
    )
    parser.add_argument(
        "--load-dir",
        default=None,
        help="Directory containing saved .tar.gz image archives to load and push (high-side air-gap import mode)",
    )
    args = parser.parse_args()

    # High-side air-gap import mode
    if args.load_dir:
        if not args.registry:
            print("Error: --registry is required when using --load-dir.")
            sys.exit(1)
        fallback = []
        if args.images_file and os.path.exists(args.images_file):
            fallback = extract_images_from_list(args.images_file)
        elif args.manifest and os.path.exists(args.manifest):
            fallback = extract_images_from_manifest(args.manifest)
        load_and_push_images(args.load_dir, args.registry, fallback)
        return

    # Extract images from --images-file or --manifest
    if args.images_file:
        print(f"Loading image list: {args.images_file}")
        extracted_images = extract_images_from_list(args.images_file)
    else:
        print(f"Loading manifest: {args.manifest}")
        extracted_images = extract_images_from_manifest(args.manifest)

    if not extracted_images:
        print("No valid image references found or input file not found.")
        print("Please ensure the manifest or images list exists and contains valid image references.")
        print(
            "Example usage: ./mirror_images.py --manifest manifest.yaml --registry <registry_url>"
        )
        sys.exit(1)

    print(f"Found {len(extracted_images)} unique images.")
    print(f"Images: {extracted_images}")

    if args.save_dir:
        save_images_offline(extracted_images, args.save_dir)
        if args.registry:
            load_and_push_images(args.save_dir, args.registry, extracted_images)
        return

    if not args.registry:
        print("Error: Either --registry or --save-dir must be specified.")
        sys.exit(1)

    direct_mirror_images(extracted_images, args.registry)


if __name__ == "__main__":
    main()
