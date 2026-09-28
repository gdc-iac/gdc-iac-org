import os
import json
import httpx
import random
import psutil
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gemma-gateway")

app = FastAPI(title="Gemma 4 Inference Gateway (GDC-ag)")

# Telemetry and Session State registries
ACTIVE_COMPLETIONS_COUNT = 0
ACTIVE_SESSIONS = {}
BLOCKED_USERS = set()

# Configuration
# 'ollama' or 'vllm' - strictly defined for this instance. Do not switch at runtime.
ACTIVE_FRAMEWORK = os.getenv("ACTIVE_FRAMEWORK", "ollama") 
# Active variant loaded on the Ollama backend ('26b' or '31b')
OLLAMA_MODEL_VARIANT = os.getenv("OLLAMA_MODEL_VARIANT", "26b")

# Routing table for models. 
# For Ollama, we map specific tags to their standalone variant services.
# For vLLM, we route different model tags to their GPU serving nodes.
DEFAULT_ROUTING = '{"gemma4:26b": "http://ollama-26b-service:11434", "gemma4:31b": "http://ollama-31b-service:11434", "*": "http://ollama-26b-service:11434"}' if ACTIVE_FRAMEWORK == "ollama" else '{"gemma4:26b": "http://vllm-26b-vllm-gke-service:8000", "gemma4:31b": "http://vllm-31b-vllm-gke-service:8000", "*": "http://vllm-26b-vllm-gke-service:8000"}'
MODEL_ROUTING_CONFIG = json.loads(os.getenv("MODEL_ROUTING_CONFIG", DEFAULT_ROUTING))

# Current generation state
CURRENT_STATE = {
    "temperature": 0.7,
    "top_p": 0.9,
    "frequency_penalty": 0.0,
    "vision_token_budget": 280, # Gemma 4 specific token budget
    "model_variant": os.getenv("OLLAMA_MODEL_VARIANT", "26b") # Hot-swappable variant
}

# System role capability register and payload message flattener
# To prevent vLLM from throwing 400 Bad Request 'System role not supported'
# when running GKE sandboxed mock environments (using google/gemma-2b-it).
UNSUPPORTED_SYSTEM_ROLE_MODELS = set()

def flatten_system_message(messages: list) -> list:
    """
    Pulls out the system message (if any) and prepends its content to the first user message.
    Preserves strict user-assistant alternation for strict tokenizers.
    Consolidates multiple system messages by concatenating their contents.
    """
    system_contents = []
    new_messages = []
    
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
                system_contents.append(" ".join(text_parts))
            else:
                system_contents.append(content)
        else:
            new_messages.append(msg)
            
    if system_contents:
        system_content = "\n\n".join(system_contents)
        first_user_idx = -1
        for i, msg in enumerate(new_messages):
            if msg.get("role") == "user":
                first_user_idx = i
                break
                
        if first_user_idx != -1:
            original_content = new_messages[first_user_idx].get("content", "")
            if isinstance(original_content, list):
                new_messages[first_user_idx]["content"].insert(0, {"type": "text", "text": f"System Directive: {system_content}\n\n"})
            else:
                new_messages[first_user_idx]["content"] = f"System Directive: {system_content}\n\nUser Query: {original_content}"
        else:
            new_messages.insert(0, {"role": "user", "content": f"System Directive: {system_content}"})
            
    return new_messages

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class UpdateConfigRequest(BaseModel):
    temperature: float = None
    top_p: float = None
    frequency_penalty: float = None
    vision_token_budget: int = None
    model_variant: str = None

