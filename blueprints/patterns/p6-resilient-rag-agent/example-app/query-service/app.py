import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from google.cloud import storage
from utils import get_db_connection, INPUT_BUCKET
from agent import Agent
import uuid

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class User(BaseModel):
    id: str
    role: str

async def get_current_user(
    x_user_id: str = Header("anonymous", alias="X-User-ID"),
    x_user_role: str = Header("user", alias="X-User-Role")
) -> User:
    return User(id=x_user_id, role=x_user_role)

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
    
    # Determine path prefix
    prefix = "shared/" if scope == "shared" else f"users/{user.id}/"
    blob_name = f"{prefix}{file.filename}"

    try:
        storage_client = storage.Client()
        bucket_name = INPUT_BUCKET.replace('gs://', '')
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        # Reset file pointer just in case
        await file.seek(0)
        blob.upload_from_file(file.file)
        return {"filename": blob_name, "status": "uploaded", "scope": scope}
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

@app.post("/ingest")
async def trigger_ingestion():
    return {"status": "ingestion_triggered", "message": "Ingestion process started (simulated)"}

@app.post("/query")
async def query(request: QueryRequest, user: User = Depends(get_current_user)):
    try:
        # Create chat session if not exists
        chat_id = request.chat_id
        conn = get_db_connection()
        cur = conn.cursor()
        
        if not chat_id:
            # Create new chat
            cur.execute(
                "INSERT INTO chats (user_id, title) VALUES (%s, %s) RETURNING id;",
                (user.id, request.query[:50])
            )
            chat_id = cur.fetchone()[0]
            conn.commit()
        else:
            # Verify ownership
            cur.execute("SELECT user_id FROM chats WHERE id = %s;", (chat_id,))
            row = cur.fetchone()
            if not row or row[0] != user.id:
                cur.close()
                conn.close()
                raise HTTPException(status_code=403, detail="Chat not found or access denied")
        
        # Save User Message
        cur.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (%s, %s, %s);",
            (chat_id, "user", request.query)
        )
        conn.commit()
        cur.close()
        conn.close()

        # Run Agent
        agent = Agent(user=user)
        result = await agent.run(request.query)
        
        # Save Assistant Message
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
        raise HTTPException(status_code=500, detail=f"Agent failed: {e}")

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chats/{chat_id}")
def get_chat_history(chat_id: int, user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Verify ownership
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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
            # Admin sees ALL documents
            cur.execute("SELECT id, filename, left(content, 100) as preview, vector_dims(embedding) as dims, owner_id FROM documents ORDER BY id DESC;")
        else:
            # User sees ONLY their own documents (and maybe shared? For management, usually just own)
            # Let's show ONLY their own documents so they can manage them.
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
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{filename:path}")
def delete_document(filename: str, user: User = Depends(get_current_user)):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check ownership
        cur.execute("SELECT owner_id FROM documents WHERE filename = %s;", (filename,))
        row = cur.fetchone()
        
        if not row:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Document not found")
            
        owner_id = row[0]
        
        # RBAC Logic
        if owner_id is None: # Shared
            if user.role != "admin":
                cur.close()
                conn.close()
                raise HTTPException(status_code=403, detail="Only admins can delete shared documents")
        else: # Personal
            if owner_id != user.id:
                cur.close()
                conn.close()
                raise HTTPException(status_code=403, detail="You can only delete your own documents")
        
        # Delete from DB
        cur.execute("DELETE FROM documents WHERE filename = %s;", (filename,))
        conn.commit()
        cur.close()
        conn.close()
        
        # Delete from GCS
        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(INPUT_BUCKET)
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/stats")
def get_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        stats = {}
        
        # Total count
        cur.execute("SELECT count(*) FROM documents;")
        stats["total_documents"] = cur.fetchone()[0]
        
        # Embedding health (count valid 768 dims)
        cur.execute("SELECT count(*) FROM documents WHERE vector_dims(embedding) = 768;")
        stats["valid_embeddings"] = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        return stats
    except Exception as e:
        print(f"Admin Stats Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
