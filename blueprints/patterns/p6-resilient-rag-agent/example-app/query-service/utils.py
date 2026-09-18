import os
import psycopg2
import httpx
import google.auth
from google.auth.transport.requests import Request
from fastapi import HTTPException

# Configuration
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'gemma')
LLM_GATEWAY_URL = os.environ.get('LLM_GATEWAY_URL', os.environ.get('GEMINI_ENDPOINT', 'http://gemma-gateway.gemma-inference.svc.cluster.local:8080/v1'))
GEMINI_ENDPOINT = os.environ.get('GEMINI_ENDPOINT', LLM_GATEWAY_URL)
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemma-2-27b-it')
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-004')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # Optional
PROJECT_ID = os.environ.get('PROJECT_ID', 'your-project-id')
AO_PROJECT_ID = os.environ.get('AO_PROJECT_ID', f"projects/{PROJECT_ID}")
LOCATION = os.environ.get('LOCATION', 'us-central1')
INPUT_BUCKET = os.environ.get('INPUT_BUCKET', 'rag-input-bucket')
GDC_TOKEN = os.environ.get('GDC_TOKEN')

def get_auth_token():
    if GEMINI_API_KEY:
        return None
    try:
        credentials, _ = google.auth.default()
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        print(f"Warning: Could not get default credentials: {e}")
        return None

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        database=os.environ.get('DB_NAME', 'rag_db'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASS', 'password')
    )

def get_embedding(text):
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{EMBEDDING_MODEL}:predict"
    
    headers = {"Content-Type": "application/json"}
    token = get_auth_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {
        "instances": [{
            "content": text,
            "task_type": "RETRIEVAL_QUERY"
        }]
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            return result['predictions'][0]['embeddings']['values']
    except Exception as e:
        print(f"Embedding API Error: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

async def call_llm(prompt: str) -> str:
    """
    Calls configured LLM backend based on LLM_PROVIDER.
    Supports:
      1. 'gemma': Gemma Inference Gateway (OpenAI /v1/chat/completions or /generate format).
      2. 'gemini': GDC Gemini AI Gateway or GCP Vertex AI Gemini endpoint with STS/Auth token and x-goog-user-project.
    """
    provider = os.environ.get('LLM_PROVIDER', LLM_PROVIDER).lower()
    endpoint = os.environ.get('LLM_GATEWAY_URL', os.environ.get('GEMINI_ENDPOINT', LLM_GATEWAY_URL))
    model = os.environ.get('GEMINI_MODEL', GEMINI_MODEL)
    ao_project_id = os.environ.get('AO_PROJECT_ID', AO_PROJECT_ID)

    if provider == 'gemma' or 'gemma' in endpoint:
        # Check endpoint style
        if endpoint.endswith('/generate'):
            url = endpoint
            headers = {"Content-Type": "application/json"}
            token = get_auth_token() or os.environ.get('GDC_TOKEN', GDC_TOKEN)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            payload = {
                "prompt": prompt,
                "temperature": 0.0,
                "stop_sequences": ["Observation:"]
            }
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(url, headers=headers, json=payload, timeout=120.0)
                    response.raise_for_status()
                    result = response.json()
                    if 'response' in result and 'text' in result['response']:
                        return result['response']['text']
                    return result.get('text', '')
                except Exception as e:
                    print(f"Gemma Gateway /generate Error: {e}")
                    raise e
        else:
            url = endpoint if endpoint.endswith('/chat/completions') else f"{endpoint.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json"}
            token = get_auth_token() or os.environ.get('GDC_TOKEN', GDC_TOKEN)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "stop": ["Observation:"]
            }
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(url, headers=headers, json=payload, timeout=120.0)
                    response.raise_for_status()
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        choice = result['choices'][0]
                        if 'message' in choice and 'content' in choice['message']:
                            return choice['message']['content']
                        elif 'text' in choice:
                            return choice['text']
                    raise ValueError(f"Unexpected response format from Gemma Gateway: {result}")
                except Exception as e:
                    # Fallback try /generate format if OpenAI call failed
                    if not endpoint.endswith('/chat/completions'):
                        try:
                            gen_url = f"{endpoint.rstrip('/')}/generate"
                            gen_payload = {"prompt": prompt, "temperature": 0.0, "stop_sequences": ["Observation:"]}
                            gen_resp = await client.post(gen_url, headers=headers, json=gen_payload, timeout=120.0)
                            if gen_resp.status_code == 200:
                                res = gen_resp.json()
                                if 'response' in res and 'text' in res['response']:
                                    return res['response']['text']
                                return res.get('text', '')
                        except Exception:
                            pass
                    print(f"Gemma Gateway API Error: {e}")
                    raise e
    else:
        # Provider: Gemini
        if "ai-gateway" in endpoint or "shared-services" in endpoint or provider == "gemini":
            url = endpoint if endpoint.endswith('/chat/completions') else f"{endpoint.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "x-goog-user-project": ao_project_id
            }
            token = get_auth_token() or os.environ.get('GDC_TOKEN', GDC_TOKEN)
            if token:
                headers["Authorization"] = f"Bearer {token}"

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "stop": ["Observation:"]
            }
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(url, headers=headers, json=payload, timeout=120.0)
                    response.raise_for_status()
                    result = response.json()
                    return result['choices'][0]['message']['content']
                except Exception as e:
                    print(f"GDC Gemini Gateway Error: {e}")
                    raise e
        else:
            url = f"{endpoint}/{model}:generateContent"
            if GEMINI_API_KEY:
                url += f"?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            token = get_auth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "stopSequences": ["Observation:"]
                }
            }

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(url, headers=headers, json=payload, timeout=120.0)
                    response.raise_for_status()
                    result = response.json()
                    return result['candidates'][0]['content']['parts'][0]['text']
                except Exception as e:
                    print(f"Gemini API Error: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        print(f"Gemini Error Response: {e.response.text}")
                    raise e

async def call_gemini_api(prompt):
    """Backward compatible helper function for call_llm."""
    return await call_llm(prompt)

