from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str

@app.post("/generate")
def generate(request: PromptRequest):
    # Simple echo response
    return {"text": f"Based on the context, here is the answer to: {request.prompt}"}
