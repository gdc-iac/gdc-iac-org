import pytest
from fastapi.testclient import TestClient
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock

# Add proxy directory to path so we can import main.py
proxy_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../gateway/proxy"))
if proxy_path not in sys.path:
    sys.path.insert(0, proxy_path)

# Clear sys.modules to avoid collision with other main.py files
if "main" in sys.modules:
    del sys.modules["main"]

import main
from main import app, CURRENT_STATE

client = TestClient(app)

def test_admin_ui_reachable():
    """Test that the GDC Admin UI loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Gemma 4 Gateway Control Plane" in response.text

def test_config_get():
    """Test configuration retrieval."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "backend" in data or "model_variant" in data
    assert "temperature" in data

def test_config_update():
    """Test that updating the configuration affects the global state."""
    response = client.post("/api/config", json={"model_variant": "31b", "temperature": 0.2, "vision_token_budget": 560})
    assert response.status_code == 200
    assert CURRENT_STATE["model_variant"] == "31b"
    assert CURRENT_STATE["temperature"] == 0.2
    assert CURRENT_STATE["vision_token_budget"] == 560


@pytest.mark.parametrize(
    "framework,requested_model,model_variant,expected_url,expected_payload_model",
    [
        # Ollama framework routing
        ("ollama", "gemma4:31b", "26b", "http://ollama-31b-service:11434/v1/chat/completions", "gemma4:31b"),
        ("ollama", "default", "26b", "http://ollama-26b-service:11434/v1/chat/completions", "gemma4:26b"),
        ("ollama", "default", "31b", "http://ollama-31b-service:11434/v1/chat/completions", "gemma4:31b"), # Prompts with "Hi" dynamically resolve to active variant 31b
        # vLLM framework routing
        ("vllm", "gemma4:26b", "26b", "http://vllm-26b-vllm-gke-service:8000/v1/chat/completions", "gemma4:26b"),
        ("vllm", "default", "26b", "http://vllm-26b-vllm-gke-service:8000/v1/chat/completions", "gemma4:26b"), # Prompts with "Hi" dynamically resolve to MoE 26b
    ]
)
def test_chat_completions_routing(monkeypatch, framework, requested_model, model_variant, expected_url, expected_payload_model):
    """Test that chat completions requests are routed to correct backend service with correct parameters and headers."""
    # Set mock state
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", framework)
    main.CURRENT_STATE["model_variant"] = model_variant
    main.CURRENT_STATE["vision_token_budget"] = 560
    main.CURRENT_STATE["temperature"] = 0.7
    main.CURRENT_STATE["top_p"] = 0.9
    main.CURRENT_STATE["frequency_penalty"] = 0.0
    
    # Re-evaluate routing config based on frameworks
    if framework == "ollama":
        monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {
            "gemma4:26b": "http://ollama-26b-service:11434",
            "gemma4:31b": "http://ollama-31b-service:11434",
            "*": "http://ollama-26b-service:11434"
        })
    else:
        monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {
            "gemma4:26b": "http://vllm-26b-vllm-gke-service:8000",
            "gemma4:31b": "http://vllm-31b-vllm-gke-service:8000",
            "*": "http://vllm-26b-vllm-gke-service:8000"
        })

    # Mock the AsyncClient for httpx
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Hello from mock!"}}]}
    mock_client.post = AsyncMock(return_value=mock_response)
    
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Request payload
    payload = {
        "messages": [{"role": "user", "content": "Hi"}]
    }
    if requested_model != "default":
        payload["model"] = requested_model

    # Fire request
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.json() == {"choices": [{"message": {"content": "Hello from mock!"}}]}

    # Assert correct endpoint and parameter routing
    mock_client.post.assert_called_once()
    called_url = mock_client.post.call_args[0][0]
    called_json = mock_client.post.call_args[1]["json"]
    called_headers = mock_client.post.call_args[1]["headers"]

    assert called_url == expected_url
    assert called_json["model"] == expected_payload_model
    assert called_json["temperature"] == 0.7
    assert called_json["top_p"] == 0.9
    assert called_json["frequency_penalty"] == 0.0
    assert called_headers["X-Gemma-Vision-Budget"] == "560"


