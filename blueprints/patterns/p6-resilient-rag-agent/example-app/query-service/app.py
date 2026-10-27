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

import os
import json
import logging
import urllib.request
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List
from google.cloud import storage
from utils import get_db_connection, INPUT_BUCKET
from agent import Agent
import uuid

try:
    import jwt
    from jwt import PyJWKSet
    from jwt.exceptions import PyJWTError as JWTError
except ImportError:
    jwt = None
    PyJWKSet = None
    JWTError = Exception

logger = logging.getLogger("p6-query-service")

app = FastAPI()

# Configure CORS with explicit origin support
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=("*" not in CORS_ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

ENABLE_OIDC = os.environ.get("ENABLE_OIDC", "false").lower() == "true"
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://keycloak-svc:8080/auth/realms/gdc-rag-realm")
ALGORITHMS = ["RS256"]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
jwks_cache = None


def get_jwks():
    global jwks_cache
    if jwks_cache is None and ENABLE_OIDC:
        try:
            certs_url = f"{KEYCLOAK_URL}/protocol/openid-connect/certs"
            with urllib.request.urlopen(certs_url, timeout=5) as response:
                jwks_cache = json.loads(response.read().decode())
        except Exception as e:
            logger.error(f"OIDC: Failed to pull certificates: {e}")
    return jwks_cache


def _resolve_signing_key(token: str, jwks):
    global jwks_cache
    if isinstance(jwks, dict) and "keys" in jwks and PyJWKSet is not None:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        jwk_set = PyJWKSet.from_dict(jwks)
        if kid:
            try:
                return jwk_set[kid].key
            except KeyError:
                jwks_cache = None
                refreshed = get_jwks()
                if refreshed and isinstance(refreshed, dict) and "keys" in refreshed:
                    return PyJWKSet.from_dict(refreshed)[kid].key
                raise JWTError(f"Signing key ID '{kid}' not found in JWKS")
        if jwk_set.keys:
            return jwk_set.keys[0].key
        raise JWTError("No signing keys present in JWKS")
    return jwks


class User(BaseModel):
    id: str
    role: str


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    x_user_id: str = Header("anonymous", alias="X-User-ID"),
    x_user_role: str = Header("user", alias="X-User-Role"),
) -> User:
    if ENABLE_OIDC or os.environ.get("ENABLE_OIDC", "false").lower() == "true":
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing dynamic identity validation bearer token",
                )
        if jwt is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT verification library unavailable",
            )
        try:
            jwks = get_jwks() or get_jwks()
            if not jwks:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Identity certificates provider offline",
                )
            signing_key = _resolve_signing_key(token, jwks)
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=ALGORITHMS,
                leeway=300,
                options={"verify_aud": False},
            )
            user_id = payload.get("preferred_username") or payload.get("sub")
            roles = payload.get("realm_access", {}).get("roles", [])
            user_role = "admin" if "admin" in roles else "user"
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid verification credentials claims",
                )
            return User(id=user_id, role=user_role)
        except JWTError as e:
            logger.error(f"OIDC Claim Check Failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cryptographic credentials validation failed",
            )
    return User(id=x_user_id, role=x_user_role)


def _sanitize_filename(filename: Optional[str]) -> str:
    safe_name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe_name


class QueryRequest(BaseModel):
    query: str
    chat_id: Optional[int] = None


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    scope: str = Form("personal"),
    user: User = Depends(get_current_user)
):
    if scope == "shared" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can upload to shared storage")

    safe_filename = _sanitize_filename(file.filename)
    safe_user_id = _sanitize_filename(user.id) if scope != "shared" else ""
    prefix = "shared/" if scope == "shared" else f"users/{safe_user_id}/"
    blob_name = f"{prefix}{safe_filename}"

    try:
        storage_client = storage.Client()
        bucket_name = INPUT_BUCKET.replace('gs://', '')
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        await file.seek(0)
        blob.upload_from_file(file.file)
        return {"filename": blob_name, "status": "uploaded", "scope": scope}
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


@app.post("/ingest")
async def trigger_ingestion(user: User = Depends(get_current_user)):
    if (ENABLE_OIDC or os.environ.get("ENABLE_OIDC", "false").lower() == "true") and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can trigger ingestion")
    return {"status": "ingestion_triggered", "message": "Ingestion process started (simulated)"}


