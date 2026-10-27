#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker Image Cleanup Helper Utility for GDC Gemma Gateway.
Provides project-scoped Docker image management to avoid cached layers
and maintain a clean environment, with safety guardrails.
"""

import argparse
import re
import sys
import subprocess
import os

# High-contrast terminal colors for premium CLI feel
COLOR_HEADER = '\033[95m'
COLOR_OKBLUE = '\033[94m'
COLOR_OKCYAN = '\033[96m'
COLOR_OKGREEN = '\033[92m'
COLOR_WARNING = '\033[93m'
COLOR_FAIL = '\033[91m'
COLOR_ENDC = '\033[0m'
COLOR_BOLD = '\033[1m'
COLOR_UNDERLINE = '\033[4m'

# List of known project image base names
PROJECT_IMAGE_BASENAMES = [
    "gemma-proxy",
    "ollama-gemma-26b",
    "ollama-gemma-31b",
    "vllm-gemma-26b",
    "vllm-gemma-31b",
    "gemma-client-backend",
    "gemma-client-frontend"
]

def print_header(msg):
    print(f"{COLOR_HEADER}{COLOR_BOLD}=== {msg} ==={COLOR_ENDC}")

def print_success(msg):
    print(f"{COLOR_OKGREEN}✓ {msg}{COLOR_ENDC}")

def print_warning(msg):
    print(f"{COLOR_WARNING}⚠️ {msg}{COLOR_ENDC}")

def print_info(msg):
    print(f"{COLOR_OKCYAN}ℹ {msg}{COLOR_ENDC}")

def print_error(msg):
    print(f"{COLOR_FAIL}{COLOR_BOLD}✗ Error: {msg}{COLOR_ENDC}")

def get_configured_registry():
    """Attempts to dynamically read the configured registry from the environment or build-and-push.sh script."""
    # Check environment variable first
    if os.environ.get("REGISTRY_HOST"):
        return os.environ.get("REGISTRY_HOST")
    
    # Check build-and-push.sh script
    script_path = os.path.join(os.path.dirname(__file__), "build-and-push.sh")
    if os.path.exists(script_path):
        try:
            with open(script_path, 'r') as f:
                content = f.read()
                # Try to extract REGISTRY_HOST=${REGISTRY_HOST:-"some-value"}
                match = re.search(r'REGISTRY_HOST=\$\{REGISTRY_HOST:-"([^"]+)"\}', content)
                if match:
                    return match.group(1)
        except Exception:
            pass
            
    return "us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"

def run_command(cmd):
    """Executes a system command and returns stdout, stderr, and exit status code."""
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def check_docker():
    """Checks if docker is installed and running."""
    code, _, _ = run_command("docker info")
    if code != 0:
        print_error("Docker daemon is not running or the docker CLI is not available.")
        sys.exit(1)

def get_all_local_images():
    """Retrieves list of all local Docker images as tuples (ID, Repository, Tag, Created, Size)."""
    code, stdout, stderr = run_command("docker images --format '{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}\t{{.Size}}'")
    if code != 0:
        print_error(f"Failed to list local Docker images: {stderr}")
        sys.exit(1)
    
    images = []
    if not stdout:
        return images
        
    for line in stdout.split('\n'):
        parts = line.split('\t')
        if len(parts) >= 3:
            images.append({
                "id": parts[0],
                "repository": parts[1],
                "tag": parts[2],
                "created": parts[3] if len(parts) > 3 else "Unknown",
                "size": parts[4] if len(parts) > 4 else "Unknown"
            })
    return images

def is_project_relevant(image, registry_host):
    """Determines if an image is relevant to this project based on repository name or registry host."""
    repo = image["repository"]
    
    # Check if the repo contains/ends with any known project image base names
    for base in PROJECT_IMAGE_BASENAMES:
        if repo == base or repo.endswith(f"/{base}"):
            return True
            
    # Check if the repo contains the configured registry host
    if registry_host and registry_host in repo:
        return True
        
    return False

def confirm_action(prompt_message):
    """Prompts the user for confirmation."""
    try:
        response = input(f"{COLOR_WARNING}{prompt_message} (y/N): {COLOR_ENDC}").strip().lower()
        return response in ('y', 'yes')
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)

def delete_images(images, dry_run=False):
    """Deletes a list of images from local Docker cache."""
    if not images:
        print_success("No matching images to delete.")
        return
        
    print_info(f"Preparing to delete {len(images)} image(s)...")
    
    # Track unique image IDs/Tags to delete
    targets = []
    for img in images:
        # Prefer deleting by specific repository:tag to avoid untagging issues
        if img["repository"] != "<none>" and img["tag"] != "<none>":
            targets.append(f"{img['repository']}:{img['tag']}")
        else:
            targets.append(img["id"])
            
    # Remove duplicates
    targets = list(set(targets))
    
    if dry_run:
        print_header("Dry Run - The following images WOULD be deleted:")
        for target in targets:
            print(f"  - {target}")
        print_success("Dry run completed. No modifications were made.")
        return

    deleted_count = 0
    for target in targets:
        print(f"Deleting {target}...")
        code, _, stderr = run_command(f"docker rmi -f '{target}'")
        if code == 0:
            print_success(f"Successfully deleted {target}")
            deleted_count += 1
        else:
            print_warning(f"Could not delete {target}: {stderr}")
            
    print_success(f"Cleanup finished. Successfully deleted {deleted_count}/{len(targets)} target(s).")

def main():
    parser = argparse.ArgumentParser(
        description="Clean up Docker images scoped specifically to the GDC Gemma Gateway project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Educational Note:
-----------------
Using commands 2 & 4 ensures that you completely clear out local or specific images.
During rapid development/iteration, Docker's layer-caching mechanism can sometimes reuse
stale cached layers even when files inside the context have changed (especially with complex dependency trees).
Removing these images forces Docker to pull or rebuild every single layer from scratch, guaranteeing 
a fully deterministic and completely clean environment to start from.
"""
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Clean out all local docker images relevant to this project.")
    group.add_argument("--image", metavar="IMAGE_ID_OR_NAME", help="Clean out a single specified local docker image (with safety check).")
    group.add_argument("--repo-all", action="store_true", help="Clean out the repo of all images (matching project registry).")
    group.add_argument("--specific", metavar="IMAGE_NAME", help="Clean out a specific project image (e.g., 'gemma-proxy' or with optional tag).")

    parser.add_argument("-f", "--force", action="store_true", help="Force deletion without confirmation prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode: shows what would be deleted without actually deleting.")
    parser.add_argument("--registry", help="Override default registry host used for safety matching.")
    
    args = parser.parse_args()
    
    check_docker()
    
    registry_host = args.registry or get_configured_registry()
    print_info(f"Configured Project Registry: {COLOR_BOLD}{registry_host}{COLOR_ENDC}")
    
    local_images = get_all_local_images()
    if not local_images:
        print_success("No local Docker images found.")
        return
        
    project_images = [img for img in local_images if is_project_relevant(img, registry_host)]
    
    images_to_delete = []
    
    # Scenario 1: Clean out all local docker images relevant to this project
    if args.all:
        print_info("Option selected: Clean all project-relevant local images.")
        images_to_delete = project_images
        if not images_to_delete:
            print_success("No project-relevant local images found.")
            return
            
        print_warning(f"This will delete ALL {len(images_to_delete)} local images belonging to this project.")
        if not args.force and not args.dry_run:
            if not confirm_action("Are you sure you want to delete all project images?"):
                print_info("Operation cancelled.")
                sys.exit(0)
                
    # Scenario 2: Clean out a single specified local docker image
    elif args.image:
        target = args.image
        print_info(f"Option selected: Clean single specified local image: '{target}'")
        
        # Find matching local images by ID, Repository, or Repository:Tag
        matches = []
        for img in local_images:
            img_tag = f"{img['repository']}:{img['tag']}"
            if target == img["id"] or target == img["repository"] or target == img_tag:
                matches.append(img)
                
        if not matches:
            print_error(f"No local image found matching '{target}'.")
            sys.exit(1)
            
        # Safety Guardrail: Check if target matches are relevant to this project
        non_project_matches = [img for img in matches if not is_project_relevant(img, registry_host)]
        if non_project_matches and not args.force:
            print_warning(f"Safety Guardrail Alert: '{target}' does not appear to belong to the GDC Gemma Gateway project.")
            print_info("Unrelated image details:")
            for img in non_project_matches:
                print(f"  - {img['repository']}:{img['tag']} ({img['id']})")
            if not confirm_action("Bypass safety check and delete this image anyway?"):
                print_info("Aborting deletion to protect non-project image.")
                sys.exit(0)
                
        images_to_delete = matches
        
    # Scenario 3: Clean out the repo of all images (matching project registry)
    elif args.repo_all:
        print_info(f"Option selected: Clean all images matching registry '{registry_host}'")
        images_to_delete = [img for img in local_images if registry_host in img["repository"]]
        
        if not images_to_delete:
            print_success(f"No local images found matching registry '{registry_host}'.")
            return
            
        print_warning(f"This will delete all {len(images_to_delete)} images matching '{registry_host}'.")
        if not args.force and not args.dry_run:
            if not confirm_action(f"Are you sure you want to delete all images matching registry '{registry_host}'?"):
                print_info("Operation cancelled.")
                sys.exit(0)
                
    # Scenario 4: Clean out a specific project image
    elif args.specific:
        target = args.specific
        print_info(f"Option selected: Clean specific project image '{target}'")
        
        # Handle optional tag suffix in input (e.g., gemma-proxy:v1)
        target_base = target
        target_tag = None
        if ":" in target:
            target_base, target_tag = target.split(":", 1)
            
        # Standardize target base name to handle registry paths or short names
        # e.g. "gemma-proxy" or "us-central1-docker.../gemma-proxy"
        is_valid_base = False
        for base in PROJECT_IMAGE_BASENAMES:
            if target_base == base or target_base.endswith(f"/{base}"):
                is_valid_base = True
                break
                
        if not is_valid_base and not args.force:
            print_error(f"'{target_base}' is not recognized as a valid project image.")
            print_info(f"Recognized project images: {', '.join(PROJECT_IMAGE_BASENAMES)}")
            sys.exit(1)
            
        images_to_delete = []
        for img in local_images:
            repo = img["repository"]
            # Match repository
            if repo == target_base or repo.endswith(f"/{target_base}"):
                if target_tag:
                    if img["tag"] == target_tag:
                        images_to_delete.append(img)
                else:
                    images_to_delete.append(img)
                    
        if not images_to_delete:
            print_success(f"No local images found matching specific target '{target}'.")
            return
            
    # Run the deletion process
    delete_images(images_to_delete, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