def test_chat_completions_streaming(monkeypatch):
    """Test that the streaming endpoint properly streams events and handles SSE format."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {"*": "http://ollama-26b-service:11434"})
    main.CURRENT_STATE["model_variant"] = "26b"
    main.CURRENT_STATE["vision_token_budget"] = 280

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_response = MagicMock()
    mock_response.status_code = 200

    # Mock async generator for stream lines
    async def mock_aiter_lines():
        yield "data: {\"choices\": [{\"delta\": {\"content\": \"chunk1\"}}]}"
        yield "data: {\"choices\": [{\"delta\": {\"content\": \"chunk2\"}}]}"

    mock_response.aiter_lines = mock_aiter_lines

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_response
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client.stream = MagicMock(return_value=AsyncContextManagerMock())
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    payload = {
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    
    # Read streaming events
    stream_content = response.text
    lines = [line.strip() for line in stream_content.split("\n") if line.strip()]
    assert len(lines) == 2
    assert "chunk1" in lines[0]
    assert "chunk2" in lines[1]


def test_chat_completions_error_propagation(monkeypatch):
    """Test that the gateway gracefully handles connection and server errors from the downstream inference engine."""
    import httpx # Import at start of function to avoid UnboundLocalError
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {"*": "http://ollama-26b-service:11434"})
    
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    # Simulate httpx.RequestError (e.g., connection failed)
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    payload = {
        "messages": [{"role": "user", "content": "Hi"}]
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 502
    assert "Error communicating with backend service" in response.json()["detail"]


def test_metrics_api():
    """Verify `/api/metrics` returns valid telemetry data fields."""
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    
    assert "cpu_utilization" in data
    assert "gpu_utilization" in data
    assert "vram_percent" in data
    assert "active_completions" in data
    assert "active_sessions_count" in data
    assert "db_connections" in data
    assert "request_throughput" in data


def test_sessions_api_and_kill_switch(monkeypatch):
    """Test that active sessions are registered dynamically and can be terminated in-flight by the kill-switch."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {"*": "http://ollama-26b-service:11434"})
    
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    # Yield line check and mock killed flag intercept
    async def mock_aiter_lines():
        yield "data: {\"choices\": [{\"delta\": {\"content\": \"token_1 \"}}]}"
        # Admin triggers kill switch dynamically by matching user_id!
        for session in main.ACTIVE_SESSIONS.values():
            if session["user_id"] == "user-abc":
                session["killed"] = True
        yield "data: {\"choices\": [{\"delta\": {\"content\": \"token_2 \"}}]}"

    mock_response.aiter_lines = mock_aiter_lines

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_response
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client.stream = MagicMock(return_value=AsyncContextManagerMock())
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Set mock request headers to track session
    headers = {
        "X-User-ID": "user-abc",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"role": "user", "content": "Stream count"}],
        "stream": True
    }

    # Reset registries
    main.ACTIVE_SESSIONS = {}
    
    response = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    
    # Read stream text
    body = response.text
    lines = [line for line in body.split("\n") if line.strip()]
    
    # We should have chunk 1, and then the Stream Terminated token, and no chunk 2!
    assert len(lines) == 2
    assert "token_1" in lines[0]
    assert "[Stream Terminated By Administrator]" in lines[1]
    assert "token_2" not in body