@app.post("/query")
async def query(request: QueryRequest, user: User = Depends(get_current_user)):
    try:
        chat_id = request.chat_id
        conn = get_db_connection()
        cur = conn.cursor()

        if not chat_id:
            cur.execute(
                "INSERT INTO chats (user_id, title) VALUES (%s, %s) RETURNING id;",
                (user.id, request.query[:50])
            )
            chat_id = cur.fetchone()[0]
            conn.commit()
        else:
            cur.execute("SELECT user_id FROM chats WHERE id = %s;", (chat_id,))
            row = cur.fetchone()
            if not row or row[0] != user.id:
                cur.close()
                conn.close()
                raise HTTPException(status_code=403, detail="Chat not found or access denied")

        cur.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (%s, %s, %s);",
            (chat_id, "user", request.query)
        )
        conn.commit()
        cur.close()
        conn.close()

        agent = Agent(user=user)
        result = await agent.run(request.query)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (%s, %s, %s);",
            (chat_id, "assistant", result["answer"])
        )
        conn.commit()
        cur.close()
        conn.close()

        result["chat_id"] = chat_id
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Agent Error: {e}")
        raise HTTPException(status_code=500, detail="Agent query processing failed")


@app.get("/chats")
def list_chats(user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title, created_at FROM chats WHERE user_id = %s ORDER BY created_at DESC;", (user.id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]
    except Exception as e:
        print(f"List Chats Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chats")


@app.get("/chats/{chat_id}")
def get_chat_history(chat_id: int, user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM chats WHERE id = %s;", (chat_id,))
        row = cur.fetchone()
        if not row or row[0] != user.id:
            cur.close()
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")

        cur.execute("SELECT role, content, timestamp FROM messages WHERE chat_id = %s ORDER BY timestamp ASC;", (chat_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get Chat History Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat history")


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: int, user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM chats WHERE id = %s AND user_id = %s;", (chat_id, user.id))
        if cur.rowcount == 0:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Chat not found")
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "deleted", "id": chat_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete Chat Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete chat")


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Admin Endpoints ---

@app.get("/documents")
def list_documents(user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if user.role == "admin":
            cur.execute("SELECT id, filename, left(content, 100) as preview, vector_dims(embedding) as dims, owner_id FROM documents ORDER BY id DESC;")
        else:
            cur.execute("SELECT id, filename, left(content, 100) as preview, vector_dims(embedding) as dims, owner_id FROM documents WHERE owner_id = %s ORDER BY id DESC;", (user.id,))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        documents = []
        for row in rows:
            documents.append({
                "id": row[0],
                "filename": row[1],
                "preview": row[2],
                "embedding_dims": row[3],
                "owner_id": row[4]
            })
        return documents
    except Exception as e:
        print(f"Admin List Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list documents")


@app.delete("/documents/{filename:path}")
def delete_document(filename: str, user: User = Depends(get_current_user)):
    if ".." in filename.split("/"):
        raise HTTPException(status_code=400, detail="Invalid document path")
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT owner_id FROM documents WHERE filename = %s;", (filename,))
        row = cur.fetchone()

        if not row:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Document not found")

        owner_id = row[0]

        if owner_id is None:  # Shared
            if user.role != "admin":
                cur.close()
                conn.close()
                raise HTTPException(status_code=403, detail="Only admins can delete shared documents")
        else:  # Personal
            if owner_id != user.id and user.role != "admin":
                cur.close()
                conn.close()
                raise HTTPException(status_code=403, detail="You can only delete your own documents")

        cur.execute("DELETE FROM documents WHERE filename = %s;", (filename,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            storage_client = storage.Client()
            bucket_name = INPUT_BUCKET.replace('gs://', '')
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(filename)
            blob.delete()
            print(f"Deleted {filename} from GCS")
        except Exception as gcs_e:
            print(f"Warning: Could not delete from GCS: {gcs_e}")

        return {"status": "deleted", "filename": filename}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")


@app.get("/admin/stats")
def get_stats(user: User = Depends(get_current_user)):
    if (ENABLE_OIDC or os.environ.get("ENABLE_OIDC", "false").lower() == "true") and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access stats")
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        stats = {}
        cur.execute("SELECT count(*) FROM documents;")
        stats["total_documents"] = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM documents WHERE vector_dims(embedding) = 768;")
        stats["valid_embeddings"] = cur.fetchone()[0]

        cur.close()
        conn.close()
        return stats
    except Exception as e:
        print(f"Admin Stats Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")