@app.get("/", response_class=HTMLResponse)
async def admin_ui(request: Request):
    """Serves the GDC-styled Admin UI."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "state": CURRENT_STATE,
            "active_framework": ACTIVE_FRAMEWORK,
            "model_routing": MODEL_ROUTING_CONFIG
        }
    )

@app.get("/api/metrics")
async def get_metrics():
    global ACTIVE_COMPLETIONS_COUNT, ACTIVE_SESSIONS
    
    # Get real system CPU utilization using psutil
    try:
        cpu_util = psutil.cpu_percent(interval=None)
    except Exception:
        cpu_util = random.uniform(15.0, 25.0)
        
    # Emulate GPU/VRAM usage
    vram_total = 24.0 # GB
    vram_used = 22.4 # GB base unquantized footprint
    
    if ACTIVE_COMPLETIONS_COUNT > 0:
        gpu_util = random.uniform(65.0, 95.0)
        vram_used += random.uniform(0.2, 0.8)
    else:
        gpu_util = random.uniform(0.0, 2.0)
        vram_used += random.uniform(-0.05, 0.05)
        
    vram_percent = (vram_used / vram_total) * 100
    
    # Database connection pool emulation relative to active sessions
    db_connections = len(ACTIVE_SESSIONS) * 2 + random.randint(2, 5)
    
    return {
        "cpu_utilization": round(cpu_util, 1),
        "gpu_utilization": round(gpu_util, 1),
        "vram_total_gb": vram_total,
        "vram_used_gb": round(vram_used, 2),
        "vram_percent": round(vram_percent, 1),
        "active_completions": ACTIVE_COMPLETIONS_COUNT,
        "active_sessions_count": len(ACTIVE_SESSIONS),
        "db_connections": db_connections,
        "request_throughput": round(ACTIVE_COMPLETIONS_COUNT * random.uniform(0.8, 1.2), 2)
    }


@app.get("/api/sessions")
async def get_sessions():
    global ACTIVE_SESSIONS
    return list(ACTIVE_SESSIONS.values())


@app.post("/api/sessions/{session_id}/kill")
async def kill_session(session_id: str):
    global ACTIVE_SESSIONS
    if session_id in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS[session_id]["killed"] = True
        ACTIVE_SESSIONS[session_id]["status"] = "killed"
        logger.warning(f"Session {session_id} flagged for administrative termination.")
        return {"status": "success", "message": f"Session {session_id} flagged for termination."}
    raise HTTPException(status_code=404, detail="Session not found.")


@app.get("/api/users/blocked")
async def get_blocked_users():
    global BLOCKED_USERS
    return list(BLOCKED_USERS)


class BlockUserRequest(BaseModel):
    blocked: bool


@app.post("/api/users/{user_id}/block")
async def block_user(user_id: str, req: BlockUserRequest):
    global BLOCKED_USERS, ACTIVE_SESSIONS
    if req.blocked:
        BLOCKED_USERS.add(user_id)
        logger.warning(f"User {user_id} has been administratively blocked.")
        # Disconnect all active sessions for this blocked user
        for session_id, session in ACTIVE_SESSIONS.items():
            if session["user_id"] == user_id:
                session["killed"] = True
                session["status"] = "killed"
    else:
        BLOCKED_USERS.discard(user_id)
        logger.info(f"User {user_id} has been administratively unblocked.")
    return {"status": "success", "blocked": user_id in BLOCKED_USERS}


@app.get("/api/config")
async def get_config():
    return CURRENT_STATE

@app.post("/api/config")
async def update_config(config: UpdateConfigRequest):
    global CURRENT_STATE
    if config.temperature is not None: CURRENT_STATE["temperature"] = config.temperature
    if config.top_p is not None: CURRENT_STATE["top_p"] = config.top_p
    if config.frequency_penalty is not None: CURRENT_STATE["frequency_penalty"] = config.frequency_penalty
    if config.vision_token_budget is not None: CURRENT_STATE["vision_token_budget"] = config.vision_token_budget
    if config.model_variant is not None: CURRENT_STATE["model_variant"] = config.model_variant
    logger.info(f"Configuration updated: {CURRENT_STATE}")
    return {"status": "success", "new_state": CURRENT_STATE}

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models discovery endpoint."""
    if ACTIVE_FRAMEWORK == "ollama":
        model_variant = CURRENT_STATE.get("model_variant", "26b")
        return {
            "object": "list",
            "data": [
                {"id": f"gemma4:{model_variant}", "object": "model", "created": 1714500000, "owned_by": "gdc-platform"}
            ]
        }
    else:
        model_data = []
        for model_id in MODEL_ROUTING_CONFIG.keys():
            if model_id != "*":
                model_data.append({"id": model_id, "object": "model", "created": 1714500000, "owned_by": "gdc-platform"})
        if not model_data:
            model_data = [{"id": "gemma4:26b", "object": "model", "created": 1714500000, "owned_by": "gdc-platform"}]
        return {"object": "list", "data": model_data}

