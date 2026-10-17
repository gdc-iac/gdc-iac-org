import asyncio
import os
from openai import OpenAI
from typing import List
from database import db
from storage import get_blob_content
from models import Message

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gemma-gateway.gemma-inference.svc.cluster.local/v1")
MAX_CHAT_TOKENS = int(os.getenv("MAX_CHAT_TOKENS", "1536"))
client = OpenAI(base_url=GATEWAY_URL, api_key="gdc-no-auth-required", timeout=240.0)


def extract_completion_text(message_obj, include_thinking: bool = True) -> str:
    """
    Extracts visible response text from an OpenAI-compatible ChatCompletionMessage.
    Handles Ollama / vLLM Gemma 4 native thinking fields (`reasoning`, `reasoning_content`, `thinking`)
    so responses never return an empty string when thinking tokens consume the budget.
    """
    if message_obj is None:
        return ""
    content = (getattr(message_obj, "content", None) or "").strip()
    extra = getattr(message_obj, "model_extra", None) or {}
    reasoning = (
        getattr(message_obj, "reasoning", None)
        or getattr(message_obj, "reasoning_content", None)
        or getattr(message_obj, "thinking", None)
        or (extra.get("reasoning") if isinstance(extra, dict) else None)
        or (extra.get("reasoning_content") if isinstance(extra, dict) else None)
        or (extra.get("thinking") if isinstance(extra, dict) else None)
        or ""
    ).strip()

    if content and reasoning and include_thinking and "<thought>" not in content.lower():
        return f"<thought>\n{reasoning}\n</thought>\n\n{content}"
    if content:
        return content
    if reasoning:
        return reasoning
    return ""

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
        system_instruction += " You MUST output your step-by-step thinking process wrapped in <thought>...</thought> tags before your final answer. Keep your <thought> section concise (3-5 bullet points) so the tactical synthesis completes rapidly."
    else:
        system_instruction += " Do not output any <thought> tags, thinking process, or internal reasoning steps. Provide ONLY the direct answer to the user's prompt."

    if only_use_sources:
        system_instruction += " You must answer the user's question STRICTLY based on the provided documents and images. If the answer is not in the provided content, say 'I cannot answer this based on the provided sources.'"
    else:
        system_instruction += (
            " The user has disabled 'Strictly use provided sources' (general chat mode is active). "
            "You MUST answer the user's question using your general knowledge whenever the answer is not found in the uploaded documents, "
            "and you MUST ignore any prior refusal ('I cannot answer this based on the provided sources') from earlier turns."
        )

    # Fetch and inject file contents into the top-level system context (avoiding mid-conversation system role messages)
    file_context = ""
    for file_id in (file_ids or []):
        row = await db.fetch_one("SELECT filename, gcs_path, content_type FROM files WHERE id = $1", file_id)
        if row:
            filename = row['filename']
            gcs_path = row['gcs_path']
            try:
                file_bytes = get_blob_content(gcs_path)
                text_content = file_bytes.decode("utf-8", errors="ignore")
                file_context += f"\n--- Document: {filename} ---\n{text_content}\n--- End Document ---\n"
            except Exception as e:
                print(f"Error loading file {filename}: {e}")

    if file_context:
        if only_use_sources:
            system_instruction += f"\n\nSTRICT SOURCE GROUNDING CONTEXT (answer ONLY from these documents):\n{file_context}"
        else:
            system_instruction += (
                f"\n\nOPTIONAL REFERENCE DOCUMENTS (use if relevant to the user's prompt; "
                f"if the prompt asks about anything outside these documents, answer normally using your general knowledge):\n{file_context}"
            )

    openai_history.append({"role": "system", "content": system_instruction})

    # Reconstruct history (avoiding consecutive duplicate 'user' messages and stripping stale source-only refusals when general mode is active)
    history_to_append = history
    if history and history[-1].role == "user" and history[-1].content == message:
        history_to_append = history[:-1]

    for msg in history_to_append[-10:]:
        if not msg.content or not str(msg.content).strip():
            continue
        normalized_role = "assistant" if msg.role == "model" else msg.role
        if normalized_role not in ("system", "user", "assistant"):
            normalized_role = "user"
        if not only_use_sources and normalized_role == "assistant" and "cannot answer this based on the provided sources" in msg.content.lower():
            continue
        openai_history.append({"role": normalized_role, "content": msg.content})

    # Append user message
    openai_history.append({"role": "user", "content": message})

    try:
        # Construct extra headers to pass X-User-ID to the gateway
        extra_headers = {}
        if user_id:
            extra_headers["X-User-ID"] = user_id

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name or "gemma4",
            messages=openai_history,
            max_tokens=MAX_CHAT_TOKENS,
            stream=False,
            extra_headers=extra_headers,
            extra_body={"think": bool(is_thinking_enabled)},
        )
        msg_obj = response.choices[0].message if response.choices else None
        reply_text = extract_completion_text(msg_obj, include_thinking=is_thinking_enabled)
        if not reply_text:
            reply_text = "No response text was generated by the inference engine. Try disabling Thinking mode or rephrasing your prompt."
        return reply_text, (response.model or model_name or "gemma4:26b")
    except Exception as e:
        print(f"Gateway Error: {e}")
        return "I encountered an error processing your request.", model_name or "gemma4:26b"
