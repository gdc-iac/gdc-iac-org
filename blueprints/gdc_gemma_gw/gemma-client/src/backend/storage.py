import os
from pathlib import Path
from google.cloud import storage
from fastapi import UploadFile, HTTPException

INPUT_BUCKET = os.getenv("INPUT_BUCKET", "gemini-gui-files-test-project").strip()
while INPUT_BUCKET.startswith(("gs://", "s3://")):
    INPUT_BUCKET = INPUT_BUCKET[5:].strip("/")

LOCAL_STORAGE_ROOT = Path(os.getenv("LOCAL_STORAGE_DIR", "/tmp/gemma-uploads"))
LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
ENABLE_GCS_UPLOAD = os.getenv("ENABLE_GCS_UPLOAD", "true").lower() == "true"

# GDC-ag Native Object Storage S3-compatible endpoint configuration (object.gdc.goog/v1 Bucket)
S3_ENDPOINT = (
    os.getenv("S3_ENDPOINT")
    or os.getenv("OBJECT_STORAGE_ENDPOINT")
    or ""
).strip()
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
S3_REGION = os.getenv("S3_REGION", os.getenv("REGION", "zone1")).strip()

s3_client = None
if ENABLE_GCS_UPLOAD and S3_ENDPOINT:
    try:
        import boto3
        from botocore.client import Config

        s3_client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10),
            region_name=S3_REGION,
        )
    except Exception as e:
        print(f"Warning: Could not initialize GDC S3 Object Storage Client: {e}")
        s3_client = None

# Initialize GCS Client (primary object storage backend on GCP / GKE Workload Identity)
try:
    storage_client = (
        storage.Client() if (ENABLE_GCS_UPLOAD and not s3_client) else None
    )
except Exception as e:
    print(f"Warning: Could not initialize GCS Storage Client: {e}")
    storage_client = None


def _sanitize_segment(name: str) -> str:
    safe = os.path.basename((name or "").replace("\\", "/")).strip()
    if not safe or safe in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid file or user path segment")
    return safe


def _local_file_path(rel_path: str) -> Path:
    parts = [p for p in rel_path.split("/") if p]
    if not parts or ".." in parts:
        raise HTTPException(status_code=400, detail="Invalid storage path")
    target = (LOCAL_STORAGE_ROOT / Path(*parts)).resolve()
    if not str(target).startswith(str(LOCAL_STORAGE_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Invalid storage path")
    return target


async def upload_file_to_gcs(file: UploadFile, user_id: str, is_shared: bool) -> str:
    safe_filename = _sanitize_segment(file.filename or "upload.bin")
    safe_user = _sanitize_segment(user_id) if not is_shared else ""

    prefix = "shared" if is_shared else f"users/{safe_user}"
    blob_name = f"{prefix}/{safe_filename}"

    data = await file.read()

    # Always persist to shared pod/PVC storage for low-latency retrieval & air-gap resilience
    local_target = _local_file_path(blob_name)
    local_target.parent.mkdir(parents=True, exist_ok=True)
    local_target.write_bytes(data)

    if INPUT_BUCKET and "PLACEHOLDER" not in INPUT_BUCKET:
        if s3_client:
            try:
                s3_client.put_object(
                    Bucket=INPUT_BUCKET,
                    Key=blob_name,
                    Body=data,
                    ContentType=file.content_type or "application/octet-stream",
                )
                return f"gs://{INPUT_BUCKET}/{blob_name}"
            except Exception as e:
                print(
                    f"Notice: GDC S3 Object Storage upload failed ({e}); using local storage for {blob_name}"
                )

        if storage_client:
            try:
                bucket = storage_client.bucket(INPUT_BUCKET)
                blob = bucket.blob(blob_name)
                blob.upload_from_string(
                    data, content_type=file.content_type, timeout=10
                )
                return f"gs://{INPUT_BUCKET}/{blob_name}"
            except Exception as e:
                print(
                    f"Notice: GCS upload failed ({e}); using local pod storage for {blob_name}"
                )

    return f"local://{blob_name}"


async def delete_file_from_gcs(gcs_path: str):
    if gcs_path.startswith("local://"):
        rel_path = gcs_path[len("local://") :]
        local_target = _local_file_path(rel_path)
        if local_target.exists():
            local_target.unlink()
        return

    if not gcs_path.startswith(("gs://", "s3://")):
        return

    stripped = gcs_path[5:]
    while stripped.startswith(("gs://", "s3://")):
        stripped = stripped[5:]
    parts = stripped.split("/", 1)
    if len(parts) != 2:
        return

    bucket_name, blob_name = parts
    if ".." in blob_name.split("/"):
        raise HTTPException(status_code=400, detail="Invalid storage path")

    local_target = _local_file_path(blob_name)
    if local_target.exists():
        local_target.unlink()

    if s3_client:
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=blob_name)
        except Exception as e:
            print(f"Notice: GDC S3 delete skipped ({e})")
    elif storage_client:
        try:
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.delete(timeout=10)
        except Exception as e:
            print(f"Notice: GCS delete skipped ({e})")


def get_blob_content(gcs_path: str) -> bytes:
    if gcs_path.startswith("local://"):
        rel_path = gcs_path[len("local://") :]
        local_target = _local_file_path(rel_path)
        if not local_target.exists():
            raise FileNotFoundError(f"Local file not found: {rel_path}")
        return local_target.read_bytes()

    if gcs_path.startswith(("gs://", "s3://")):
        stripped = gcs_path[5:]
        while stripped.startswith(("gs://", "s3://")):
            stripped = stripped[5:]
        parts = stripped.split("/", 1)
        if len(parts) != 2:
            raise ValueError("Invalid storage path")
        bucket_name, blob_name = parts
        if ".." in blob_name.split("/"):
            raise ValueError("Invalid storage path")

        local_target = _local_file_path(blob_name)
        if local_target.exists():
            return local_target.read_bytes()

        if s3_client:
            resp = s3_client.get_object(Bucket=bucket_name, Key=blob_name)
            return resp["Body"].read()

        if not storage_client:
            raise Exception("Storage service unavailable")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.download_as_bytes(timeout=10)

    raise ValueError(f"Unsupported storage path: {gcs_path}")
