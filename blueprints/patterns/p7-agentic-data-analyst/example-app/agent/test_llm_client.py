# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Safe sys.modules mocks for standalone unittest execution
mock_requests = MagicMock()
mock_psycopg2 = MagicMock()
mock_flask = MagicMock()
mock_pandas = MagicMock()

sys.modules.setdefault('psycopg2', mock_psycopg2)
sys.modules.setdefault('flask', mock_flask)
sys.modules.setdefault('pandas', mock_pandas)

try:
    import requests
except ImportError:
    sys.modules['requests'] = mock_requests

from app import ask_llm

class TestP7LLMClient(unittest.TestCase):

    @patch('app.requests.post')
    def test_ask_llm_gemma_openai(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": "SELECT count(*) FROM sales;"}}
            ]
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "gemma",
            "LLM_GATEWAY_URL": "http://gemma-gateway:8080/v1"
        }):
            res = ask_llm("How many sales?")
            self.assertEqual(res, "SELECT count(*) FROM sales;")
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertIn("/v1/chat/completions", args[0])

    @patch('app.requests.post')
    def test_ask_llm_gemma_generate(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": {"text": "SELECT * FROM sales LIMIT 5;"}
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "gemma",
            "LLM_GATEWAY_URL": "http://gemma-gateway:8080/generate"
        }):
            res = ask_llm("Show sales sample")
            self.assertEqual(res, "SELECT * FROM sales LIMIT 5;")

    @patch('app.requests.post')
    def test_ask_llm_gemini_gdc(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": "SELECT SUM(amount) FROM sales;"}}
            ]
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "gemini",
            "LLM_GATEWAY_URL": "https://ai-gateway.shared-services.gdc.local/v1",
            "AO_PROJECT_ID": "projects/my-workload-project",
            "GDC_TOKEN": "gdc-test-sts-token"
        }):
            res = ask_llm("Total sales amount")
            self.assertEqual(res, "SELECT SUM(amount) FROM sales;")
            headers = mock_post.call_args[1]["headers"]
            self.assertEqual(headers["x-goog-user-project"], "projects/my-workload-project")
            self.assertEqual(headers["Authorization"], "Bearer gdc-test-sts-token")

if __name__ == "__main__":
    unittest.main()
