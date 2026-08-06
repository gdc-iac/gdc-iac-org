#!/bin/bash
# Step 1: Configure IAM
kubectl create sa rag-sa -n test-project
gdcloud iam service-accounts add-iam-policy-binding rag-sa --project=${PROJECT_ID} --role=Role/ai-ocr-developer
gdcloud iam service-accounts add-iam-policy-binding rag-sa --project=${PROJECT_ID} --role=Role/ai-translation-developer
