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
    model: str = "gemini-2.5-flash"
    file_ids: List[str] = []
    only_use_sources: bool = False
    chat_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    chat_id: str
