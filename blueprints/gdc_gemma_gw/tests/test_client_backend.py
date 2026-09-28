import pytest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add client backend directory to path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../gemma-client/src/backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Clear sys.modules to avoid collision with other main.py files
if "main" in sys.modules:
    del sys.modules["main"]

# Mock database module BEFORE importing app to prevent connection issues
import database
database.db.connect = AsyncMock()
database.db.disconnect = AsyncMock()
database.db.fetch_one = AsyncMock()
database.db.fetch_all = AsyncMock()
database.db.execute = AsyncMock()

# Mock storage module
import storage
storage.upload_file_to_gcs = AsyncMock()
storage.delete_file_from_gcs = AsyncMock()
storage.get_blob_content = MagicMock()

# Mock chat module
import chat
chat.generate_chat_response = AsyncMock()

from main import app

client = TestClient(app)

class MockRow(dict):
    """Helper class that acts like an asyncpg.Record row."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def __getitem__(self, key):
        return super().__getitem__(key)


def test_client_health():
    """Test that gemma-client backend healthcheck works."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_client_dynamic_models(monkeypatch):
    """Test that dynamic model discovery maps gateway models correctly."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "gemma4:26b-moe"},
            {"id": "gemma4:31b-dense"}
        ]
    }
    mock_client.get = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "gemma4:26b-moe"
    assert "MoE" in data[0]["name"]
    assert data[1]["id"] == "gemma4:31b-dense"
    assert "Dense" in data[1]["name"]


def test_client_list_files():
    """Test listing files available to a specific user."""
    mock_files = [
        MockRow({
            "id": "file-1",
            "user_id": "user-123",
            "filename": "my_doc.pdf",
            "gcs_path": "users/user-123/my_doc.pdf",
            "file_size_bytes": 1024,
            "content_type": "application/pdf",
            "uploaded_at": "2026-05-05T08:00:00",
            "is_shared": False
        }),
        MockRow({
            "id": "file-2",
            "user_id": "admin-user",
            "filename": "shared_resource.txt",
            "gcs_path": "shared/shared_resource.txt",
            "file_size_bytes": 2048,
            "content_type": "text/plain",
            "uploaded_at": "2026-05-05T07:00:00",
            "is_shared": True
        })
    ]
    database.db.fetch_all.return_value = mock_files

    headers = {"X-User-ID": "user-123", "X-User-Role": "user"}
    response = client.get("/files", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "file-1"
    assert data[0]["is_shared"] is False
    assert data[1]["id"] == "file-2"
    assert data[1]["is_shared"] is True


def test_client_upload_rbac():
    """Test RBAC policies for uploading files (shared requires admin)."""
    storage.upload_file_to_gcs.return_value = "shared/admin_resource.pdf"
    database.db.execute.return_value = "INSERT 0 1"

    # 1. Non-admin attempting to upload shared file
    headers_user = {"X-User-ID": "user-123", "X-User-Role": "user"}
    files = {"file": ("test.pdf", b"pdf_content", "application/pdf")}
    data = {"is_shared": "true"}
    
    response = client.post("/upload", headers=headers_user, data=data, files=files)
    assert response.status_code == 403
    assert "Only admins can upload shared files" in response.json()["detail"]

    # 2. Admin successfully uploading shared file
    headers_admin = {"X-User-ID": "admin-123", "X-User-Role": "admin"}
    files = {"file": ("test.pdf", b"pdf_content", "application/pdf")}
    
    response = client.post("/upload", headers=headers_admin, data=data, files=files)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["filename"] == "test.pdf"
    assert res_data["gcs_path"] == "shared/admin_resource.pdf"


def test_client_delete_file_ownership():
    """Test file deletion ownership validation and admin override."""
    mock_file = MockRow({
        "user_id": "user-123",
        "gcs_path": "users/user-123/doc.txt"
    })
    database.db.fetch_one.return_value = mock_file
    storage.delete_file_from_gcs.return_value = True
    database.db.execute.return_value = "DELETE 1"

    # 1. Delete another user's file (Unauthorized)
    headers_other = {"X-User-ID": "user-999", "X-User-Role": "user"}
    response = client.delete("/files/file-123", headers=headers_other)
    assert response.status_code == 403

    # 2. Delete own file (Authorized)
    headers_owner = {"X-User-ID": "user-123", "X-User-Role": "user"}
    response = client.delete("/files/file-123", headers=headers_owner)
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}

    # 3. Delete another user's file as Admin (Authorized bypass)
    headers_admin = {"X-User-ID": "admin-123", "X-User-Role": "admin"}
    response = client.delete("/files/file-123", headers=headers_admin)
    assert response.status_code == 200


def test_client_get_file_content():
    """Test file contents retrieval and access validation."""
    mock_file = MockRow({
        "user_id": "user-123",
        "filename": "doc.txt",
        "gcs_path": "users/user-123/doc.txt",
        "content_type": "text/plain",
        "is_shared": False
    })
    database.db.fetch_one.return_value = mock_file
    storage.get_blob_content.return_value = b"Hello Ground Truth!"

    # 1. Unauthorized user fetch
    headers_other = {"X-User-ID": "user-999", "X-User-Role": "user"}
    response = client.get("/files/file-123/content", headers=headers_other)
    assert response.status_code == 403

    # 2. Authorized user fetch
    headers_owner = {"X-User-ID": "user-123", "X-User-Role": "user"}
    response = client.get("/files/file-123/content", headers=headers_owner)
    assert response.status_code == 200
    assert response.content == b"Hello Ground Truth!"
    assert response.headers["content-type"].startswith("text/plain")


def test_client_chat_completions():
    """Test end-to-end chat creation and response persistence."""
    chat.generate_chat_response.return_value = ("I am Gemma's assistant response.", "gemma4:26b")
    
    # Mock chat ownership lookup (for existing chat)
    database.db.fetch_one.return_value = MockRow({"user_id": "user-123"})
    database.db.fetch_all.return_value = [] # Mock empty history
    database.db.execute.return_value = "INSERT"

    headers = {"X-User-ID": "user-123", "X-User-Role": "user"}
    payload = {
        "message": "What is Gemma?",
        "chat_id": "existing-chat-uuid",
        "model": "gemma4:26b",
        "file_ids": [],
        "only_use_sources": False,
        "is_thinking_enabled": True
    }

    response = client.post("/chat", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["response"] == "I am Gemma's assistant response."
    assert response.json()["chat_id"] == "existing-chat-uuid"