def test_user_blocklist_enforcement(monkeypatch):
    """Test administrative blocking and subsequent request rejections at gateway boundary."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {"*": "http://ollama-26b-service:11434"})
    
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Hello user"}}]}
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Reset blocklist
    main.BLOCKED_USERS = set()
    
    headers = {"X-User-ID": "unwanted-user"}
    payload = {"messages": [{"role": "user", "content": "Hi"}]}

    # 1. First query (authorized)
    res1 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res1.status_code == 200

    # 2. Administrative Block
    res_block = client.post("/api/users/unwanted-user/block", json={"blocked": True})
    assert res_block.status_code == 200
    assert "unwanted-user" in main.BLOCKED_USERS

    # Check GET /api/users/blocked lists it
    res_list = client.get("/api/users/blocked")
    assert "unwanted-user" in res_list.json()

    # 3. Second query (blocked with 403)
    res2 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res2.status_code == 403
    assert "User has been administratively blocked" in res2.json()["detail"]

    # 4. Administrative Unblock
    res_unblock = client.post("/api/users/unwanted-user/block", json={"blocked": False})
    assert res_unblock.status_code == 200
    assert "unwanted-user" not in main.BLOCKED_USERS

    # 5. Third query (authorized again)
    res3 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res3.status_code == 200


def test_prompt_routing_classifier_complex(monkeypatch):
    """Verify that a complex logic/code prompt is dynamically classified and routed to 31B Dense serving pool."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {
        "gemma4:26b": "http://ollama-26b-service:11434",
        "gemma4:31b": "http://ollama-31b-service:11434",
        "*": "http://ollama-26b-service:11434"
    })

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Mocked complex response"}}]}
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Send a complex prompt containing logic/code keywords
    payload = {
        "messages": [{"role": "user", "content": "Write a python function to solve a derivative equation."}]
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    # Verify it routed to the 31B Dense service URL
    mock_client.post.assert_called_once()
    called_url = mock_client.post.call_args[0][0]
    called_json = mock_client.post.call_args[1]["json"]
    
    assert called_url == "http://ollama-31b-service:11434/v1/chat/completions"
    assert called_json["model"] == "gemma4:31b"


def test_prompt_routing_classifier_conversational(monkeypatch):
    """Verify that a simple conversational prompt is dynamically routed to the 26B MoE serving pool."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    main.CURRENT_STATE["model_variant"] = "26b"
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {
        "gemma4:26b": "http://ollama-26b-service:11434",
        "gemma4:31b": "http://ollama-31b-service:11434",
        "*": "http://ollama-26b-service:11434"
    })

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Mocked greeting"}}]}
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Send a conversational prompt
    payload = {
        "messages": [{"role": "user", "content": "Hello! How has your day been?"}]
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    # Verify it routed to the 26B MoE service URL
    mock_client.post.assert_called_once()
    called_url = mock_client.post.call_args[0][0]
    called_json = mock_client.post.call_args[1]["json"]
    
    assert called_url == "http://ollama-26b-service:11434/v1/chat/completions"
    assert called_json["model"] == "gemma4:26b"


def test_prompt_routing_classifier_explicit_override(monkeypatch):
    """Verify that an explicit client model selection overrides any dynamic prompt classification."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {
        "gemma4:26b": "http://ollama-26b-service:11434",
        "gemma4:31b": "http://ollama-31b-service:11434",
        "*": "http://ollama-26b-service:11434"
    })

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Forced response"}}]}
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Explicitly request 31b (Dense) even though the text is simple conversational
    payload = {
        "model": "gemma4:31b",
        "messages": [{"role": "user", "content": "Hi"}]
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    # Verify it routed strictly to 31b, ignoring the conversational classifier!
    mock_client.post.assert_called_once()
    called_url = mock_client.post.call_args[0][0]
    called_json = mock_client.post.call_args[1]["json"]
    
    assert called_url == "http://ollama-31b-service:11434/v1/chat/completions"
    assert called_json["model"] == "gemma4:31b"



def test_flatten_system_message_concatenation():
    """Verify that multiple system messages are combined and concatenated rather than overwritten."""
    messages = [
        {"role": "system", "content": "Instruction 1: Strict mode."},
        {"role": "user", "content": "What is the secret?"},
        {"role": "system", "content": "Instruction 2: Here is context."}
    ]
    
    flattened = main.flatten_system_message(messages)
    
    # Assert system role messages were completely flattened
    assert len(flattened) == 1
    assert flattened[0]["role"] == "user"
    
    content = flattened[0]["content"]
    assert "System Directive: Instruction 1: Strict mode.\n\nInstruction 2: Here is context." in content
    assert "User Query: What is the secret?" in content


def test_prompt_routing_classifier_dynamic_fallback(monkeypatch):
    """Verify that a general conversational query resolves to the active/hot-swapped variant."""
    # Case A: active variant is 31b
    main.CURRENT_STATE["model_variant"] = "31b"
    payload = {"messages": [{"role": "user", "content": "Hello!"}]}
    resolved = main.classify_prompt_complexity(payload)
    assert resolved == "gemma4:31b"
    
    # Case B: active variant is 26b
    main.CURRENT_STATE["model_variant"] = "26b"
    resolved = main.classify_prompt_complexity(payload)
    assert resolved == "gemma4:26b"


def test_prompt_routing_classifier_history_does_not_stick(monkeypatch):
    """Verify that a historic complex query does not get subsequent simple queries stuck on 31B."""
    monkeypatch.setattr(main, "ACTIVE_FRAMEWORK", "ollama")
    main.CURRENT_STATE["model_variant"] = "26b"
    monkeypatch.setattr(main, "MODEL_ROUTING_CONFIG", {
        "gemma4:26b": "http://ollama-26b-service:11434",
        "gemma4:31b": "http://ollama-31b-service:11434",
        "*": "http://ollama-26b-service:11434"
    })

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Mocked greeting"}}]}
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=mock_client))

    # Send a payload with history containing a complex prompt, but the LATEST is conversational
    payload = {
        "messages": [
            {"role": "user", "content": "Write a python function to solve a derivative equation."},
            {"role": "model", "content": "Here is the function..."},
            {"role": "user", "content": "Thanks, that works!"}
        ]
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    # Verify it routed to the 26B MoE service URL, not 31B!
    mock_client.post.assert_called_once()
    called_url = mock_client.post.call_args[0][0]
    called_json = mock_client.post.call_args[1]["json"]
    
    assert called_url == "http://ollama-26b-service:11434/v1/chat/completions"
    assert called_json["model"] == "gemma4:26b"



