from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Optional
import uuid
from datetime import datetime

from database import db
from auth import get_current_user
from models import (
    User, ChatRequest, ChatResponse, ChatSession, Message, FileMetadata,
    TelemetryEvent, AnalystRequest, AnalystResponse, RagQueryRequest, RagQueryResponse
)
from storage import upload_file_to_gcs, delete_file_from_gcs, get_blob_content
from chat import generate_chat_response
from intel_services import execute_analyst_query, execute_rag_search
import json

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

@app.get("/models")
async def get_serving_models():
    import httpx
    from chat import GATEWAY_URL
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"{GATEWAY_URL}/models", timeout=10.0)
            if response.status_code != 200:
                print(f"WARNING: Gateway models discovery endpoint returned status code {response.status_code} for URL: {GATEWAY_URL}/models")
                return [
                    {"id": "gemma4:26b", "name": "Gemma 4 26B A4B (MoE)"},
                    {"id": "gemma4:31b", "name": "Gemma 4 31B (Dense)"}
                ]
            openai_data = response.json()
            models_list = []
            for item in openai_data.get("data", []):
                model_id = item.get("id")
                friendly_name = "Gemma 4 26B A4B (MoE)" if "26b" in model_id.lower() else "Gemma 4 31B (Dense)"
                if "8b" in model_id.lower() or "e4b" in model_id.lower():
                    friendly_name = "Gemma 4 8B Multimodal (E4B)"
                models_list.append({"id": model_id, "name": friendly_name})
            return models_list
    except Exception as e:
        print(f"Error querying dynamic models: {e}")
        return [
            {"id": "gemma4:26b", "name": "Gemma 4 26B A4B (MoE)"},
            {"id": "gemma4:31b", "name": "Gemma 4 31B (Dense)"}
        ]

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
    response_text, model_used = await generate_chat_response(
        message=req.message,
        history=history,
        file_ids=req.file_ids,
        model_name=req.model,
        only_use_sources=req.only_use_sources,
        is_thinking_enabled=req.is_thinking_enabled,
        user_id=user.id
    )

    # Save Model Response
    await db.execute(
        "INSERT INTO messages (chat_id, role, content) VALUES ($1, $2, $3)",
        chat_id, "model", response_text
    )
    
    # Update Chat Timestamp
    await db.execute("UPDATE chats SET updated_at = NOW() WHERE id = $1", chat_id)

    return ChatResponse(response=response_text, chat_id=chat_id, model=model_used)

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user: User = Depends(get_current_user)):
    chat = await db.fetch_one("SELECT user_id FROM chats WHERE id = $1", chat_id)
    if not chat or chat['user_id'] != user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    await db.execute("DELETE FROM chats WHERE id = $1", chat_id)
    return {"status": "deleted"}

# --- Intelligence & Decision Support (Operation Vanguard Shield) ---

@app.get("/telemetry/events", response_model=List[TelemetryEvent])
async def get_telemetry_events(
    domain: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(get_current_user)
):
    """Retrieve live or historical multi-domain sensor telemetry from Kafka ingestion table."""
    try:
        if domain and domain.upper() != "ALL":
            query = """
                SELECT id, event_timestamp, domain, sensor_id, sector, threat_level, latitude, longitude, title, summary, raw_payload
                FROM sensor_telemetry
                WHERE UPPER(domain) = $1
                ORDER BY event_timestamp DESC
                LIMIT $2
            """
            rows = await db.fetch_all(query, domain.upper(), limit)
        else:
            query = """
                SELECT id, event_timestamp, domain, sensor_id, sector, threat_level, latitude, longitude, title, summary, raw_payload
                FROM sensor_telemetry
                ORDER BY event_timestamp DESC
                LIMIT $1
            """
            rows = await db.fetch_all(query, limit)
            
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("raw_payload"), str):
                try:
                    d["raw_payload"] = json.loads(d["raw_payload"])
                except Exception:
                    pass
            result.append(TelemetryEvent(**d))
        return result
    except Exception as e:
        print(f"Error fetching telemetry: {e}")
        return []

