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

from fastapi import Request, HTTPException
from models import User

async def get_current_user(request: Request) -> User:
    # In a real app, this would validate a JWT.
    # For Stepping Stone / Dev, we use headers.
    user_id = request.headers.get("X-User-ID")
    user_role = request.headers.get("X-User-Role", "user")

    if not user_id:
        # Fallback for local testing or if header missing
        user_id = "anonymous"
        # In production, raise HTTPException(status_code=401, detail="Missing User ID")

    return User(id=user_id, role=user_role)
