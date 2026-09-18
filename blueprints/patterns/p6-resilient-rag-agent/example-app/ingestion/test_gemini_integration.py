import unittest
from unittest.mock import patch, MagicMock
import base64
import json
import os
import sys

# Mock missing dependencies
sys.modules['boto3'] = MagicMock()
sys.modules['psycopg2'] = MagicMock()
sys.modules['botocore'] = MagicMock()
sys.modules['botocore.client'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.auth.transport'] = MagicMock()
sys.modules['google.auth.transport.requests'] = MagicMock()

# Add the directory containing app.py to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import call_gemini_api

class TestGeminiIntegration(unittest.TestCase):

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
        self.assertEqual(parts[1]['inline_data']['mime_type'], "image/png")
        self.assertEqual(parts[1]['inline_data']['data'], base64.b64encode(content).decode('utf-8'))

if __name__ == '__main__':
    unittest.main()
