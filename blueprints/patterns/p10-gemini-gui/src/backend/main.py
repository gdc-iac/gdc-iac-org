from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Optional
import uuid
from datetime import datetime

from database import db
from auth import get_current_user
from models import User, ChatRequest, ChatResponse, ChatSession, Message, FileMetadata
from storage import upload_file_to_gcs, delete_file_from_gcs, get_blob_content
from chat import generate_chat_response

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Files ---

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    is_shared: bool = Form(False),
    user: User = Depends(get_current_user)
):
    # RBAC: Only admin can upload shared
    if is_shared and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can upload shared files")

    gcs_path = await upload_file_to_gcs(file, user.id, is_shared)
    
    file_id = str(uuid.uuid4())
    query = """
        INSERT INTO files (id, user_id, filename, gcs_path, file_size_bytes, content_type, is_shared)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
    """
    # Note: file.size might not be available in SpooledTemporaryFile until read/seek. 
    # We'll assume 0 or try to get it.
    size = 0 
    
    await db.execute(query, file_id, user.id, file.filename, gcs_path, size, file.content_type, is_shared)
    
    return {"id": file_id, "filename": file.filename, "gcs_path": gcs_path}

@app.get("/files", response_model=List[FileMetadata])
async def list_files(user: User = Depends(get_current_user)):
    # Users see their own + shared
    query = """
        SELECT id, user_id, filename, gcs_path, file_size_bytes, content_type, uploaded_at, is_shared
        FROM files
        WHERE user_id = $1 OR is_shared = TRUE
        ORDER BY uploaded_at DESC
    """
    rows = await db.fetch_all(query, user.id)
    return [FileMetadata(**dict(row)) for row in rows]

@app.delete("/files/{file_id}")
async def delete_file(file_id: str, user: User = Depends(get_current_user)):
    # Check ownership
    row = await db.fetch_one("SELECT user_id, gcs_path FROM files WHERE id = $1", file_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
        
    if row['user_id'] != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Delete from GCS
    await delete_file_from_gcs(row['gcs_path'])
    
    # Delete from DB
    await db.execute("DELETE FROM files WHERE id = $1", file_id)
    return {"status": "deleted"}

@app.get("/files/{file_id}/content")
async def get_file_content(file_id: str, user: User = Depends(get_current_user)):
    # Check access
    row = await db.fetch_one("SELECT user_id, filename, gcs_path, content_type, is_shared FROM files WHERE id = $1", file_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
        
    if row['user_id'] != user.id and not row['is_shared']:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get content from GCS
    try:
        print(f"DEBUG: Reading file {file_id} from GCS path: {row['gcs_path']}")
        content = get_blob_content(row['gcs_path'])
    except Exception as e:
        print(f"ERROR: Failed to read file {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

    # Return as stream/file
    from fastapi.responses import Response
    return Response(content=content, media_type=row['content_type'], headers={
        "Content-Disposition": f"inline; filename={row['filename']}"
    })

# --- Chat ---

@app.get("/chats", response_model=List[ChatSession])
async def list_chats(user: User = Depends(get_current_user)):
    rows = await db.fetch_all("SELECT * FROM chats WHERE user_id = $1 ORDER BY updated_at DESC", user.id)
    return [ChatSession(**dict(row)) for row in rows]

@app.get("/chats/{chat_id}/messages", response_model=List[Message])
async def get_chat_messages(chat_id: str, user: User = Depends(get_current_user)):
    # Verify access
    chat = await db.fetch_one("SELECT user_id FROM chats WHERE id = $1", chat_id)
    if not chat or chat['user_id'] != user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    rows = await db.fetch_all("SELECT * FROM messages WHERE chat_id = $1 ORDER BY created_at ASC", chat_id)
    return [Message(**dict(row)) for row in rows]

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    chat_id = req.chat_id
    
    # Create chat if new
    if not chat_id:
        chat_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO chats (id, user_id, title) VALUES ($1, $2, $3)",
            chat_id, user.id, req.message[:50] # Simple title
        )
    else:
        # Verify access
        chat = await db.fetch_one("SELECT user_id FROM chats WHERE id = $1", chat_id)
        if not chat or chat['user_id'] != user.id:
            raise HTTPException(status_code=404, detail="Chat not found")

    # Save User Message
    await db.execute(
        "INSERT INTO messages (chat_id, role, content) VALUES ($1, $2, $3)",
        chat_id, "user", req.message
    )

    # Fetch History
    history_rows = await db.fetch_all("SELECT * FROM messages WHERE chat_id = $1 ORDER BY created_at ASC", chat_id)
    history = [Message(**dict(row)) for row in history_rows]

    # Generate Response
    response_text = await generate_chat_response(
        message=req.message,
        history=history,
        file_ids=req.file_ids,
        model_name=req.model,
        only_use_sources=req.only_use_sources
    )

    # Save Model Response
    await db.execute(
        "INSERT INTO messages (chat_id, role, content) VALUES ($1, $2, $3)",
        chat_id, "model", response_text
    )
    
    # Update Chat Timestamp
    await db.execute("UPDATE chats SET updated_at = NOW() WHERE id = $1", chat_id)

    return ChatResponse(response=response_text, chat_id=chat_id)

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user: User = Depends(get_current_user)):
    chat = await db.fetch_one("SELECT user_id FROM chats WHERE id = $1", chat_id)
    if not chat or chat['user_id'] != user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    await db.execute("DELETE FROM chats WHERE id = $1", chat_id)
    return {"status": "deleted"}
