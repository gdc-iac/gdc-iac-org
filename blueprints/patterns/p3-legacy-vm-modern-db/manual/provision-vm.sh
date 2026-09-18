#!/bin/bash
# Step 2: Provision VM
# Prerequisite: Run `gdcloud compute images list` to find your exact image name.
gdcloud compute instances create app-vm-01 \
  --project=test-project \
  --zone=zone-1 \
  --machine-type=n2-highcpu-8-gdc \
  --image-project=gradec-images --image-family=ubuntu-2004 \
  --subnet=vm-subnet
