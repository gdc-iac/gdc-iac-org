import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import vertexai
from google import genai
from google.genai import types

app = FastAPI()

PROJECT_ID = os.environ.get('PROJECT_ID', 'test-project')
REGION = os.environ.get('REGION', 'us-central1')
GEMINI_ENDPOINT = os.environ.get('GEMINI_ENDPOINT') # Optional override for GDC endpoint
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash-001')

FAILOVER_URL = os.environ.get('FAILOVER_URL', 'http://ollama-service:11434/api/generate')
FAILOVER_MODEL = os.environ.get('FAILOVER_MODEL', 'gemma:7b')
FAILOVER_BACKEND = os.environ.get('FAILOVER_BACKEND', 'ollama') # Options: 'ollama', 'vllm'

class PromptRequest(BaseModel):
    prompt: str
    temperature: Optional[float] = None
    stop_sequences: Optional[List[str]] = None

# Initialize google-genai globally
try:
    print("Initializing GenAI Client via Vertex SDK auth flow...")
    
    # Let the legacy vertexai library handle Workload Identity auth mapping
    init_args = {"project": PROJECT_ID, "location": REGION}
    if GEMINI_ENDPOINT:
        init_args["api_endpoint"] = GEMINI_ENDPOINT
    vertexai.init(**init_args)
    
    # Initialize the new genai client specifying vertex mode
    client_kwargs = {
        "vertexai": True,
        "project": PROJECT_ID,
        "location": REGION
    }
    if GEMINI_ENDPOINT:
        client_kwargs["http_options"] = {"api_endpoint": GEMINI_ENDPOINT}
        print(f"Overriding GenAI Client endpoint to: {GEMINI_ENDPOINT}")

    client = genai.Client(**client_kwargs)
    print("GenAI Client initialized.")
except Exception as e:
    print(f"Warning: Could not initialize GenAI Client: {e}")
    client = None

@app.post("/generate")
async def generate(request: PromptRequest):
    try:
        print(f"Attempting Primary: Gemini API (Model: {GEMINI_MODEL})")
        if client is None:
            raise ValueError("GenAI Client not initialized")
            
        kwargs = {}
        if request.temperature is not None or request.stop_sequences is not None:
            config_dict = {}
            if request.temperature is not None:
                config_dict["temperature"] = request.temperature
            if request.stop_sequences is not None:
                config_dict["stop_sequences"] = request.stop_sequences
            kwargs["config"] = types.GenerateContentConfig(**config_dict)
            
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=request.prompt,
            **kwargs
        )
        return {"source": "primary", "response": {"text": response.text}}
    except Exception as e:
        print(f"Primary failed: {e}. Failing over to Secondary.")
    
    async with httpx.AsyncClient() as client_http:
        try:
            print(f"Attempting Failover: {FAILOVER_URL} (Model: {FAILOVER_MODEL}, Backend: {FAILOVER_BACKEND})")
            
            if FAILOVER_BACKEND == 'vllm':
                # vLLM (OpenAI compatible) payload
                payload = {
                    "model": FAILOVER_MODEL,
                    "prompt": request.prompt,
                    "max_tokens": 512, # Default max output
                    "stream": False
                }
                if request.temperature is not None:
                     payload["temperature"] = request.temperature
                if request.stop_sequences is not None:
                     payload["stop"] = request.stop_sequences
                     
                response = await client_http.post(FAILOVER_URL, json=payload, timeout=300.0)
                response.raise_for_status()
                data = response.json()
                # OpenAI format: choices[0].text
                output_text = data["choices"][0]["text"]
                return {"source": "failover", "response": {"text": output_text}}

            else:
                # Default: Ollama payload
                payload = {
                    "model": FAILOVER_MODEL,
                    "prompt": request.prompt,
                    "stream": False
                }
                options = {}
                if request.temperature is not None:
                    options["temperature"] = request.temperature
                if request.stop_sequences is not None:
                    options["stop"] = request.stop_sequences
                if options:
                    payload["options"] = options
                
                response = await client_http.post(FAILOVER_URL, json=payload, timeout=300.0)
                response.raise_for_status()
                data = response.json()
                output_text = data.get("response", data.get("text", str(data)))
                return {"source": "failover", "response": {"text": output_text}}
                
        except Exception as e:
            import traceback
            print(f"Failover fallback failed: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=503, detail="All LLM providers unavailable")

@app.get("/health")
def health():
    return {"status": "ok"}