def classify_prompt_complexity(payload: dict) -> str:
    """
    Heuristically parses the request messages prompt.
    Returns 'gemma4:31b' (Dense) if complex logic, code, or math is detected.
    Returns the dynamic override variant (hot-swapped from Admin Control Plane) for general conversational queries.
    """
    messages = payload.get("messages", [])
    if not messages:
        fallback_variant = CURRENT_STATE.get("model_variant", "26b")
        return f"gemma4:{fallback_variant}"
        
    # Evaluate only the latest user prompt content (the last user message in the array)
    full_prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                # Multimodal block content
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        full_prompt = item.get("text", "")
                        break
            elif isinstance(content, str):
                full_prompt = content
            break
            
    full_prompt = full_prompt.lower()
    
    # Heuristic logic, coding, and math keywords list
    complexity_keywords = [
        "code", "function", "program", "script", "algorithm", "implement", "write a class",
        "math", "calculate", "prove", "equation", "formula", "solve for", "derivative", "integral",
        "reason", "analyze", "step-by-step", "detailed explanation", "logic", "deduce", "proof"
    ]
    
    for kw in complexity_keywords:
        if kw in full_prompt:
            logger.info(f"[Classifier] Complexity keyword detected: '{kw}'. Routing to Gemma 4 31B Dense.")
            return "gemma4:31b"
            
    fallback_variant = CURRENT_STATE.get("model_variant", "26b")
    logger.info(f"[Classifier] General conversational query detected. Routing to dynamic override: gemma4:{fallback_variant}")
    return f"gemma4:{fallback_variant}"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible proxy endpoint.
    Routes to Ollama or vLLM based on the current configuration.
    Injects Gemma 4 specific headers (e.g. for Vision Token Budgets).
    """
    global ACTIVE_COMPLETIONS_COUNT, ACTIVE_SESSIONS, BLOCKED_USERS
    
    # Extract user and session metadata
    user_id = request.headers.get("X-User-ID", "anonymous")
    
    # Blocklist boundary check
    if user_id in BLOCKED_USERS:
        logger.warning(f"Blocked user {user_id} attempted to access completion APIs.")
        raise HTTPException(status_code=403, detail="User has been administratively blocked.")
        
    client_ip = request.client.host if request.client else "unknown"
    session_id = f"{user_id}@{client_ip}"
    
    payload = await request.json()
    
    # Inject system-wide generation parameters if not specified in request
    if "temperature" not in payload: payload["temperature"] = CURRENT_STATE["temperature"]
    if "top_p" not in payload: payload["top_p"] = CURRENT_STATE["top_p"]
    if "frequency_penalty" not in payload: payload["frequency_penalty"] = CURRENT_STATE["frequency_penalty"]

    # Determine target URL based on requested model
    # Determine target URL based on requested model and dynamic classification
    requested_model = payload.get("model", "default")
    
    # 1. If client explicitly requests a specific valid variant
    if requested_model in MODEL_ROUTING_CONFIG and requested_model != "*":
        base_url = MODEL_ROUTING_CONFIG[requested_model]
        payload["model"] = requested_model
        determined_tag = requested_model
        logger.info(f"Routing to explicitly requested variant: {requested_model} at {base_url}")
    else:
        # 2. Dynamic Prompt Routing Classifier (Generic / Default model)
        determined_tag = classify_prompt_complexity(payload)
        base_url = MODEL_ROUTING_CONFIG.get(determined_tag)
        if not base_url:
            base_url = MODEL_ROUTING_CONFIG.get("*")
        payload["model"] = determined_tag
        logger.info(f"[Classifier] Dynamic route resolved: {determined_tag} at {base_url}")
    
    if not base_url:
        raise HTTPException(status_code=400, detail=f"Model '{requested_model}' not configured in routing table.")

    target_url = f"{base_url}/v1/chat/completions"

    logger.info(f"Routing request (Model: {payload['model']}) to: {target_url} via {ACTIVE_FRAMEWORK}")

    headers = {
        "Content-Type": "application/json",
        "X-Gemma-Vision-Budget": str(CURRENT_STATE["vision_token_budget"])
    }

    # Downstream LLM generation timeout. Allow up to 300 seconds for slow/split-model staging servers.
    gateway_timeout = float(os.getenv("GATEWAY_TIMEOUT", "300.0"))
    timeout = httpx.Timeout(gateway_timeout)

    # Preemptively flatten system message if this model tag is registered as lacking system role support
    if determined_tag in UNSUPPORTED_SYSTEM_ROLE_MODELS:
        logger.info(f"Model {determined_tag} is registered in UNSUPPORTED_SYSTEM_ROLE_MODELS. Preemptively flattening system messages...")
        payload["messages"] = flatten_system_message(payload["messages"])

    # Create/Update Active Session details
    ACTIVE_SESSIONS[session_id] = {
        "session_id": session_id,
        "user_id": user_id,
        "client_ip": client_ip,
        "status": "generating" if payload.get("stream", False) else "active",
        "last_active": datetime.now().strftime("%H:%M:%S"),
        "killed": False
    }

    if payload.get("stream", False):
        ACTIVE_COMPLETIONS_COUNT += 1
        
        async def stream_generator():
            global ACTIVE_COMPLETIONS_COUNT, UNSUPPORTED_SYSTEM_ROLE_MODELS
            current_payload = payload
            try:
                async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                    async with client.stream("POST", target_url, json=current_payload, headers=headers) as response:
                        # Catch system role limitation in-flight for streaming and register/retry
                        if response.status_code == 400:
                            error_content = await response.aread()
                            error_msg = ""
                            try:
                                error_json = json.loads(error_content.decode('utf-8'))
                                error_msg = error_json.get("error", {}).get("message", "")
                            except Exception:
                                pass
                                
                            if "System role not supported" in error_msg:
                                logger.warning(f"Detected System role limitation on backend {determined_tag}. Registering capability and retrying...")
                                UNSUPPORTED_SYSTEM_ROLE_MODELS.add(determined_tag)
                                
                                # Flatten system message and retry in-flight
                                retry_payload = current_payload.copy()
                                retry_payload["messages"] = flatten_system_message(current_payload["messages"])
                                
                                async with client.stream("POST", target_url, json=retry_payload, headers=headers) as retry_response:
                                    if retry_response.status_code != 200:
                                        retry_error = await retry_response.aread()
                                        logger.error(f"Retried inference engine failed: {retry_error}")
                                        yield f"data: {json.dumps({'error': {'message': 'Inference engine error'}})}\n\n".encode('utf-8')
                                        return
                                        
                                    async for line in retry_response.aiter_lines():
                                        if ACTIVE_SESSIONS.get(session_id, {}).get("killed", False):
                                            yield f"data: {json.dumps({'choices': [{'delta': {'content': '[Stream Terminated By Administrator]'}}], 'finish_reason': 'stop'})}\n\n".encode('utf-8')
                                            return
                                        yield f"{line}\n".encode('utf-8')
                                return
                            else:
                                logger.error(f"Inference engine returned 400 bad request: {error_content}")
                                yield f"data: {json.dumps({'error': {'message': error_msg or 'Bad Request'}})}\n\n".encode('utf-8')
                                return
                                
                        elif response.status_code != 200:
                            error_content = await response.aread()
                            logger.error(f"Inference engine returned error code {response.status_code}: {error_content}")
                            yield f"data: {json.dumps({'error': {'message': 'Inference engine error'}})}\n\n".encode('utf-8')
                            return
                        
                        async for line in response.aiter_lines():
                            # In-flight stream Kill-Switch interception
                            if ACTIVE_SESSIONS.get(session_id, {}).get("killed", False):
                                logger.warning(f"Streaming connection killed in-flight for session: {session_id}")
                                yield f"data: {json.dumps({'choices': [{'delta': {'content': '[Stream Terminated By Administrator]'}}], 'finish_reason': 'stop'})}\n\n".encode('utf-8')
                                return
                            yield f"{line}\n".encode('utf-8')
            except httpx.RequestError as e:
                logger.error(f"Inference engine streaming error: {e}")
                yield f"data: {json.dumps({'error': {'message': 'Error communicating with backend service'}})}\n\n".encode('utf-8')
            finally:
                ACTIVE_COMPLETIONS_COUNT = max(0, ACTIVE_COMPLETIONS_COUNT - 1)
                if session_id in ACTIVE_SESSIONS and not ACTIVE_SESSIONS[session_id].get("killed", False):
                    ACTIVE_SESSIONS[session_id]["status"] = "idle"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    # Non-Streaming completions block
    ACTIVE_COMPLETIONS_COUNT += 1
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post(target_url, json=payload, headers=headers)
            
            # Catch system role limitation on non-streaming and register/retry
            if response.status_code == 400:
                try:
                    error_json = response.json()
                    logger.info(f"[Retry Engine] Downstream 400 raw body: {error_json}")
                    error_msg = error_json.get("error", {}).get("message", "")
                    if "System role not supported" in error_msg:
                        logger.warning(f"Detected System role limitation on backend {determined_tag} in non-streaming call. Retrying with flattened payload...")
                        UNSUPPORTED_SYSTEM_ROLE_MODELS.add(determined_tag)
                        
                        retry_payload = payload.copy()
                        retry_payload["messages"] = flatten_system_message(payload["messages"])
                        
                        retry_response = await client.post(target_url, json=retry_payload, headers=headers)
                        logger.info(f"[Retry Engine] Retry status: {retry_response.status_code}, body: {retry_response.text}")
                        return JSONResponse(content=retry_response.json(), status_code=retry_response.status_code)
                    else:
                        logger.info("[Retry Engine] Message did not match limitation context.")
                except Exception as e:
                    logger.exception(f"[Retry Engine] Exception during retry flattening: {e}")
                    
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except httpx.RequestError as e:
        logger.error(f"Inference engine connection error: {e}")
        raise HTTPException(status_code=502, detail=f"Error communicating with backend service: {base_url}")
    finally:
        ACTIVE_COMPLETIONS_COUNT = max(0, ACTIVE_COMPLETIONS_COUNT - 1)
        if session_id in ACTIVE_SESSIONS and not ACTIVE_SESSIONS[session_id].get("killed", False):
            ACTIVE_SESSIONS[session_id]["status"] = "idle"
