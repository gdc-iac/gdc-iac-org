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

import unittest
from unittest.mock import patch, MagicMock
import base64
import json
import os
import sys

# Mock missing dependencies
class MockInsufficientPrivilege(Exception):
    pass

mock_psycopg2 = MagicMock()
mock_psycopg2.errors.InsufficientPrivilege = MockInsufficientPrivilege

sys.modules['boto3'] = MagicMock()
sys.modules['psycopg2'] = mock_psycopg2
sys.modules['botocore'] = MagicMock()
sys.modules['botocore.client'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.auth.transport'] = MagicMock()
sys.modules['google.auth.transport.requests'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()

# Add the directory containing app.py to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import call_gemini_api, init_db

class TestGeminiIntegration(unittest.TestCase):

    @patch.dict(os.environ, {
        'LLM_PROVIDER': 'gemini',
        'LLM_GATEWAY_URL': 'https://generativelanguage.googleapis.com/v1beta/models',
    })
    @patch('app.httpx.Client')
    @patch('app.get_auth_token')
    def test_call_gemini_api_text(self, mock_get_token, mock_client_cls):
        # Setup mocks
        mock_get_token.return_value = "fake_token"
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Translated Text"}]
                }
            }]
        }
        mock_client.post.return_value = mock_response

        # Call function
        result = call_gemini_api("Translate this")

        # Verify
        self.assertEqual(result, "Translated Text")
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        self.assertIn("Authorization", kwargs['headers'])
        self.assertEqual(kwargs['headers']['Authorization'], "Bearer fake_token")
        self.assertEqual(kwargs['json']['contents'][0]['parts'][0]['text'], "Translate this")

    @patch.dict(os.environ, {
        'LLM_PROVIDER': 'gemini',
        'LLM_GATEWAY_URL': 'https://generativelanguage.googleapis.com/v1beta/models',
    })
    @patch('app.httpx.Client')
    @patch('app.get_auth_token')
    def test_call_gemini_api_multimodal(self, mock_get_token, mock_client_cls):
        # Setup mocks
        mock_get_token.return_value = "fake_token"
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Image Description"}]
                }
            }]
        }
        mock_client.post.return_value = mock_response

        # Call function
        content = b"fake_image_data"
        result = call_gemini_api("Describe this", content, "image/png")

        # Verify
        self.assertEqual(result, "Image Description")
        kwargs = mock_client.post.call_args[1]
        parts = kwargs['json']['contents'][0]['parts']
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]['text'], "Describe this")
        self.assertEqual(parts[1]['inlineData']['mimeType'], "image/png")
        self.assertEqual(parts[1]['inlineData']['data'], base64.b64encode(content).decode('utf-8'))

    @patch('app.get_db_connection')
    def test_init_db_skips_create_extension_when_vector_preinstalled(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # 1) pg_extension has 'vector' -> (1,)
        # 2) documents exists -> ('documents',)
        # 3) chats exists -> ('chats',)
        # 4) messages exists -> ('messages',)
        mock_cur.fetchone.side_effect = [(1,), ('documents',), ('chats',), ('messages',)]
        mock_cur.fetchall.return_value = [('id',), ('filename',), ('content',), ('embedding',), ('owner_id',), ('source_path',)]

        init_db()

        executed_sql = [call_args[0][0] for call_args in mock_cur.execute.call_args_list]
        self.assertTrue(any("FROM pg_extension WHERE extname = 'vector'" in s for s in executed_sql))
        self.assertFalse(any("CREATE EXTENSION" in s for s in executed_sql))
        mock_conn.commit.assert_called_once()
        mock_cur.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('app.get_db_connection')
    def test_init_db_creates_extension_and_tables_when_privileged(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # vector missing -> None, tables missing -> (None,)
        mock_cur.fetchone.side_effect = [None, (None,), (None,), (None,)]

        init_db()

        executed_sql = [call_args[0][0] for call_args in mock_cur.execute.call_args_list]
        self.assertTrue(any("CREATE EXTENSION IF NOT EXISTS vector;" in s for s in executed_sql))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS documents" in s for s in executed_sql))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS chats" in s for s in executed_sql))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS messages" in s for s in executed_sql))
        mock_conn.commit.assert_called_once()

    @patch('app.get_db_connection')
    def test_init_db_raises_actionable_error_on_insufficient_privilege(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_cur.fetchone.return_value = None

        def execute_side_effect(sql, *args, **kwargs):
            if "CREATE EXTENSION" in sql:
                raise MockInsufficientPrivilege("permission denied to create extension \"vector\"")

        mock_cur.execute.side_effect = execute_side_effect

        with self.assertRaises(RuntimeError) as ctx:
            init_db()

        self.assertIn("dbsadmin", str(ctx.exception))
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector;", str(ctx.exception))
        mock_conn.rollback.assert_called_once()
        mock_cur.close.assert_called_once()
        mock_conn.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()
