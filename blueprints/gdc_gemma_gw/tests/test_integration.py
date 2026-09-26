import os
import pytest
import asyncio
import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
import threading
import time
import sys

# Define Mock Inference Backend
mock_inference_app = FastAPI()

@mock_inference_app.post("/v1/chat/completions")
async def mock_completions(payload: dict):
    if payload.get("stream", False):
        async def stream_generator():
            for i in range(3):
                yield f"data: {{\"choices\": [{{\"delta\": {{\"content\": \"token_{i} \"}}}}]}}\n".encode('utf-8')
                await asyncio.sleep(0.05)
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    
    return JSONResponse(content={
        "choices": [{"message": {"role": "assistant", "content": "Hello from integration mock!"}}]
    })

@mock_inference_app.get("/v1/models")
async def mock_models():
    return JSONResponse(content={
        "data": [{"id": "gemma4:26b"}, {"id": "gemma4:31b"}]
    })


# Fixture to handle mock services locally when no live environment is configured
@pytest.fixture(scope="session")
def gateway_server_url():
    # If the user has specified a target gateway URL, use it directly
    target_url = os.getenv("GATEWAY_URL")
    if target_url:
        print(f"\n🎯 Running integration tests against LIVE Gateway: {target_url}")
        yield target_url
        return

    print("\n🧬 No GATEWAY_URL configured. Spinning up high-fidelity local Gateway and Mock Inference server...")

    # 1. Start Mock Inference Backend on port 50081
    def run_mock_inference():
        uvicorn.run(mock_inference_app, host="127.0.0.1", port=50081, log_level="error")
    
    inference_thread = threading.Thread(target=run_mock_inference, daemon=True)
    inference_thread.start()

    # 2. Configure Gateway environment and import fresh
    os.environ["ACTIVE_FRAMEWORK"] = "ollama"
    os.environ["MODEL_ROUTING_CONFIG"] = '{"gemma4:26b": "http://127.0.0.1:50081", "gemma4:31b": "http://127.0.0.1:50081", "*": "http://127.0.0.1:50081"}'
    
    if "main" in sys.modules:
        del sys.modules["main"]

    # Add proxy folder to python path
    proxy_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../gateway/proxy"))
    if proxy_path not in sys.path:
        sys.path.insert(0, proxy_path)
        
    import main
    
    # Force variables just to be absolutely sure
    main.ACTIVE_FRAMEWORK = "ollama"
    main.MODEL_ROUTING_CONFIG = {
        "gemma4:26b": "http://127.0.0.1:50081",
        "gemma4:31b": "http://127.0.0.1:50081",
        "*": "http://127.0.0.1:50081"
    }
    
    gateway_app = main.app

    # 3. Start Gateway Proxy on port 50082
    def run_mock_gateway():
        uvicorn.run(gateway_app, host="127.0.0.1", port=50082, log_level="error")
        
    gateway_thread = threading.Thread(target=run_mock_gateway, daemon=True)
    gateway_thread.start()

    # Allow servers to warm up
    time.sleep(1.5)
    
    yield "http://127.0.0.1:50082/v1"
    
    print("\n🛑 Tearing down local test servers.")


@pytest.mark.asyncio
async def test_concurrent_non_streaming(gateway_server_url):
    """Fire concurrent requests against the gateway to verify session isolation and response consistency."""
    is_live = os.getenv("GATEWAY_URL") is not None
    async with httpx.AsyncClient(trust_env=False) as client:
        # Run 5 concurrent non-streaming completions calls
        tasks = []
        for i in range(5):
            payload = {
                "model": "gemma4:26b",
                "messages": [{"role": "user", "content": f"Query {i}"}],
                "stream": False
            }
            tasks.append(client.post(f"{gateway_server_url}/chat/completions", json=payload, timeout=10.0))
            
        responses = await asyncio.gather(*tasks)
        
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if is_live:
                assert len(content) > 0
            else:
                assert "Hello from integration mock!" in content


@pytest.mark.asyncio
async def test_concurrent_streaming(gateway_server_url):
    """Assert that concurrent streaming connections receive chunked tokens independently without cross-talk."""
    is_live = os.getenv("GATEWAY_URL") is not None
    model_name = "gemma4:26b" # Query active variant loaded in sandboxes
    
    async with httpx.AsyncClient(trust_env=False) as client:
        async def fetch_stream(i):
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": f"Stream query {i}"}],
                "stream": True
            }
            async with client.stream("POST", f"{gateway_server_url}/chat/completions", json=payload, timeout=15.0) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                body_bytes = await response.aread()
                return body_bytes.decode("utf-8")

        tasks = [fetch_stream(i) for i in range(3)]
        responses = await asyncio.gather(*tasks)
        
        for stream_body in responses:
            if is_live:
                # Live GKE cluster should stream at least 1 SSE chunk
                lines = [line for line in stream_body.split("\n") if line.strip().startswith("data:")]
                assert len(lines) > 0
            else:
                # Mock should stream exactly 3 token_ chunks
                chunks = [line for line in stream_body.split("\n") if "token_" in line]
                assert len(chunks) == 3
                assert "token_0" in chunks[0]
                assert "token_1" in chunks[1]
                assert "token_2" in chunks[2]
