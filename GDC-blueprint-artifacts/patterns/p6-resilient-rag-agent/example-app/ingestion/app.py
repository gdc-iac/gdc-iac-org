import time
import os
import boto3
import psycopg2
import hashlib
import json
from botocore.client import Config
import base64
import httpx
import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage

# Vertex AI Embedding
def get_embedding(text):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{EMBEDDING_MODEL}:predict"
    
    headers = {"Content-Type": "application/json"}
    token = get_auth_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {
        "instances": [{
            "content": text,
            "task_type": "RETRIEVAL_DOCUMENT"
        }]
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            return result['predictions'][0]['embeddings']['values']
    except Exception as e:
        print(f"Embedding API Error: {e}")
        # Fallback to zero vector if API fails (should not happen in prod)
        return [0.0] * 768

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        database=os.environ.get('DB_NAME', 'rag_db'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASS', 'password')
    )

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    # Note: We are using 768 dimensions for text-embedding-004
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            filename TEXT UNIQUE,
            content TEXT,
            embedding vector(768),
            owner_id TEXT DEFAULT NULL,
            source_path TEXT
        );
    """)
    
    # Migration for existing documents table (idempotent)
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_id TEXT DEFAULT NULL;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_path TEXT;")
    except Exception as e:
        print(f"Migration warning (documents): {e}")
        conn.rollback()

    # Chats Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Messages Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

def get_s3_client():
    return boto3.client('s3',
        endpoint_url=os.environ.get('S3_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID', 'minioadmin'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY', 'minioadmin'),
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

GEMINI_ENDPOINT = os.environ.get('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')
GEMINI_ENDPOINT = os.environ.get('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-004')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # Optional if using ADC
PROJECT_ID = os.environ.get('PROJECT_ID')
LOCATION = os.environ.get('LOCATION', 'us-central1')

def get_auth_token():
    if GEMINI_API_KEY:
        return None
    try:
        credentials, _ = google.auth.default()
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        print(f"Warning: Could not get default credentials: {e}")
        return None

def call_gemini_api(prompt, content_bytes=None, mime_type=None):
    provider = os.environ.get('LLM_PROVIDER', 'gemma').lower()
    endpoint = os.environ.get('LLM_GATEWAY_URL', GEMINI_ENDPOINT)
    model = os.environ.get('GEMINI_MODEL', GEMINI_MODEL)
    ao_project_id = os.environ.get('AO_PROJECT_ID', 'projects/your-project-id')

    final_prompt = prompt
    if content_bytes and mime_type:
        try:
            if "pdf" in mime_type or "text" in mime_type:
                final_prompt = prompt + "\n\nContent:\n" + content_bytes.decode('utf-8', errors='ignore')
        except Exception as ex:
            print(f"Failed to append content string for gateway: {ex}")

    is_gateway = provider == 'gemma' or 'gemma' in endpoint or 'llm-gateway' in endpoint or '/v1' in endpoint

    if is_gateway:
        url = endpoint if endpoint.endswith('/chat/completions') else f"{endpoint.rstrip('/')}/chat/completions" if '/v1' in endpoint else endpoint
        headers = {"Content-Type": "application/json"}
        token = get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if ao_project_id:
            headers["x-goog-user-project"] = ao_project_id

        if '/v1' in url:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": final_prompt}]
            }
        else:
            payload = {"prompt": final_prompt}

        try:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, json=payload, timeout=180.0)
                response.raise_for_status()
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                elif 'response' in result and 'text' in result['response']:
                    return result['response']['text']
                else:
                    return str(result)
        except Exception as e:
            if not endpoint.endswith('/generate'):
                try:
                    gen_url = f"{endpoint.rstrip('/')}/generate"
                    with httpx.Client() as client:
                        resp = client.post(gen_url, headers=headers, json={"prompt": final_prompt}, timeout=180.0)
                        resp.raise_for_status()
                        res = resp.json()
                        return res.get('response', {}).get('text', '') or res.get('text', '')
                except Exception:
                    pass
            print(f"Gateway API Error: {e}")
            return ""
    else:
        url = f"{GEMINI_ENDPOINT}/{GEMINI_MODEL}:generateContent"
        if GEMINI_API_KEY:
            url += f"?key={GEMINI_API_KEY}"
        
        headers = {"Content-Type": "application/json"}
        token = get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        parts = [{"text": prompt}]
        if content_bytes and mime_type:
            parts.append({
                "inlineData": {
                    "mimeType": mime_type,
                    "data": base64.b64encode(content_bytes).decode('utf-8')
                }
            })

        payload = {
            "contents": [{
                "role": "user",
                "parts": parts
            }]
        }

        try:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, json=payload, timeout=120.0)
                response.raise_for_status()
                result = response.json()
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    print(f"Unexpected Gemini response structure: {result}")
                    return ""
        except Exception as e:
            print(f"Gemini API Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Gemini Error Response: {e.response.text}")
            return ""

BUCKET_NAME = os.environ.get('INPUT_BUCKET', 'documents')

def file_exists_in_db(filename):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM documents WHERE filename = %s", (filename,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        print(f"DB Check Error: {e}")
        return False

def process_files():
    use_gcs = BUCKET_NAME.startswith('gs://') or BUCKET_NAME.startswith('raw-docs') or os.environ.get('USE_GCS', 'true').lower() == 'true'
    bucket_name = BUCKET_NAME.replace('gs://', '') if use_gcs else BUCKET_NAME
    
    s3 = None
    gcs_client = None
    bucket = None

    if use_gcs:
        print(f"Using Native GCS for bucket: {bucket_name}")
        gcs_client = storage.Client()
        bucket = gcs_client.bucket(bucket_name)
    else:
        print(f"Using S3/MinIO for bucket: {bucket_name}")
        s3 = get_s3_client()
        # Ensure bucket exists (S3 only)
        try:
            s3.create_bucket(Bucket=bucket_name)
        except:
            pass

    try:
        current_objects = []
        
        if use_gcs:
            print("Listing blobs from GCS...")
            blobs = list(bucket.list_blobs())
            print(f"Found {len(blobs)} blobs.")
            for blob in blobs:
                current_objects.append({'Key': blob.name, 'Blob': blob})
        else:
            response = s3.list_objects_v2(Bucket=bucket_name)
            if 'Contents' in response:
                current_objects = response['Contents']

        print(f"Starting batch processing of {len(current_objects)} files...")

        for obj in current_objects:
            key = obj['Key']
            
            # Check DB to avoid re-ingestion
            if file_exists_in_db(key):
                print(f"Skipping {key} (already indexed).")
                continue

            print(f"Processing {key}...")
            
            content_bytes = None
            if use_gcs:
                content_bytes = obj['Blob'].download_as_bytes()
            else:
                obj_data = s3.get_object(Bucket=bucket_name, Key=key)
                content_bytes = obj_data['Body'].read()
            
            # Determine MIME type
            mime_type = None
            ext = os.path.splitext(key)[1].lower()
            if ext in ['.mp3', '.wav', '.flac', '.ogg']:
                mime_type = 'audio/mpeg' if ext == '.mp3' else f'audio/{ext[1:]}'
            elif ext in ['.png', '.jpg', '.jpeg']:
                mime_type = 'image/png' if ext == '.png' else 'image/jpeg'
            elif ext == '.pdf':
                mime_type = 'application/pdf'
                
            final_text = ""
                
            if mime_type:
                print(f"Detected {mime_type} for {key}. Calling Gemini...")
                prompt = "Extract all text from this file. If it is audio, transcribe it. If it is an image, describe it and extract visible text. If it is a PDF, summarize it. Return ONLY the text."
                final_text = call_gemini_api(prompt, content_bytes, mime_type)
            else:
                # Assume text
                try:
                    print("Decoding text content...")
                    text_content = content_bytes.decode('utf-8')
                    # Optional: Translate if needed, or just store
                    # For now, let's just use Gemini to ensure it's English if it looks like text
                    prompt = "Translate the following text to English if it is not already. Return ONLY the English text."
                    print("Calling LLM API (Gemma/Gemini)...")
                    final_text = call_gemini_api(prompt + f"\n\n{text_content}")
                    print(f"LLM returned: {len(final_text)} chars")
                    if not final_text and text_content:
                        print("LLM translation timed out or returned empty text. Falling back to raw text content...")
                        final_text = text_content
                except UnicodeDecodeError:
                    print(f"Skipping {key}: Cannot decode as text and not a supported binary format.")
                    continue

            if final_text:
                # Embed
                print("Embedding text...")
                embedding = get_embedding(final_text)
                print(f"DEBUG: Embedding length: {len(embedding)}")
                
                # Determine owner_id from key (path)
                # Structure: shared/doc.txt or users/<user_id>/doc.txt
                owner_id = None
                parts = key.split('/')
                if len(parts) > 2 and parts[0] == 'users':
                    owner_id = parts[1]
                
                # Save to DB
                print(f"Saving to DB (Owner: {owner_id})...")
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO documents (filename, content, embedding, owner_id, source_path)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (filename) DO UPDATE 
                    SET content = EXCLUDED.content, embedding = EXCLUDED.embedding, owner_id = EXCLUDED.owner_id, source_path = EXCLUDED.source_path;
                """, (key, final_text, embedding, owner_id, key))
                conn.commit()
                cur.close()
                conn.close()
                
                print(f"Indexed {key}")
            else:
                print(f"Failed to extract text from {key}")

    except Exception as e:
        print(f"Error processing files: {e}")
        # We do NOT want to crash the pod if one file fails, but we should log it.
        # However, if the whole listing fails, we exit.
    
    print("Batch processing complete.")

if __name__ == "__main__":
    time.sleep(5) # Wait for services
    try:
        init_db()
        process_files()
    except Exception as e:
        print(f"Fatal error: {e}")
