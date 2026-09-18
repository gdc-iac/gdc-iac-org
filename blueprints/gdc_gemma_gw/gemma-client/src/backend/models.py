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
