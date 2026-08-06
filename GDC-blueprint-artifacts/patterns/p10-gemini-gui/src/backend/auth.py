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
