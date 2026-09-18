import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Safe sys.modules mocks for standalone unittest execution
class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    async def post(self, *args, **kwargs):
        pass

mock_httpx = MagicMock()
mock_httpx.AsyncClient = DummyAsyncClient
mock_httpx.Client = MagicMock()

mock_google = MagicMock()
mock_auth = MagicMock()
mock_requests = MagicMock()
mock_fastapi = MagicMock()

sys.modules.setdefault('psycopg2', MagicMock())
sys.modules.setdefault('google', mock_google)
sys.modules.setdefault('google.auth', mock_auth)
sys.modules.setdefault('google.auth.transport', MagicMock())
sys.modules.setdefault('google.auth.transport.requests', mock_requests)
sys.modules.setdefault('fastapi', mock_fastapi)

try:
    import httpx
except ImportError:
    sys.modules['httpx'] = mock_httpx

import asyncio
from utils import call_llm

class TestP6LLMClient(unittest.TestCase):

    @patch('utils.httpx.AsyncClient')
    def test_call_llm_gemma_openai(self, mock_async_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": "Final Answer: GDC is Google Distributed Cloud."}}
            ]
        }
        
        async def mock_post(*args, **kwargs):
            return mock_resp

        mock_client.post = mock_post
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "gemma",
            "LLM_GATEWAY_URL": "http://gemma-gateway:8080/v1"
        }):
            res = asyncio.run(call_llm("What is GDC?"))
            self.assertEqual(res, "Final Answer: GDC is Google Distributed Cloud.")

    @patch('utils.httpx.AsyncClient')
    def test_call_llm_gemma_generate(self, mock_async_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": {"text": "Gemma generate response"}
        }

        async def mock_post(*args, **kwargs):
            return mock_resp

        mock_client.post = mock_post
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "gemma",
            "LLM_GATEWAY_URL": "http://gemma-gateway:8080/generate"
        }):
            res = asyncio.run(call_llm("Test prompt"))
            self.assertEqual(res, "Gemma generate response")

    @patch('utils.httpx.AsyncClient')
    def test_call_llm_gemini_gdc(self, mock_async_client_cls):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": "Gemini response"}}
            ]
        }

        captured_kwargs = {}
        async def mock_post(*args, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return mock_resp

        mock_client.post = mock_post
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "gemini",
            "LLM_GATEWAY_URL": "https://ai-gateway.shared-services.gdc.local/v1",
            "AO_PROJECT_ID": "projects/my-test-project",
            "GDC_TOKEN": "test-sts-token"
        }):
            res = asyncio.run(call_llm("Test prompt"))
            self.assertEqual(res, "Gemini response")
            headers = captured_kwargs.get("headers", {})
            self.assertEqual(headers.get("x-goog-user-project"), "projects/my-test-project")
            self.assertEqual(headers.get("Authorization"), "Bearer test-sts-token")

if __name__ == "__main__":
    unittest.main()
