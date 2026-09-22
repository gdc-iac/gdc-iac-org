from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Literal, Union
from datetime import datetime
import uuid

class User(BaseModel):
    id: str
    role: Literal["user", "admin"] = "user"

class ChatSession(BaseModel):
    id: Union[str, uuid.UUID]
    user_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(coerce_numbers_to_str=True)

class Message(BaseModel):
    id: Union[str, uuid.UUID]
    chat_id: Union[str, uuid.UUID]
    role: Literal["user", "model", "system"]
    content: str
    created_at: datetime

    model_config = ConfigDict(coerce_numbers_to_str=True)

class FileMetadata(BaseModel):
    id: Union[str, uuid.UUID]
    user_id: Optional[str]
    filename: str
    gcs_path: str
    file_size_bytes: int
    content_type: str
    uploaded_at: datetime
    is_shared: bool

    model_config = ConfigDict(coerce_numbers_to_str=True)

class ChatRequest(BaseModel):
    message: str
    model: str = "gemma4:26b"
    file_ids: List[str] = []
    only_use_sources: bool = False
    chat_id: Optional[str] = None
    is_thinking_enabled: bool = True

class ChatResponse(BaseModel):
    response: str
    chat_id: str
    model: Optional[str] = None

class TelemetryEvent(BaseModel):
    id: Optional[Union[str, uuid.UUID]] = None
    event_timestamp: Optional[datetime] = None
    domain: str # LAND, AIR, SEA, SPACE, CYBER
    sensor_id: str
    sector: str = "Sector 9"
    threat_level: str # CRITICAL, HIGH, MEDIUM, LOW
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    title: str
    summary: Optional[str] = None
    raw_payload: Optional[dict] = None

    model_config = ConfigDict(coerce_numbers_to_str=True)

class AnalystRequest(BaseModel):
    query: str
    model: Optional[str] = "gemma4:26b"

class AnalystResponse(BaseModel):
    query: str
    generated_sql: str
    results: List[dict]
    summary: str
    row_count: int
    execution_time_ms: float
    model_used: str

class RagQueryRequest(BaseModel):
    query: str
    sector: Optional[str] = "Sector 9"

class Citation(BaseModel):
    report_id: str
    title: str
    source_agency: str
    snippet: str

class RagQueryResponse(BaseModel):
    query: str
    answer: str
    citations: List[Citation]
    model_used: str

