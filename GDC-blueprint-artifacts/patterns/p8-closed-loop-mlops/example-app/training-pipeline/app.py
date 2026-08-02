import time
import os
import json

# Simulates a training job that:
# 1. Reads training data (mocked)
# 2. Trains a model (sleeps)
# 3. Uploads model artifact to "Model Registry" (MinIO or GCS)

def upload_to_storage(bucket_name, blob_name, data):
    if os.environ.get('USE_GCS_NATIVE'):
        from google.cloud import storage
        print(f"Using Native GCS Client to upload to {bucket_name}/{blob_name}")
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data)
    else:
        import boto3
        from botocore.client import Config
        print(f"Using Boto3 Client to upload to {bucket_name}/{blob_name}")
        s3 = boto3.client('s3',
            endpoint_url=os.environ.get('S3_ENDPOINT', 'http://minio:9000'),
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID', 'minioadmin'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY', 'minioadmin'),
            config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
        try:
            s3.create_bucket(Bucket=bucket_name)
        except:
            pass
        s3.put_object(Bucket=bucket_name, Key=blob_name, Body=data)

BUCKET_NAME = os.environ.get('BUCKET_NAME', 'model-registry')

def train_and_upload():
    print("Starting training job...")
    
    # Simulate training
    for epoch in range(1, 6):
        print(f"Epoch {epoch}/5 - Loss: {0.5 - epoch * 0.05}")
        time.sleep(1)
    
    print("Training complete. Saving model...")
    
    # Create dummy model artifact
    model_artifact = {
        "model_name": "my-model",
        "version": "v1",
        "weights": [0.1, 0.2, 0.3, 0.4],
        "timestamp": time.time()
    }
    
    filename = f"model-v{int(time.time())}.json"
    
    # Upload
    try:
        upload_to_storage(BUCKET_NAME, filename, json.dumps(model_artifact))
        print(f"Model uploaded successfully to {BUCKET_NAME}/{filename}")
    except Exception as e:
        print(f"Upload failed: {e}")
        raise e

if __name__ == "__main__":
    # Wait a bit
    time.sleep(2)
    try:
        train_and_upload()
    except Exception as e:
        print(f"Training failed: {e}")
        exit(1)
