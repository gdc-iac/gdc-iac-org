import os
from openai import OpenAI
from typing import List
from database import db
from storage import get_blob_content
from models import Message

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gemma-gateway.gemma-inference.svc.cluster.local/v1")
client = OpenAI(base_url=GATEWAY_URL, api_key="gdc-no-auth-required")

async def generate_chat_response(
    message: str,
    history: List[Message],
    file_ids: List[str],
    model_name: str,
    only_use_sources: bool,
    is_thinking_enabled: bool = True,
    user_id: str = None
) -> tuple:
    print(f"DEBUG: generate_chat_response called with only_use_sources={only_use_sources}, user_id={user_id}")

    openai_history = []
    
    # System Instruction
    system_instruction = "You are a helpful AI assistant."
    if is_thinking_enabled:
        system_instruction += " You MUST output your step-by-step thinking process wrapped in <thought>...</thought> tags before your final answer."
    else:
        system_instruction += " Do not output any <thought> tags, thinking process, or internal reasoning steps. Provide ONLY the direct answer to the user's prompt."

    if only_use_sources:
        system_instruction += " You must answer the user's question STRICTLY based on the provided documents and images. If the answer is not in the provided content, say 'I cannot answer this based on the provided sources.'"
    
    openai_history.append({"role": "system", "content": system_instruction})

    # Reconstruct history (avoiding consecutive duplicate 'user' messages)
    history_to_append = history
    if history and history[-1].role == "user" and history[-1].content == message:
        history_to_append = history[:-1]

    for msg in history_to_append[-10:]:
        openai_history.append({"role": msg.role, "content": msg.content})
        
    # Fetch and inject file contents into prompt context
    file_context = ""
    for file_id in file_ids:
        row = await db.fetch_one("SELECT filename, gcs_path, content_type FROM files WHERE id = $1", file_id)
        if row:
            filename = row['filename']
            gcs_path = row['gcs_path']
            content_type = row['content_type']
            try:
                file_bytes = get_blob_content(gcs_path)
                text_content = file_bytes.decode("utf-8", errors="ignore")
                file_context += f"\n--- Document: {filename} ---\n{text_content}\n--- End Document ---\n"
            except Exception as e:
                print(f"Error loading file {filename}: {e}")

    if file_context:
        openai_history.append({"role": "system", "content": f"Here is the ground truth context from uploaded files:\n{file_context}"})

    # Append user message
    openai_history.append({"role": "user", "content": message})

    try:
        # Construct extra headers to pass X-User-ID to the gateway
        extra_headers = {}
        if user_id:
            extra_headers["X-User-ID"] = user_id

        response = client.chat.completions.create(
            model=model_name or "gemma4:26b",
            messages=openai_history,
            temperature=0.7,
            stream=False,
            extra_headers=extra_headers
        )
        return response.choices[0].message.content, response.model
    except Exception as e:
        print(f"Gateway Error: {e}")
        return "I encountered an error processing your request.", model_name or "gemma4:26b"
