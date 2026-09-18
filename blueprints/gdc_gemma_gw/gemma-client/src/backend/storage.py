import os
from google.cloud import storage
from fastapi import UploadFile, HTTPException
import uuid

INPUT_BUCKET = os.getenv("INPUT_BUCKET", "gemini-gui-files-test-project")
if INPUT_BUCKET.startswith("gs://"):
    INPUT_BUCKET = INPUT_BUCKET[5:]

# Initialize Client (works with Workload Identity)
try:
    storage_client = storage.Client()
except Exception as e:
    print(f"Warning: Could not initialize Storage Client: {e}")
    storage_client = None

async def upload_file_to_gcs(file: UploadFile, user_id: str, is_shared: bool) -> str:
    if not storage_client:
        raise HTTPException(status_code=500, detail="Storage service unavailable")

    bucket = storage_client.bucket(INPUT_BUCKET)
    
    # Determine path
    # shared/filename or users/{user_id}/filename
    # We prepend UUID to filename to avoid collisions? Or keep original name?
    # Let's keep original name but maybe prepend a short UUID or handle overwrite.
    # For simplicity: users/{user_id}/{filename}
    
    prefix = "shared" if is_shared else f"users/{user_id}"
    blob_name = f"{prefix}/{file.filename}"
    blob = bucket.blob(blob_name)

    # Upload
    # file.file is a SpooledTemporaryFile
    blob.upload_from_file(file.file, content_type=file.content_type)
    
    return f"gs://{INPUT_BUCKET}/{blob_name}"

async def delete_file_from_gcs(gcs_path: str):
    if not storage_client:
        raise HTTPException(status_code=500, detail="Storage service unavailable")
        
    # Parse bucket and blob name
    # gs://bucket/path/to/file
    if not gcs_path.startswith("gs://"):
        return # Invalid path
        
    parts = gcs_path.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        return
        
    bucket_name, blob_name = parts
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.delete()

def get_blob_content(gcs_path: str) -> bytes:
    if not storage_client:
        raise Exception("Storage service unavailable")
        
    parts = gcs_path.replace("gs://", "").split("/", 1)
    bucket_name, blob_name = parts
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()
