import os
import vertexai
from vertexai.generative_models import GenerativeModel, Part, SafetySetting
from typing import List
from database import db
from storage import get_blob_content
from models import Message

PROJECT_ID = os.getenv("PROJECT_ID", "test-project")
REGION = os.getenv("REGION", "us-central1")
GEMINI_ENDPOINT = os.getenv("GEMINI_ENDPOINT") # Optional override

# Initialize Vertex AI
try:
    init_args = {"project": PROJECT_ID, "location": REGION}
    if GEMINI_ENDPOINT:
        init_args["api_endpoint"] = GEMINI_ENDPOINT
    
    vertexai.init(**init_args)
except Exception as e:
    print(f"Warning: Could not initialize Vertex AI: {e}")

async def generate_chat_response(
    message: str,
    history: List[Message],
    file_ids: List[str],
    model_name: str,
    only_use_sources: bool
) -> str:
    
    print(f"DEBUG: generate_chat_response called with only_use_sources={only_use_sources}")

    # 1. Load Files
    parts = []
    
    # System Instruction
    system_instruction = "You are a helpful AI assistant."
    if only_use_sources:
        system_instruction += " You must answer the user's question STRICTLY based on the provided documents and images. If the answer is not in the provided content, say 'I cannot answer this based on the provided sources.'"
    
    print(f"DEBUG: system_instruction='{system_instruction}'")

    # Fetch file metadata and content
    for file_id in file_ids:
        row = await db.fetch_one("SELECT filename, gcs_path, content_type FROM files WHERE id = $1", file_id)
        if row:
            filename = row['filename']
            gcs_path = row['gcs_path']
            content_type = row['content_type']
            
            try:
                file_bytes = get_blob_content(gcs_path)
                
                # Create Part based on type
                if content_type.startswith("text/"):
                    # Decode text
                    text_content = file_bytes.decode("utf-8", errors="ignore")
                    parts.append(Part.from_text(f"--- Document: {filename} ---\n{text_content}\n--- End Document ---\n"))
                elif content_type.startswith("image/") or content_type == "application/pdf":
                    # Pass as Blob
                    parts.append(Part.from_data(data=file_bytes, mime_type=content_type))
                else:
                    # Fallback for other types (like .md, .csv which might come as octet-stream)
                    print(f"DEBUG: Unknown content_type '{content_type}' for {filename}, attempting to read as text")
                    try:
                        text_content = file_bytes.decode("utf-8")
                        parts.append(Part.from_text(f"--- Document: {filename} ---\n{text_content}\n--- End Document ---\n"))
                    except UnicodeDecodeError:
                        print(f"DEBUG: File {filename} is binary and unsupported format.")
            except Exception as e:
                print(f"Error loading file {filename}: {e}")
                parts.append(Part.from_text(f"[Error loading file {filename}]"))

    # 2. Construct History
    # Gemini SDK expects history in a specific format (Content objects)
    # But for simplicity in "Direct Context" (stateless REST), we can just append history to the prompt 
    # OR use the ChatSession object if we want multi-turn.
    # Given we are building a "Chatbot Wrapper", using ChatSession is better.
    
    model = GenerativeModel(
        model_name=model_name,
        system_instruction=[system_instruction]
    )
    
    chat = model.start_chat(history=[]) # We will manually feed history if needed, or just send the full context each time.
    # Actually, for "Direct Context" with files, it's often easier to send a single generate_content request 
    # with [System, Files, History, Current Message].
    
    # Let's build the full prompt parts
    request_parts = []
    
    # Add Files first (Context)
    request_parts.extend(parts)
    
    # Add History (Text only for now to save tokens/complexity, or we can try to reconstruct)
    # For this implementation, let's append recent history as text to the prompt to ensure it fits with the files.
    # (A robust implementation would use Content objects properly)
    if history:
        history_text = "\nChat History:\n"
        for msg in history[-10:]: # Last 10 messages
            history_text += f"{msg.role}: {msg.content}\n"
        request_parts.append(Part.from_text(history_text))
        
    # Add User Message
    request_parts.append(Part.from_text(f"User: {message}"))
    
    # 3. Generate
    try:
        response = await model.generate_content_async(
            request_parts,
            stream=False # Streaming requires different handling in FastAPI
        )
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "I encountered an error processing your request."