@app.post("/telemetry/ingest")
async def ingest_telemetry_event(event: TelemetryEvent):
    """Ingest a sensor telemetry event (called by Kafka consumer or synthetic generator)."""
    query = """
        INSERT INTO sensor_telemetry (domain, sensor_id, sector, threat_level, latitude, longitude, title, summary, raw_payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
    """
    payload_json = json.dumps(event.raw_payload) if event.raw_payload else None
    row = await db.fetch_one(
        query,
        event.domain.upper(),
        event.sensor_id,
        event.sector,
        event.threat_level.upper(),
        event.latitude,
        event.longitude,
        event.title,
        event.summary,
        payload_json
    )
    return {"status": "ingested", "id": str(row["id"])}

@app.post("/telemetry/simulate")
async def simulate_telemetry_stream(count: int = 5, user: User = Depends(get_current_user)):
    """Generate a batch of multi-domain sensor events directly into the database for live UI demonstration."""
    import random
    domains = ["LAND", "AIR", "SEA", "SPACE", "CYBER"]
    threats = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    titles = {
        "LAND": [("Acoustic Sensor Tripwire", "Tracked vehicle signature approaching Waypoint Echo"),
                 ("UAV Visual Recon", "Bridge at Route 9 under active repair; lane capacity restricted")],
        "AIR": [("Radar Contact Track 402", "Unidentified fast-moving contact 12,000 ft heading 180 deg"),
                ("Electronic Warfare Sniffer", "RF jammer burst detected on tactical UHF band")],
        "SEA": [("AIS Littoral Ping", "Patrol cutter Bravo verifying security of harbor entrance"),
                ("Sonar Harbor Buoy", "Acoustic signature normal across transit channel")],
        "SPACE": [("SAR Satellite Pass", "Synthetic aperture radar downlink confirms clear bypass route"),
                  ("Tactical Downlink Ping", "16th Space Ops antenna locking high-bandwidth uplink")],
        "CYBER": [("SCADA Anomaly Alert", "Modbus port probe blocked at FOB Alpha fuel pump"),
                  ("Firewall SYN Flood", "External scanning detected targeting tactical gateway IP")]
    }
    
    inserted = 0
    for _ in range(count):
        dom = random.choice(domains)
        title, summary = random.choice(titles[dom])
        threat = random.choice(threats)
        sensor_id = f"{dom}-SNS-{random.randint(100, 999)}"
        lat = round(36.8 + random.uniform(-0.3, 0.3), 4)
        lon = round(-115.9 + random.uniform(-0.3, 0.3), 4)
        payload = json.dumps({"automated_simulation": True, "confidence": round(random.uniform(0.75, 0.99), 2)})
        
        await db.execute(
            """INSERT INTO sensor_telemetry (domain, sensor_id, sector, threat_level, latitude, longitude, title, summary, raw_payload)
               VALUES ($1, $2, 'Sector 9', $3, $4, $5, $6, $7, $8)""",
            dom, sensor_id, threat, lat, lon, title, summary, payload
        )
        inserted += 1
        
    return {"status": "simulated", "count": inserted}

@app.post("/analyst/query", response_model=AnalystResponse)
async def query_data_analyst(req: AnalystRequest, user: User = Depends(get_current_user)):
    """Agentic Data Analyst: Translates natural language commander queries into safe read-only SQL."""
    result = await execute_analyst_query(req.query, user_id=user.id)
    return AnalystResponse(**result)

@app.post("/rag/query", response_model=RagQueryResponse)
async def query_all_source_rag(req: RagQueryRequest, user: User = Depends(get_current_user)):
    """All-Source Intelligence RAG: Searches unstructured SITREPs and debriefs with citations."""
    result = await execute_rag_search(req.query, sector=req.sector or "Sector 9", user_id=user.id)
    return RagQueryResponse(**result)

